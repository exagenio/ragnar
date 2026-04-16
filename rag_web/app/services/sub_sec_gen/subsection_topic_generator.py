import json
import re
from pathlib import Path
from collections import defaultdict
from django.conf import settings
from app.services.llm_config.llm_provider import (
    get_llm,
    LLMBackend,
    ModelSize,
)
from ..vector_db_config.vector_store import get_vector_store


PROMPT_PATH = settings.BASE_DIR / "app" / "prompts" / "subsection_topics_prompt.txt"


def extract_json(text: str) -> dict:
    """Extract json from text"""

    # Extract json object from text
    match = re.search(r"\{[\s\S]*\}", text)
    if not match:
        raise ValueError("No JSON object found in LLM response")

    return json.loads(match.group())


def generate_subsection_topics(
    *,
    context: dict,
    project=None,
    project_id: int,
    backend: LLMBackend | None = None,
) -> dict:
    """Generate subsection topics"""

    backend = backend or LLMBackend(settings.DEFAULT_LLM_BACKEND)

    prompt_template = PROMPT_PATH.read_text(encoding="utf-8")

    # Retrieve relevant documents from vector store
    vector_store = get_vector_store(backend=backend)
    docs = vector_store.similarity_search(
        query=f"{context.get('section_title', '')} {context.get('subsection_title', '')}",
        k=50,
        filter={
            "project_id": project_id,
            "type": ["table_description", "column", "analytical_capability", "confidence_note"],
        },
    )

    # Build prompt from template
    prompt = prompt_template

    for key, value in context.items():
        prompt = prompt.replace(f"{{{{{key}}}}}", str(value))

    # Inject retrieved context
    retrieved_context = build_retrieved_context(docs)
    prompt = prompt.replace("{{retrieved_context}}", retrieved_context)
    
    # Initialize llm
    llm = get_llm(
        backend=backend,
        model_size=ModelSize.SMALL,
        temperature=0.2,
        project=project,
    )

    # Invoke llm
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

    # Extract json output
    try:
        return extract_json(raw_output)
    except Exception as e:
        raise ValueError(f"Invalid JSON returned from LLM: {e}")


def build_retrieved_context(docs) -> str:
    """Build retrieved context"""

    # Group documents by table
    grouped = defaultdict(list)

    for doc in docs:
        table = doc.metadata.get("table_name", "unknown_table")
        grouped[table].append(doc)

    output = []

    # Format grouped context
    for table, table_docs in grouped.items():
        output.append(f"### Table: {table}")

        for doc in table_docs:
            meta = doc.metadata
            output.append(f"- Type: {meta.get('type')}")
            if "column" in meta:
                output.append(f"  Column: {meta['column']}")
            output.append(f"  {doc.page_content}")

    return "\n".join(output)
