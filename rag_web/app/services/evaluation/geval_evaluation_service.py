import json
from concurrent.futures import ThreadPoolExecutor, as_completed

from deepeval.metrics import GEval
from deepeval.models import GeminiModel, OllamaModel, OpenRouterModel
from deepeval.test_case import LLMTestCase, LLMTestCaseParams
from django.conf import settings
from django.db import close_old_connections, connections

from app.models import (
    Project,
    Report,
    SelectedTable,
    Topic,
    TopicAnalysisPlan,
    TopicContent,
    TopicEvaluation,
)
from app.services.evaluation.evaluation_service import extract_content_blocks_text
from app.services.llm_config.llm_provider import LLMProvider
from app.services.metadata_generation.metadata_retriever import (
    build_retrieved_context,
    get_dataset_mode,
    retrieve_multi_table_metadata,
)
from app.services.metadata_generation.schema_context_builder import build_schema_context
from app.services.topic_gen.topic_analysis_plan_generator import normalize_topic_analysis_plan


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
            For multi-table datasets, verify that claims respect table relationships,
            join paths, relationship cardinality, enum meanings, and column business
            definitions. For single-table datasets, do not penalize the output for
            not using joins when no joins are available.
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
            provided numerical insights, schema metadata, enum metadata, or table
            relationship context. Penalize unsupported cross-table claims, invented
            joins, invented enum meanings, and numbers that are not supported by the
            supplied analytical evidence.
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
            required elements, analytical questions, and dataset structure. In
            multi-table projects, reward correct relationship-aware reasoning. In
            single-table projects, reward analysis that stays within the selected
            table's measures, dimensions, timestamps, identifiers, and enums.
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
            Evaluate whether the report presents information in a logical analytical flow, clearly connecting evidence, explanation, and significance while maintaining overall clarity and coherence.
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
        futures = [executor.submit(run_metric, metric) for metric in metrics]

        for future in futures:
            result = future.result()
            if result:
                results.append(result)

    return results


def _run_with_db_connection_cleanup(func, *args, **kwargs):
    close_old_connections()
    try:
        return func(*args, **kwargs)
    finally:
        connections.close_all()


def _safe_topic_plan(topic, report):
    plan = TopicAnalysisPlan.objects.filter(topic=topic, report=report).first()
    if not plan or not plan.plan_json:
        return {}
    return normalize_topic_analysis_plan(plan.plan_json)


def _selected_objects_summary(project):
    selected_objects = list(
        SelectedTable.objects.filter(project=project).order_by(
            "created_at",
            "object_type",
            "display_name",
            "table_name",
        )
    )
    tables = [item.object_name for item in selected_objects if item.object_type == "table"]
    enums = [
        {
            "enum": item.object_name,
            "used_by": (
                f"{item.source_table}.{item.source_column}"
                if item.source_table and item.source_column
                else ""
            ),
        }
        for item in selected_objects
        if item.object_type == "enum"
    ]

    return {
        "dataset_mode": get_dataset_mode(project),
        "selected_tables": tables,
        "selected_enums": enums,
    }


def _compact_data_requirements(plan_json):
    compact = []

    for index, requirement in enumerate(plan_json.get("data_requirements", [])):
        compact.append(
            {
                "index": index,
                "type": requirement.get("type"),
                "tables": requirement.get("tables", []),
                "columns": requirement.get("columns", []),
                "filters": requirement.get("filters", []),
                "group_by": requirement.get("group_by", []),
                "operation": requirement.get("operation"),
                "business_logic": requirement.get("business_logic", ""),
                "description": requirement.get("description", ""),
            }
        )

    return compact


def build_geval_input(project, topic, report):
    plan_json = _safe_topic_plan(topic, report)

    return f"""
REPORT:
Title: {report.title}
Industry: {report.industry}
Report type: {report.report_type}
Audience: {report.audience}
Purpose: {report.purpose}
Focus areas: {report.focus_areas}

DATASET:
{json.dumps(_selected_objects_summary(project), indent=2)}

REPORT LOCATION:
Section: {topic.subsection.section.title}
Subsection: {topic.subsection.title}
Topic: {topic.title}

TOPIC ANALYSIS PLAN:
Topic: {plan_json.get("topic") or topic.title}
Intent: {plan_json.get("intent", "")}
Required elements: {json.dumps(plan_json.get("required_elements", []), indent=2)}
Business questions: {json.dumps(plan_json.get("business_questions", []), indent=2)}
Data requirements: {json.dumps(_compact_data_requirements(plan_json), indent=2)}
"""


def _summarize_schema_context(project):
    try:
        schema_context = build_schema_context(project)
    except Exception as exc:
        return f"Schema context unavailable: {exc}"

    compact_tables = []
    for table in schema_context.get("tables", []):
        compact_tables.append(
            {
                "table": table.get("table"),
                "columns": [
                    {
                        "name": column.get("name"),
                        "type": column.get("type"),
                        "enum_name": column.get("enum_name"),
                        "nullable": column.get("nullable"),
                    }
                    for column in table.get("columns", [])
                ],
            }
        )

    compact_schema = {
        "dataset_mode": schema_context.get("dataset_mode"),
        "tables": compact_tables,
        "relationships": schema_context.get("relationships", []),
    }
    return json.dumps(compact_schema, indent=2, default=str)


def _build_metadata_query(topic, plan_json):
    required_elements = plan_json.get("required_elements", [])
    business_questions = plan_json.get("business_questions", [])
    data_requirements = _compact_data_requirements(plan_json)

    return f"""
Section: {topic.subsection.section.title}
Subsection: {topic.subsection.title}
Topic: {topic.title}
Intent: {plan_json.get("intent", "")}
Required elements: {'; '.join(str(item) for item in required_elements)}
Business questions: {'; '.join(str(item) for item in business_questions)}
Data requirements: {json.dumps(data_requirements)}
Evaluate report correctness using table metadata, column metadata, enum meanings,
relationships, join paths, measures, dimensions, identifiers, timestamps, and analytical capabilities.
"""


def retrieve_geval_metadata_context(project, topic, report):
    plan_json = _safe_topic_plan(topic, report)
    metadata_context = retrieve_multi_table_metadata(
        project=project,
        primary_query=_build_metadata_query(topic, plan_json),
        secondary_queries=[
            "GEval analytical correctness multi table joins relationship cardinality foreign keys",
            "single table analytical measures dimensions timestamps identifiers enum values statuses",
            "numerical insight validation business logic filters aggregations ratios trends segmentation",
        ],
        metadata_types=[
            "table_description",
            "table_relationship",
            "column",
            "column_relationship",
            "enum_description",
            "enum_usage",
            "enum_value",
            "analytical_capability",
            "confidence_note",
        ],
        per_query_k=12,
        max_docs=36,
    )
    return build_retrieved_context(metadata_context)


def _extract_numerical_insights(sql_placeholders):
    insights = []

    for placeholder in sql_placeholders:
        content = placeholder.get("content", {})
        query = content.get("query", {})
        insights.append(
            {
                "id": content.get("id"),
                "calculation": content.get("calculation"),
                "description": content.get("description"),
                "business_logic": content.get("business_logic", ""),
                "query_steps": content.get("query_steps", []),
                "status": query.get("status"),
                "row_count": query.get("row_count"),
                "insights": query.get("insights"),
                "failure_reason": query.get("reason") or query.get("error"),
            }
        )

    return insights


def build_geval_context(project, topic, report, content_json):
    numerical_insights = _extract_numerical_insights(
        content_json.get("precomputed_sql_placeholders", [])
    )
    metadata_context = retrieve_geval_metadata_context(project, topic, report)
    schema_context = _summarize_schema_context(project)

    context_list = [
        f"DATASET SCHEMA AND RELATIONSHIPS:\n{schema_context}",
        f"RETRIEVED METADATA CONTEXT:\n{metadata_context}",
    ]

    if numerical_insights:
        context_list.append(
            "NUMERICAL INSIGHTS FROM EXECUTED SQL PLACEHOLDERS:\n"
            f"{json.dumps(numerical_insights, indent=2, default=str)}"
        )

    return context_list


def build_geval_model(project):
    if project.llm_provider == LLMProvider.OPENROUTER.value:
        api_key = project.get_openrouter_api_key() or settings.OPENROUTER_API_KEY
        return OpenRouterModel(
            model=project.primary_llm_model,
            api_key=api_key,
        )

    if project.llm_provider == LLMProvider.OLLAMA.value:
        return OllamaModel(
            model=project.primary_llm_model,
            base_url=getattr(settings, "OLLAMA_BASE_URL", "http://localhost:11434"),
            temperature=0,
        )

    return GeminiModel(
        model=project.primary_llm_model,
        project=settings.VERTEX_AI_PROJECT,
        location=settings.VERTEX_AI_LOCATION,
        temperature=0,
    )


def evaluate_topic_geval(project, topic, report, model):
    content_obj = TopicContent.objects.filter(topic=topic).first()
    if not content_obj:
        return None

    content_json = content_obj.content_json or {}
    content_text = extract_content_blocks_text(content_json)
    input_text = build_geval_input(project, topic, report)
    context_list = build_geval_context(project, topic, report, content_json)

    test_case = build_test_case(
        input_text,
        content_text,
        context_list,
    )

    metrics = get_geval_metrics(model)
    results = run_geval_metrics(test_case, metrics)

    if not results:
        return None

    raw_scores = {result["metric"]: result["score"] for result in results}
    scores = {
        "correctness": raw_scores.get("correctness", 0),
        "hallucination": raw_scores.get("hallucination", 0),
        "relevance": raw_scores.get("relevance", 0),
        "conciseness": raw_scores.get("coherence", 0),
    }
    overall_score = (
        scores.get("correctness", 0)
        + scores.get("hallucination", 0)
        + scores.get("relevance", 0)
    ) / 3

    issues = [result["reason"] for result in results if result["reason"]]

    return {
        "scores": scores,
        "issues": issues,
        "summary": " | ".join(issues),
        "overall_score": overall_score,
    }


def evaluate_and_save_topic_geval(project, report, topic, model=None):
    close_old_connections()
    try:
        model = model or build_geval_model(project)
        result = evaluate_topic_geval(project, topic, report, model)

        if not result:
            return None

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

        return result
    finally:
        connections.close_all()


def evaluate_project_geval(project_id: int, report_id: int):
    print("G eval eval started")
    project = Project.objects.get(id=project_id)
    report = Report.objects.get(id=report_id)

    topics = Topic.objects.filter(
        subsection__section__report=report
    ).select_related("subsection__section")

    model = build_geval_model(project)

    topic_results = []

    def process_topic(topic):
        try:
            result = evaluate_and_save_topic_geval(
                project,
                report,
                topic,
                model,
            )

            if not result:
                return None

            print(f"\n[GEVAL DONE] Topic: {topic.id} - {topic.title}")
            print("Scores:", result["scores"])
            print("Overall:", result["overall_score"])
            print("Issues:", result["issues"])
            print("-" * 60)

            return result

        except Exception as e:
            print(f"[GEVAL ERROR] Topic {topic.id}: {e}")
            return None

    with ThreadPoolExecutor(max_workers=3) as executor:
        futures = [executor.submit(process_topic, topic) for topic in topics]

        for future in as_completed(futures):
            result = future.result()
            if result:
                topic_results.append(result)

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
        key: sum(values) / len(values)
        for key, values in category_scores.items()
    }

    overall_score = (
        averaged_scores.get("correctness", 0)
        + averaged_scores.get("hallucination", 0)
        + averaged_scores.get("relevance", 0)
    ) / 3

    return {
        "overall_score": round(overall_score, 2),
        "category_scores": averaged_scores,
        "topics_evaluated": len(topic_results),
    }
