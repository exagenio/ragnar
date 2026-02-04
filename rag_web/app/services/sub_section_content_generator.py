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


# ==========================
# CONFIG
# ==========================

PROMPT_PATH = (
    Path(__file__).resolve().parent.parent / "prompts" / "subsection_content_gen_prompt.txt"
)


# ==========================
# PUBLIC ENTRY POINT
# ==========================

def generate_subsection_content(
    *,
    project_id: int,
    industry: str,
    report_type: str,
    audience: str,
    purpose: str,
    report_title: str,
    section_title: str,
    subsection_title: str,
    topics_progress: Dict[str, Dict],  # topic_title -> element_progress
    backend: LLMBackend | None = None,
) -> Dict:
    """
    Generate subsection introduction content by synthesizing all topics' progress.

    Args:
        project_id: The project ID
        industry: Industry context
        report_type: Type of report
        audience: Target audience
        purpose: Report purpose
        report_title: Title of the report
        section_title: Title of the section
        subsection_title: Title of the subsection
        topics_progress: Dictionary mapping topic titles to their element_progress data
        backend: Optional LLM backend

    Returns:
        Dictionary containing subsection introduction content
    """

    backend = backend or LLMBackend(settings.DEFAULT_LLM_BACKEND)

    llm = get_llm(
        backend=backend,
        model_size=ModelSize.PRIMARY,
        temperature=0.2,
    )

    # Format topics progress for the prompt
    topics_progress_formatted = json.dumps(topics_progress, indent=2)

    # Render the prompt
    prompt = render_prompt(
        PROMPT_PATH,
        {
            "industry": industry,
            "report_type": report_type,
            "audience": audience,
            "purpose": purpose,
            "report_title": report_title,
            "section_title": section_title,
            "subsection_title": subsection_title,
            "topics_progress_json": topics_progress_formatted,
        },
    )

    # Invoke LLM
    response = llm.invoke(prompt)
    raw_text = response.content.strip()

    # Extract and return JSON
    result = extract_json_or_fail(raw_text)

    return result


# ==========================
# HELPERS
# ==========================

def render_prompt(prompt_path: Path, context: dict) -> str:
    """
    Render a prompt template by replacing placeholders with context values.

    Args:
        prompt_path: Path to the prompt template file
        context: Dictionary of placeholder values

    Returns:
        Rendered prompt string
    """
    prompt = prompt_path.read_text(encoding="utf-8")
    for key, value in context.items():
        prompt = prompt.replace(f"{{{{{key}}}}}", str(value))
    return prompt


def extract_json_or_fail(raw_text: str) -> dict:
    """
    Extract JSON object from LLM response.

    Args:
        raw_text: Raw text response from LLM

    Returns:
        Parsed JSON dictionary

    Raises:
        ValueError: If no valid JSON found in response
    """
    if not raw_text:
        raise ValueError("LLM returned empty response")

    match = re.search(r"\{[\s\S]*\}", raw_text)
    if not match:
        raise ValueError(f"LLM did not return JSON:\n{raw_text[:500]}")

    return json.loads(match.group())
