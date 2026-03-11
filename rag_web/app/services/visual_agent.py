# app/services/visual_agent.py

import json
import re
from typing import Dict, Any

from django.conf import settings

from app.services.llm_provider import (
    get_llm,
    LLMBackend,
    ModelSize,
)

VISUAL_AGENT_PROMPT_PATH = (
    settings.BASE_DIR / "app" / "prompts" / "visual_agent_prompt.txt"
)


# ==========================
# PUBLIC ENTRY POINT
# ==========================

def generate_visual_plan(
    *,
    visual_placeholder: Dict[str, Any],
    topic_plan: Dict[str, Any],
    metadata_context: Dict,
    database_schema: Dict,
    backend: LLMBackend | None = None,
) -> Dict[str, Any]:
    """
    Generate a visual plan + SQL intent for a visual placeholder.

    Returns structured JSON:
    - status: ok | not_possible
    - sql_request
    - visual_spec
    """

    backend = backend or LLMBackend(settings.DEFAULT_LLM_BACKEND)

    llm = get_llm(
        backend=backend,
        model_size=ModelSize.PRIMARY,  # needs reasoning
        temperature=0,
    )

    parsed_visual = parse_visual_placeholder(visual_placeholder)

    prompt = _render_visual_agent_prompt(
        visual_type=parsed_visual["type"],
        visual_purpose=parsed_visual["purpose"],
        topic_plan=topic_plan,
        metadata_context=metadata_context,
        database_schema=database_schema,
    )

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

    result = _extract_json_or_fail(raw_text)

    if result.get("status") == "ok":
        result["visual_spec"] = _normalize_visual_spec(result["visual_spec"])

    return result



# ==========================
# PROMPT RENDERING
# ==========================

def _render_visual_agent_prompt(
    *,
    visual_type: str,
    visual_purpose: str,
    topic_plan: Dict,
    metadata_context: Dict,
    database_schema: Dict,
) -> str:
    """
    Render Visual Agent prompt safely.
    """

    template = VISUAL_AGENT_PROMPT_PATH.read_text(encoding="utf-8")

    replacements = {
        "visual_type": visual_type,
        "visual_purpose": visual_purpose,
        "topic_plan_json": json.dumps(topic_plan, indent=2),
        "metadata_context_json": json.dumps(metadata_context, indent=2),
        "database_schema_json": json.dumps(database_schema, indent=2),
    }

    prompt = template
    for key, value in replacements.items():
        prompt = prompt.replace(f"{{{{{key}}}}}", str(value))

    return prompt


# ==========================
# PARSING
# ==========================

def parse_visual_placeholder(block: Dict[str, Any]) -> Dict[str, str]:
    """
    Extract type & purpose from VISUAL placeholder block.
    """

    raw = block.get("content")

    # Content may already be parsed / structured
    if isinstance(raw, dict):
        if not raw.get("type") or not raw.get("purpose"):
            raise ValueError("Structured VISUAL placeholder missing type or purpose")

        return {
            "type": raw["type"],
            "purpose": raw["purpose"],
        }

    if not isinstance(raw, str) or not raw.strip().startswith("{{VISUAL"):
        raise ValueError("Invalid VISUAL placeholder")


    def extract(field: str) -> str:
        match = re.search(rf"{field}\s*:\s*(.*?);", raw, re.IGNORECASE | re.DOTALL)
        if not match:
            raise ValueError(f"Missing '{field}' in VISUAL placeholder")
        return match.group(1).strip().strip('"')

    return {
        "type": extract("type"),
        "purpose": extract("purpose"),
    }


# ==========================
# JSON SAFETY
# ==========================

def _extract_json_or_fail(raw_text: str) -> Dict[str, Any]:
    """
    Visual agent MUST return JSON only.
    """

    if not raw_text:
        raise ValueError("Visual agent returned empty response")

    match = re.search(r"\{[\s\S]*\}", raw_text)
    if not match:
        raise ValueError(
            f"Visual agent did not return valid JSON.\nRaw output:\n{raw_text[:500]}"
        )

    return json.loads(match.group())

def _normalize_visual_spec(visual_spec: Dict[str, Any]) -> Dict[str, Any]:
    """
    Normalize visual_spec to a strict, renderer-safe schema.
    Handles different requirements for tables vs charts.
    """

    if not visual_spec:
        raise ValueError("visual_spec is missing")

    # Get visual type
    visual_type = visual_spec.get("type", "").lower()

    # ---- Normalize x-axis (only required for charts, not tables) ----
    x_col = visual_spec.get("x_axis_column")

    if visual_type == "table":
        # Tables don't need x_axis_column
        visual_spec["x_axis_column"] = None
    else:
        # Charts require x_axis_column
        if not isinstance(x_col, str) or not x_col.strip():
            raise ValueError("x_axis_column must be a non-empty string for chart types")
        visual_spec["x_axis_column"] = x_col

    # ---- Normalize y-axes / columns ----
    y_cols = visual_spec.get("y_axis_columns")

    if isinstance(y_cols, str):
        y_cols = [y_cols]

    if not isinstance(y_cols, list) or not y_cols:
        raise ValueError("y_axis_columns must be a non-empty list")

    for c in y_cols:
        if not isinstance(c, str):
            raise ValueError("Each y_axis_columns item must be a string")

    visual_spec["y_axis_columns"] = y_cols

    # Optional fields safety
    visual_spec.setdefault("series", None)
    visual_spec.setdefault("notes", None)

    return visual_spec

