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
    draft_content: str | list[str],
    computed_result: Dict[str, Any],
    backend: LLMBackend | None = None,
) -> str | list[str]:
    """
    Integrate a computed SQL result into existing content (paragraph or bullet list)
    using an LLM-based interpretation step.

    `draft_content` can be:
    - str: A paragraph of text
    - list[str]: A bullet list (list of bullet points)

    `computed_result` is expected to be the output of sql_executor:
    {
        "status": "ok",
        "result": <scalar | table>,
        "row_count": int
    }

    Returns:
    - str if input was a string (paragraph)
    - list[str] if input was a list (bullet list)
    """

    # Track original type for return value
    is_bullet_list = isinstance(draft_content, list)

    # Validate content
    if is_bullet_list:
        if not draft_content or not any(item.strip() for item in draft_content):
            raise ValueError("Draft content is empty")
        # Convert list to bullet format for LLM
        draft_text = _list_to_bullets(draft_content)
    else:
        if not draft_content.strip():
            raise ValueError("Draft content is empty")
        draft_text = draft_content

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
        draft_content=draft_text,
        computed_value=_format_value(computed_result["result"]),
    )

    response = llm.invoke(prompt)
    text = response.content.strip()

    if not text:
        raise ValueError("LLM returned empty interpretation")

    # Convert back to list if original was a bullet list
    if is_bullet_list:
        return _bullets_to_list(text)

    return text


# ==========================
# HELPERS
# ==========================

def _list_to_bullets(items: list[str]) -> str:
    """
    Convert a list of strings to bullet-formatted text.

    Example:
        ["First point", "Second point"] → "- First point\n- Second point"
    """
    return "\n".join(f"- {item.strip()}" for item in items if item.strip())


def _bullets_to_list(text: str) -> list[str]:
    """
    Convert bullet-formatted text back to a list of strings.
    Handles various bullet formats: -, *, •, numbered lists, etc.

    Example:
        "- First point\n- Second point" → ["First point", "Second point"]
    """
    lines = text.strip().split("\n")
    items = []

    for line in lines:
        line = line.strip()
        if not line:
            continue

        # Remove common bullet markers
        # Supports: -, *, •, numbered lists (1., 2.), etc.
        if line.startswith(("- ", "* ", "• ")):
            items.append(line[2:].strip())
        elif line[0].isdigit() and ". " in line[:4]:
            # Handle numbered lists like "1. Item"
            items.append(line.split(". ", 1)[1].strip())
        else:
            # If no bullet marker found, keep the line as-is
            items.append(line)

    return items


def _render_prompt(
    *,
    draft_content: str,
    computed_value: str,
) -> str:
    """
    Render the interpretation prompt.
    """

    template = PROMPT_PATH.read_text(encoding="utf-8")

    replacements = {
        "draft_content": draft_content,
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