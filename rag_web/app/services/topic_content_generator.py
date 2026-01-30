import json
from pathlib import Path
from typing import Dict, List, Set
from collections import defaultdict

from django.conf import settings

from langchain_core.prompts import PromptTemplate

from app.services.llm_provider import (
    get_llm,
    LLMBackend,
    ModelSize,
)
from .vector_store import get_vector_store
import re


# ==========================
# CONFIG
# ==========================

MAX_ITERATIONS = 5

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
    backend: LLMBackend | None = None,
) -> Dict:
    """
    Iteratively generate content for ONE topic using:
    - Unified LLM provider (local / cloud)
    - PGVector metadata retrieval
    """

    backend = backend or LLMBackend(settings.DEFAULT_LLM_BACKEND)

    llm = get_llm(
        backend=backend,
        model_size=ModelSize.PRIMARY,
        temperature=0,
    )

    vector_store = get_vector_store()

    # ==========================
    # INTERNAL RUNTIME STATE
    # ==========================

    content_state = {
        "sections": [],
        "covered_elements": set(),
        "iteration_count": 0,
        "status": "in_progress",
    }

    if existing_content:
        content_state["sections"] = existing_content.get("sections", [])
        content_state["covered_elements"] = set(
            existing_content.get("covered_elements", [])
        )
        content_state["iteration_count"] = existing_content.get("iteration_count", 0)

    required_elements = set(topic_plan.get("required_elements", []))

    # ==========================
    # ITERATIVE LOOP
    # ==========================

    while True:
        if content_state["iteration_count"] >= MAX_ITERATIONS:
            content_state["status"] = "forced_stop"
            break

        missing_elements = list(required_elements - content_state["covered_elements"])

        metadata_context = retrieve_metadata_context(
            vector_store=vector_store,
            project_id=project_id,
            query=_build_metadata_query(
                section_title,
                subsection_title,
                topic_title,
                topic_plan,
                missing_elements,
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
            existing_content=content_state,
            missing_elements=missing_elements,
        )
        print("interation = ",content_state["iteration_count"])
        print(iteration_output)
        print("___________________\n\n")
        merge_content(content_state, iteration_output)

        content_state["covered_elements"].update(
            iteration_output.get("newly_covered_elements", [])
        )

        content_state["iteration_count"] += 1

        if stop_conditions_met(
            required_elements,
            content_state["covered_elements"],
            iteration_output.get("quality_flags", {}),
        ):
            content_state["status"] = "generated"
            break

    content_state["covered_elements"] = list(content_state["covered_elements"])
    return content_state


# ==========================
# METADATA RETRIEVAL
# ==========================

def retrieve_metadata_context(
    *,
    vector_store,
    project_id: int,
    query: str,
    k: int = 8,
) -> List[Dict]:

    docs = vector_store.similarity_search(
        query,
        k=k,
        filter={"project_id": project_id},
    )

    return [
        {
            "content": d.page_content,
            "metadata": d.metadata,
        }
        for d in docs
    ]


def _build_metadata_query(
    section_title: str,
    subsection_title: str,
    topic_title: str,
    topic_plan: Dict,
    missing_elements: List[str],
) -> str:

    parts = [
        section_title,
        subsection_title,
        topic_title,
        " ".join(topic_plan.get("required_elements", [])),
        " ".join(missing_elements),
    ]

    return " ".join(p for p in parts if p)


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
    existing_content: Dict,
    missing_elements: List[str],
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
            "existing_content_json": json.dumps(
                make_json_safe_content_state(existing_content), indent=2
            ),
            "covered_elements": list(existing_content["covered_elements"]),
            "missing_elements": missing_elements,
        },
    )


    response = llm.invoke(prompt)
    raw_text = response.content.strip()

    try:
        return extract_json_or_fail(raw_text)
    except Exception as e:
        print("❌ LLM OUTPUT ERROR")
        print(raw_text)
        raise



# ==========================
# MERGE + STOP LOGIC
# ==========================

def merge_content(content_state: Dict, iteration_output: Dict) -> None:
    existing_sections = content_state["sections"]

    for new_section in iteration_output.get("sections", []):
        heading = new_section["heading"]

        existing = next(
            (s for s in existing_sections if s["heading"] == heading), None
        )

        if not existing:
            existing_sections.append(new_section)
        else:
            for block in new_section.get("content_blocks", []):
                if block not in existing["content_blocks"]:
                    existing["content_blocks"].append(block)


def stop_conditions_met(
    required_elements: Set[str],
    covered_elements: Set[str],
    quality_flags: Dict,
) -> bool:
    if required_elements - covered_elements:
        return False
    if quality_flags.get("needs_more_depth"):
        return False
    if quality_flags.get("has_repetition"):
        return False
    return quality_flags.get("professional_tone", False)


def make_json_safe_content_state(state: Dict) -> Dict:
    safe = state.copy()
    safe["covered_elements"] = list(state.get("covered_elements", []))
    return safe


def render_prompt(prompt_path: Path, context: dict) -> str:
    """
    Safely render an LLM prompt using plain-text replacement.
    This avoids Jinja / format() issues with JSON and placeholders.
    """
    prompt = prompt_path.read_text(encoding="utf-8")

    for key, value in context.items():
        prompt = prompt.replace(f"{{{{{key}}}}}", str(value))

    return prompt


def extract_json_or_fail(raw_text: str) -> dict:
    """
    Safely extract JSON object from LLM output.
    Raises a clear error if JSON is missing.
    """
    if not raw_text:
        raise ValueError("LLM returned empty response")

    match = re.search(r"\{[\s\S]*\}", raw_text)
    if not match:
        raise ValueError(
            f"LLM did not return JSON. Raw output:\n{raw_text[:500]}"
        )

    return json.loads(match.group())