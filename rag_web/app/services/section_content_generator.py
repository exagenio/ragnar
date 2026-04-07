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
from app.agents.rate_limiter import rate_limiter

# ==========================
# CONFIG
# ==========================

PROMPT_PATH = (
    Path(__file__).resolve().parent.parent / "prompts" / "section_content_gen_prompt.txt"
)


# ==========================
# PUBLIC ENTRY POINT
# ==========================

def generate_section_content(
    *,
    project_id: int,
    industry: str,
    report_type: str,
    audience: str,
    purpose: str,
    report_title: str,
    section_title: str,
    subsections_themes: Dict[str, List[str]],  # subsection_title -> key_themes[]
    backend: LLMBackend | None = None,
) -> Dict:
    """
    Generate section introduction content by synthesizing all subsections' themes.

    Args:
        project_id: The project ID
        industry: Industry context
        report_type: Type of report
        audience: Target audience
        purpose: Report purpose
        report_title: Title of the report
        section_title: Title of the section
        subsections_themes: Dictionary mapping subsection titles to their key themes
        backend: Optional LLM backend

    Returns:
        Dictionary containing section introduction content
    """

    backend = backend or LLMBackend(settings.DEFAULT_LLM_BACKEND)

    llm = get_llm(
        backend=backend,
        model_size=ModelSize.SMALL,
        temperature=0.2,
    )

    # Format subsections themes for the prompt
    subsections_themes_formatted = json.dumps(subsections_themes, indent=2)

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
            "subsections_themes_json": subsections_themes_formatted,
        },
    )

    # Invoke LLM
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
