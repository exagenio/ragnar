from django.shortcuts import render, redirect
from django.contrib import messages
from django.http import HttpResponse
from django.shortcuts import render, get_object_or_404
from app.models import (
    Project,
    Report,
    Section,
    SubSection,
)
from django.http import JsonResponse
from django.shortcuts import get_object_or_404, render, redirect
from django.contrib import messages
from app.services.document_export_job import create_document_export_task

def get_manager():
    from app.agents.manager_agent import ManagerAgent
    return ManagerAgent()

def generate_subsection_content_view(
    request,
    project_id,
    report_id,
    subsection_id,
):
    manager = get_manager()

    project = get_object_or_404(Project, id=project_id)
    report = get_object_or_404(Report, id=report_id)
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

    project = get_object_or_404(Project, id=project_id)
    report = get_object_or_404(Report, id=report_id)
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
    project = get_object_or_404(Project, id=project_id)
    report = get_object_or_404(Report, id=report_id)

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

    project = get_object_or_404(Project, id=project_id)
    report = get_object_or_404(Report, id=report_id)
    subsection = get_object_or_404(SubSection, id=subsection_id)

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
