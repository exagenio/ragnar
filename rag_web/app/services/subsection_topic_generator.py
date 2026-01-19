import json
from pathlib import Path
from langchain_ollama import ChatOllama

PROMPT_PATH = Path(__file__).parent.parent / "prompts" / "subsection_topics_prompt.txt"

llm = ChatOllama(
    model="llama3.1:8b",
    temperature=0.2,
)

def generate_subsection_topics(context):
    prompt = PROMPT_PATH.read_text()

    for key, value in context.items():
        prompt = prompt.replace(f"{{{{{key}}}}}", value)

    response = llm.invoke(prompt)
    content = response.content.strip()

    try:
        return json.loads(content)
    except json.JSONDecodeError:
        raise ValueError("Invalid JSON returned from LLM")
