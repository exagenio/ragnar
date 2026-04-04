import json
from app.services.llm_provider import (
    get_llm,
    LLMBackend,
    ModelSize,
)
from django.conf import settings
from app.services.visual_agent import parse_visual_placeholder
from app.services.topic_content_generator import extract_json_or_fail
from app.agents.rate_limiter import rate_limiter

def generate_visual_narrative(
    *,
    content_obj,
    section_index,
    block_index,
    visual_placeholder,
    visual_spec,
    sql_result,
):
    """
    Modify existing surrounding blocks instead of generating new ones.
    Only modifies:
    - block_index - 1
    - block_index + 1
    """

    import json

    # ----------------------------------------
    # STEP 1: SAFE PARSE VISUAL
    # ----------------------------------------
    try:
        parsed = parse_visual_placeholder(visual_placeholder)
        visual_id = parsed.get("id")
        visual_type = parsed.get("type")
        visual_purpose = parsed.get("purpose")
    except Exception:
        visual_id = "unknown_visual"
        visual_type = visual_spec.get("type")
        visual_purpose = visual_spec.get("notes")
    # ----------------------------------------
    # STEP 2: EXTRACT CONTEXT BLOCKS (DYNAMIC)
    # ----------------------------------------
    sections = content_obj.content_json.get("sections", [])
    blocks = sections[section_index].get("content_blocks", [])
    context = build_context_window(blocks, block_index)
    # ----------------------------------------
    # STEP 3: INIT LLM
    # ----------------------------------------
    llm = get_llm(
        backend=LLMBackend(settings.DEFAULT_LLM_BACKEND),
        model_size=ModelSize.PRIMARY,
        temperature=0,
    )

    # ----------------------------------------
    # STEP 4: PROMPT
    # ----------------------------------------
    prompt = f"""
You are a senior business analyst.

Your task is to MODIFY existing content blocks to integrate a visual (chart/table) into the narrative.

DO NOT create new blocks.

========================
VISUAL INFORMATION
========================

Visual Type: {visual_type}
Purpose: {visual_purpose}
X Axis: {visual_spec.get("x_axis_column")}
Y Axis: {visual_spec.get("y_axis_columns")}

========================
DATA (SQL RESULT)
========================
{json.dumps(sql_result, indent=2)}

========================
CONTEXT BLOCKS
========================

Context Before (2 steps earlier):
{json.dumps(context["context_before_2"], indent=2)}

Context Before (immediately before - MODIFY THIS):
{json.dumps(context["context_before_1"], indent=2)}

Context After (immediately after - MODIFY THIS):
{json.dumps(context["context_after_1"], indent=2)}

Context After (2 steps ahead):
{json.dumps(context["context_after_2"], indent=2)}

========================
MISSING BLOCK HANDLING (CRITICAL)
========================

Some context blocks may not exist.

If a block says:
"This block is not present in the current context."

Then:

• DO NOT modify that block  
• DO NOT assume its content  
• DO NOT try to reconstruct it  

-----------------------------
SPECIAL CASE — NO BEFORE BLOCK
-----------------------------

If the BEFORE block is missing:

→ DO NOT attempt to modify it  

→ Instead:

• Add BOTH:
  - visual introduction
  - visual analysis

into the AFTER block

→ Ensure the AFTER block:
• introduces the visual  
• explains the insights  
• maintains flow  

-----------------------------
VISUAL BLOCK FILTERING
-----------------------------

If surrounding blocks were visual or SQL placeholders:

→ They are intentionally removed from context  
→ Treat them as NOT PRESENT  


========================
INSTRUCTIONS
========================

Modify ONLY:

• Context Before (immediately before)
• Context After (immediately after)

Do NOT create new blocks.

Integrate the visual naturally into the narrative:

Ensure:
   - smooth flow across all blocks
   - no repetition
   - business-focused explanation

Keep content concise and relevant

========================
ADAPTIVE BLOCK REWRITE RULE (CRITICAL)
========================

You MUST first analyze whether each block is already related to the visual.

--------------------------------
STEP 1 — DETERMINE RELEVANCE
--------------------------------

For BOTH blocks:

• Context Before (immediately before)
• Context After (immediately after)

Decide:

Is this block already discussing the SAME data, metric, or insight as the visual?

--------------------------------
STEP 2 — APPLY CORRECT STRATEGY
--------------------------------

CASE A — BLOCK IS NOT RELATED TO THE VISUAL

• DO NOT remove existing content
• DO NOT rewrite the entire block

Instead:

For BEFORE block:
- Keep existing content
- Add a new paragraph at the END to introduce the visual

For AFTER block:
- Add a new paragraph at the BEGINNING with visual insights
- Then continue with existing content

--------------------------------
CASE B — BLOCK IS ALREADY RELATED TO THE VISUAL

• This means:
  - same metric
  - same numbers
  - same entities
  - same comparison or trend

In this case:

• DO NOT duplicate content
• DO NOT append new paragraphs

Instead:

• Rewrite the ENTIRE block by:
  - integrating the visual insights
  - correcting inconsistencies
  - improving clarity and flow
  - removing repeated or redundant statements

--------------------------------
STEP 3 — REMOVE DUPLICATION (MANDATORY)
--------------------------------

You MUST:

• Remove repeated insights
• Remove repeated numbers
• Remove paraphrased duplicates
• Ensure each idea appears ONLY ONCE

--------------------------------
STEP 4 — FLOW CONSISTENCY
--------------------------------

Ensure:

• smooth transition across blocks
• no abrupt topic shifts
• consistent narrative tone

--------------------------------
STRICT RULES
--------------------------------

• NEVER delete meaningful existing content unless it is redundant
• NEVER repeat the same insight in multiple blocks
• NEVER create conflicting interpretations

• If merging:
  → produce ONE clean, non-repetitive block

• If extending:
  → preserve + add (without duplication)

REPETITION CONTROL RULE:

Before finalizing output:

• Check if the same metric or insight appears in both blocks
→ Keep it in ONLY ONE place

• Prefer:
  - BEFORE block → introduction
  - AFTER block → analysis

Remove duplicates accordingly.

========================
OUTPUT FORMAT (STRICT JSON)
========================

{{
  "updated_block_-1": {{
    "type": "...",
    "content": "..."
  }},
  "updated_block_+1": {{
    "type": "...",
    "content": "..."
  }}
}}

Return ONLY JSON
"""

    # ----------------------------------------
    # STEP 5: INVOKE
    # ----------------------------------------
    estimated_tokens = len(prompt) // 4  # rough estimate

    rate_limiter.consume(estimated_tokens)

    response = llm.invoke(prompt)

    content = response.content
    if isinstance(content, list):
        if isinstance(content[0], dict) and "text" in content[0]:
            raw_text = content[0]["text"].strip()
        else:
            raw_text = str(content[0]).strip()
    else:
        raw_text = content.strip()

    # ----------------------------------------
    # STEP 6: PARSE
    # ----------------------------------------
    try:
        result = extract_json_or_fail(raw_text)
    except Exception:
        return None

    return result

def build_context_window(blocks, block_index):
    total = len(blocks)

    def safe(idx):
        if 0 <= idx < total:
            return blocks[idx]
        return None

    # ----------------------------------------
    # STEP 1: BASE INDICES
    # ----------------------------------------
    before_1 = block_index - 1
    after_1 = block_index + 1

    before_2 = block_index - 2
    after_2 = block_index + 2

    # ----------------------------------------
    # STEP 2: HANDLE EDGE CASE (NO BEFORE)
    # ----------------------------------------
    if before_1 < 0:
        # shift forward
        before_1 = None
        before_2 = None

        after_1 = block_index + 1
        after_2 = block_index + 2
        after_3 = block_index + 3

        context = {
            "context_before_2": format_block(None),
            "context_before_1": format_block(None),
            "context_after_1": format_block(safe(after_1)),
            "context_after_2": format_block(safe(after_2)),
            "extra_after": format_block(safe(after_3)),  # NEW
        }

        return context

    # ----------------------------------------
    # STEP 3: NORMAL CASE
    # ----------------------------------------
    context = {
        "context_before_2": format_block(safe(before_2)),
        "context_before_1": format_block(safe(before_1)),
        "context_after_1": format_block(safe(after_1)),
        "context_after_2": format_block(safe(after_2)),
    }

    return context

def format_block(block):
    if block is None:
        return {
            "type": "missing",
            "content": "This block is not present in the current context."
        }


    if block.get("type") in ["visual_placeholder", "sql_placeholder"]:
        return {
            "type": "missing",
            "content": "This block is not present in the current context."
        }

    return block

def repair_content_chunk(*, blocks_chunk):

    llm = get_llm(
        backend=LLMBackend(settings.DEFAULT_LLM_BACKEND),
        model_size=ModelSize.PRIMARY,
        temperature=0,
    )

    prompt = f"""
    You are a senior business analyst.

    Your task is to IMPROVE and CORRECT analytical report content.

    ========================
    CONTENT BLOCKS (ORDERED)
    ========================

    Blocks are in exact document order.

    Each block is one of:

    1. TEXT BLOCK:
    - type: paragraph | bullet_list
    - content: text or list

    2. VISUAL BLOCK:
    - type: visual
    - visual_id
    - visual_type
    - purpose
    - data (already computed)

    {json.dumps(blocks_chunk, indent=2)}

    ========================
    OBJECTIVE
    ========================

    Improve ALL TEXT blocks by:

    1. Removing repetition
    2. Fixing incorrect or weak analysis
    3. Ensuring logical flow:
    DATA → INTERPRETATION → IMPLICATION
    4. Keeping strict relevance to the topic
    5. Improving clarity and professional tone

    ========================
    VISUAL HANDLING (CRITICAL)
    ========================

    Visual blocks MUST NOT be modified.

    Use them ONLY as context.

    Rules:

    • If a TEXT block is immediately BEFORE a visual:
    → Briefly introduce the visual at the END of that block

    • If a TEXT block is immediately AFTER a visual:
    → Start with insights derived from that visual data

    • Otherwise:
    → DO NOT mention visuals

    ========================
    CRITICAL RULES
    ========================

    DO NOT:

    - modify visual blocks
    - add new blocks
    - remove valid insights
    - hallucinate data
    - repeat the same metric multiple times

    REMOVE:

    - duplicated explanations
    - generic filler content
    - unsupported claims

    ENSURE:

    - each insight appears only once
    - all analysis is based ONLY on provided data
    - no contradiction between text and visuals

    ========================
    OUTPUT FORMAT (STRICT JSON)
    ========================

    Return ONLY updated TEXT blocks.

    [
    {{
        "block_index": int,
        "content": "updated string OR list"
    }}
    ]

    Do NOT return visual blocks.
    Do NOT return unchanged blocks.
    Return ONLY modified ones.

    Return ONLY JSON.
    """

    response = llm.invoke(prompt)

    content = response.content

    if isinstance(content, list):
        content = content[0].get("text", "")

    return extract_json_or_fail(content)