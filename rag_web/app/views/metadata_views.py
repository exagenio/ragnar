from django.shortcuts import render, redirect
from django.contrib import messages
from django.shortcuts import render, get_object_or_404
from django.urls import reverse
from ..models import (
    Project,
)
from ..forms import ProjectDBConnectionForm
from ..forms import TableSelectionForm
from ..models import (
    TableMetadata,
)


def get_manager():
    from app.agents.manager_agent import ManagerAgent
    return ManagerAgent()


def create_project_and_connect_db(request):
    manager = get_manager()

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
    metadata_items = list(project.metadata.all())
    metadata_ready = bool(metadata_items) and all(
        item.status == "approved" for item in metadata_items
    )

    return render(
        request,
        "project_detail.html",
        {
            "project": project,
            "reports": reports,
            "metadata_ready": metadata_ready,
        },
    )


def select_tables(request, project_id):
    manager = get_manager()

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
    manager = get_manager()

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
            "schema_info": schema_info["tables"],
            "relationships": schema_info["relationships"],
        },
    )


def row_sampling(request, project_id):
    manager = get_manager()

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
    manager = get_manager()

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
            "task": result.get("task"),
        },
    )


def review_metadata(request, project_id, table_name):
    manager = get_manager()

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
            generated_columns = metadata_obj.generated_metadata.get("columns", {})
            for col_name, col_data in generated_columns.items():
                description = request.POST.get(f"column__{col_name}", "")

                if isinstance(col_data, str):
                    columns[col_name] = {
                        "description": description,
                        "semantic_role": "unknown",
                        "entity_type": None,
                        "relationships": [],
                    }
                    continue

                columns[col_name] = {
                    **col_data,
                    "description": description,
                }

            table_relationships = []
            generated_relationships = metadata_obj.generated_metadata.get(
                "table_relationships",
                [],
            )
            for index, relationship in enumerate(generated_relationships):
                description = request.POST.get(
                    f"relationship__{index}",
                    relationship.get("description", ""),
                )
                table_relationships.append(
                    {
                        **relationship,
                        "description": description,
                    }
                )

            confidence_notes_raw = request.POST.get("confidence_notes", "")

            confidence_notes = [
                line.strip("- ").strip()
                for line in confidence_notes_raw.splitlines()
                if line.strip()
            ]

            manager.approve_table_metadata(
                metadata_obj,
                table_description,
                table_relationships,
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
