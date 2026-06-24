from app.agents.manager_agent import ManagerAgent
from django.contrib import messages
from django.shortcuts import get_object_or_404, redirect, render
from app.models import (
    BackgroundTask,
    Project,
    Report,
    Section,
    SubSection,
)

def get_manager():
    return ManagerAgent()


def generate_topics(request, project_id, report_id, subsection_id):
    manager = get_manager()

    report = get_object_or_404(Report, id=report_id)
    subsection = get_object_or_404(SubSection, id=subsection_id, report=report)
    section = subsection.section

    if not report.outline_approved:
        return render(
            request,
            "error.html",
            {"message": "Outline must be approved before generating topics."},
        )

    if request.method == "POST":

        action = request.POST.get("action")

        submitted_titles = []
        index = 0

        while f"topic_{index}" in request.POST:
            value = request.POST.get(f"topic_{index}", "").strip()
            if value:
                submitted_titles.append(value)
            index += 1

        manager.save_topics(report, subsection, submitted_titles)

        if action == "save":

            messages.success(request, "Topics saved successfully.")

            return redirect(
                "generate_topics",
                project_id=project_id,
                report_id=report_id,
                subsection_id=subsection.id,
            )

        if action == "approve":

            manager.approve_topics(subsection, section)

            messages.success(request, "Topics approved.")

            return redirect(
                "view_topics",
                project_id=project_id,
                report_id=report_id,
                subsection_id=subsection.id,
            )

    should_generate = False

    if request.method == "GET" and not subsection.topics.exists():
        should_generate = True

    if request.method == "POST" and request.POST.get("action") == "regenerate":
        should_generate = True
        subsection.topics.all().delete()

    if should_generate:

        manager.generate_topics(
            report,
            subsection,
            section,
            project_id,
        )

    topics = subsection.topics.order_by("created_at")

    return render(
        request,
        "topics_review.html",
        {
            "project": report.project,
            "report": report,
            "section": section,
            "subsection": subsection,
            "topics": topics,
        },
    )


def subtopic_dashboard(request, project_id, report_id):
    project = get_object_or_404(Project, id=project_id)
    report = get_object_or_404(Report, id=report_id)

    sections = (
        Section.objects.filter(report=report)
        .prefetch_related("sub_sections__topics")
        .order_by("created_at")
    )

    # Check if all subsections have generated content for each section
    for section in sections:
        subsections = section.sub_sections.all()
        section.all_subsections_have_content = (
            all(
                hasattr(subsection, "content")
                and subsection.content.status == "generated"
                for subsection in subsections
            )
            if subsections.exists()
            else False
        )

    return render(
        request,
        "subtopic_dashboard.html",
        {
            "project": project,
            "report": report,
            "sections": sections,
        },
    )


def view_topics(request, project_id, report_id, subsection_id):
    project = get_object_or_404(Project, id=project_id)
    report = get_object_or_404(Report, id=report_id)
    subsection = get_object_or_404(SubSection, id=subsection_id, report=report)

    topics = subsection.topics.filter(is_approved=True)
    has_auto_generated_topics = (
        topics.exists()
        and BackgroundTask.objects.filter(
            topic__in=topics,
            task_type="topic_pipeline",
        ).exists()
    )

    # Check if all topics have generated content
    all_topics_have_content = all(
        hasattr(topic, "content") and topic.content.status == "generated"
        for topic in topics
    )

    return render(
        request,
        "topics_list.html",
        {
            "project": project,
            "report": report,
            "subsection": subsection,
            "topics": topics,
            "all_topics_have_content": all_topics_have_content,
            "has_auto_generated_topics": has_auto_generated_topics,
        },
    )

