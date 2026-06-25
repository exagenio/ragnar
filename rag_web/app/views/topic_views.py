from app.agents.manager_agent import ManagerAgent
from app.models import Project, Report, Topic, TopicAnalysisPlan
from app.services.task_tracker import has_running_task
from app.services.topic_content_job import create_topic_content_task
from app.views.access import get_user_project, get_user_report
from django.shortcuts import get_object_or_404, redirect, render
from django.contrib import messages
import json

from app.utils.text import normalize_title

def get_manager():
    return ManagerAgent()

def generate_topic_analysis_plan_view(
    request,
    project_id,
    report_id,
    topic_id,
):
    manager = get_manager()

    project = get_user_project(request.user, project_id)
    report = get_user_report(request.user, report_id, project)
    topic = get_object_or_404(Topic, id=topic_id, report=report)

    if request.method == "POST":

        action = request.POST.get("action")

        plan_obj = get_object_or_404(
            TopicAnalysisPlan,
            report=report,
            topic=topic,
        )

        try:
            manager.update_topic_analysis_plan(
                plan_obj,
                topic,
                request.POST,
                approve=(action == "approve"),
            )

        except json.JSONDecodeError:
            messages.error(request, "Invalid JSON in data requirements.")
            return redirect(request.path)

        if action == "approve":
            messages.success(request, "Topic analysis plan approved.")
            return redirect(
                "topic_content",
                project_id=project.id,
                report_id=report.id,
                topic_id=topic.id,
            )

        messages.success(request, "Topic analysis plan saved.")
        return redirect(request.path)

    plan_obj = manager.generate_topic_analysis_plan(
        project,
        report,
        topic,
    )

    plan = plan_obj.plan_json

    return render(
        request,
        "topic_analysis_plan_review.html",
        {
            "project": project,
            "report": report,
            "topic": topic,
            "plan": plan,
            "data_requirements_json": json.dumps(
                plan.get("data_requirements", []),
                indent=2,
            ),
            "is_approved": plan_obj.is_approved,
        },
    )

def topic_overview(request, project_id, report_id):
    project = get_user_project(request.user, project_id)
    report = get_user_report(request.user, report_id, project)

    outline = report.outline.outline_json

    # Approved topics
    subsection_topics_qs = SubsectionTopics.objects.filter(
        report=report, is_approved=True
    )

    # Build normalized lookup
    subsection_topic_map = {}
    for obj in subsection_topics_qs:
        key = (
            normalize_title(obj.section_title)
            + "|||"
            + normalize_title(obj.subsection_title)
        )
        subsection_topic_map[key] = obj.topics_json.get("topics", [])

    # Enrich outline with topics
    for section in outline["sections"]:
        for i, subsection in enumerate(section["subsections"]):
            key = (
                normalize_title(section["section_title"])
                + "|||"
                + normalize_title(subsection)
            )

            section["subsections"][i] = {
                "title": subsection,
                "topics": subsection_topic_map.get(key, []),
            }

    return render(
        request,
        "topic_overview.html",
        {
            "project": project,
            "report": report,
            "outline": outline,
        },
    )

def generate_topic_content_view(
    request,
    project_id,
    report_id,
    topic_id,
):
    manager = get_manager()

    project = get_user_project(request.user, project_id)
    report = get_user_report(request.user, report_id, project)
    topic = get_object_or_404(Topic, id=topic_id, report=report)

    try:
        content_obj = manager.content_agent.get_topic_content(topic)
    except ValueError as e:
        return render(request, "error.html", {"message": str(e)})

    is_generating = has_running_task(task_type="topic_pipeline", topic=topic)

    if request.method == "POST":

        action = request.POST.get("action")

        if action in {"generate", "regenerate"}:
            if is_generating:
                messages.warning(
                    request,
                    "Topic content generation is already running.",
                )
            else:
                create_topic_content_task(
                    project,
                    report,
                    topic,
                    regenerate=(action == "regenerate"),
                )
                messages.success(
                    request,
                    "Topic content generation started in the background.",
                )

            return redirect(request.path)

        if action == "compute_visual":

            try:
                manager.compute_visual_block(
                    project,
                    report,
                    topic,
                    content_obj,
                    int(request.POST.get("section_index")),
                    int(request.POST.get("block_index")),
                )

                messages.success(request, "Visual data prepared successfully.")

            except ValueError as e:
                messages.error(request, str(e))

            return redirect(request.path)

    limitations = (
        content_obj.content_json.get("limitations", [])
        if content_obj.content_json
        else []
    )

    return render(
        request,
        "topic_content_generation.html",
        {
            "project": project,
            "report": report,
            "topic": topic,
            "content": content_obj,
            "limitations": limitations,
            "is_generating": is_generating,
        },
    )

