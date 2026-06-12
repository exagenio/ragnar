import json
import re
from typing import Dict, Any
from django.conf import settings
from app.services.llm_config.llm_provider import get_llm, LLMBackend, ModelSize
from app.agents.rate_limiter import rate_limiter


VISUAL_AGENT_PROMPT_PATH = settings.BASE_DIR / "app" / "prompts" / "visual_agent_prompt.txt"


def generate_visual_plan(
    *,
    project=None,
    visual_placeholder: Dict[str, Any],
    topic_plan: Dict[str, Any],
    retrieved_data_context: list,
    existing_visuals: list | None = None,
    backend: LLMBackend | None = None,
) -> Dict[str, Any]:
    """Generate visual plan"""

    backend = backend or LLMBackend(settings.DEFAULT_LLM_BACKEND)

    llm = get_llm(
        backend=backend,
        model_size=ModelSize.PRIMARY,
        temperature=0,
        project=project,
    )

    parsed_visual = parse_visual_placeholder(visual_placeholder)

    prompt = _render_visual_agent_prompt(
        visual_type=parsed_visual["type"],
        visual_purpose=parsed_visual["purpose"],
        topic_plan=topic_plan,
        retrieved_data_context=retrieved_data_context,
        existing_visuals=existing_visuals or [],
    )

    # Estimate tokens and apply rate limiting
    estimated_tokens = len(prompt) // 4
    rate_limiter.consume(estimated_tokens)

    # Invoke llm and extract text
    response = llm.invoke(prompt)
    raw_text = _extract_text_from_response(response.content)

    result = _extract_json_or_fail(raw_text)

    # Normalize visual spec if valid
    if result.get("status") == "ok":
        result["visual_spec"] = _normalize_visual_spec(result.get("visual_spec"))
        result["visual_data"] = _normalize_visual_data(
            result.get("visual_data"),
            result["visual_spec"],
        )

    return result


def _render_visual_agent_prompt(
    *,
    visual_type: str,
    visual_purpose: str,
    topic_plan: Dict,
    retrieved_data_context: list,
    existing_visuals: list,
) -> str:
    """Render visual agent prompt"""

    template = VISUAL_AGENT_PROMPT_PATH.read_text(encoding="utf-8")

    replacements = {
        "visual_type": visual_type,
        "visual_purpose": visual_purpose,
        "topic_plan_json": json.dumps(topic_plan, indent=2),
        "retrieved_data_context_json": json.dumps(
            retrieved_data_context,
            indent=2,
        ),
        "existing_visuals_json": json.dumps(existing_visuals, indent=2),
    }

    prompt = template

    # Replace placeholders with values
    for key, value in replacements.items():
        prompt = prompt.replace(f"{{{{{key}}}}}", str(value))

    return prompt


def parse_visual_placeholder(block: Dict[str, Any]) -> Dict[str, str]:
    """Parse visual placeholder"""

    raw = block.get("content")

    # Handle structured dictionary
    if isinstance(raw, dict):
        for field in ["id", "type", "purpose"]:
            if not raw.get(field):
                raise ValueError(f"Missing '{field}' in visual placeholder")

        return {
            "id": raw["id"],
            "type": raw["type"],
            "purpose": raw["purpose"],
        }

    # Handle string placeholder
    if not isinstance(raw, str) or not raw.strip().startswith("{{VISUAL"):
        raise ValueError("Invalid visual placeholder")

    # Extract fields using regex
    def extract(field: str) -> str:
        match = re.search(rf"{field}\s*:\s*(.*?);", raw, re.IGNORECASE | re.DOTALL)
        if not match:
            raise ValueError(f"Missing '{field}' in visual placeholder")
        return match.group(1).strip().strip('"')

    return {
        "id": extract("id"),
        "type": extract("type"),
        "purpose": extract("purpose"),
    }


def _extract_json_or_fail(raw_text: str) -> Dict[str, Any]:
    """Extract json from text"""

    if not raw_text:
        raise ValueError("Visual agent returned empty response")

    match = re.search(r"\{[\s\S]*\}", raw_text)
    if not match:
        raise ValueError(f"Invalid JSON response:\n{raw_text[:500]}")

    return json.loads(match.group())


def _normalize_visual_spec(visual_spec: Dict[str, Any]) -> Dict[str, Any]:
    """Normalize visual spec"""

    if not visual_spec:
        raise ValueError("visual_spec is missing")

    visual_type = visual_spec.get("type", "").lower()
    visual_spec["type"] = visual_type

    # Handle x axis
    x_col = visual_spec.get("x_axis_column")

    if visual_type == "table":
        visual_spec["x_axis_column"] = None
    else:
        if not isinstance(x_col, str) or not x_col.strip():
            raise ValueError("x_axis_column must be valid for charts")
        visual_spec["x_axis_column"] = x_col

    # Handle y axis columns
    y_cols = visual_spec.get("y_axis_columns")

    if isinstance(y_cols, str):
        y_cols = [y_cols]

    if not isinstance(y_cols, list) or not y_cols:
        raise ValueError("y_axis_columns must be a non-empty list")

    for col in y_cols:
        if not isinstance(col, str):
            raise ValueError("y_axis_columns must contain strings")

    visual_spec["y_axis_columns"] = y_cols

    # Set optional fields
    visual_spec.setdefault("series", None)
    visual_spec.setdefault("notes", None)

    return visual_spec


def _normalize_visual_data(
    visual_data: Dict[str, Any],
    visual_spec: Dict[str, Any],
) -> Dict[str, Any]:
    """Validate compact chart data calculated by the LLM."""

    if not isinstance(visual_data, dict):
        raise ValueError("visual_data is missing")

    columns = visual_data.get("columns")
    rows = visual_data.get("rows")

    if not isinstance(columns, list) or not columns:
        raise ValueError("visual_data.columns must be a non-empty list")
    if not all(isinstance(column, str) and column for column in columns):
        raise ValueError("visual_data.columns must contain non-empty strings")
    if not isinstance(rows, list) or not rows:
        raise ValueError("visual_data.rows must be a non-empty list")
    if len(rows) > 20:
        raise ValueError("visual_data must not contain more than 20 rows")

    normalized_rows = []
    for row in rows:
        if isinstance(row, dict):
            normalized_rows.append([row.get(column) for column in columns])
        elif isinstance(row, list) and len(row) == len(columns):
            normalized_rows.append(row)
        else:
            raise ValueError(
                "Each visual_data row must match the declared columns"
            )

    required_columns = set(visual_spec.get("y_axis_columns", []))
    x_axis = visual_spec.get("x_axis_column")
    if x_axis:
        required_columns.add(x_axis)

    missing_columns = required_columns.difference(columns)
    if missing_columns:
        raise ValueError(
            "visual_data is missing visual columns: "
            + ", ".join(sorted(missing_columns))
        )

    if visual_spec.get("type") != "table":
        for y_column in visual_spec.get("y_axis_columns", []):
            y_index = columns.index(y_column)
            if not all(
                isinstance(row[y_index], (int, float))
                and not isinstance(row[y_index], bool)
                for row in normalized_rows
            ):
                raise ValueError(
                    f"visual_data column '{y_column}' must contain numeric values"
                )

    return {
        "columns": columns,
        "rows": normalized_rows,
    }


def _extract_text_from_response(content):
    """Extract text from llm response"""

    if isinstance(content, list):
        first = content[0]

        if isinstance(first, dict) and "text" in first:
            return first["text"].strip()

        return str(first).strip()

    return content.strip()
