import json
import base64
import struct
from concurrent.futures import ThreadPoolExecutor
from django.conf import settings
from django.shortcuts import render, get_object_or_404
from langchain_google_genai import ChatGoogleGenerativeAI
from langchain_openrouter import ChatOpenRouter
from openevals.llm import create_llm_as_judge
from app.models import Topic, TopicContent, TopicEvaluation, Report, Project, TopicAnalysisPlan
from app.services.vector_db_config.vector_store import get_vector_store
from app.services.llm_config.llm_provider import LLMBackend, ModelSize, get_llm
from app.services.metadata_generation.metadata_retriever import retrieve_multi_table_metadata

def get_judge_llm(project=None):
    """Get judge llm"""

    return get_llm(
        backend=LLMBackend(settings.DEFAULT_LLM_BACKEND),
        model_size=ModelSize.PRIMARY,
        temperature=0,
        project=project,
    )


def stringify_blocks(blocks):
    """Convert blocks to string"""

    lines = []

    # Convert structured blocks into text format
    for block in blocks:

        if block["type"] == "paragraph":
            lines.append(block["content"])

        elif block["type"] == "bullet_list":
            for item in block["content"]:
                lines.append(f"- {item}")

        elif block["type"] == "visual":
            lines.append(
                f"[VISUAL]\n"
                f"Type: {block.get('visual_type')}\n"
                f"Purpose: {block.get('purpose')}\n"
            )

    return "\n\n".join(lines)


def build_eval_input(topic, report):
    """Build evaluation input"""

    plan = get_object_or_404(
        TopicAnalysisPlan,
        report=report,
        topic=topic,
    )

    if not plan:
        return ""

    plan_json = plan.plan_json or {}

    return f"""
TOPIC: {plan_json.get("topic")}

INTENT:
{plan_json.get("intent")}

REQUIRED ELEMENTS:
{json.dumps(plan_json.get("required_elements", []), indent=2)}

BUSINESS QUESTIONS:
{json.dumps(plan_json.get("business_questions", []), indent=2)}

"""


def extract_content_blocks_text(content_json):
    """Extract content blocks text"""

    sections = content_json.get("sections", [])
    all_blocks = []

    # Flatten content blocks
    for section in sections:
        all_blocks.extend(section.get("content_blocks", []))

    formatted = build_prompt_blocks(all_blocks, _decode_sql_result)

    return stringify_blocks(formatted)


def retrieve_metadata_for_topic(project, topic, vector_store, report):
    """Retrieve metadata for topic"""

    # Build semantic query using section, subsection and topic
    section_title = topic.subsection.section.title
    subsection_title = topic.subsection.title
    topic_title = topic.title

    plan = TopicAnalysisPlan.objects.filter(
        topic=topic,
        report=report
    ).first()

    required_elements = []

    if plan and plan.plan_json:
        required_elements = plan.plan_json.get("required_elements", [])

    query = f"""
    Section: {section_title}
    Subsection: {subsection_title}
    Topic: {topic_title}

    Required Analysis:
    {'; '.join(required_elements)}
    """

    metadata_context = retrieve_multi_table_metadata(
        project=project,
        primary_query=query,
        secondary_queries=[
            "topic evaluation joins relationships analytical capabilities business entities",
        ],
        metadata_types=[
            "table_description",
            "table_relationship",
            "column",
            "column_relationship",
            "analytical_capability",
        ],
        per_query_k=10,
        max_docs=24,
    )

    return "\n".join([item["content"] for item in metadata_context])


def build_evaluators(llm):
    """Build evaluators"""

    return [
        ("hallucination", create_llm_as_judge(
            prompt=HALLUCINATION_PROMPT,
            judge=llm,
            continuous=True,
            feedback_key="hallucination",
        )),
        ("correctness", create_llm_as_judge(
            prompt=CORRECTNESS_PROMPT,
            judge=llm,
            continuous=True,
            feedback_key="correctness",
        )),
        ("relevance", create_llm_as_judge(
            prompt=ANSWER_RELEVANCE_PROMPT,
            judge=llm,
            continuous=True,
            feedback_key="relevance",
        )),
        ("conciseness", create_llm_as_judge(
            prompt=CONCISENESS_PROMPT,
            judge=llm,
            continuous=True,
            feedback_key="conciseness",
        )),
    ]


def evaluate_topic(project, topic, evaluators, vector_store, report):
    """Evaluate topic"""

    content_obj = TopicContent.objects.filter(topic=topic).first()
    if not content_obj:
        return None

    content_json = content_obj.content_json or {}

    # Extract content, input and context
    content_text = extract_content_blocks_text(content_json)
    input_text = build_eval_input(topic, report)
    sql_results = content_json.get("precomputed_sql_placeholders", [])

    metadata_context = retrieve_metadata_for_topic(
        project, topic, vector_store, report
    )

    context_str = f"""
    SQL DATA:
    {json.dumps(sql_results, indent=2)}

    METADATA:
    {metadata_context}
    """

    results = []

    # Run evaluators in parallel
    def run_eval(name, evaluator):
        try:

            if name == "hallucination":
                return evaluator(
                    inputs=input_text,
                    outputs=content_text,
                    context=context_str,
                )

            elif name == "correctness":
                return evaluator(
                    inputs=input_text,
                    outputs=content_text,
                )

            else:
                return evaluator(
                    inputs=input_text,
                    outputs=content_text,
                )

        except Exception as e:
            print(f"[EVAL ERROR] {name} → Topic {topic.id}: {e}")
            return None

    # Execute evaluations concurrently
    with ThreadPoolExecutor(max_workers=4) as executor:

        futures = [
            executor.submit(run_eval, name, evaluator)
            for name, evaluator in evaluators
        ]

        for f in futures:
            res = f.result()
            if res:
                results.append(res)

    if not results:
        return None

    scores = {}

    for r in results:
        key = r.get("key")
        score = float(r.get("score", 0)) * 100
        scores[key] = score

    overall_score = sum(scores.values()) / len(scores)

    issues = [r.get("comment", "") for r in results if r.get("comment")]

    return {
        "scores": scores,
        "issues": issues,
        "summary": " | ".join(issues),
        "overall_score": overall_score,
    }


def evaluate_project(project_id: int, report_id: int):
    """Evaluate project"""

    project = Project.objects.get(id=project_id)
    report = Report.objects.get(id=report_id)

    topics = Topic.objects.filter(
        subsection__section__report=report
    )

    vector_store = get_vector_store(
        backend=settings.DEFAULT_LLM_BACKEND
    )

    llm = get_judge_llm(project)
    evaluators = build_evaluators(llm)

    topic_results = []

    for topic in topics:

        result = evaluate_topic(
            project,
            topic,
            evaluators,
            vector_store,
            report,
        )

        if not result:
            continue

        topic_res = {
            "scores": result["scores"],
            "issues": result["issues"],
            "summary": result["summary"],
            "overall_score": result["overall_score"],
        }

        print("\n\n__Result__\n", topic_res, "\n\n\n")

        TopicEvaluation.objects.update_or_create(
            topic=topic,
            report=report,
            defaults=topic_res,
        )

        topic_results.append(result)

    return compute_report_score(topic_results)


def compute_report_score(topic_results):
    """Compute report score"""

    if not topic_results:
        return {
            "overall_score": 0,
            "category_scores": {},
            "topics_evaluated": 0,
        }

    category_scores = {}

    # Aggregate scores by category
    for result in topic_results:
        for key, value in result["scores"].items():
            category_scores.setdefault(key, []).append(value)

    averaged_scores = {
        k: sum(v) / len(v)
        for k, v in category_scores.items()
    }

    overall_score = sum(averaged_scores.values()) / len(averaged_scores)

    return {
        "overall_score": round(overall_score, 2),
        "category_scores": averaged_scores,
        "topics_evaluated": len(topic_results),
    }


def decode_bdata(bdata, dtype):
    """Decode binary data"""

    binary = base64.b64decode(bdata)

    if dtype == "f8":
        return list(struct.unpack(f"{len(binary)//8}d", binary))
    elif dtype == "f4":
        return list(struct.unpack(f"{len(binary)//4}f", binary))
    elif dtype == "i4":
        return list(struct.unpack(f"{len(binary)//4}i", binary))
    elif dtype == "i2":
        return list(struct.unpack(f"{len(binary)//2}h", binary))
    elif dtype == "i1":
        return list(struct.unpack(f"{len(binary)}b", binary))

    return []


def _decode_sql_result(sql_result):
    """Decode sql result"""

    # Handle decoding of binary encoded sql results
    if not sql_result:
        return sql_result

    if isinstance(sql_result, dict) and "rows" in sql_result:
        return sql_result

    if isinstance(sql_result, dict):

        decoded = {}

        for key, val in sql_result.items():

            if isinstance(val, dict) and "bdata" in val:
                decoded[key] = decode_bdata(val["bdata"], val.get("dtype"))
            else:
                decoded[key] = val

        return decoded

    return sql_result


def build_prompt_blocks(blocks, decode_fn):
    """Build prompt blocks"""

    formatted = []

    # Convert blocks into prompt-ready format
    for i, block in enumerate(blocks):

        if block["type"] == "visual_placeholder":
            block = normalize_visual_block(block)

            content = block.get("content", {})

            decoded = decode_fn(
                block.get("generated_visual", {}).get("data")
            )

            formatted.append({
                "block_index": i,
                "type": "visual",
                "visual_id": content.get("id"),
                "visual_type": content.get("type"),
                "purpose": content.get("purpose"),
                "data": decoded
            })

        elif block["type"] in ["paragraph", "bullet_list"]:

            formatted.append({
                "block_index": i,
                "type": block["type"],
                "content": block["content"]
            })

    return formatted


def normalize_visual_block(block):
    """Normalize visual block"""

    raw = block.get("content")

    if isinstance(raw, dict):
        return block

    # Parse visual placeholder string into structured dict
    if isinstance(raw, str) and "{{VISUAL" in raw:

        import re

        def extract(field):
            match = re.search(rf"{field}\\s*:\\s*(.*?);", raw, re.DOTALL)
            return match.group(1).strip().strip('"') if match else ""

        block["content"] = {
            "id": extract("id"),
            "type": extract("type"),
            "purpose": extract("purpose"),
        }

    return block
