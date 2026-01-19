from django.shortcuts import render, redirect
from django.contrib import messages
import psycopg2
from django.shortcuts import render, get_object_or_404

from .models import Project, DBConnection,Report, ReportOutline
from .forms import ProjectDBConnectionForm

from .forms import ReportIntentForm
from .models import Report, ReportOutline
from .services.report_outline_generator import generate_report_outline



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
from .services.vector_store import get_vector_store
from .services.metadata_to_documents import metadata_to_documents


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
        vector_store = get_vector_store()
        docs = metadata_to_documents(metadata_obj)

        vector_store.add_documents(docs)
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

def start_report(request, project_id):
    project = get_object_or_404(Project, id=project_id)

    if request.method == "POST":
        form = ReportIntentForm(request.POST)
        if form.is_valid():
            data = form.cleaned_data

            outline = generate_report_outline(data)

            report = Report.objects.create(
                project=project,
                title=outline["report_title"],
                industry=data["industry"],
                report_type=data["report_type"],
                audience=data["audience"],
                purpose=data["purpose"],
                focus_areas=data.get("focus_areas", ""),
                additional_notes=data.get("additional_notes", ""),
            )

            ReportOutline.objects.create(
                report=report,
                outline_json=outline,
            )

            return redirect("review_outline", report_id=report.id)
    else:
        form = ReportIntentForm()

    return render(
        request,
        "report_start.html",
        {"project": project, "form": form},
    )

def review_outline(request, report_id):
    report = get_object_or_404(Report, id=report_id)
    outline_obj = report.outline
    outline = outline_obj.outline_json

    if request.method == "POST":
        action = request.POST.get("action")

        # 🔹 Handle SAVE (edit only)
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

                updated_outline["sections"].append({
                    "section_title": section_title,
                    "subsections": subsections,
                })

                section_index += 1

            outline_obj.outline_json = updated_outline
            outline_obj.save()

            messages.success(request, "Outline updated successfully.")
            return redirect("review_outline", report_id=report.id)
        # 🔹 Handle APPROVE
        if action == "approve":
            outline_obj.approved = True
            outline_obj.save()

            report.status = "outline_approved"
            report.save()

            messages.success(request, "Outline approved.")
            return redirect("project_detail", project_id=report.project.id)

    return render(
        request,
        "report_outline_review.html",
        {
            "report": report,
            "outline": outline,
        },
    )

def generate_subsection_topics_view(request, report_id, section_title, subsection_title):
    report = get_object_or_404(Report, id=report_id)

    context = {
        "industry": report.industry,
        "report_type": report.report_type,
        "audience": report.audience,
        "purpose": report.purpose,
        "section_title": section_title,
        "subsection_title": subsection_title,
    }

    result = generate_subsection_topics(context)

    obj, _ = SubsectionTopics.objects.update_or_create(
        report=report,
        section_title=section_title,
        subsection_title=subsection_title,
        defaults={"topics_json": result}
    )

    return render(request, "subsection_topics_review.html", {
        "report": report,
        "topics": result["topics"],
        "section_title": section_title,
        "subsection_title": subsection_title,
    })



