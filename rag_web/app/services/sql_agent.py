import json
import re
from typing import Dict, Any

from django.conf import settings

from app.services.llm_provider import (
    get_llm,
    LLMBackend,
    ModelSize,
)


SQL_AGENT_PROMPT_PATH = settings.BASE_DIR / "app" / "prompts" / "sql_agent_prompt.txt"

SQL_METRIC_PROMPT_PATH = settings.BASE_DIR / "app/prompts/sql_metric_prompt.txt"
SQL_VISUAL_PROMPT_PATH = settings.BASE_DIR / "app/prompts/sql_visual_prompt.txt"

# ==========================
# PUBLIC ENTRY POINT
# ==========================


def generate_sql_from_placeholder(
    *,
    sql_placeholder: Dict[str, Any],
    metadata_context: Dict,
    database_schema: Dict,
    query_intent: str = "metric",
    visual_context: Dict | None = None,
    backend: LLMBackend | None = None,
) -> Dict:
    """
    Convert a SQL_CALCULATION placeholder into an executable SQL query
    using a schema-grounded SQL agent.

    Returns a structured response:
    - status: ok | not_possible
    - sql (if ok)
    """

    backend = backend or LLMBackend(settings.DEFAULT_LLM_BACKEND)

    llm = get_llm(
        backend=backend,
        model_size=ModelSize.PRIMARY,
        temperature=0,
    )

    parsed = parse_sql_placeholder(sql_placeholder)

    prompt = _render_sql_agent_prompt(
        calculation_id=parsed["id"],
        calculation_expression=parsed["calculation"],
        calculation_description=parsed["description"],
        metadata_context=metadata_context,
        database_schema=database_schema,
        query_intent=query_intent,
        visual_context=visual_context,
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

    if query_intent == "visual" and result.get("result_type") != "table":
        raise ValueError("Visual SQL must return a table result")

    return result


# ==========================
# PROMPT RENDERING
# ==========================


def _render_sql_agent_prompt(
    *,
    calculation_id: str,
    calculation_expression: str,
    calculation_description: str,
    metadata_context: Dict,
    database_schema: Dict,
    query_intent: str,
    visual_context: Dict | None,
    visual_plan: Dict | None = None, 
) -> str:
    """
    Render SQL agent prompt using plain-text replacement.
    """

    if query_intent == "visual":
        prompt_template = SQL_VISUAL_PROMPT_PATH.read_text(encoding="utf-8")
    else:
        prompt_template = SQL_METRIC_PROMPT_PATH.read_text(encoding="utf-8")

    replacements = {
        "calculation_id": calculation_id,
        "calculation_expression": calculation_expression,
        "calculation_description": calculation_description,
        "metadata_context_json": json.dumps(metadata_context, indent=2),
        "database_schema_json": json.dumps(database_schema, indent=2),
        "query_intent": query_intent,
        "visual_x_axis_column": visual_context.get("x_axis_column", "") if visual_context else "",
        "visual_y_axis_columns": json.dumps(visual_context.get("y_axis_columns", [])) if visual_context else "",
        "visual_plan_json": json.dumps(visual_plan, indent=2) if visual_plan else "",
    }

    if query_intent == "visual" and visual_context:
        replacements.update(
            {
                "visual_type": visual_context.get("type", ""),
                "visual_purpose": visual_context.get("purpose", ""),
            }
        )
    else:
        replacements.update(
            {
                "visual_type": "",
                "visual_purpose": "",
            }
        )

    prompt = prompt_template
    for key, value in replacements.items():
        prompt = prompt.replace(f"{{{{{key}}}}}", str(value))

    return prompt


# ==========================
# JSON SAFETY
# ==========================


def _extract_json_or_fail(raw_text: str) -> Dict:
    """
    Strict JSON extraction.
    SQL agent MUST return JSON only.
    """

    if not raw_text:
        raise ValueError("SQL agent returned empty response")

    match = re.search(r"\{[\s\S]*\}", raw_text)
    if not match:
        raise ValueError(
            f"SQL agent did not return valid JSON.\nRaw output:\n{raw_text[:500]}"
        )

    return json.loads(match.group())


def parse_sql_placeholder(block: Dict[str, Any]) -> Dict[str, str]:
    """
    Extract id, calculation, description from a SQL_CALCULATION placeholder block.
    """

    raw = block.get("content", "")

    if not raw.startswith("{{SQL_CALCULATION"):
        raise ValueError("Invalid SQL_CALCULATION placeholder")

    def extract(field: str) -> str:
        match = re.search(rf"{field}\s*:\s*(.*?);", raw, re.IGNORECASE | re.DOTALL)
        if not match:
            raise ValueError(f"Missing '{field}' in SQL_CALCULATION placeholder")
        return match.group(1).strip().strip('"')

    return {
        "id": extract("id"),
        "calculation": extract("calculation"),
        "description": extract("description"),
    }


def generate_sql_from_visual_plan(
    *,
    visual_plan: Dict[str, Any],
    metadata_context: Dict,
    database_schema: Dict,
    backend: LLMBackend | None = None,
) -> Dict:
    """
    Convert a visual_plan.sql_request into an executable SQL query
    using the SAME SQL agent prompt.
    """

    backend = backend or LLMBackend(settings.DEFAULT_LLM_BACKEND)

    llm = get_llm(
        backend=backend,
        model_size=ModelSize.PRIMARY,
        temperature=0,
    )

    sql_request = visual_plan.get("sql_request")
    if not sql_request:
        raise ValueError("Visual plan missing sql_request")

    prompt = _render_sql_agent_prompt(
        calculation_id="visual_query",
        calculation_expression=sql_request.get("calculation_expression", ""),
        calculation_description=sql_request.get("description", ""),
        metadata_context=metadata_context,
        database_schema=database_schema,
        query_intent="visual",
        visual_context=visual_plan["visual_spec"],
        visual_plan=visual_plan,
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

    return _extract_json_or_fail(raw_text)
