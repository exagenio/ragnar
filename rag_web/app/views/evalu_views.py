from django.contrib import messages
from django.db.models import Avg
from django.http import HttpResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from app.models import (
    Project,
    Report,
    Topic,
    TopicReadability,
    ReportEvaluation,
    TopicEvaluation
)
from app.services.evaluation.evaluation_service import (
    evaluate_project,
    evaluate_single_topic,
)
from app.services.evaluation.readability_service import evaluate_project_readability
from app.services.evaluation.geval_evaluation_service import (
    evaluate_project_geval,
    evaluate_single_topic_geval,
)
from app.services.evaluation.evaluation_doc_generator import generate_evaluation_document

def evaluation_dashboard_view(request, project_id):
    project = get_object_or_404(Project, id=project_id)
    reports = Report.objects.filter(project=project)

    selected_report = None
    report_eval = None
    topic_evals = None

    # GET eval_type
    eval_type = request.GET.get("eval_type", "openeval")

    try:
        report_id = request.GET.get("report_id")

        if report_id:
            selected_report = get_object_or_404(Report, id=report_id, project=project)

        # RUN EVALUATION
        if request.method == "POST":

            report_id = request.POST.get("report_id")
            action = request.POST.get("action")
            eval_type_post = request.POST.get("eval_type", "openeval")

            if not report_id:
                messages.error(request, "Please select a report.")
                return redirect("evaluation_dashboard_view", project_id=project.id)

            # READABILITY
            if action == "readability":
                evaluate_project_readability(project.id, report_id)

                messages.success(request, "Flesch-Kincaid readability computed.")

                return redirect(
                    f"{reverse('evaluation_dashboard_view', kwargs={'project_id': project.id})}?report_id={report_id}&eval_type={eval_type_post}"
                )

            # SWITCH ENGINE
            if eval_type_post == "geval":
                evaluate_project_geval(project.id, report_id)
                messages.success(request, "GEval evaluation completed.")
            else:
                evaluate_project(project.id, report_id)
                messages.success(request, "OpenEval evaluation completed.")

            return redirect(
                f"{reverse('evaluation_dashboard_view', kwargs={'project_id': project.id})}?report_id={report_id}&eval_type={eval_type_post}"
            )

        # LOAD RESULTS
        readability_scores = None
        readability_average = None
        geval_project_summary = None

        if selected_report:

            report_eval = ReportEvaluation.objects.filter(
                report=selected_report
            ).first()

            topic_evals = TopicEvaluation.objects.filter(
                topic__subsection__section__report=selected_report
            ).select_related("topic")
            if eval_type == "geval":
                topic_evals = topic_evals.filter(geval_scores__isnull=False)
            else:
                topic_evals = topic_evals.filter(scores__isnull=False)

            readability_scores = TopicReadability.objects.filter(
                report=selected_report
            ).select_related("topic")
            readability_average = readability_scores.aggregate(
                average=Avg("flesch_kincaid_grade")
            )["average"]

            # GEVAL CALCULATION
            project_overall_scores = []

            agg_correctness = []
            agg_relevance = []
            agg_hallucination = []
            agg_conciseness = []

            for eval_obj in topic_evals:

                if eval_type == "geval":
                    scores = eval_obj.geval_scores or {}
                else:
                    scores = eval_obj.scores or {}

                correctness = float(scores.get("correctness", 0))
                relevance = float(scores.get("relevance", 0))
                hallucination = float(scores.get("hallucination", 0))
                conciseness = float(scores.get("conciseness", 0))

                overall = (
                    correctness * 0.25
                    + relevance * 0.25
                    + hallucination * 0.25
                    + conciseness * 0.25
                )

                eval_obj.overall_score = round(overall, 2)
                eval_obj.display_scores = scores

                # collect for project aggregation
                project_overall_scores.append(overall)
                agg_correctness.append(correctness)
                agg_relevance.append(relevance)
                agg_hallucination.append(hallucination)
                agg_conciseness.append(conciseness)

            # PROJECT-LEVEL SUMMARY
            def safe_avg(arr):
                return round(sum(arr) / len(arr), 2) if arr else 0

            geval_project_summary = {
                "overall_score": safe_avg(project_overall_scores),
                "correctness": safe_avg(agg_correctness),
                "relevance": safe_avg(agg_relevance),
                "hallucination": safe_avg(agg_hallucination),
                "conciseness": safe_avg(agg_conciseness),
            }

        context = {
            "project": project,
            "reports": reports,
            "selected_report": selected_report,
            "report_eval": report_eval,
            "topic_evals": topic_evals,
            "readability_scores": readability_scores,
            "readability_average": readability_average,
            "geval_project_summary": geval_project_summary,
            "eval_type": eval_type,
        }

        return render(request, "evaluation/dashboard.html", context)

    except Exception as e:
        messages.error(request, f"Evaluation failed: {str(e)}")
        return redirect("evaluation_dashboard_view", project_id=project.id)


def reevaluate_topic_view(request, project_id, topic_id):
    project = get_object_or_404(Project, id=project_id)
    report_id = request.POST.get("report_id")
    eval_type = request.POST.get("eval_type", "openeval")

    if request.method != "POST" or not report_id:
        messages.error(request, "A report is required to re-evaluate a topic.")
        return redirect("evaluation_dashboard_view", project_id=project.id)

    report = get_object_or_404(Report, id=report_id, project=project)
    topic = get_object_or_404(
        Topic,
        id=topic_id,
        subsection__section__report=report,
    )

    try:
        if eval_type == "geval":
            evaluate_single_topic_geval(project, report, topic)
        else:
            evaluate_single_topic(project, report, topic)
        messages.success(request, f'Re-evaluated topic "{topic.title}".')
    except Exception as exc:
        messages.error(request, f"Topic re-evaluation failed: {exc}")

    dashboard_url = reverse(
        "evaluation_dashboard_view",
        kwargs={"project_id": project.id},
    )
    return redirect(
        f"{dashboard_url}?report_id={report.id}&eval_type={eval_type}"
    )


def export_evaluation_doc(request, project_id):

    report_id = request.GET.get("report_id")
    eval_type = request.GET.get("eval_type", "geval")

    if not report_id:
        return HttpResponse("Missing report_id", status=400)

    project = get_object_or_404(Project, id=project_id)
    report = get_object_or_404(Report, id=report_id, project=project)

    topic_evals = TopicEvaluation.objects.filter(
        topic__subsection__section__report=report
    ).select_related("topic")
    if eval_type == "geval":
        topic_evals = topic_evals.filter(geval_scores__isnull=False)
    else:
        topic_evals = topic_evals.filter(scores__isnull=False)

    buffer = generate_evaluation_document(
        report,
        topic_evals,
        eval_type=eval_type,
    )

    response = HttpResponse(
        buffer,
        content_type="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    )

    response["Content-Disposition"] = (
        f'attachment; filename="{eval_type}_evaluation_report_{report.id}.docx"'
    )

    return response
