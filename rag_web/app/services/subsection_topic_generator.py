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

# ==========================
# CONFIG
# ==========================

PROMPT_PATH = (
    Path(__file__).resolve().parent.parent / "prompts" / "subsection_topics_prompt.txt"
)


# ==========================
# JSON EXTRACTION
# ==========================

def extract_json(text: str) -> dict:
    """
    Extract the first valid JSON object from LLM output.
    """
    match = re.search(r"\{[\s\S]*\}", text)
    if not match:
        raise ValueError("No JSON object found in LLM response")

    return json.loads(match.group())


# ==========================
# MAIN ENTRY
# ==========================

def generate_subsection_topics(
    context: dict,
    *,
    backend: LLMBackend | None = None,
) -> dict:
    """
    Generate subsection-level topics using the unified LLM provider.
    """

    backend = backend or LLMBackend(settings.DEFAULT_LLM_BACKEND)

    prompt_template = PROMPT_PATH.read_text(encoding="utf-8")

    prompt = prompt_template
    for key, value in context.items():
            prompt = prompt.replace(f"{{{{{key}}}}}", str(value))

    # 🔹 Get LLM from provider
    llm = get_llm(
        backend=backend,
        model_size=ModelSize.PRIMARY,  # topic structure needs quality
        temperature=0.2,
    )

    # 🔹 Invoke LLM
    response = llm.invoke(prompt)
    raw_output = response.content.strip()

    try:
        return extract_json(raw_output)
    except Exception as e:
        raise ValueError(f"Invalid JSON returned from LLM: {e}")
