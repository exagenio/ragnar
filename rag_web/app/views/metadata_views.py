from django.shortcuts import render, redirect
from django.contrib import messages
from django.shortcuts import render, get_object_or_404
from django.urls import reverse
from ..models import (
    Project,
)
from ..forms import ProjectDBConnectionForm
from ..forms import TableSelectionForm
from app.agents.manager_agent import ManagerAgent
from ..models import (
    TableMetadata,
)


manager = ManagerAgent()


def create_project_and_connect_db(request):

    if request.method == "POST":
        form = ProjectDBConnectionForm(request.POST)

        if form.is_valid():
            data = form.cleaned_data

            try:
                project = manager.create_project_with_database(data)

                messages.success(
                    request,
                    "Project created and database connected successfully.",
                )

                return redirect("project_detail", project_id=project.id)

            except Exception as e:
                messages.error(request, f"Database connection failed: {e}")

    else:
        form = ProjectDBConnectionForm()

    return render(
        request,
        "project_create.html",
        {
            "form": form,
            "provider_model_map": ProjectDBConnectionForm.provider_model_map,
        },
    )


def project_detail(request, project_id):
    project = get_object_or_404(Project, id=project_id)
    reports = project.reports.all()
    return render(
        request,
        "project_detail.html",
        {
            "project": project,
            "reports": reports,
        },
    )


def select_tables(request, project_id):

    project = get_object_or_404(Project, id=project_id)

    db_conn = project.db_connection

    tables = manager.discover_tables(db_conn)

    table_choices = [(t, t) for t in tables]

    if request.method == "POST":

        form = TableSelectionForm(request.POST, table_choices=table_choices)

        if form.is_valid():

            selected = form.cleaned_data["tables"]

            manager.save_selected_tables(project, selected)

            return redirect("project_detail", project_id=project.id)

    else:
        form = TableSelectionForm(table_choices=table_choices)

    return render(
        request,
        "select_tables.html",
        {
            "project": project,
            "form": form,
        },
    )


def column_introspection(request, project_id):

    project = get_object_or_404(Project, id=project_id)

    try:
        schema_info = manager.get_schema_info(project)

    except ValueError as e:
        return render(request, "error.html", {"message": str(e)})

    return render(
        request,
        "column_introspection.html",
        {
            "project": project,
            "schema_info": schema_info,
        },
    )


def row_sampling(request, project_id):

    project = get_object_or_404(Project, id=project_id)

    try:
        sampled_data = manager.sample_table_rows(project, limit=10)

    except ValueError as e:
        return render(request, "error.html", {"message": str(e)})

    return render(
        request,
        "row_sampling.html",
        {
            "project": project,
            "sampled_data": sampled_data,
        },
    )


def metadata_generation(request, project_id):

    project = get_object_or_404(Project, id=project_id)

    try:
        result = manager.start_metadata_generation(project)

    except ValueError as e:
        return render(request, "error.html", {"message": str(e)})

    return render(
        request,
        "metadata_preview.html",
        {
            "project": project,
            "metadata_results": [],
            "message": result["message"],
        },
    )


def review_metadata(request, project_id, table_name):

    project = get_object_or_404(Project, id=project_id)

    metadata_obj = get_object_or_404(
        TableMetadata,
        project=project,
        table_name=table_name,
    )

    if request.method == "POST":

        action = request.POST.get("action")

        if action == "regenerate":
            return redirect(
                reverse(
                    "metadata_generation",
                    kwargs={"project_id": project.id},
                )
            )

        if action == "approve":

            table_description = request.POST.get("table_description")

            columns = {}
            for key, value in request.POST.items():
                if key.startswith("column__"):
                    col_name = key.replace("column__", "")
                    columns[col_name] = value

            confidence_notes_raw = request.POST.get("confidence_notes", "")

            confidence_notes = [
                line.strip("- ").strip()
                for line in confidence_notes_raw.splitlines()
                if line.strip()
            ]

            manager.approve_table_metadata(
                metadata_obj,
                table_description,
                columns,
                confidence_notes,
            )

            return redirect("project_detail", project_id=project.id)

    return render(
        request,
        "review_metadata.html",
        {
            "project": project,
            "table_name": table_name,
            "metadata": metadata_obj,
        },
    )
