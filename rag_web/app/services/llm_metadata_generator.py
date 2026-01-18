import json
import requests
from pathlib import Path

from decimal import Decimal
from datetime import date, datetime


def make_json_safe(value):
    """
    Convert non-JSON-serializable values into safe representations.
    """
    if isinstance(value, Decimal):
        return float(value)  # or str(value) if precision matters
    if isinstance(value, (datetime, date)):
        return value.isoformat()
    return value


OLLAMA_API_URL = "http://localhost:11434/api/generate"
MODEL_NAME = "llama3.1:8b"

PROMPT_PATH = (
    Path(__file__).resolve().parent.parent / "prompts" / "table_metadata_prompt.txt"
)


def generate_table_metadata(table_name, columns, rows):
    prompt_template = PROMPT_PATH.read_text(encoding="utf-8")

    safe_rows = [{k: make_json_safe(v) for k, v in row.items()} for row in rows]

    evidence = {"table_name": table_name, "columns": columns, "sample_rows": safe_rows}

    prompt = prompt_template.replace("{{evidence}}", json.dumps(evidence, indent=2))

    payload = {
        "model": MODEL_NAME,
        "prompt": prompt,
        "stream": False,
    }

    print(payload)

    response = requests.post(OLLAMA_API_URL, json=payload, timeout=1800)

    if response.status_code != 200:
        raise RuntimeError(response.text)

    result = response.json()
    raw_output = result.get("response", "").strip()

    try:
        return extract_json_from_text(raw_output)
    except Exception as e:
        return {
        "error": "LLM output was not valid JSON",
        "raw_output": raw_output,
        "exception": str(e),
    }

import re
def extract_json_from_text(text: str):
    """
    Extract the first JSON object from LLM output.
    Handles markdown fences and extra text.
    """
    # Remove markdown code fences if present
    text = re.sub(r"```json|```", "", text, flags=re.IGNORECASE).strip()

    # Find first JSON object
    match = re.search(r"\{[\s\S]*\}", text)
    if not match:
        raise ValueError("No JSON object found in LLM output")

    return json.loads(match.group())