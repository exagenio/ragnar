import json
import requests
from pathlib import Path

from .industry_guidance import get_industry_guidance

OLLAMA_API_URL = "http://localhost:11434/api/generate"
MODEL_NAME = "llama3.1:8b"

PROMPT_PATH = (
    Path(__file__).resolve().parent.parent / "prompts" / "report_outline_prompt.txt"
)

import re


def extract_json(text: str) -> dict:
    """
    Extract the first valid JSON object from text.
    """
    match = re.search(r"\{.*\}", text, re.DOTALL)
    if not match:
        raise ValueError("No JSON object found in LLM response")

    json_text = match.group(0)
    return json.loads(json_text)



def generate_report_outline(data: dict) -> dict:
    prompt_template = PROMPT_PATH.read_text(encoding="utf-8")

    industry_guidance = get_industry_guidance(data["industry"])

    prompt = prompt_template.format(
        industry=data["industry"],
        report_type=data["report_type"],
        audience=data["audience"],
        purpose=data["purpose"],
        focus_areas=data.get("focus_areas", ""),
        additional_notes=data.get("additional_notes", ""),
        industry_guidance=industry_guidance,
    )

    payload = {
        "model": MODEL_NAME,
        "prompt": prompt,
        "stream": False,
        "options": {
            "temperature": 0
        }
    }

    response = requests.post(OLLAMA_API_URL, json=payload, timeout=300)

    if response.status_code != 200:
        raise RuntimeError(response.text)

    raw_output = response.json().get("response", "").strip()

    try:
        return extract_json(raw_output)
    except Exception as e:
        raise ValueError(f"LLM returned invalid JSON: {e}")

