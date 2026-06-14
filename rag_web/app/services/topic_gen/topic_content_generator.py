import json
import re
from pathlib import Path
from typing import Dict, List
from django.conf import settings
from sentence_transformers import SentenceTransformer, util
from app.services.llm_config.llm_provider import (
    get_llm,
    LLMBackend,
    ModelSize,
)
from app.agents.rate_limiter import rate_limiter
from app.services.metadata_generation.metadata_retriever import (
    format_metadata_context_json,
    retrieve_multi_table_metadata,
)
from app.services.topic_gen.topic_analysis_plan_generator import normalize_topic_analysis_plan


# Load semantic model once
semantic_model = SentenceTransformer("all-MiniLM-L6-v2")
SIMILARITY_THRESHOLD = 0.8


MAX_ITERATIONS_PER_ELEMENT = 2

PROMPT_PATH = settings.BASE_DIR / "app" / "prompts" / "topic_content_prompt.txt"


def generate_topic_content(
    *,
    project=None,
    project_id: int,
    industry: str,
    report_type: str,
    audience: str,
    purpose: str,
    section_title: str,
    subsection_title: str,
    topic_title: str,
    topic_plan: Dict,
    existing_content: Dict | None = None,
    precomputed_sql_placeholders: List[Dict] | None = None,
    backend: LLMBackend | None = None,
) -> Dict:
    """Generate topic content"""

    backend = backend or LLMBackend(settings.DEFAULT_LLM_BACKEND)
    llm = get_llm(
        backend=backend,
        model_size=ModelSize.PRIMARY,
        temperature=0,
        project=project,
    )

    # Initialize content state
    default_state = {
        "sections": [],
        "element_progress": {},
        "completed_elements": [],
        "limitations": [],
        "status": "in_progress",
    }

    if existing_content:
        content_state = {
            **default_state,
            **existing_content,
        }

        # Ensure nested structures exist
        content_state["sections"] = existing_content.get("sections", [])
        content_state["element_progress"] = existing_content.get("element_progress", {})
        content_state["completed_elements"] = existing_content.get("completed_elements", [])
        content_state["limitations"] = existing_content.get("limitations", [])
    else:
        content_state = default_state

    topic_plan = normalize_topic_analysis_plan(topic_plan or {})
    required_elements = topic_plan.get("required_elements", [])

    # Iterate through required elements
    for element in required_elements:
        if element in content_state["completed_elements"]:
            continue

        covered_points = []

        for elem, points in content_state["element_progress"].items():
            for p in points:
                covered_points.append(f"[{elem}] {p}")

        iteration_count = 0
        retry_used = False

        # Handle iterative content generation logic
        while iteration_count < MAX_ITERATIONS_PER_ELEMENT:

            metadata_context = retrieve_metadata_context(
                project=project,
                query=_build_metadata_query(
                    section_title,
                    subsection_title,
                    topic_title,
                    element,
                ),
            )

            iteration_output = generate_single_iteration(
                llm=llm,
                industry=industry,
                report_type=report_type,
                audience=audience,
                purpose=purpose,
                section_title=section_title,
                subsection_title=subsection_title,
                topic_title=topic_title,
                topic_plan=topic_plan,
                metadata_context=metadata_context,
                current_required_element=element,
                covered_points=covered_points,
                precomputed_sql_placeholders=precomputed_sql_placeholders,
            )

            # Merge generated blocks
            all_blocks = []

            for section in iteration_output.get("sections", []):
                all_blocks.extend(section.get("content_blocks", []))

            any_added = _merge_blocks(content_state["sections"], all_blocks)

            # Handle duplicate case
            if not any_added:
                print("[SKIP] Duplicate found, moving forward")
                retry_used = False
                iteration_count += 1
                continue

            # Update state after successful merge
            retry_used = False
            iteration_count += 1

            existing_limits = content_state.get("limitations", [])
            new_limits = iteration_output.get("limitations", [])

            content_state["limitations"] = list(
                dict.fromkeys(existing_limits + new_limits)
            )

            new_points = iteration_output.get("newly_covered_points", [])
            covered_points = list(dict.fromkeys(covered_points + new_points))

            content_state["element_progress"][element] = covered_points

            if iteration_output.get("is_element_complete") is True:
                content_state["completed_elements"].append(element)
                break

    content_state["status"] = "generated"
    return content_state


def generate_single_iteration(
    *,
    llm,
    industry: str,
    report_type: str,
    audience: str,
    purpose: str,
    section_title: str,
    subsection_title: str,
    topic_title: str,
    topic_plan: Dict,
    metadata_context: List[Dict],
    current_required_element: str,
    covered_points: List[str],
    precomputed_sql_placeholders: List[Dict] | None = None,
) -> Dict:
    """Generate single iteration"""

    # Build prompt from template
    prompt = render_prompt(
        PROMPT_PATH,
        {
            "industry": industry,
            "report_type": report_type,
            "audience": audience,
            "purpose": purpose,
            "section_title": section_title,
            "subsection_title": subsection_title,
            "topic_title": topic_title,
            "topic_plan_json": json.dumps(topic_plan, indent=2),
            "metadata_context_json": format_metadata_context_json(metadata_context),
            "current_required_element": current_required_element,
            "covered_elements_summary": "\n".join(f"- {p}" for p in covered_points),
            "precomputed_sql_json": json.dumps(precomputed_sql_placeholders or [], indent=2),
        },
    )

    # Apply rate limiting
    estimated_tokens = len(prompt) // 4
    rate_limiter.consume(estimated_tokens)

    # Invoke llm
    response = llm.invoke(prompt)
    content = response.content

    # Extract response text
    if isinstance(content, list):
        if isinstance(content[0], dict) and "text" in content[0]:
            raw_text = content[0]["text"].strip()
        else:
            raw_text = str(content[0]).strip()
    else:
        raw_text = content.strip()

    return extract_json_or_fail(raw_text)


def retrieve_metadata_context(*, project, query: str, k: int = 8):
    """Retrieve metadata context"""

    return retrieve_multi_table_metadata(
        project=project,
        primary_query=query,
        secondary_queries=[
            "topic content generation business entities measures dimensions join paths",
        ],
        per_query_k=k,
        max_docs=max(k * 2, 16),
    )


def _build_metadata_query(section, subsection, topic, element):
    """Build metadata query"""

    return f"{section} {subsection} {topic} {element}"


def _merge_blocks(sections: List[Dict], new_blocks: List[Dict]) -> bool:
    """Merge blocks atomically"""

    # Handle atomic merge logic
    if not sections:
        sections.append({"heading": "Analysis", "content_blocks": []})

    existing_blocks = sections[0]["content_blocks"]

    temp_blocks = []

    for block in new_blocks:

        comparison_pool = existing_blocks + temp_blocks

        is_duplicate = filter_similar_blocks(comparison_pool, block)

        if is_duplicate:
            print(f"[REJECTED BATCH - DUPLICATE FOUND] {block.get('type')}")
            return False

        temp_blocks.append(block)

    existing_blocks.extend(temp_blocks)

    return True


def render_prompt(prompt_path: Path, context: dict) -> str:
    """Render prompt"""

    prompt = prompt_path.read_text(encoding="utf-8")
    for key, value in context.items():
        prompt = prompt.replace(f"{{{{{key}}}}}", str(value))
    return prompt


def extract_json_or_fail(raw_text: str):
    """Extract json from text"""

    if not raw_text:
        raise ValueError("LLM returned empty response")

    raw_text = raw_text.strip()

    # Extract json array first
    array_match = re.search(r"\[[\s\S]*\]", raw_text)

    if array_match:
        try:
            return json.loads(array_match.group())
        except Exception:
            pass

    # Extract json object fallback
    obj_match = re.search(r"\{[\s\S]*\}", raw_text)

    if obj_match:
        try:
            return json.loads(obj_match.group())
        except Exception:
            pass

    raise ValueError(f"Invalid JSON from LLM:\n{raw_text[:1000]}")


def _extract_visual_purpose(content) -> str:
    """Extract visual purpose"""

    if isinstance(content, dict):
        return content.get("purpose", "") or ""

    if isinstance(content, str):
        match = re.search(r'purpose:\s*"(.*?)"', content, re.DOTALL)
        return match.group(1).strip() if match else ""

    return ""


def _is_similar(text1: str, text2: str) -> bool:
    """Check similarity between texts"""

    if not text1 or not text2:
        return False

    emb1 = semantic_model.encode(text1, convert_to_tensor=True)
    emb2 = semantic_model.encode(text2, convert_to_tensor=True)

    score = util.cos_sim(emb1, emb2)
    score_value = float(score.max())
    return score_value >= SIMILARITY_THRESHOLD


def filter_similar_blocks(existing_blocks: List[Dict], new_block: Dict) -> bool:
    """Filter similar blocks"""

    new_type = new_block.get("type")

    # Handle text blocks
    if new_type in ["paragraph", "bullet_list"]:

        new_text = new_block.get("content", "")
        new_text = _normalize_bullet_content(new_text)
        for block in existing_blocks:
            if block.get("type") not in ["paragraph", "bullet_list"]:
                continue

            existing_text = block.get("content", "")
            existing_text = _normalize_bullet_content(existing_text)
            if _is_similar(new_text, existing_text):
                print("[simiar text new]", new_text)
                print("[simiar text exist]", existing_text)
                return True

    # Handle visual placeholders
    elif new_type == "visual_placeholder":
        content = new_block.get("content")
        new_purpose = _extract_visual_purpose(content)

        for block in existing_blocks:
            if block.get("type") != "visual_placeholder":
                continue

            existing_purpose = _extract_visual_purpose(block.get("content", ""))

            if _is_similar(new_purpose, existing_purpose):
                return True

    return False


def _normalize_bullet_content(content):
    """Normalize bullet content"""

    if isinstance(content, list):
        return " ".join(content)
    return content
