import json
import re
from pathlib import Path
from typing import Dict, List

from django.conf import settings

from app.services.llm_config.llm_provider import get_llm, LLMBackend, ModelSize
from app.agents.rate_limiter import rate_limiter


PROMPT_PATH = settings.BASE_DIR / "app" / "prompts" / "section_content_gen_prompt.txt"


def generate_section_content(
    *,
    project=None,
    project_id: int,
    industry: str,
    report_type: str,
    audience: str,
    purpose: str,
    report_title: str,
    section_title: str,
    subsections_themes: Dict[str, List[str]],
    backend: LLMBackend | None = None,
) -> Dict:
    """Generate section content"""

    backend = backend or LLMBackend(settings.DEFAULT_LLM_BACKEND)

    llm = get_llm(
        backend=backend,
        model_size=ModelSize.SMALL,
        temperature=0.2,
        project=project,
    )

    # Format subsection themes as json string
    subsections_themes_formatted = json.dumps(subsections_themes, indent=2)

    # Build prompt using template
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

    # Estimate tokens and apply rate limiting
    estimated_tokens = len(prompt) // 4
    rate_limiter.consume(estimated_tokens)

    # Invoke llm and normalize response
    response = llm.invoke(prompt)
    raw_text = _extract_text_from_response(response.content)

    # Extract json result
    return extract_json_or_fail(raw_text)


def render_prompt(prompt_path: Path, context: dict) -> str:
    """Render prompt"""

    prompt = prompt_path.read_text(encoding="utf-8")

    # Replace placeholders with values
    for key, value in context.items():
        prompt = prompt.replace(f"{{{{{key}}}}}", str(value))

    return prompt


def extract_json_or_fail(raw_text: str) -> dict:
    """Extract json from text"""

    if not raw_text:
        raise ValueError("LLM returned empty response")

    # Find json object inside text
    match = re.search(r"\{[\s\S]*\}", raw_text)
    if not match:
        raise ValueError(f"LLM did not return JSON:\n{raw_text[:500]}")

    return json.loads(match.group())


def _extract_text_from_response(content):
    """Extract text from llm response"""

    # Handle structured and unstructured responses
    if isinstance(content, list):
        first_item = content[0]

        if isinstance(first_item, dict) and "text" in first_item:
            return first_item["text"].strip()

        return str(first_item).strip()

    return content.strip()
