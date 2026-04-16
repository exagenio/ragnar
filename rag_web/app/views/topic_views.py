
from app.models import (
    Report,
    TopicAnalysisPlan,
    Project,
    Report,
    Topic,
)
from app.agents.manager_agent import ManagerAgent
from app.utils.text import normalize_title
from django.shortcuts import get_object_or_404, render, redirect
from django.contrib import messages
import json

manager = ManagerAgent()

def generate_topic_analysis_plan_view(
    request,
    project_id,
    report_id,
    topic_id,
):

    project = get_object_or_404(Project, id=project_id)
    report = get_object_or_404(Report, id=report_id)
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

        return redirect(
            "subtopic_dashboard",
            project_id=project.id,
            report_id=report.id,
        )

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
    project = get_object_or_404(Project, id=project_id)
    report = get_object_or_404(Report, id=report_id)

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

    project = get_object_or_404(Project, id=project_id)
    report = get_object_or_404(Report, id=report_id)
    topic = get_object_or_404(Topic, id=topic_id, report=report)

    try:
        content_obj = manager.content_agent.get_topic_content(topic)
    except ValueError as e:
        return render(request, "error.html", {"message": str(e)})

    if request.method == "POST":

        action = request.POST.get("action")

        if action == "generate":

            content_obj = manager.generate_topic_content(
                project,
                report,
                topic,
                content_obj,
            )

            messages.success(
                request,
                f"Content generation iteration {content_obj.iteration_count} completed.",
            )

            return redirect(request.path)

        if action == "regenerate":

            existing_content = content_obj.content_json or {}

            # Preserve SQL placeholders
            preserved_sql = existing_content.get("precomputed_sql_placeholders", [])

            # Reset content BUT keep SQL placeholders
            content_obj.content_json = {
                "sections": [],
                "element_progress": {},
                "completed_elements": [],
                "limitations": [],
                "status": "in_progress",
                "precomputed_sql_placeholders": preserved_sql,
            }
            content_obj.iteration_count = 0
            content_obj.status = "draft"
            content_obj.save()

            # Generate fresh content
            content_obj = manager.generate_topic_content(
                project,
                report,
                topic,
                content_obj,
            )

            messages.success(request, "Topic content regenerated successfully.")

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
        },
    )
