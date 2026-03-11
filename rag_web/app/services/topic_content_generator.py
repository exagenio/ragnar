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


# ==========================
# CONFIG
# ==========================

MAX_ITERATIONS_PER_ELEMENT = 4

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

    content_state = existing_content or {
        "sections": [],
        "element_progress": {},  # element → covered_points[]
        "completed_elements": [],
        "limitations": [], 
        "status": "in_progress",
    }

    required_elements = topic_plan.get("required_elements", [])

    # ==========================
    # MAIN LOOP (ELEMENT BY ELEMENT)
    # ==========================

    for element in required_elements:
        if element in content_state["completed_elements"]:
            continue

        covered_points = content_state["element_progress"].get(element, [])

        for _ in range(MAX_ITERATIONS_PER_ELEMENT):

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
            )

            print(iteration_output)

            # ---- Merge limitations (STRUCTURAL ONLY)
            existing_limits = content_state.get("limitations", [])
            new_limits = iteration_output.get("limitations", [])

            content_state["limitations"] = list(
                dict.fromkeys(existing_limits + new_limits)  # dedupe, preserve order
            )

            # ---- Merge content
            for section in iteration_output.get("sections", []):
                _merge_blocks(content_state["sections"], section["content_blocks"])

            # ---- Update semantic memory
            new_points = iteration_output.get("newly_covered_points", [])
            covered_points = list(dict.fromkeys(covered_points + new_points))

            content_state["element_progress"][element] = covered_points

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

        },
    )

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


def _merge_blocks(sections: List[Dict], new_blocks: List[Dict]):
    if not sections:
        sections.append({"heading": "Analysis", "content_blocks": []})

    existing_blocks = sections[0]["content_blocks"]

    for block in new_blocks:
        if block not in existing_blocks:
            existing_blocks.append(block)


def render_prompt(prompt_path: Path, context: dict) -> str:
    prompt = prompt_path.read_text(encoding="utf-8")
    for key, value in context.items():
        prompt = prompt.replace(f"{{{{{key}}}}}", str(value))
    return prompt


def extract_json_or_fail(raw_text: str) -> dict:
    if not raw_text:
        raise ValueError("LLM returned empty response")

    match = re.search(r"\{[\s\S]*\}", raw_text)
    if not match:
        raise ValueError(f"LLM did not return JSON:\n{raw_text[:500]}")

    return json.loads(match.group())
