import json
import re
from typing import Dict, Any

from django.conf import settings

from app.services.llm_provider import (
    get_llm,
    LLMBackend,
    ModelSize,
)


SQL_AGENT_PROMPT_PATH = (
    settings.BASE_DIR / "app" / "prompts" / "sql_agent_prompt.txt"
)


# ==========================
# PUBLIC ENTRY POINT
# ==========================

def generate_sql_from_placeholder(
    *,
    sql_placeholder: Dict[str, Any],
    metadata_context: Dict,
    database_schema: Dict,
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
    )

    response = llm.invoke(prompt)
    raw_text = response.content.strip()

    return _extract_json_or_fail(raw_text)


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
) -> str:
    """
    Render SQL agent prompt using plain-text replacement.
    """

    prompt_template = SQL_AGENT_PROMPT_PATH.read_text(encoding="utf-8")

    replacements = {
        "calculation_id": calculation_id,
        "calculation_expression": calculation_expression,
        "calculation_description": calculation_description,
        "metadata_context_json": json.dumps(metadata_context, indent=2),
        "database_schema_json": json.dumps(database_schema, indent=2),
    }

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

