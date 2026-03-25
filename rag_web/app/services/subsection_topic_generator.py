import json
import re
from pathlib import Path
from collections import defaultdict

from django.conf import settings

from app.services.llm_provider import (
    get_llm,
    LLMBackend,
    ModelSize,
)
from app.services.llm_provider import get_embeddings
from .vector_store import get_vector_store

# ==========================
# CONFIG
# ==========================

PROMPT_PATH = (
    Path(__file__).resolve().parent.parent / "prompts" / "subsection_topics_prompt.txt"
)


# ==========================
# JSON EXTRACTION
# ==========================

def extract_json(text: str) -> dict:
    """
    Extract the first valid JSON object from LLM output.
    """
    match = re.search(r"\{[\s\S]*\}", text)
    if not match:
        raise ValueError("No JSON object found in LLM response")

    return json.loads(match.group())


# ==========================
# MAIN ENTRY
# ==========================

def generate_subsection_topics(
    *,
    context: dict,
    project_id: int,
    backend: LLMBackend | None = None,
) -> dict:

    """
    Generate subsection-level topics using the unified LLM provider.
    """

    backend = backend or LLMBackend(settings.DEFAULT_LLM_BACKEND)

    prompt_template = PROMPT_PATH.read_text(encoding="utf-8")

    vector_store = get_vector_store(backend=backend)
    docs = vector_store.similarity_search(
        query="database schema and analytical capabilities",
        k=50,
        filter={
            "project_id": project_id,
            "type": ["table_description", "column", "analytical_capability", "confidence_note"],
        },
    )

    prompt = prompt_template

    for key, value in context.items():
        prompt = prompt.replace(f"{{{{{key}}}}}", str(value))

    retrieved_context = build_retrieved_context(docs)
    prompt = prompt.replace("{{retrieved_context}}", retrieved_context)
    
    # 🔹 Get LLM from provider
    llm = get_llm(
        backend=backend,
        model_size=ModelSize.PRIMARY,  # topic structure needs quality
        temperature=0.2,
    )

    # 🔹 Invoke LLM
    response = llm.invoke(prompt)
    content = response.content

    if isinstance(content, list):
        # LangChain structured output
        if isinstance(content[0], dict) and "text" in content[0]:
         raw_output = content[0]["text"].strip()
        else:
            raw_output = str(content[0]).strip()
    else:
        raw_output = content.strip()

    try:
        return extract_json(raw_output)
    except Exception as e:
        raise ValueError(f"Invalid JSON returned from LLM: {e}")


def build_retrieved_context(docs) -> str:
    grouped = defaultdict(list)

    for doc in docs:
        table = doc.metadata.get("table_name", "unknown_table")
        grouped[table].append(doc)

    output = []

    for table, table_docs in grouped.items():
        output.append(f"### Table: {table}")

        for doc in table_docs:
            meta = doc.metadata
            output.append(f"- Type: {meta.get('type')}")
            if "column" in meta:
                output.append(f"  Column: {meta['column']}")
            output.append(f"  {doc.page_content}")

    return "\n".join(output)
