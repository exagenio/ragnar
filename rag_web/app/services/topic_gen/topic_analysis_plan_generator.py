import json
import re
from pathlib import Path
from django.conf import settings
from app.services.llm_config.llm_provider import (
    get_llm,
    LLMBackend,
    ModelSize,
)
from app.agents.rate_limiter import rate_limiter


PROMPT_PATH = settings.BASE_DIR / "app" / "prompts" / "topic_analysis_plan_prompt.txt"

SUPPORTED_VISUAL_TYPES = {
    "line_chart",
    "bar_chart",
    "pie_chart",
    "table",
    "combo_chart",
}


def extract_json_from_text(text: str) -> dict:
    """Extract json from text"""

    # Remove markdown formatting
    text = re.sub(r"```json|```", "", text, flags=re.IGNORECASE).strip()

    # Extract json object
    match = re.search(r"\{[\s\S]*\}", text)
    if not match:
        raise ValueError("No JSON object found in LLM output")

    return json.loads(match.group())


def generate_topic_analysis_plan(
    context: dict,
    *,
    project=None,
    backend: LLMBackend | None = None,
) -> dict:
    """Generate topic analysis plan"""

    backend = backend or LLMBackend(settings.DEFAULT_LLM_BACKEND)

    # Load prompt template
    prompt_template = PROMPT_PATH.read_text(encoding="utf-8")

    # Inject database schema
    prompt = prompt_template.replace(
        "{{database_schema}}",
        json.dumps(context.get("database_schema", []), indent=2),
    )

    # Replace remaining placeholders
    for key, value in context.items():
        prompt = prompt.replace(f"{{{{{key}}}}}", str(value))

    # Initialize llm
    llm = get_llm(
        backend=backend,
        model_size=ModelSize.SMALL,
        temperature=0,
        project=project,
    )

    # Apply rate limiting
    estimated_tokens = len(prompt) // 4
    rate_limiter.consume(estimated_tokens)

    # Invoke llm
    response = llm.invoke(prompt)
    content = response.content

    # Extract response text
    if isinstance(content, list):
        if isinstance(content[0], dict) and "text" in content[0]:
            raw_output = content[0]["text"].strip()
        else:
            raw_output = str(content[0]).strip()
    else:
        raw_output = content.strip()

    # Parse json output
    try:
        plan = extract_json_from_text(raw_output)
        plan = normalize_topic_analysis_plan(plan)
        return plan
    except Exception as e:
        raise ValueError(f"LLM returned invalid JSON: {e}")


def normalize_topic_analysis_plan(plan: dict) -> dict:
    """Normalize topic analysis plan fields."""

    required_elements = plan.get("required_elements", [])
    normalized_required_elements = []

    if isinstance(required_elements, list):
        for element in required_elements:
            if isinstance(element, str):
                normalized = element.strip()
            elif isinstance(element, dict):
                normalized = (
                    element.get("element")
                    or element.get("title")
                    or element.get("name")
                    or element.get("description")
                    or ""
                ).strip()
            else:
                normalized = str(element).strip()

            if normalized:
                normalized_required_elements.append(normalized)

    plan["required_elements"] = list(dict.fromkeys(normalized_required_elements))

    visuals = plan.get("visual_requirements", [])

    # Ensure visuals is a list
    if not isinstance(visuals, list):
        plan["visual_requirements"] = []
        return plan

    filtered = []

    # Filter valid visual types
    for v in visuals:

        if not isinstance(v, str):
            continue

        v = v.strip().lower()

        if v in SUPPORTED_VISUAL_TYPES:
            filtered.append(v)
        else:
            print(f"[PLAN FILTER] Removed unsupported visual type: {v}")

    # Remove duplicates
    plan["visual_requirements"] = filtered
    plan["visual_requirements"] = list(dict.fromkeys(filtered))

    return plan
