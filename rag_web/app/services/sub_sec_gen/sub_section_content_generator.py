import json
import re
from pathlib import Path
from typing import Dict, List
from django.conf import settings
from app.services.llm_config.llm_provider import (
    get_llm,
    LLMBackend,
    ModelSize,
)
from app.agents.rate_limiter import rate_limiter


PROMPT_PATH = settings.BASE_DIR / "app" / "prompts" / "subsection_content_gen_prompt.txt"


def generate_subsection_content(
    *,
    project=None,
    project_id: int,
    industry: str,
    report_type: str,
    audience: str,
    purpose: str,
    report_title: str,
    section_title: str,
    subsection_title: str,
    topics_progress: Dict[str, Dict],
    backend: LLMBackend | None = None,
) -> Dict:
    """Generate subsection content"""

    backend = backend or LLMBackend(settings.DEFAULT_LLM_BACKEND)

    llm = get_llm(
        backend=backend,
        model_size=ModelSize.SMALL,
        temperature=0.2,
        project=project,
    )

    # Format topics progress as json
    topics_progress_formatted = json.dumps(topics_progress, indent=2)

    # Build prompt from template
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

    # Apply rate limiting
    estimated_tokens = len(prompt) // 4
    rate_limiter.consume(estimated_tokens)

    # Invoke llm and extract text
    response = llm.invoke(prompt)
    content = response.content

    # Handle structured and plain responses
    if isinstance(content, list):
        if isinstance(content[0], dict) and "text" in content[0]:
            raw_text = content[0]["text"].strip()
        else:
            raw_text = str(content[0]).strip()
    else:
        raw_text = content.strip()

    # Extract json result
    result = extract_json_or_fail(raw_text)

    return result


def render_prompt(prompt_path: Path, context: dict) -> str:
    """Render prompt"""

    prompt = prompt_path.read_text(encoding="utf-8")
    for key, value in context.items():
        prompt = prompt.replace(f"{{{{{key}}}}}", str(value))
    return prompt


def extract_json_or_fail(raw_text: str) -> dict:
    """Extract json from text"""

    if not raw_text:
        raise ValueError("LLM returned empty response")

    # Extract json object from text
    match = re.search(r"\{[\s\S]*\}", raw_text)
    if not match:
        raise ValueError(f"LLM did not return JSON:\n{raw_text[:500]}")

    return json.loads(match.group())
