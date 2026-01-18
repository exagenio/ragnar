from django.shortcuts import render, redirect
from django.contrib import messages
import psycopg2
from django.shortcuts import render, get_object_or_404

from .models import Project, DBConnection
from .forms import ProjectDBConnectionForm


def create_project_and_connect_db(request):
    if request.method == "POST":
        form = ProjectDBConnectionForm(request.POST)

        if form.is_valid():
            data = form.cleaned_data

            # 🔹 1. Test DB connection FIRST
            try:
                psycopg2.connect(
                    host=data["host"],
                    port=data["port"],
                    dbname=data["database_name"],
                    user=data["username"],
                    password=data["password"],
                )
            except Exception as e:
                messages.error(request, f"Database connection failed: {e}")
                return render(request, "project_create.html", {"form": form})

            # 🔹 2. Create Project
            project = Project.objects.create(
                name=data["project_name"],
                description=data["project_description"],
                is_initialized=False,
            )

            # 🔹 3. Create DBConnection
            DBConnection.objects.create(
                project=project,
                db_type=data["db_type"],
                host=data["host"],
                port=data["port"],
                database_name=data["database_name"],
                username=data["username"],
                password=data["password"],
                schema=data["schema"],
                is_active=True,
            )

            messages.success(
                request, "Project created and database connected successfully."
            )
            return redirect("project_detail", project_id=project.id)

    else:
        form = ProjectDBConnectionForm()

    return render(request, "project_create.html", {"form": form})


def project_detail(request, project_id):
    project = get_object_or_404(Project, id=project_id)

    return render(request, "project_detail.html", {"project": project})


from .models import Project, SelectedTable
from .services.schema_introspector import get_tables
from .forms import TableSelectionForm
from django.shortcuts import get_object_or_404


def select_tables(request, project_id):
    project = get_object_or_404(Project, id=project_id)
    db_conn = project.db_connection

    # 🔹 Discover tables dynamically
    tables = get_tables(db_conn)
    table_choices = [(t, t) for t in tables]

    if request.method == "POST":
        form = TableSelectionForm(request.POST, table_choices=table_choices)
        if form.is_valid():
            selected = form.cleaned_data["tables"]

            # Clear old selections
            SelectedTable.objects.filter(project=project).delete()

            # Save new selections
            for table in selected:
                SelectedTable.objects.create(project=project, table_name=table)

            project.is_initialized = True
            project.save()

            return redirect("project_detail", project_id=project.id)

    else:
        form = TableSelectionForm(table_choices=table_choices)

    return render(request, "select_tables.html", {"project": project, "form": form})


from django.shortcuts import render, get_object_or_404
from .models import Project, SelectedTable
from .services.column_introspector import get_table_columns


def column_introspection(request, project_id):
    project = get_object_or_404(Project, id=project_id)

    # Safety check
    if not project.is_initialized:
        return render(
            request, "error.html", {"message": "Project is not initialized yet."}
        )

    db_conn = project.db_connection
    selected_tables = SelectedTable.objects.filter(project=project)

    schema_info = []

    for table in selected_tables:
        columns = get_table_columns(db_conn, table.table_name)
        schema_info.append({"table_name": table.table_name, "columns": columns})

    return render(
        request,
        "column_introspection.html",
        {"project": project, "schema_info": schema_info},
    )


from .services.row_sampler import sample_table_rows


def row_sampling(request, project_id):
    project = get_object_or_404(Project, id=project_id)

    if not project.is_initialized:
        return render(
            request, "error.html", {"message": "Project is not initialized yet."}
        )

    db_conn = project.db_connection
    selected_tables = SelectedTable.objects.filter(project=project)

    sampled_data = []

    for table in selected_tables:
        rows = sample_table_rows(db_conn, table.table_name, limit=10)
        sampled_data.append({"table_name": table.table_name, "rows": rows})

    return render(
        request, "row_sampling.html", {"project": project, "sampled_data": sampled_data}
    )


from .services.llm_metadata_generator import generate_table_metadata
from .services.column_introspector import get_table_columns
from .services.row_sampler import sample_table_rows
from .services.background_tasks import run_in_background
from .services.metadata_job import run_metadata_generation

def metadata_generation(request, project_id):
    project = get_object_or_404(Project, id=project_id)

    if not project.is_initialized:
        return render(request, "error.html", {
            "message": "Project is not initialized yet."
        })

    run_in_background(run_metadata_generation, project.id)

    return render(
        request,
        "metadata_preview.html",
        {
            "project": project,
            "metadata_results": [],
            "message": "Metadata generation started in background. Please wait."
        }
    )

from .models import TableMetadata
import json


def review_metadata(request, project_id, table_name):
    project = get_object_or_404(Project, id=project_id)
    metadata_obj = get_object_or_404(
        TableMetadata, project=project, table_name=table_name
    )

    if request.method == "POST":
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

        approved_metadata = {
            "table_description": table_description,
            "columns": columns,
            "confidence_notes": confidence_notes,
        }

        metadata_obj.approved_metadata = approved_metadata
        metadata_obj.status = "approved"
        metadata_obj.save()

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
