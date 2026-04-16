import json
import re
from django.conf import settings
from app.services.llm_config.llm_provider import get_llm, LLMBackend, ModelSize


def interpret_sql_result(
    *,
    project=None,
    placeholders: list,
    backend: LLMBackend | None = None,
):
    """Interpret sql result"""

    backend = backend or LLMBackend(settings.DEFAULT_LLM_BACKEND)

    llm = get_llm(
        backend=backend,
        model_size=ModelSize.SMALL,
        temperature=0,
        project=project,
    )

    # Build prompt from placeholders
    prompt = _build_prompt(placeholders)

    # Invoke llm and extract response
    response = llm.invoke(prompt)
    content = response.content
    print(response)

    # Handle structured and plain responses
    if isinstance(content, list):
        raw = content[0].get("text", "").strip()
    else:
        raw = content.strip()

    return _extract_json(raw)


def _build_prompt(placeholders):
    """Build prompt"""

    # Process placeholders and normalize results
    cleaned = []

    for p in placeholders:
        content = p.get("content", {}).copy()
        q = content.get("query", {})

        if q.get("status") != "ok":
            continue

        content.pop("id", None)

        result = q.get("result")

        # normalize scalar
        if not isinstance(result, dict):
            content["query"]["result"] = {
                "type": "scalar",
                "value": result
            }

        # limit large tables
        if isinstance(result, dict) and "rows" in result:
            content["query"]["result"]["rows"] = result["rows"][:30]

        cleaned.append({
            "id": p.get("content", {}).get("id"),
            "content": content
        })

    # Return prompt string
    return f"""
You are a senior data analyst.

Your task is to analyze SQL query results and generate concise,
accurate, and business-relevant insights.

INPUT:
{json.dumps(cleaned, indent=2)}

Each item contains:

• calculation → business metric definition  
• description → explanation of the metric  
• query → executed SQL and its result  

========================
CORE RULES
========================

You MUST:

• Use ONLY the provided data  
• NOT recalculate or derive new metrics  
• NOT assume missing values  
• NOT generalize beyond the data  

All insights MUST be directly supported by the input.

========================
ANALYSIS GUIDELINES
========================

Interpret the result based on its structure:

1. SCALAR RESULT
   → Identify the value and explain its meaning

2. TABLE RESULT
   → Identify:
     • highest and lowest values  
     • key comparisons  
     • patterns or distribution  
     • ranking if present  

Focus on:
• extremes (max, min)
• relative differences
• notable gaps or concentrations

=======================
INSIGHT REQUIREMENTS
========================

Each insight MUST:

• Reference actual numerical values from the result  
• Be precise and factual  
• Be written in business language  
• Be concise (1–2 sentences)  

DO NOT:

• restate the query  
• include technical SQL terms  
• make assumptions beyond the data

========================
TERMINOLOGY CLARITY (CRITICAL)
========================

You MUST NOT use ambiguous or technical terms such as:

• "line item"
• "row"
• "record"

You MUST:

• Use clear business terminology
• Follow the meaning defined in the calculation

Examples:

If calculation:
AVG(sales amount) BY product

Correct:
"average sales amount per product"

NOT:
"average sales per line item"

========================
COVERAGE RULE (MANDATORY)
========================

You MUST return insights for EVERY input item.

If data is limited:
→ still produce the best possible factual insight

========================
OUTPUT FORMAT (STRICT)
========================

{{
  "results": [
    {{
      "id": "placeholder_id",
      "insights": ["insight 1", "insight 2"]
    }}
  ]
}}

Return ONLY JSON.
"""


def _extract_json(text):
    """Extract json"""

    match = re.search(r"\{[\s\S]*\}", text)
    if not match:
        raise ValueError("Invalid JSON from interpreter")

    return json.loads(match.group())
