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
                return render(
                    request,
                    "project_create.html",
                    {"form": form}
                )

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

            messages.success(request, "Project created and database connected successfully.")
            return redirect("project_detail", project_id=project.id)

    else:
        form = ProjectDBConnectionForm()

    return render(
        request,
        "project_create.html",
        {"form": form}
    )


def project_detail(request, project_id):
    project = get_object_or_404(Project, id=project_id)

    return render(
        request,
        "project_detail.html",
        {"project": project}
    )

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
                SelectedTable.objects.create(
                    project=project,
                    table_name=table
                )

            project.is_initialized = True
            project.save()

            return redirect("project_detail", project_id=project.id)

    else:
        form = TableSelectionForm(table_choices=table_choices)

    return render(
        request,
        "select_tables.html",
        {
            "project": project,
            "form": form
        }
    )
