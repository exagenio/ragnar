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
from .industry_guidance import get_industry_guidance
from app.services.vector_db_config.vector_store import get_vector_store
from app.services.sub_sec_gen.subsection_topic_generator import build_retrieved_context


PROMPT_PATH = settings.BASE_DIR / "app" / "prompts" / "report_outline_prompt.txt"


def extract_json(text: str) -> dict:
    """Extract json from text"""

    # Extract json object from text
    match = re.search(r"\{[\s\S]*\}", text)
    if not match:
        raise ValueError("No JSON object found in LLM response")

    return json.loads(match.group())


def generate_report_outline(
    data: dict,
    *,
    project=None,
    project_id: int,
    backend: LLMBackend | None = None,
) -> dict:
    """Generate report outline"""

    backend = backend or LLMBackend(settings.DEFAULT_LLM_BACKEND)

    prompt_template = PROMPT_PATH.read_text(encoding="utf-8")

    # Get industry guidance
    industry_guidance = get_industry_guidance(data["industry"])

    # Retrieve schema context using vector search
    vector_store = get_vector_store(backend=backend)

    docs = vector_store.similarity_search(
        query="full database schema tables columns analytical capabilities",
        k=50,
        filter={
            "project_id": project_id,
            "type": [
                "table_description",
                "column",
                "analytical_capability",
                "confidence_note",
            ],
        },
    )

    print(docs)

    retrieved_context = build_retrieved_context(docs)

    # Build prompt with placeholders
    prompt = prompt_template.format_map(
        defaultdict(
            str,
            {
                "industry": data["industry"],
                "report_type": data["report_type"],
                "audience": data["audience"],
                "purpose": data["purpose"],
                "focus_areas": data.get("focus_areas", ""),
                "additional_notes": data.get("additional_notes", ""),
                "industry_guidance": industry_guidance,
            },
        )
    )

    prompt = prompt.replace("{{retrieved_context}}", retrieved_context)

    # Initialize llm and generate response
    llm = get_llm(
        backend=backend,
        model_size=ModelSize.SMALL,
        temperature=0,
        project=project,
    )

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
        return extract_json(raw_output)
    except Exception as e:
        raise ValueError(f"LLM returned invalid JSON: {e}")
