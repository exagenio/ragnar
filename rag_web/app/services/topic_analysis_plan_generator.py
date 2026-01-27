import json
from pathlib import Path
import requests
import re


PROMPT_PATH = (
    Path(__file__).resolve().parent.parent / "prompts" / "topic_analysis_plan_prompt.txt"
)
OLLAMA_URL = "http://localhost:11434/api/generate"
MODEL = "llama3.1:8b"


def generate_topic_analysis_plan(context: dict) -> dict:
    prompt_template = PROMPT_PATH.read_text(encoding="utf-8")

    prompt = prompt_template.replace(
        "{{database_schema}}",
        json.dumps(context["database_schema"], indent=2)
    )

    for key, value in context.items():
        if key != "database_schema":
            prompt = prompt.replace(f"{{{{{key}}}}}", str(value))

    payload = {
        "model": MODEL,
        "prompt": prompt,
        "stream": False,
        "options": {
            "temperature": 0
        }
    }

    response = requests.post(OLLAMA_URL, json=payload, timeout=300)
    response.raise_for_status()

    raw = response.json().get("response", "").strip()
    print(raw)
    final = extract_json_from_text(raw)
    print("json output")
    print(final)
    return final


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