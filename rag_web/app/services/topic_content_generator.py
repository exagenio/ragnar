# topic content generator
import json
import re
from pathlib import Path
from typing import Dict, List

from django.conf import settings

from app.services.llm_provider import (
    get_llm,
    LLMBackend,
    ModelSize,
)
from .vector_store import get_vector_store
from sentence_transformers import SentenceTransformer, util
from app.agents.rate_limiter import rate_limiter

# Load once (global)
semantic_model = SentenceTransformer("all-MiniLM-L6-v2")
SIMILARITY_THRESHOLD = 0.8


# ==========================
# CONFIG
# ==========================

MAX_ITERATIONS_PER_ELEMENT = 2

PROMPT_PATH = (
    Path(__file__).resolve().parent.parent / "prompts" / "topic_content_prompt.txt"
)


# ==========================
# PUBLIC ENTRY POINT
# ==========================

def generate_topic_content(
    *,
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

    backend = backend or LLMBackend(settings.DEFAULT_LLM_BACKEND)
    llm = get_llm(
        backend=backend,
        model_size=ModelSize.PRIMARY,
        temperature=0,
    )

    vector_store = get_vector_store()

    # ==========================
    # STATE (TOKEN SAFE)
    # ==========================

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

        # Ensure nested structures exist (critical)
        content_state["sections"] = existing_content.get("sections", [])
        content_state["element_progress"] = existing_content.get("element_progress", {})
        content_state["completed_elements"] = existing_content.get("completed_elements", [])
        content_state["limitations"] = existing_content.get("limitations", [])
    else:
        content_state = default_state

    required_elements = topic_plan.get("required_elements", [])

    # ==========================
    # MAIN LOOP (ELEMENT BY ELEMENT)
    # ==========================

    for element in required_elements:
        if element in content_state["completed_elements"]:
            continue

        covered_points = []


        for elem, points in content_state["element_progress"].items():
            for p in points:
                covered_points.append(f"[{elem}] {p}")

        iteration_count = 0
        retry_used = False

        while iteration_count < MAX_ITERATIONS_PER_ELEMENT:

            metadata_context = retrieve_metadata_context(
                vector_store=vector_store,
                project_id=project_id,
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

            # ---- TRY MERGE CONTENT
            all_blocks = []

            for section in iteration_output.get("sections", []):
                all_blocks.extend(section.get("content_blocks", []))

            any_added = _merge_blocks(content_state["sections"], all_blocks)

            # -------------------------------------
            # CASE 1: DUPLICATE → RETRY LOGIC
            # -------------------------------------
            if not any_added:
                print("[SKIP] Duplicate found, moving forward")
                retry_used = False
                iteration_count += 1
                continue

            

            # -------------------------------------
            # CASE 2: SUCCESS → UPDATE STATE
            # -------------------------------------

            retry_used = False
            iteration_count += 1

            # ---- Merge limitations
            existing_limits = content_state.get("limitations", [])
            new_limits = iteration_output.get("limitations", [])

            content_state["limitations"] = list(
                dict.fromkeys(existing_limits + new_limits)
            )

            # ---- Update semantic memory ONLY IF SUCCESS
            new_points = iteration_output.get("newly_covered_points", [])
            covered_points = list(dict.fromkeys(covered_points + new_points))

            content_state["element_progress"][element] = covered_points

            # ---- Completion check ONLY IF SUCCESS
            if iteration_output.get("is_element_complete") is True:
                content_state["completed_elements"].append(element)
                break

    content_state["status"] = "generated"
    return content_state


# ==========================
# SINGLE ITERATION
# ==========================

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
            "metadata_context_json": json.dumps(metadata_context, indent=2),
            "current_required_element": current_required_element,
            "covered_elements_summary": "\n".join(f"- {p}" for p in covered_points),
            "precomputed_sql_json": json.dumps(precomputed_sql_placeholders or [], indent=2),
        },
    )

    estimated_tokens = len(prompt) // 4  # rough estimate

    rate_limiter.consume(estimated_tokens)

    response = llm.invoke(prompt)
    content = response.content

    if isinstance(content, list):
        # LangChain structured output
        if isinstance(content[0], dict) and "text" in content[0]:
            raw_text = content[0]["text"].strip()
        else:
            raw_text = str(content[0]).strip()
    else:
        raw_text = content.strip()

    return extract_json_or_fail(raw_text)


# ==========================
# HELPERS
# ==========================

def retrieve_metadata_context(*, vector_store, project_id: int, query: str, k: int = 8):
    docs = vector_store.similarity_search(
        query,
        k=k,
        filter={"project_id": project_id},
    )
    return [{"content": d.page_content, "metadata": d.metadata} for d in docs]


def _build_metadata_query(section, subsection, topic, element):
    return f"{section} {subsection} {topic} {element}"

def _merge_blocks(sections: List[Dict], new_blocks: List[Dict]) -> bool:
    """
    Atomic merge:
    - Validate ALL blocks first
    - If ANY duplicate → reject entire batch
    - If ALL unique → append ALL
    Returns True if merged, False if rejected
    """

    if not sections:
        sections.append({"heading": "Analysis", "content_blocks": []})

    existing_blocks = sections[0]["content_blocks"]

    # -------------------------
    # TEMP BUFFER (CRITICAL)
    # -------------------------
    temp_blocks = []

    for block in new_blocks:

        # Compare against BOTH:
        # 1. existing content
        # 2. already validated new blocks
        comparison_pool = existing_blocks + temp_blocks

        is_duplicate = filter_similar_blocks(comparison_pool, block)

        if is_duplicate:
            print(f"[REJECTED BATCH - DUPLICATE FOUND] {block.get('type')}")
            return False  # ❌ Reject entire batch

        temp_blocks.append(block)

    # -------------------------
    # COMMIT (ALL AT ONCE)
    # -------------------------
    existing_blocks.extend(temp_blocks)

    return True


def render_prompt(prompt_path: Path, context: dict) -> str:
    prompt = prompt_path.read_text(encoding="utf-8")
    for key, value in context.items():
        prompt = prompt.replace(f"{{{{{key}}}}}", str(value))
    return prompt


def extract_json_or_fail(raw_text: str):

    if not raw_text:
        raise ValueError("LLM returned empty response")

    raw_text = raw_text.strip()

    import re

    # -----------------------------
    # TRY ARRAY FIRST
    # -----------------------------
    array_match = re.search(r"\[[\s\S]*\]", raw_text)

    if array_match:
        try:
            return json.loads(array_match.group())
        except Exception:
            pass

    # -----------------------------
    # FALLBACK OBJECT
    # -----------------------------
    obj_match = re.search(r"\{[\s\S]*\}", raw_text)

    if obj_match:
        try:
            return json.loads(obj_match.group())
        except Exception:
            pass

    # -----------------------------
    # DEBUG
    # -----------------------------
    raise ValueError(f"Invalid JSON from LLM:\n{raw_text[:1000]}")

def _extract_visual_purpose(content) -> str:
    """
    Supports both:
    - string placeholder
    - structured dict
    """

    # NEW FORMAT (dict)
    if isinstance(content, dict):
        return content.get("purpose", "") or ""

    # OLD FORMAT (string)
    if isinstance(content, str):
        match = re.search(r'purpose:\s*"(.*?)"', content, re.DOTALL)
        return match.group(1).strip() if match else ""

    return ""

def _is_similar(text1: str, text2: str) -> bool:
    if not text1 or not text2:
        return False

    emb1 = semantic_model.encode(text1, convert_to_tensor=True)
    emb2 = semantic_model.encode(text2, convert_to_tensor=True)

    score = util.cos_sim(emb1, emb2)
    score_value = float(score.max())
    return score_value >= SIMILARITY_THRESHOLD

def filter_similar_blocks(existing_blocks: List[Dict], new_block: Dict) -> bool:
    """
    Returns True → if block is similar (should be REMOVED)
    Returns False → if block is unique (should be ADDED)
    """

    new_type = new_block.get("type")

    # -------------------------
    # CASE 1: PARAGRAPH / BULLET
    # -------------------------
    if new_type in ["paragraph", "bullet_list"]:

        new_text = new_block.get("content", "")
        new_text = _normalize_bullet_content(new_text)
        for block in existing_blocks:
            if block.get("type") not in ["paragraph", "bullet_list"]:
                continue

            existing_text = block.get("content", "")
            existing_text = _normalize_bullet_content(existing_text)
            if _is_similar(new_text, existing_text):
                print("[simiar text new]",new_text)
                print("[simiar text exist]",existing_text)
                return True

    # -------------------------
    # CASE 2: VISUAL PLACEHOLDER
    # -------------------------
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
    """
    Convert bullet list (list of strings) into a single string.
    """
    if isinstance(content, list):
        return " ".join(content)
    return content
