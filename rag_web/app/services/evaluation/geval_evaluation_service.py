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
    log_evaluation_payload,
    retrieve_metadata_for_topic,
)
from django.conf import settings
from app.services.llm_config.llm_provider import LLMProvider
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
            retrieved dataset rows. Penalize unsupported claims.
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


def run_geval_metrics(test_case, metrics, topic, report):

    results = []

    def run_metric(metric):
        category = (
            "conciseness"
            if metric.name.lower() == "coherence"
            else metric.name.lower()
        )
        try:
            input_text = (
                test_case.input
                if category in {"correctness", "relevance"}
                else None
            )
            context_text = (
                "\n".join(test_case.context or [])
                if category in {"correctness", "hallucination"}
                else None
            )
            log_evaluation_payload(
                engine="G-Eval",
                category=category,
                topic=topic,
                report=report,
                input_text=input_text,
                output_text=test_case.actual_output,
                context_text=context_text,
            )
            metric.measure(test_case)

            result = {
                "metric": metric.name,
                "score": float(metric.score) * 100,
                "reason": metric.reason or "",
            }
            print(
                f"[EVALUATION CATEGORY RESULT] engine=G-Eval "
                f"category={category} topic={topic.id} result={result}"
            )
            return result

        except Exception as e:
            print(
                f"[EVALUATION CATEGORY ERROR] engine=G-Eval "
                f"category={category} topic={topic.id} "
                f"error={type(e).__name__}: {e}"
            )
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
    retrieved_context = retrieve_metadata_for_topic(
        project, topic, vector_store, report
    )

    context_list = []

    if retrieved_context:
        context_list.append(
            f"RETRIEVED DATA:\n{retrieved_context}"
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
    results = run_geval_metrics(test_case, metrics, topic, report)

    if not results:
        return None

    raw_scores = {r["metric"]: r["score"] for r in results}

    scores = {
        "correctness": raw_scores.get("correctness", 0),
        "hallucination": raw_scores.get("hallucination", 0),
        "relevance": raw_scores.get("relevance", 0),
        "conciseness": raw_scores.get("coherence", 0),
    }
    completed_categories = {
        "conciseness" if name == "coherence" else name
        for name in raw_scores
    }
    missing_categories = {
        "hallucination",
        "correctness",
        "relevance",
        "conciseness",
    } - completed_categories
    if missing_categories:
        print(
            f"[EVALUATION INCOMPLETE] engine=G-Eval topic={topic.id} "
            f"missing={sorted(missing_categories)}. "
            "A category evaluator failed or returned no usable score."
        )
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


def get_geval_model(project):
    """Create the same judge model used by full and single-topic G-Eval."""

    if project.llm_provider == LLMProvider.OPENROUTER.value:
        api_key = project.get_openrouter_api_key() or settings.OPENROUTER_API_KEY
        return OpenRouterModel(
            model=project.primary_llm_model,
            api_key=api_key,
        )
    return GeminiModel(
        model=project.primary_llm_model,
        project=settings.VERTEX_AI_PROJECT,
        location=settings.VERTEX_AI_LOCATION,
        temperature=0,
    )


def evaluate_single_topic_geval(
    project,
    report,
    topic,
    vector_store=None,
    model=None,
):
    """Run and persist G-Eval for one topic."""

    vector_store = vector_store or get_vector_store(backend="local")
    model = model or get_geval_model(project)
    result = evaluate_topic_geval(
        project,
        topic,
        report,
        vector_store,
        model,
    )
    if not result:
        raise ValueError(f"Topic {topic.id} has no generated content to evaluate.")

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
    print(f"\n[GEVAL DONE] Topic: {topic.id} - {topic.title}")
    print("Scores:", result["scores"])
    print("Overall:", result["overall_score"])
    print("Issues:", result["issues"])
    print("-" * 60)
    return result


def evaluate_project_geval(project_id: int, report_id: int):
    print("G eval eval started")
    project = Project.objects.get(id=project_id)
    report = Report.objects.get(id=report_id)

    topics = Topic.objects.filter(
        subsection__section__report=report
    )

    vector_store = get_vector_store(backend="local")

    model = get_geval_model(project)
    topic_results = []
    topic_errors = []


    # Concurrent execution
    def process_topic(topic):

        try:
            result = evaluate_single_topic_geval(
                project,
                report,
                topic,
                vector_store=vector_store,
                model=model,
            )

            if not result:
                return None

            return result

        except Exception as e:
            print(f"[GEVAL ERROR] Topic {topic.id}: {e}")
            topic_errors.append(f"{topic.title}: {e}")
            return None

    # Thread pool
    with ThreadPoolExecutor(max_workers=3) as executor:

        futures = [executor.submit(process_topic, topic) for topic in topics]

        for future in as_completed(futures):
            res = future.result()
            if res:
                topic_results.append(res)

    if not topic_results and topics.exists():
        details = " | ".join(topic_errors) or "No metric returned a result."
        raise RuntimeError(f"G-Eval failed for all topics: {details}")

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
