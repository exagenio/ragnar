from django.contrib import messages
from django.http import HttpResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse

from app.models import Project, Report, Topic, TopicEvaluation, TopicReadability
from app.services.evaluation.evaluation_doc_generator import generate_evaluation_document
from app.services.evaluation.geval_evaluation_service import (
    evaluate_and_save_topic_geval,
    evaluate_project_geval,
)
from app.services.evaluation.readability_service import evaluate_project_readability

EVAL_TYPE = "geval"


def _dashboard_url(project_id, report_id=None):
    url = reverse("evaluation_dashboard_view", kwargs={"project_id": project_id})
    if report_id:
        return f"{url}?report_id={report_id}&eval_type={EVAL_TYPE}"
    return url


def _average(values):
    return round(sum(values) / len(values), 2) if values else 0


def _readability_summary(readability_scores):
    values = [
        item.flesch_kincaid_grade
        for item in readability_scores
        if item.flesch_kincaid_grade is not None
    ]
    return {
        "average_grade": _average(values),
        "topics_evaluated": len(values),
    }


def _prepare_geval_results(topic_evals):
    project_overall_scores = []
    category_scores = {
        "correctness": [],
        "relevance": [],
        "hallucination": [],
        "conciseness": [],
    }

    for eval_obj in topic_evals:
        scores = eval_obj.geval_scores or {}
        correctness = float(scores.get("correctness", 0))
        relevance = float(scores.get("relevance", 0))
        hallucination = float(scores.get("hallucination", 0))
        conciseness = float(scores.get("conciseness", 0))

        overall = (correctness + relevance + hallucination + conciseness) / 4

        eval_obj.overall_score = round(overall, 2)
        eval_obj.display_scores = scores
        eval_obj.display_summary = eval_obj.geval_summary
        eval_obj.display_issues = eval_obj.geval_issues or []

        project_overall_scores.append(overall)
        category_scores["correctness"].append(correctness)
        category_scores["relevance"].append(relevance)
        category_scores["hallucination"].append(hallucination)
        category_scores["conciseness"].append(conciseness)

    return {
        "overall_score": _average(project_overall_scores),
        "correctness": _average(category_scores["correctness"]),
        "relevance": _average(category_scores["relevance"]),
        "hallucination": _average(category_scores["hallucination"]),
        "conciseness": _average(category_scores["conciseness"]),
    }


def _handle_readability(request, project, report_id):
    result = evaluate_project_readability(project.id, report_id)
    messages.success(
        request,
        (
            "Flesch-Kincaid readability computed. "
            f"Processed {result['processed']} topic(s), skipped {result['skipped']}."
        ),
    )
    return redirect(_dashboard_url(project.id, report_id))


def _handle_topic_reevaluation(request, project, report_id):
    topic = get_object_or_404(
        Topic,
        id=request.POST.get("topic_id"),
        subsection__section__report_id=report_id,
    )
    report = get_object_or_404(Report, id=report_id, project=project)
    result = evaluate_and_save_topic_geval(project, report, topic)

    if result:
        messages.success(request, f"GEval re-evaluated topic: {topic.title}")
    else:
        messages.warning(request, f"GEval could not evaluate topic: {topic.title}")

    return redirect(_dashboard_url(project.id, report_id))


def evaluation_dashboard_view(request, project_id):
    project = get_object_or_404(Project, id=project_id)
    reports = Report.objects.filter(project=project)
    report_id = request.GET.get("report_id") or request.POST.get("report_id")
    selected_report = None
    topic_evals = None
    readability_scores = None
    readability_summary = None
    geval_project_summary = None
    has_geval_results = False

    if report_id:
        selected_report = get_object_or_404(Report, id=report_id, project=project)

    if request.method == "POST":
        if not report_id:
            messages.error(request, "Please select a report.")
            return redirect(_dashboard_url(project.id))

        action = request.POST.get("action")
        if action == "readability":
            return _handle_readability(request, project, report_id)

        if action == "reevaluate_geval_topic":
            return _handle_topic_reevaluation(request, project, report_id)

        evaluate_project_geval(project.id, report_id)
        messages.success(request, "GEval evaluation completed.")
        return redirect(_dashboard_url(project.id, report_id))

    if selected_report:
        topic_evals = TopicEvaluation.objects.filter(
            topic__subsection__section__report=selected_report
        ).select_related("topic")
        has_geval_results = topic_evals.filter(geval_scores__isnull=False).exists()

        readability_scores = TopicReadability.objects.filter(
            report=selected_report
        ).select_related("topic").order_by("topic__created_at", "topic__id")
        readability_summary = _readability_summary(readability_scores)
        geval_project_summary = _prepare_geval_results(topic_evals)

    return render(
        request,
        "evaluation/dashboard.html",
        {
            "project": project,
            "reports": reports,
            "selected_report": selected_report,
            "topic_evals": topic_evals,
            "readability_scores": readability_scores,
            "readability_summary": readability_summary,
            "geval_project_summary": geval_project_summary,
            "has_geval_results": has_geval_results,
            "eval_type": EVAL_TYPE,
        },
    )


def export_evaluation_doc(request, project_id):
    report_id = request.GET.get("report_id")
    if not report_id:
        return HttpResponse("Missing report_id", status=400)

    report = get_object_or_404(Report, id=report_id, project_id=project_id)
    topic_evals = TopicEvaluation.objects.filter(
        topic__subsection__section__report=report
    ).select_related("topic")

    response = HttpResponse(
        generate_evaluation_document(report, topic_evals),
        content_type="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    )
    response["Content-Disposition"] = (
        f'attachment; filename="evaluation_report_{report.id}.docx"'
    )
    return response

