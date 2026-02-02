import json
from pathlib import Path
from typing import Dict, Any

from django.conf import settings

from app.services.llm_provider import (
    get_llm,
    LLMBackend,
    ModelSize,
)
from decimal import Decimal

PROMPT_PATH = (settings.BASE_DIR/ "app"/ "prompts"/ "sql_result_interpretation_prompt.txt")


def interpret_sql_result(
    *,
    draft_paragraph: str,
    computed_result: Dict[str, Any],
    backend: LLMBackend | None = None,
) -> str:
    """
    Integrate a computed SQL result into an existing paragraph
    using an LLM-based interpretation step.

    `computed_result` is expected to be the output of sql_executor:
    {
        "status": "ok",
        "result": <scalar | table>,
        "row_count": int
    }
    """

    if not draft_paragraph.strip():
        raise ValueError("Draft paragraph is empty")

    if computed_result.get("status") != "ok":
        raise ValueError("SQL result is not successful")

    if "result" not in computed_result:
        raise ValueError("Invalid computed_result structure")

    backend = backend or LLMBackend(settings.DEFAULT_LLM_BACKEND)

    llm = get_llm(
        backend=backend,
        model_size=ModelSize.SMALL,  # interpretation ≠ heavy reasoning
        temperature=0.1,
    )

    prompt = _render_prompt(
        draft_paragraph=draft_paragraph,
        computed_value=_format_value(computed_result["result"]),
    )

    response = llm.invoke(prompt)
    text = response.content.strip()

    if not text:
        raise ValueError("LLM returned empty interpretation")

    return text


# ==========================
# HELPERS
# ==========================

def _render_prompt(
    *,
    draft_paragraph: str,
    computed_value: str,
) -> str:
    """
    Render the interpretation prompt.
    """

    template = PROMPT_PATH.read_text(encoding="utf-8")

    replacements = {
        "draft_paragraph": draft_paragraph,
        "computed_value": computed_value,
    }

    prompt = template
    for key, value in replacements.items():
        prompt = prompt.replace(f"{{{{{key}}}}}", str(value))

    return prompt


def _format_value(value: Any) -> str:
    """
    Normalize SQL results into LLM-friendly text.
    Safely handles:
    - Decimal
    - int / float
    - scalar
    - table results (dict)
    - row tuples / lists
    """

    # Decimal → float string
    if isinstance(value, Decimal):
        return f"{round(float(value), 2)}"

    # Numeric scalar
    if isinstance(value, (int, float)):
        return f"{round(value, 2)}"

    # Table result (columns + rows)
    if isinstance(value, dict):
        return json.dumps(value, indent=2, default=str)

    # Row or list result
    if isinstance(value, (list, tuple)):
        return json.dumps(value, indent=2, default=str)

    # Fallback (safe)
    return str(value)