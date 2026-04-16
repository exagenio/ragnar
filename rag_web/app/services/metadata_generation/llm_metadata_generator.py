# Standard library imports
import json
import re
from pathlib import Path
from decimal import Decimal
from datetime import date, datetime

# Third-party imports
from django.conf import settings

# Local imports
from app.services.llm_config.llm_provider import (
    get_llm,
    LLMBackend,
    ModelSize,
)
from app.agents.rate_limiter import rate_limiter


PROMPT_PATH = (
    Path(__file__).resolve().parent.parent / "prompts" / "table_metadata_prompt.txt"
)


def make_json_safe(value):
    """Make json safe"""

    # Convert special types to json serializable values
    if isinstance(value, Decimal):
        return float(value)
    if isinstance(value, (datetime, date)):
        return value.isoformat()
    return value


def extract_json_from_text(text: str):
    """Extract json from text"""

    # Clean markdown and extract json
    text = re.sub(r"```json|```", "", text, flags=re.IGNORECASE).strip()

    match = re.search(r"\{[\s\S]*\}", text)
    if not match:
        raise ValueError("No JSON object found in LLM output")

    return json.loads(match.group())


def generate_table_metadata(
    *,
    table_name: str,
    columns: list,
    rows: list,
    backend: LLMBackend | None = None,
):
    """Generate table metadata"""

    backend = backend or LLMBackend(settings.DEFAULT_LLM_BACKEND)

    # Load prompt template
    prompt_template = PROMPT_PATH.read_text(encoding="utf-8")

    # Convert rows to json safe format
    safe_rows = [{k: make_json_safe(v) for k, v in row.items()} for row in rows]

    # Build prompt with replacements
    prompt = prompt_template
    prompt = prompt.replace("{{table_name}}", table_name)
    prompt = prompt.replace("{{columns}}", json.dumps(columns, indent=2))
    prompt = prompt.replace("{{rows}}", json.dumps(safe_rows, indent=2))

    # Initialize llm
    llm = get_llm(
        backend=backend,
        model_size=ModelSize.SMALL,
        temperature=0,
    )

    # Apply rate limiting
    estimated_tokens = len(prompt) // 4
    rate_limiter.consume(estimated_tokens)

    # Invoke llm and extract response
    response = llm.invoke(prompt)

    content = response.content

    # Handle structured and plain responses
    if isinstance(content, list):
        if isinstance(content[0], dict) and "text" in content[0]:
            raw_output = content[0]["text"].strip()
        else:
            raw_output = str(content[0]).strip()
    else:
        raw_output = content.strip()

    try:
        return extract_json_from_text(raw_output)
    except Exception as e:
        return {
            "error": "LLM output was not valid JSON",
            "raw_output": raw_output,
            "exception": str(e),
        }