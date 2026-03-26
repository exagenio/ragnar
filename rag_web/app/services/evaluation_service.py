# app/services/evaluation_service.py

import json
from django.conf import settings
from app.models import (
    Project,
    Topic,
    TopicContent,
    TopicEvaluation,
    ReportEvaluation,
    Report,
)
from app.services.llm_provider import (
    get_llm,
    LLMBackend,
    ModelSize,
)
from app.services.llm_provider import get_embeddings
from .vector_store import get_vector_store
import re
from app.services.topic_content_generator import extract_json_or_fail


# =========================
# METADATA RETRIEVAL
# =========================
def retrieve_metadata_for_topic(project, topic):
    vector_store = get_vector_store()

    docs = vector_store.similarity_search(
        f"{topic.title}",
        k=8,
        filter={"project_id": project.id},
    )

    return [
        {"content": d.page_content, "metadata": d.metadata}
        for d in docs
    ]


# =========================
# PROMPT BUILDER
# =========================
def build_evaluation_prompt(
    *,
    project,
    topic,
    content_json,
    metadata_context,
    sql_results,
):
    return f"""
You are a STRICT, DOMAIN-AWARE evaluation judge for data-driven business reports.

Your responsibility is to evaluate the quality of generated analytical content.

You MUST behave like a critical reviewer, NOT a content generator.

========================
PROJECT CONTEXT
========================
Project ID: {project.id}
Report Type: {topic.report.report_type}
Topic: {topic.title}

========================
AVAILABLE DATA CONTEXT
========================
{json.dumps(metadata_context)}

========================
PRECOMPUTED METRICS (SOURCE OF TRUTH)
========================
{json.dumps(sql_results)}

========================
GENERATED CONTENT
========================
{json.dumps(content_json)}

========================
CRITICAL EVALUATION RULES
========================

You MUST strictly enforce:

1. DATA GROUNDING
- Every claim MUST be supported by provided metrics or metadata
- If a statement is not directly supported → penalize

2. NO HALLUCINATION
- No invented numbers
- No fabricated trends
- No assumptions beyond available data

3. DOMAIN CONSISTENCY
- Content must match business domain and topic intent
- No generic filler explanations

4. ANALYTICAL QUALITY
- Must demonstrate reasoning (comparisons, trends, insights)
- Not just descriptive statements

5. CLARITY
- Clear, structured, professional writing
- No redundancy or vague wording

========================
MANDATORY EVALUATION PROCESS
========================

You MUST follow this process BEFORE assigning scores:

STEP 1 — CONTENT UNDERSTANDING
- Identify what the topic is trying to analyze

STEP 2 — DATA VERIFICATION
- Check whether the claims in the content are supported by:
  - Provided metadata
  - Precomputed metrics

STEP 3 — ISSUE IDENTIFICATION
- List:
  - Unsupported claims
  - Missing insights where data exists
  - Weak or generic explanations
  - Redundant or unclear statements

STEP 4 — QUALITY ASSESSMENT
- Evaluate:
  - Is analysis shallow or deep?
  - Is reasoning present or missing?
  - Is content aligned with topic?

ONLY AFTER completing these steps:
→ Assign scores

========================
SCORING (0–100)
========================

Each score MUST reflect actual observed quality based on the evaluation process.

Do NOT assign 100 unless:
- No issues are identified
- All claims are fully supported by data
- Strong analytical reasoning is present

If ANY issue exists:
→ Score MUST be reduced accordingly

========================
SCORING GUIDELINES
========================

hallucination:
- Reduce score if ANY unsupported claim exists

data_grounding:
- Reduce score if content is not clearly tied to data

relevance:
- Reduce score if content includes generic or unrelated discussion

analytical_depth:
- Reduce score if:
  - no comparisons
  - no trends
  - no reasoning

clarity:
- Reduce score if:
  - repetition exists
  - vague wording
  - poor structure

========================
SCORING CALIBRATION
========================

You MUST score based on actual quality, NOT artificially high or low.

Guidelines:

- High-quality, fully data-grounded, well-structured analysis → 85–100
- Good analysis with minor gaps → 70–84
- Moderate quality with noticeable issues → 50–69
- Weak analysis with major issues → 30–49
- Poor or incorrect analysis → 0–29

IMPORTANT:

- Assign scores proportionally to the actual quality observed
- Do NOT artificially lower or inflate scores
- Be consistent across topics

========================
EVIDENCE-BASED EVALUATION
========================

Before assigning scores, you MUST:

1. Identify whether claims in the content are supported by:
   - Provided metadata
   - Precomputed metrics

2. Check for:
   - Unsupported claims
   - Missing analysis where data exists
   - Incorrect interpretations

3. Base your scores ONLY on this verification

You MUST NOT rely on general impressions.

========================
HALLUCINATION DETECTION RULE
========================

If the content includes:

- Specific numbers not present in provided metrics
- Trends or comparisons not supported by data
- Assumptions beyond available data

You MUST reduce the hallucination and data_grounding scores accordingly.

========================
JUSTIFICATION REQUIREMENT
========================

For EACH score below 90:
You MUST include at least one issue explaining the deduction.

For scores above 90:
You MUST ensure no meaningful issues exist.

========================
OUTPUT FORMAT (STRICT JSON)
========================

{{
  "scores": {{
    "hallucination": int,
    "data_grounding": int,
    "relevance": int,
    "analytical_depth": int,
    "clarity": int
  }},
  "issues": [
    "specific issue 1",
    "specific issue 2"
  ],
  "summary": "Concise evaluation summary"
}}

Return ONLY JSON.
"""


# =========================
# TOPIC EVALUATION
# =========================
def evaluate_topic(
    *,
    project,
    topic,
    llm,
):
    content_obj = TopicContent.objects.filter(topic=topic).first()
    if not content_obj:
        return None

    content_json = content_obj.content_json or {}

    sql_results = content_json.get("precomputed_sql_placeholders", [])

    metadata_context = retrieve_metadata_for_topic(project, topic)

    prompt = build_evaluation_prompt(
        project=project,
        topic=topic,
        content_json=content_json,
        metadata_context=metadata_context,
        sql_results=sql_results,
    )

    print("\n================ EVALUATION PROMPT =================")
    print(f"Topic ID: {topic.id}")
    print(prompt)  # limit to avoid huge logs
    print("===================================================\n")

    try:
        response = llm.invoke(prompt)

        content = response.content

        if isinstance(content, list):
            if isinstance(content[0], dict) and "text" in content[0]:
                raw_text = content[0]["text"].strip()
            else:
                raw_text = str(content[0]).strip()
        else:
            raw_text = content.strip()

        result = extract_json_or_fail(raw_text)
        scores = result["scores"]

        overall_score = sum(scores.values()) / len(scores)

        print("\n✅ [EVAL SUCCESS]")
        print(f"Topic ID: {topic.id}")
        print(f"Scores: {scores}")
        print(f"Overall Score: {overall_score}")
        print("---------------------------------------------------\n")

        return {
            "scores": scores,
            "issues": result.get("issues", []),
            "summary": result.get("summary", ""),
            "overall_score": overall_score,
        }

    except Exception as e:

        print("\n❌ [EVAL ERROR]")
        print(f"Topic ID: {topic.id}")
        print(f"Error: {e}")

        try:
            print("----- RAW LLM OUTPUT -----")
            print(raw_text)
        except:
            print("No raw_text available")

        print("---------------------------------------------------\n")

        return None


# =========================
# REPORT AGGREGATION
# =========================
def compute_report_score(project, report, topic_results):

    if not topic_results:
        return None

    aggregated = {
        "hallucination": 0,
        "data_grounding": 0,
        "relevance": 0,
        "analytical_depth": 0,
        "clarity": 0,
    }

    for r in topic_results:
        for k in aggregated:
            aggregated[k] += r["scores"][k]

    n = len(topic_results)

    average_scores = {k: v / n for k, v in aggregated.items()}
    overall_score = sum(average_scores.values()) / len(average_scores)

    ReportEvaluation.objects.update_or_create(
        report=report,
        defaults={
            "average_scores": average_scores,
            "overall_score": overall_score,
        },
    )

    return {
        "average_scores": average_scores,
        "overall_score": overall_score,
    }


def evaluate_project(project_id: int, report_id: int):

    project = Project.objects.get(id=project_id)
    report = Report.objects.get(id=report_id)

    topics = Topic.objects.filter(
        subsection__section__report=report
    )

    llm = get_llm(
        backend=settings.DEFAULT_LLM_BACKEND,
        model_size=ModelSize.PRIMARY,
        temperature=0,
    )

    topic_results = []

    for topic in topics:

        result = evaluate_topic(
            project=project,
            topic=topic,
            llm=llm,
        )

        if not result:
            continue

        TopicEvaluation.objects.update_or_create(
            topic=topic,
            report=report,
            defaults={
                "scores": result["scores"],
                "issues": result["issues"],
                "summary": result["summary"],
                "overall_score": result["overall_score"],
            },
        )

        topic_results.append(result)

    return compute_report_score(project, report, topic_results)