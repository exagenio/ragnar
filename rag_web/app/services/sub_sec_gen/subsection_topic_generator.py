import json
import re
from pathlib import Path
from django.conf import settings
from app.services.llm_config.llm_provider import (
    get_llm,
    LLMBackend,
    ModelSize,
)
from app.services.metadata_generation.metadata_retriever import (
    build_retrieved_context,
    retrieve_multi_table_metadata,
)


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

    metadata_context = retrieve_multi_table_metadata(
        project=project,
        primary_query=(
            f"{context.get('section_title', '')} {context.get('subsection_title', '')}"
        ),
        secondary_queries=[
            "subsection topic generation feasible analyses joins relationships measures dimensions",
        ],
        metadata_types=[
            "table_description",
            "table_relationship",
            "column",
            "column_relationship",
            "analytical_capability",
            "confidence_note",
        ],
        per_query_k=10,
        max_docs=30,
        backend=backend,
    )

    # Build prompt from template
    prompt = prompt_template

    for key, value in context.items():
        prompt = prompt.replace(f"{{{{{key}}}}}", str(value))

    # Inject retrieved context
    retrieved_context = build_retrieved_context(metadata_context)
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

