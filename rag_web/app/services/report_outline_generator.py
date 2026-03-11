import json
import re
from pathlib import Path
from collections import defaultdict

from django.conf import settings

from app.services.llm_provider import (
    get_llm,
    LLMBackend,
    ModelSize,
)
from .industry_guidance import get_industry_guidance


# ==========================
# CONFIG
# ==========================

PROMPT_PATH = (
    Path(__file__).resolve().parent.parent / "prompts" / "report_outline_prompt.txt"
)


# ==========================
# JSON EXTRACTION
# ==========================


def extract_json(text: str) -> dict:
    """
    Extract the first valid JSON object from text.
    """
    match = re.search(r"\{[\s\S]*\}", text)
    if not match:
        raise ValueError("No JSON object found in LLM response")

    return json.loads(match.group())


# ==========================
# MAIN ENTRY
# ==========================


def generate_report_outline(
    data: dict,
    *,
    backend: LLMBackend | None = None,
) -> dict:
    """
    Generate a structured report outline using the unified LLM provider.
    """

    backend = backend or LLMBackend(settings.DEFAULT_LLM_BACKEND)

    prompt_template = PROMPT_PATH.read_text(encoding="utf-8")

    industry_guidance = get_industry_guidance(data["industry"])

    prompt = prompt_template.format_map(
        defaultdict(
            str,
            {
                "industry": data["industry"],
                "report_type": data["report_type"],
                "audience": data["audience"],
                "purpose": data["purpose"],
                "focus_areas": data.get("focus_areas", ""),
                "additional_notes": data.get("additional_notes", ""),
                "industry_guidance": industry_guidance,
            },
        )
    )

    # 🔹 Get LLM from provider
    llm = get_llm(
        backend=backend,
        model_size=ModelSize.PRIMARY,  # outline quality is important
        temperature=0,
    )

    # 🔹 Invoke via LangChain
    response = llm.invoke(prompt)

    content = response.content

    if isinstance(content, list):
        # LangChain structured output
        if isinstance(content[0], dict) and "text" in content[0]:
            raw_output = content[0]["text"].strip()
        else:
            raw_output = str(content[0]).strip()
    else:
        raw_output = content.strip()

    try:
        return extract_json(raw_output)
    except Exception as e:
        raise ValueError(f"LLM returned invalid JSON: {e}")
