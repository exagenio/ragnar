import json
from pathlib import Path
from langchain_ollama import ChatOllama

PROMPT_PATH = Path(__file__).parent.parent / "prompts" / "subsection_topics_prompt.txt"

llm = ChatOllama(
    model="llama3.1:8b",
    temperature=0.2,
)

import json
import re


def extract_json(text: str) -> dict:
    """
    Extract first JSON object from LLM output.
    """
    match = re.search(r"\{.*\}", text, re.DOTALL)
    if not match:
        raise ValueError("No JSON object found in LLM response")

    return json.loads(match.group(0))


def generate_subsection_topics(context):
    prompt = PROMPT_PATH.read_text()

    for key, value in context.items():
        prompt = prompt.replace(f"{{{{{key}}}}}", value)

    response = llm.invoke(prompt)
    raw_output = response.content.strip()

    try:
        return extract_json(raw_output)
    except Exception as e:
        raise ValueError(f"Invalid JSON returned from LLM: {e}")
