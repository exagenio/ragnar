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
from .industry_guidance import get_industry_guidance
from app.services.vector_store import get_vector_store
from app.services.subsection_topic_generator import build_retrieved_context
# ==========================
# CONFIG
# ==========================

PROMPT_PATH = (
    Path(__file__).resolve().parent.parent / "prompts" / "report_outline_prompt.txt"
)


# ==========================
# JSON EXTRACTION
# ==========================


def extract_json(text: str) -> dict:
    """
    Extract the first valid JSON object from text.
    """
    match = re.search(r"\{[\s\S]*\}", text)
    if not match:
        raise ValueError("No JSON object found in LLM response")

    return json.loads(match.group())


# ==========================
# MAIN ENTRY
# ==========================


def generate_report_outline(
    data: dict,
    *,
    project_id: int,
    backend: LLMBackend | None = None,
) -> dict:

    backend = backend or LLMBackend(settings.DEFAULT_LLM_BACKEND)

    prompt_template = PROMPT_PATH.read_text(encoding="utf-8")

    industry_guidance = get_industry_guidance(data["industry"])

    # -------------------------
    # 🔹 VECTOR RETRIEVAL (NEW)
    # -------------------------
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

    # -------------------------
    # 🔹 PROMPT BUILD
    # -------------------------
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

    # -------------------------
    # 🔹 LLM
    # -------------------------
    llm = get_llm(
        backend=backend,
        model_size=ModelSize.SMALL,
        temperature=0,
    )

    response = llm.invoke(prompt)

    content = response.content

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
