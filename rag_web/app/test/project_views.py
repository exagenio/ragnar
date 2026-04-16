from django.shortcuts import render, redirect
from django.contrib import messages
from django.shortcuts import render, get_object_or_404
from app.forms import ReportIntentForm
from ..models import (Report, Project)
from app.agents.manager_agent import ManagerAgent

manager = ManagerAgent()
def start_report(request, project_id):

    project = get_object_or_404(Project, id=project_id)

    if request.method == "POST":

        form = ReportIntentForm(request.POST)

        if form.is_valid():

            data = form.cleaned_data

            report = manager.start_report(project, data)

            return redirect("review_outline", report_id=report.id)

    else:
        form = ReportIntentForm()

    return render(
        request,
        "report_start.html",
        {
            "project": project,
            "form": form,
        },
    )


def review_outline(request, report_id):

    report = get_object_or_404(Report, id=report_id)
    outline_obj = report.outline
    outline = outline_obj.outline_json

    if request.method == "POST":

        action = request.POST.get("action")

        # SAVE
        if action == "save":

            updated_outline = {
                "report_title": request.POST.get("report_title", "").strip(),
                "sections": [],
            }

            section_index = 0

            while f"section_title_{section_index}" in request.POST:

                section_title = request.POST.get(
                    f"section_title_{section_index}", ""
                ).strip()

                if not section_title:
                    section_index += 1
                    continue

                subsections = []
                sub_index = 0

                while f"sub_{section_index}_{sub_index}" in request.POST:

                    sub_value = request.POST.get(
                        f"sub_{section_index}_{sub_index}", ""
                    ).strip()

                    if sub_value:
                        subsections.append(sub_value)

                    sub_index += 1

                updated_outline["sections"].append(
                    {
                        "section_title": section_title,
                        "subsections": subsections,
                    }
                )

                section_index += 1

            manager.update_outline(outline_obj, updated_outline)

            messages.success(request, "Outline updated successfully.")

            return redirect("review_outline", report_id=report.id)

        # APPROVE
        if action == "approve":

            manager.approve_outline(report)

            messages.success(
                request,
                "Outline approved and sections created.",
            )

            return redirect(
                "subtopic_dashboard",
                project_id=report.project.id,
                report_id=report.id,
            )

    return render(
        request,
        "report_outline_review.html",
        {
            "report": report,
            "outline": outline,
        },
    )
