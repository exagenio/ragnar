from app.agents.manager_agent import ManagerAgent
from django.contrib import messages
from django.http import HttpResponse, JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from app.models import (
    BackgroundTask,
    Project,
    Report,
    Section,
    SubSection,
)
from app.services.document_export_job import create_document_export_task
from app.views.access import get_user_project, get_user_report

def get_manager():
    return ManagerAgent()

def generate_subsection_content_view(
    request,
    project_id,
    report_id,
    subsection_id,
):
    manager = get_manager()

    project = get_user_project(request.user, project_id)
    report = get_user_report(request.user, report_id, project)
    subsection = get_object_or_404(SubSection, id=subsection_id, report=report)

    try:
        topics = manager.validate_subsection_generation(subsection)
    except ValueError as e:
        return render(request, "error.html", {"message": str(e)})

    content_obj = manager.get_subsection_content(subsection)

    if request.method == "POST":

        action = request.POST.get("action")

        if action == "generate":

            content_obj = manager.generate_subsection_content(
                project,
                report,
                subsection,
                topics,
                content_obj,
            )

            messages.success(
                request,
                "Subsection content generated successfully.",
            )

            return redirect(request.path)

        if action == "regenerate":

            # Reset content
            content_obj.content_json = {}
            content_obj.status = "pending"
            content_obj.save()

            # Regenerate
            content_obj = manager.generate_subsection_content(
                project,
                report,
                subsection,
                topics,
                content_obj,
            )

            messages.success(request, "Subsection content regenerated successfully.")
            return redirect(request.path)

    return render(
        request,
        "subsection_content_generation.html",
        {
            "project": project,
            "report": report,
            "subsection": subsection,
            "content": content_obj,
        },
    )


def generate_section_content_view(
    request,
    project_id,
    report_id,
    section_id,
):
    manager = get_manager()

    project = get_user_project(request.user, project_id)
    report = get_user_report(request.user, report_id, project)
    section = get_object_or_404(Section, id=section_id, report=report)

    try:
        subsections = manager.validate_section_generation(section)
    except ValueError as e:
        return render(request, "error.html", {"message": str(e)})

    content_obj = manager.get_section_content(section)

    if request.method == "POST":

        action = request.POST.get("action")

        if action == "generate":

            content_obj = manager.generate_section_content(
                project,
                report,
                section,
                subsections,
                content_obj,
            )

            messages.success(
                request,
                "Section content generated successfully.",
            )

            return redirect(request.path)

        if action == "regenerate":

            content_obj.content_json = {}
            content_obj.status = "pending"
            content_obj.save()

            content_obj = manager.generate_section_content(
                project,
                report,
                section,
                subsections,
                content_obj,
            )

            messages.success(request, "Section content regenerated successfully.")
            return redirect(request.path)

    return render(
        request,
        "section_content_generation.html",
        {
            "project": project,
            "report": report,
            "section": section,
            "content": content_obj,
        },
    )


def generate_document_view(request, project_id, report_id):
    project = get_user_project(request.user, project_id)
    report = get_user_report(request.user, report_id, project)

    try:
        task = create_document_export_task(
            project=project,
            report=report,
        )

        messages.success(
            request,
            "Document export started in the background. You can track it live from the task page.",
        )
        return redirect("background_task_detail", task_id=task.id)

    except Exception as e:

        messages.error(request, f"Error generating document: {str(e)}")

        return redirect(
            "subtopic_dashboard",
            project_id=project.id,
            report_id=report.id,
        )


def trigger_auto_generate_subsection(request, project_id, report_id, subsection_id):
    manager = get_manager()

    project = get_user_project(request.user, project_id)
    report = get_user_report(request.user, report_id, project)
    subsection = get_object_or_404(SubSection, id=subsection_id, report=report)

    if request.POST.get("action") == "re_auto_generate":
        has_auto_generated_topics = (
            subsection.topics.exists()
            and BackgroundTask.objects.filter(
                topic__subsection=subsection,
                task_type="topic_pipeline",
            ).exists()
        )

        if not has_auto_generated_topics:
            messages.warning(
                request,
                "Re auto generation is available only after auto generation has created topics for this subsection.",
            )
            return redirect(
                "view_topics",
                project_id=project_id,
                report_id=report_id,
                subsection_id=subsection_id,
            )

        started = manager.re_auto_generate_subsection(project, report, subsection)
        if started:
            messages.success(
                request,
                "Existing generated data was reset. Re auto generation started in the background.",
            )
        else:
            messages.info(request, "This subsection is already generating.")

        return redirect(
            "subtopic_dashboard",
            project_id=project_id,
            report_id=report_id,
        )

    started = manager.trigger_subsection_auto_generation(
        project,
        report,
        subsection,
    )

    return JsonResponse(
        {
            "started": bool(started),
            "task_id": started.id if started else None,
        }
    )


