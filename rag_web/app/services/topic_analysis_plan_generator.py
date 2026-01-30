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
    Path(__file__).resolve().parent.parent / "prompts" / "topic_analysis_plan_prompt.txt"
)


# ==========================
# JSON EXTRACTION
# ==========================

def extract_json_from_text(text: str) -> dict:
    """
    Extract the first JSON object from LLM output.
    Handles markdown fences and extra text.
    """
    text = re.sub(r"```json|```", "", text, flags=re.IGNORECASE).strip()

    match = re.search(r"\{[\s\S]*\}", text)
    if not match:
        raise ValueError("No JSON object found in LLM output")

    return json.loads(match.group())


# ==========================
# MAIN ENTRY
# ==========================

def generate_topic_analysis_plan(
    context: dict,
    *,
    backend: LLMBackend | None = None,
) -> dict:
    """
    Generate a Topic Analysis Plan using unified LLM provider.
    """

    backend = backend or LLMBackend(settings.DEFAULT_LLM_BACKEND)

    prompt_template = PROMPT_PATH.read_text(encoding="utf-8")

    # 🔹 Inject database schema first (JSON block)
    prompt = prompt_template.replace(
        "{{database_schema}}",
        json.dumps(context.get("database_schema", []), indent=2),
    )

    # 🔹 Safe placeholder replacement for remaining fields
    for key, value in context.items():
            prompt = prompt.replace(f"{{{{{key}}}}}", str(value))

    # 🔹 Get LLM
    llm = get_llm(
        backend=backend,
        model_size=ModelSize.PRIMARY,  # analysis planning = quality > speed
        temperature=0,
    )

    # 🔹 Invoke model
    response = llm.invoke(prompt)
    raw_output = response.content.strip()

    try:
        return extract_json_from_text(raw_output)
    except Exception as e:
        raise ValueError(f"LLM returned invalid JSON: {e}")
