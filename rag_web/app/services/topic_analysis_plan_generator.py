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
from app.agents.rate_limiter import rate_limiter

# ==========================
# CONFIG
# ==========================

PROMPT_PATH = (
    Path(__file__).resolve().parent.parent / "prompts" / "topic_analysis_plan_prompt.txt"
)

SUPPORTED_VISUAL_TYPES = {
    "line_chart",
    "bar_chart",
    "pie_chart",
    "table",
    "combo_chart",
}


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
    estimated_tokens = len(prompt) // 4  # rough estimate

    rate_limiter.consume(estimated_tokens)

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
        plan = extract_json_from_text(raw_output)
        return plan
    except Exception as e:
        raise ValueError(f"LLM returned invalid JSON: {e}")


def normalize_topic_analysis_plan(plan: dict) -> dict:
    """
    Ensure the analysis plan only contains supported visual types.
    Remove invalid visuals automatically.
    """

    visuals = plan.get("visual_requirements", [])

    if not isinstance(visuals, list):
        plan["visual_requirements"] = []
        return plan

    filtered = []

    for v in visuals:

        if not isinstance(v, str):
            continue

        v = v.strip().lower()

        if v in SUPPORTED_VISUAL_TYPES:
            filtered.append(v)
        else:
            print(f"[PLAN FILTER] Removed unsupported visual type: {v}")

    plan["visual_requirements"] = filtered
    plan["visual_requirements"] = list(dict.fromkeys(filtered))
    return plan