import json
from concurrent.futures import ThreadPoolExecutor
from deepeval.models import OpenRouterModel
from django.conf import settings
from deepeval.metrics import GEval
from deepeval.test_case import LLMTestCase, LLMTestCaseParams
from langchain_openrouter import ChatOpenRouter
from app.models import Topic, TopicContent, TopicEvaluation, Report, Project
from app.services.vector_db_config.vector_store import get_vector_store
from deepeval.models.base_model import DeepEvalBaseLLM
from app.services.evaluation.evaluation_service import (
    extract_content_blocks_text,
    build_eval_input,
    retrieve_metadata_for_topic,
)
from django.conf import settings
from app.services.llm_config.llm_provider import (
    get_llm,
    LLMBackend,
    ModelSize,
)
from deepeval.models import GeminiModel

def build_test_case(input_text, output_text, context_text):
    return LLMTestCase(
        input=input_text,
        actual_output=output_text,
        context=context_text,
    )


def get_geval_metrics(model):
    return [
        GEval(
            name="correctness",
            criteria="""
            Evaluate whether the analytical report content is factually correct,
            complete, and logically consistent with the intended business analysis.
            """,
            evaluation_params=[
                LLMTestCaseParams.INPUT,
                LLMTestCaseParams.ACTUAL_OUTPUT,
                LLMTestCaseParams.CONTEXT,
            ],
            model=model,
        ),
        GEval(
            name="hallucination",
            criteria="""
            Check whether the output contains any claims not supported by the
            provided SQL COMPUTED ANALYTICAL INSIGHTS or metadata context. Penalize unsupported claims.
            """,
            evaluation_params=[
                LLMTestCaseParams.ACTUAL_OUTPUT,
                LLMTestCaseParams.CONTEXT,
            ],
            model=model,
        ),
        GEval(
            name="relevance",
            criteria="""
            Evaluate whether the output directly addresses the business intent,
            required elements, and analytical questions.
            """,
            evaluation_params=[
                LLMTestCaseParams.INPUT,
                LLMTestCaseParams.ACTUAL_OUTPUT,
            ],
            model=model,
        ),
        GEval(
            name="coherence",
            criteria="""
            Evaluate whether the report follows a logical analytical structure:
            DATA → INTERPRETATION → IMPLICATION and maintains clarity.
            """,
            evaluation_params=[LLMTestCaseParams.ACTUAL_OUTPUT],
            model=model,
        ),
    ]


def run_geval_metrics(test_case, metrics):

    results = []

    def run_metric(metric):
        try:
            metric.measure(test_case)

            return {
                "metric": metric.name,
                "score": float(metric.score) * 100,
                "reason": metric.reason or "",
            }

        except Exception as e:
            print(f"[GEVAL ERROR] {metric.name}: {e}")
            return None

    with ThreadPoolExecutor(max_workers=4) as executor:
        futures = [executor.submit(run_metric, m) for m in metrics]

        for f in futures:
            res = f.result()
            if res:
                results.append(res)

    return results


def evaluate_topic_geval(project, topic, report, vector_store, model):

    content_obj = TopicContent.objects.filter(topic=topic).first()
    if not content_obj:
        return None

    content_json = content_obj.content_json or {}

    # Content
    content_text = extract_content_blocks_text(content_json)

    # Input
    input_text = build_eval_input(topic, report)

    # Context
    sql_results = content_json.get("precomputed_sql_placeholders", [])

    metadata_context = retrieve_metadata_for_topic(
        project, topic, vector_store, report
    )

    context_str = f"""
SQL COMPUTED ANALYTICAL INSIGHTS:
{json.dumps(sql_results, indent=2)}

METADATA:
{metadata_context}
"""
    
    context_list = []

    if sql_results:
        context_list.append(
            f"SQL COMPUTED ANALYTICAL INSIGHTS:\n{json.dumps(sql_results, indent=2)}"
        )

    if metadata_context:
        context_list.append(
            f"METADATA:\n{metadata_context}"
        )

    # Test case
    test_case = build_test_case(
        input_text,
        content_text,
        context_list,
    )

    # Metrics
    metrics = get_geval_metrics(model)

    # run metrics
    results = run_geval_metrics(test_case, metrics)

    if not results:
        return None

    raw_scores = {r["metric"]: r["score"] for r in results}

    scores = {
        "correctness": raw_scores.get("correctness", 0),
        "hallucination": raw_scores.get("hallucination", 0),
        "relevance": raw_scores.get("relevance", 0),
        "conciseness": raw_scores.get("coherence", 0),
    }
    overall_score = (
        scores.get("correctness", 0) +
        scores.get("hallucination", 0) +
        scores.get("relevance", 0)
    ) / 3

    issues = [r["reason"] for r in results if r["reason"]]

    return {
        "scores": scores,
        "issues": issues,
        "summary": " | ".join(issues),
        "overall_score": overall_score,
    }


from concurrent.futures import ThreadPoolExecutor, as_completed


def evaluate_project_geval(project_id: int, report_id: int):
    print("G eval eval started")
    project = Project.objects.get(id=project_id)
    report = Report.objects.get(id=report_id)

    topics = Topic.objects.filter(
        subsection__section__report=report
    )

    vector_store = get_vector_store(
        backend=settings.DEFAULT_LLM_BACKEND
    )

    backend = LLMBackend(settings.DEFAULT_LLM_BACKEND)

    model = GeminiModel(
        model="gemini-2.5-pro",   # or gemini-2.5-pro
        project="project-08491770-bd93-473e-a10",
        location="us-central1",
        temperature=0,
    )


    # model = OpenRouterModel(
    #     model="openai/gpt-4.1",
    #     api_key=settings.OPENROUTER_API_KEY,
    # )
    topic_results = []


    # Concurrent execution
    def process_topic(topic):

        try:
            result = evaluate_topic_geval(
                project,
                topic,
                report,
                vector_store,
                model,
            )

            if not result:
                return None

            # Save result
            TopicEvaluation.objects.update_or_create(
                topic=topic,
                report=report,
                defaults={
                    "geval_scores": result["scores"],
                    "geval_issues": result["issues"],
                    "geval_summary": result["summary"],
                    "geval_overall_score": result["overall_score"],
                },
            )

            # Log output
            print(f"\n[GEVAL DONE] Topic: {topic.id} - {topic.title}")
            print("Scores:", result["scores"])
            print("Overall:", result["overall_score"])
            print("Issues:", result["issues"])
            print("-" * 60)

            return result

        except Exception as e:
            print(f"[GEVAL ERROR] Topic {topic.id}: {e}")
            return None

    # Thread pool
    with ThreadPoolExecutor(max_workers=3) as executor:

        futures = [executor.submit(process_topic, topic) for topic in topics]

        for future in as_completed(futures):
            res = future.result()
            if res:
                topic_results.append(res)

    # FINAL AGGREGATION
    return compute_geval_report_score(topic_results)


def compute_geval_report_score(topic_results):

    if not topic_results:
        return {
            "overall_score": 0,
            "category_scores": {},
            "topics_evaluated": 0,
        }

    category_scores = {}

    for result in topic_results:
        for key, value in result["scores"].items():
            category_scores.setdefault(key, []).append(value)

    averaged_scores = {
        k: sum(v) / len(v)
        for k, v in category_scores.items()
    }

    overall_score = (
        averaged_scores.get("correctness", 0) +
        averaged_scores.get("hallucination", 0) +
        averaged_scores.get("relevance", 0)
    ) / 3

    return {
        "overall_score": round(overall_score, 2),
        "category_scores": averaged_scores,
        "topics_evaluated": len(topic_results),
    }