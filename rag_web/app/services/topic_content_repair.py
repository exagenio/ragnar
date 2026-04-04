import json
import re
from typing import Dict, Any
from pathlib import Path

from django.conf import settings

from app.services.llm_provider import (
    get_llm,
    LLMBackend,
    ModelSize,
)
from app.agents.rate_limiter import rate_limiter


REPAIR_PROMPT_PATH = settings.BASE_DIR / "app" / "prompts" / "topic_content_repair_prompt.txt"

def repair_topic_content(
    *,
    industry,
    report_type,
    audience,
    purpose,
    section_title,
    subsection_title,
    topic_title,
    topic_plan,
    content_json,
):

    backend = LLMBackend(settings.DEFAULT_LLM_BACKEND)

    llm = get_llm(
        backend=backend,
        model_size=ModelSize.PRIMARY,
        temperature=0,
    )

    repair_windows = find_repair_windows(content_json)

    if not repair_windows:
        return content_json

    sections = content_json["sections"]

    for window in repair_windows:

        s_idx = window["section_index"]
        start = window["window_start"]
        end = window["window_end"]

        original_blocks = window["window_blocks"]

        prompt = render_prompt(
            REPAIR_PROMPT_PATH,
            {
                "industry": industry,
                "report_type": report_type,
                "audience": audience,
                "purpose": purpose,
                "section_title": section_title,
                "subsection_title": subsection_title,
                "topic_title": topic_title,
                "topic_plan_json": json.dumps(topic_plan, indent=2),
                "content_window": json.dumps(original_blocks, indent=2),
                "limitations": json.dumps(content_json.get("limitations", []), indent=2),
                "completed_elements": json.dumps(
                    content_json.get("completed_elements", []),
                    indent=2,
                ),
            },
        )

        estimated_tokens = len(prompt) // 4  # rough estimate

        rate_limiter.consume(estimated_tokens)

        response = llm.invoke(prompt)

        repaired = extract_json_or_fail(response.content)

        repaired_blocks = repaired.get("content_blocks")

        if repaired_blocks:

            sections[s_idx]["content_blocks"][start:end] = repaired_blocks

    return content_json

def render_prompt(prompt_path: Path, context: dict) -> str:
    prompt = prompt_path.read_text(encoding="utf-8")
    for key, value in context.items():
        prompt = prompt.replace(f"{{{{{key}}}}}", str(value))
    return prompt

def extract_json_or_fail(raw_text: str) -> dict:
    if not raw_text:
        raise ValueError("LLM returned empty response")

    match = re.search(r"\{[\s\S]*\}", raw_text)
    if not match:
        raise ValueError(f"LLM did not return JSON:\n{raw_text[:500]}")

    return json.loads(match.group())


def find_repair_windows(content_json: dict):
    windows = []

    sections = content_json.get("sections", [])

    for s_idx, section in enumerate(sections):

        blocks = section.get("content_blocks", [])

        for b_idx, block in enumerate(blocks):

            if block.get("type") != "removed_placeholder":
                continue

            start = max(0, b_idx - 2)
            end = min(len(blocks), b_idx + 2)

            windows.append(
                {
                    "section_index": s_idx,
                    "block_index": b_idx,
                    "window_blocks": blocks[start:end],
                    "window_start": start,
                    "window_end": end,
                }
            )

    return windows