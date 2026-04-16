import json
from concurrent.futures import ThreadPoolExecutor

from django.conf import settings

from langchain_google_genai import ChatGoogleGenerativeAI
from openevals.llm import create_llm_as_judge
# from openevals.prompts import (
#     CORRECTNESS_PROMPT,
#     ANSWER_RELEVANCE_PROMPT,
#     CONCISENESS_PROMPT,
#     HALLUCINATION_PROMPT,
# )
from langchain_openrouter import ChatOpenRouter

from app.models import Topic, TopicContent, TopicEvaluation, Report, Project, TopicAnalysisPlan
from rag_web.app.services.vector_db_config.vector_store import get_vector_store

import base64
import struct
from django.shortcuts import render, get_object_or_404

EVAL_SYSTEM_CONTEXT = """
You are evaluating a BUSINESS ANALYTICAL REPORT SECTION.

IMPORTANT CONTEXT ABOUT HOW THIS REPORT WAS GENERATED:

- This is a sub-topic of a professional analytical report
- The report is generated using a structured pipeline:

  1. An analytical plan defines:
     - intent
     - required_elements
     - business_questions

  2. SQL queries are executed to produce numerical results

  3. Content is generated iteratively using:
     - SQL results (numerical facts)
     - metadata (table + column meaning)

  4. Visual placeholders represent charts/tables:
     - Each visual includes purpose + data
     - Visuals are part of the analysis and must be explained

  5. A final repair step ensures:
     - logical flow
     - no duplication
     - alignment with required_elements

CRITICAL EVALUATION PRINCIPLES:

- ALL insights MUST come from SQL data or provided context
- NO invented numbers, trends, or explanations
- Content MUST cover required_elements from the plan
- Content MUST follow:
  DATA → INTERPRETATION → IMPLICATION
- Visuals MUST be correctly referenced and interpreted
"""

CORRECTNESS_PROMPT = f"""
{EVAL_SYSTEM_CONTEXT}

You are evaluating correctness of an analytical report.

<Rubric>
  A correct answer:
  - Provides accurate and complete information
  - Contains no factual errors
  - Addresses all parts of the question
  - Is logically consistent
  - Uses precise and accurate terminology

  When scoring, you should penalize:
  - Factual errors or inaccuracies
  - Incomplete or partial answers
  - Misleading or ambiguous statements
  - Incorrect terminology
  - Logical inconsistencies
  - Missing key information
</Rubric>

<Instructions>
  - Carefully read the input and output
  - Check for factual accuracy and completeness
  - Focus on correctness of information rather than style or verbosity
</Instructions>

<Reminder>
  The goal is to evaluate factual correctness and completeness of the response.
</Reminder>

<input>
{{inputs}}
</input>

<output>
{{outputs}}
</output>

Use the reference outputs below to help you evaluate the correctness of the response:

"""


CONCISENESS_PROMPT = f"""
{EVAL_SYSTEM_CONTEXT}

You are evaluating correctness of an analytical report.
<Rubric>
  A perfectly concise answer:
  - Contains only the exact information requested.
  - Uses the minimum number of words necessary to convey the complete answer.
  - Omits pleasantries, hedging language, and unnecessary context.
  - Excludes meta-commentary about the answer or the model's capabilities.
  - Avoids redundant information or restatements.
  - Does not include explanations unless explicitly requested.

  When scoring, you should deduct points for:
  - Introductory phrases like "I believe," "I think," or "The answer is."
  - Hedging language like "probably," "likely," or "as far as I know."
  - Unnecessary context or background information.
  - Explanations when not requested.
  - Follow-up questions or offers for more information.
  - Redundant information or restatements.
  - Polite phrases like "hope this helps" or "let me know if you need anything else."
</Rubric>

<Instructions>
  - Carefully read the input and output.
  - Check for any unnecessary elements, particularly those mentioned in the <Rubric> above.
  - The score should reflect how close the response comes to containing only the essential information requested based on the rubric above.
</Instructions>

<Reminder>
  The goal is to reward responses that provide complete answers with absolutely no extraneous information.
</Reminder>

<input>
{{inputs}}
</input>

<output>
{{outputs}}
</output>
"""

HALLUCINATION_PROMPT = f"""
{EVAL_SYSTEM_CONTEXT}

You are evaluating correctness of an analytical report.

<Rubric>
  A response without hallucinations:
  - Contains only verifiable facts that are directly supported by the input context
  - Makes no unsupported claims or assumptions
  - Does not add speculative or imagined details
  - Maintains perfect accuracy in dates, numbers, and specific details
  - Appropriately indicates uncertainty when information is incomplete
</Rubric>

<Instructions>
  - Read the input context thoroughly
  - Identify all claims made in the output
  - Cross-reference each claim with the input context
  - Note any unsupported or contradictory information
  - Consider the severity and quantity of hallucinations
</Instructions>

<Reminder>
  Focus solely on factual accuracy and support from the input context. Do not consider style, grammar, or presentation in scoring. A shorter, factual response should score higher than a longer response with unsupported claims.
</Reminder>

Use the following context to help you evaluate for hallucinations in the output:

<context>
{{context}}
</context>

<input>
{{inputs}}
</input>

<output>
{{outputs}}
</output>

"""

ANSWER_RELEVANCE_PROMPT = f"""
{EVAL_SYSTEM_CONTEXT}

You are evaluating correctness of an analytical report.

<Rubric>
A relevant output:
- Directly answers the question or addresses the request
- Provides information specifically asked for
- Stays on topic with the input's intent
- Contributes meaningfully to fulfilling the request

An irrelevant output:
- Discusses topics not requested or implied by the input
- Provides unnecessary tangents or digressions
- Includes information that doesn't answer the question
- Addresses a different question than what was asked
</Rubric>

<Instructions>
For each output:
- Read the original input carefully to understand what was asked
- Examine the output and identify its core claim or purpose
- Determine if the output directly addresses the input's request
- Assess whether the information helps fulfill what was asked
- Determine the answer relevancy of output and output a score
</Instructions>

<Reminder>
Focus on whether each statement helps answer the specific input question, not whether the statement is true or well-written. A statement can be factually correct but still irrelevant if it doesn't address what was asked.
</Reminder>

Now, grade the following example according to the above instructions:

<example>
<input>
{{inputs}}
</input>

<output>
{{outputs}}
</output>
</example>
"""


# ==========================
# LLM (GEMINI JUDGE)
# ==========================

def get_judge_llm():
    # return ChatGoogleGenerativeAI(
    #     model="gemini-2.5-flash",
    #     temperature=0,
    # )
    return ChatOpenRouter(
        model="openai/gpt-5.4",
        temperature=0,
        api_key=settings.OPENROUTER_API_KEY,
        max_retries=2,
    )


# ==========================
# BLOCK → STRING (CRITICAL FIX)
# ==========================

def stringify_blocks(blocks):

    lines = []

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


# ==========================
# BUILD INPUT (NEW)
# ==========================

def build_eval_input(topic, report):

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


# ==========================
# HELPER FUNCTIONS
# ==========================

def extract_content_blocks_text(content_json):

    sections = content_json.get("sections", [])
    all_blocks = []

    for section in sections:
        all_blocks.extend(section.get("content_blocks", []))

    formatted = build_prompt_blocks(all_blocks, _decode_sql_result)

    return stringify_blocks(formatted)


def retrieve_metadata_for_topic(project, topic, vector_store, report):

    # -------------------------
    # 1. GET SECTION + SUBSECTION
    # -------------------------
    section_title = topic.subsection.section.title
    subsection_title = topic.subsection.title
    topic_title = topic.title

    # -------------------------
    # 2. GET ANALYSIS PLAN
    # -------------------------
    plan = TopicAnalysisPlan.objects.filter(
        topic=topic,
        report=report
    ).first()

    required_elements = []

    if plan and plan.plan_json:
        required_elements = plan.plan_json.get("required_elements", [])

    # -------------------------
    # 3. BUILD SEMANTIC QUERY (CRITICAL)
    # -------------------------
    query = f"""
    Section: {section_title}
    Subsection: {subsection_title}
    Topic: {topic_title}

    Required Analysis:
    {'; '.join(required_elements)}
    """

    # -------------------------
    # 4. VECTOR SEARCH (CORRECT)
    # -------------------------
    docs = vector_store.similarity_search(
        query=query,
        k=10,  # slightly higher improves recall
        filter={
            "project_id": project.id,
            "type": ["table_description", "column", "analytical_capability"],
        },
    )

    return "\n".join([doc.page_content for doc in docs])

# ==========================
# EVALUATOR SETUP
# ==========================

def build_evaluators(llm):

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


# ==========================
# TOPIC EVALUATION (UPDATED)
# ==========================

def evaluate_topic(project, topic, evaluators, vector_store, report):

    content_obj = TopicContent.objects.filter(topic=topic).first()
    if not content_obj:
        return None

    content_json = content_obj.content_json or {}

    # ✔ CONTENT (FIXED)
    content_text = extract_content_blocks_text(content_json)

    # ✔ INPUT (NEW)
    input_text = build_eval_input(topic, report)

    # ✔ CONTEXT (SQL + METADATA)
    sql_results = content_json.get("precomputed_sql_placeholders", [])

    #should implement this below object


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


# ==========================
# PROJECT EVALUATION
# ==========================

def evaluate_project(project_id: int, report_id: int):

    project = Project.objects.get(id=project_id)
    report = Report.objects.get(id=report_id)

    topics = Topic.objects.filter(
        subsection__section__report=report
    )

    vector_store = get_vector_store(
        backend=settings.DEFAULT_LLM_BACKEND
    )

    llm = get_judge_llm()
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
        topic_res={
            "scores": result["scores"],
            "issues": result["issues"],
            "summary": result["summary"],
            "overall_score": result["overall_score"],
        }
        print("\n\n__Result__\n", topic_res,"\n\n\n")

        TopicEvaluation.objects.update_or_create(
            topic=topic,
            report=report,
            defaults=topic_res,
        )

        topic_results.append(result)

    return compute_report_score(topic_results)


# ==========================
# REPORT AGGREGATION
# ==========================

def compute_report_score(topic_results):

    if not topic_results:
        return {
            "overall_score": 0,
            "category_scores": {},
            "topics_evaluated": 0,
        }

    category_scores = {}

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


# ==========================
# DECODE HELPERS
# ==========================

def decode_bdata(bdata, dtype):

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

    formatted = []

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

    raw = block.get("content")

    if isinstance(raw, dict):
        return block

    if isinstance(raw, str) and "{{VISUAL" in raw:

        import re

        def extract(field):
            match = re.search(rf"{field}\s*:\s*(.*?);", raw, re.DOTALL)
            return match.group(1).strip().strip('"') if match else ""

        block["content"] = {
            "id": extract("id"),
            "type": extract("type"),
            "purpose": extract("purpose"),
        }

    return block

