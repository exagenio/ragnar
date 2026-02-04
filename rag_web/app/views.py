from django.shortcuts import render, redirect
from django.contrib import messages
import psycopg2
from django.shortcuts import render, get_object_or_404
from django.utils.text import slugify
from app.services.sql_agent import generate_sql_from_placeholder
from app.services.sql_executor import execute_sql_safely
from django.urls import reverse


from .models import (
    Project,
    DBConnection,
    Report,
    ReportOutline,
    SelectedTable,
    Section,
    SubSection,
    Topic,
)
from .forms import ProjectDBConnectionForm

from .forms import ReportIntentForm, TableSelectionForm
from .models import (
    Report,
    ReportOutline,
    TopicAnalysisPlan,
    Section,
    SubSection,
    TopicContent,
    SubSectionContent,
    SectionContent,
)
from .services.report_outline_generator import generate_report_outline
from .services.subsection_topic_generator import generate_subsection_topics
from .services.topic_analysis_plan_generator import generate_topic_analysis_plan
from .services.sub_section_content_generator import generate_subsection_content
from .services.section_content_generator import generate_section_content

from .services.schema_introspector import get_tables
from .services.column_introspector import get_table_columns
from app.services.sql_result_interpreter import interpret_sql_result
from app.services.visual_agent import generate_visual_plan
from app.services.visual_renderer import render_visual
from app.services.sql_agent import generate_sql_from_visual_plan
from pathlib import Path
from django.conf import settings


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
        return render(
            request, "error.html", {"message": "Project is not initialized yet."}
        )
    print("\n_______metadata generation started______\n")
    run_in_background(run_metadata_generation, project.id)
    return render(
        request,
        "metadata_preview.html",
        {
            "project": project,
            "metadata_results": [],
            "message": "Metadata generation started in background. Please wait.",
        },
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
        action = request.POST.get("action")

        if action == "regenerate":
            return redirect(
                reverse("metadata_generation", kwargs={"project_id": project.id})
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

                updated_outline["sections"].append(
                    {
                        "section_title": section_title,
                        "subsections": subsections,
                    }
                )

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
            report.outline_approved = True
            report.save()

            outline_data = outline_obj.outline_json

            # Create Sections & SubSections
            for section_data in outline_data.get("sections", []):
                section_title = section_data.get("section_title", "").strip()
                if not section_title:
                    continue
                section_obj, _ = Section.objects.get_or_create(
                    report=report, title=section_title, is_sub_sec_appvroved=True
                )
                for subsection_title in section_data.get("subsections", []):
                    subsection_title = subsection_title.strip()
                    if not subsection_title:
                        continue

                    SubSection.objects.get_or_create(
                        section=section_obj, title=subsection_title, report=report
                    )

            messages.success(request, "Outline approved and sections created.")

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


from django.shortcuts import get_object_or_404, redirect, render
from django.contrib import messages
from .models import Report, Section, SubSection, Topic
from .services.subsection_topic_generator import generate_subsection_topics


def generate_topics(request, project_id, report_id, subsection_id):
    report = get_object_or_404(Report, id=report_id)
    subsection = get_object_or_404(SubSection, id=subsection_id, report=report)
    section = subsection.section

    if not report.outline_approved:
        return render(
            request,
            "error.html",
            {"message": "Outline must be approved before generating topics."},
        )

    # ==========================
    # POST → Save / Approve
    # ==========================
    if request.method == "POST":
        action = request.POST.get("action")

        submitted_titles = []
        index = 0
        while f"topic_{index}" in request.POST:
            value = request.POST.get(f"topic_{index}", "").strip()
            if value:
                submitted_titles.append(value)
            index += 1

        # Existing topics
        existing_topics = {t.title: t for t in subsection.topics.all()}

        # Delete removed topics
        for title, topic_obj in existing_topics.items():
            if title not in submitted_titles:
                topic_obj.delete()

        # Create / update topics
        for title in submitted_titles:
            Topic.objects.update_or_create(
                subsection=subsection,
                report=report,
                title=title,
                defaults={"is_approved": False},
            )

        # SAVE
        if action == "save":
            messages.success(request, "Topics saved successfully.")
            return redirect(
                "generate_topics",
                project_id=project_id,
                report_id=report_id,
                subsection_id=subsection.id,
            )

        # APPROVE
        if action == "approve":
            Topic.objects.filter(subsection=subsection).update(is_approved=True)
            subsection.is_topics_approved = True
            subsection.save()

            section.is_sub_sec_appvroved = True
            section.save()

            messages.success(request, "Topics approved.")
            return redirect(
                "subtopic_dashboard",
                project_id=project_id,
                report_id=report_id,
            )
        

    # ==========================
    # GET → Generate if empty
    # ==========================
    should_generate = False

    if request.method == "GET" and not subsection.topics.exists():
        should_generate = True

    if request.method == "POST" and request.POST.get("action") == "regenerate":
        should_generate = True
        subsection.topics.all().delete()

    if should_generate:
        context = {
            "industry": report.industry,
            "report_type": report.report_type,
            "audience": report.audience,
            "purpose": report.purpose,
            "section_title": section.title,
            "subsection_title": subsection.title,
        }

        result = generate_subsection_topics(
            context=context,
            project_id=project_id
        )

        for topic_title in result.get("topics", []):
            Topic.objects.create(
                subsection=subsection,
                report=report,
                title=topic_title,
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
        section.all_subsections_have_content = all(
            hasattr(subsection, 'content') and subsection.content.status == 'generated'
            for subsection in subsections
        ) if subsections.exists() else False

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

    # Check if all topics have generated content
    all_topics_have_content = all(
        hasattr(topic, 'content') and topic.content.status == 'generated'
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
        },
    )


def generate_topic_analysis_plan_view(
    request,
    project_id,
    report_id,
    topic_id,
):
    project = get_object_or_404(Project, id=project_id)
    report = get_object_or_404(Report, id=report_id)
    topic = get_object_or_404(Topic, id=topic_id, report=report)

    subsection = topic.subsection
    section = subsection.section

    # 🔹 Collect DB schema info
    tables = SelectedTable.objects.filter(project=project)

    schema_context = []
    for t in tables:
        columns = get_table_columns(project.db_connection, t.table_name)
        schema_context.append(
            {
                "table": t.table_name,
                "columns": [
                    {"name": col["name"], "type": col["type"]} for col in columns
                ],
            }
        )

    # ==========================
    # POST → Approve existing plan
    # ==========================
    print("request method = ", request.method)
    if request.method == "POST":
        action = request.POST.get("action")

        plan_obj = get_object_or_404(
            TopicAnalysisPlan,
            report=report,
            topic=topic,
        )

        # 🔹 Rebuild edited plan JSON
        plan = plan_obj.plan_json.copy()

        plan["intent"] = request.POST.get("intent", "").strip()

        def collect_list(prefix):
            items = []
            i = 0
            while f"{prefix}_{i}" in request.POST:
                val = request.POST.get(f"{prefix}_{i}", "").strip()
                if val:
                    items.append(val)
                i += 1
            return items

        plan["required_elements"] = collect_list("required_elements")
        plan["business_questions"] = collect_list("business_questions")
        plan["visual_requirements"] = collect_list("visual_requirements")

        try:
            plan["data_requirements"] = json.loads(
                request.POST.get("data_requirements", "[]")
            )
        except json.JSONDecodeError:
            messages.error(request, "Invalid JSON in data requirements.")
            return redirect(request.path)

        plan_obj.plan_json = plan

        if action == "approve":
            print("start approval")
            plan_obj.is_approved = True
            topic.is_approved = True
            topic.save()
            print("comes to this point new 1")
        plan_obj.save()
        print("comes to this point")
        return redirect(
            "subtopic_dashboard",
            project_id=project.id,
            report_id=report.id,
        )

    # ==========================
    # GET → Generate or load plan
    # ==========================
    plan_obj, created = TopicAnalysisPlan.objects.get_or_create(
        report=report,
        topic=topic,
        defaults={"plan_json": {}},
    )

    if not plan_obj.plan_json:
        context = {
            "industry": report.industry,
            "report_type": report.report_type,
            "audience": report.audience,
            "purpose": report.purpose,
            "section_title": section.title,
            "subsection_title": subsection.title,
            "topic_title": topic.title,
            "database_schema": schema_context,
        }

        plan = generate_topic_analysis_plan(context)
        plan_obj.plan_json = plan
        plan_obj.save()
    else:
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
                plan.get("data_requirements", []), indent=2
            ),
            "is_approved": plan_obj.is_approved,
        },
    )


from app.utils.text import normalize_title


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


from django.shortcuts import get_object_or_404, render, redirect
from django.contrib import messages

from .models import Project, Report, Topic, TopicContent
from .services.topic_content_generator import generate_topic_content


def generate_topic_content_view(
    request,
    project_id,
    report_id,
    topic_id,
):
    project = get_object_or_404(Project, id=project_id)
    report = get_object_or_404(Report, id=report_id)
    topic = get_object_or_404(Topic, id=topic_id, report=report)

    # ------------------------
    # Guardrails
    # ------------------------
    if not topic.is_approved:
        return render(
            request,
            "error.html",
            {"message": "Topic must be approved before content generation."},
        )

    if not hasattr(topic, "analysis_plan") or not topic.analysis_plan.is_approved:
        return render(
            request,
            "error.html",
            {"message": "Topic analysis plan must be approved first."},
        )

    content_obj, _ = TopicContent.objects.get_or_create(
        topic=topic,
        defaults={
            "content_json": {},
            "status": "draft",
            "iteration_count": 0,
        },
    )

    # ------------------------
    # POST → Generate / Continue
    # ------------------------
    if request.method == "POST":
        action = request.POST.get("action")

        if action == "generate":
            content_obj.status = "in_progress"
            content_obj.save()

            result = generate_topic_content(
                project_id=project.id,
                industry=report.industry,
                report_type=report.report_type,
                audience=report.audience,
                purpose=report.purpose,
                section_title=topic.subsection.section.title,
                subsection_title=topic.subsection.title,
                topic_title=topic.title,
                topic_plan=topic.analysis_plan.plan_json,
                existing_content=content_obj.content_json or None,
            )

            print(result)

            content_obj.content_json = result
            content_obj.iteration_count = result.get("iteration_count", 0)
            content_obj.status = result.get("status", "draft")
            content_obj.save()

            messages.success(
                request,
                f"Content generation iteration {content_obj.iteration_count} completed.",
            )

            return redirect(request.path)

        if action == "compute_sql":
            print("start compute sql")
            section_index = int(request.POST.get("section_index"))
            block_index = int(request.POST.get("block_index"))
            content_json = content_obj.content_json
            sections = content_json.get("sections", [])
            sql_block = None
            try:
                sql_block = sections[section_index]["content_blocks"][block_index]
            except (IndexError, KeyError, TypeError):
                messages.error(request, "Invalid SQL placeholder reference.")
                return redirect(request.path)

            if sql_block.get("type") != "sql_placeholder":
                messages.error(request, "Selected block is not a SQL placeholder.")
                return redirect(request.path)
            
            tables = SelectedTable.objects.filter(project=project)

            schema_context = []
            for t in tables:
                columns = get_table_columns(project.db_connection, t.table_name)
                schema_context.append(
                    {
                        "table": t.table_name,
                        "columns": [
                            {"name": col["name"], "type": col["type"]} for col in columns
                        ],
                    }
                )

            generated_sql = generate_sql_from_placeholder(
                sql_placeholder=sql_block,
                metadata_context=content_json.get("metadata_context"),
                database_schema=schema_context,
            )
            print("\ngenerated sql query = ", generated_sql)
            result = execute_sql_safely(
                generated_sql["sql"],
                project_id=project.id,
                expected_result_type=generated_sql["result_type"],
            )
            print("\nresult = ", result)
            blocks = sections[section_index]["content_blocks"]
            previous_block = blocks[block_index - 1]
            if block_index == 0 or blocks[block_index - 1]["type"] not in ["paragraph", "bullet_list"]:
                messages.error(request, "No paragraph or bullet list found to attach SQL result.")
                return redirect(request.path)

            interpreted_text = interpret_sql_result(
                draft_content=previous_block["content"],
                computed_result=result,
            )


            # Replace blocks
            previous_block["content"] = interpreted_text
            sql_block["generated_result"] = {
                "status": "ok",
                "value": result["result"],
                "row_count": result.get("row_count"),
            }
            sql_block["computed"] = True
            content_obj.content_json = content_json
            content_obj.save()

            messages.success(request, "SQL calculation completed.")
            # return redirect(request.path)
    
        if action == "compute_visual":
            section_index = int(request.POST.get("section_index"))
            block_index = int(request.POST.get("block_index"))

            content_json = content_obj.content_json
            sections = content_json.get("sections", [])

            try:
                visual_block = sections[section_index]["content_blocks"][block_index]
            except (IndexError, KeyError, TypeError):
                messages.error(request, "Invalid visual placeholder reference.")
                return redirect(request.path)

            if visual_block.get("type") != "visual_placeholder":
                messages.error(request, "Selected block is not a visual placeholder.")
                return redirect(request.path)

            # -------------------------
            # Build schema context (same as SQL)
            # -------------------------
            tables = SelectedTable.objects.filter(project=project)

            schema_context = []
            for t in tables:
                columns = get_table_columns(project.db_connection, t.table_name)
                schema_context.append({
                    "table": t.table_name,
                    "columns": [{"name": c["name"], "type": c["type"]} for c in columns],
                })

            # -------------------------
            # Call Visual Agent
            # -------------------------
            visual_plan = generate_visual_plan(
                visual_placeholder=visual_block,
                topic_plan=topic.analysis_plan.plan_json,
                metadata_context=content_json.get("metadata_context"),
                database_schema=schema_context,
            )
            print("visual plan = ", visual_plan)
            if visual_plan["status"] != "ok":
                visual_block["generated_visual"] = visual_plan
                content_obj.save()
                messages.warning(request, "Visual could not be generated.")
                return redirect(request.path)

            # -------------------------
            # Use SQL Agent for visual data
            # -------------------------
            sql_response = generate_sql_from_visual_plan(
                visual_plan=visual_plan,
                metadata_context=content_json.get("metadata_context"),
                database_schema=schema_context,
            )
            print("generate_sql_from_visual_plan = ",sql_response)

            sql_result = execute_sql_safely(
                sql_response["sql"],
                project_id=project.id,
                expected_result_type="table",
            )
            print("execute_sql_safely = ",sql_result)

            # -------------------------
            # Save visual result (NO rendering yet)
            # -------------------------
            relative_path = (
                Path("generated_visuals")
                / f"project_{project.id}"
                / f"topic_{topic.id}"
                / f"section_{section_index}_block_{block_index}.png"
            )

            output_path = Path(settings.MEDIA_ROOT) / relative_path

            render_result = render_visual(
                visual_spec=visual_plan["visual_spec"],
                sql_result=sql_result["result"],
                output_path=output_path,
            )

            visual_block["generated_visual"] = {
                "status": "ok",
                "visual_spec": visual_plan["visual_spec"],
                "image_path": f"{settings.MEDIA_URL}{relative_path.as_posix()}",
                "row_count": sql_result["row_count"],
            }


            content_obj.content_json = content_json
            content_obj.save()

            messages.success(request, "Visual data prepared successfully.")
            return redirect(request.path)

    limitations = (
        content_obj.content_json.get("limitations", [])
        if content_obj.content_json
        else []
    )
    # ------------------------
    # GET → Render
    # ------------------------
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


def generate_subsection_content_view(
    request,
    project_id,
    report_id,
    subsection_id,
):
    project = get_object_or_404(Project, id=project_id)
    report = get_object_or_404(Report, id=report_id)
    subsection = get_object_or_404(SubSection, id=subsection_id, report=report)

    # ------------------------
    # Guardrails
    # ------------------------
    topics = subsection.topics.filter(is_approved=True)

    if not topics.exists():
        return render(
            request,
            "error.html",
            {"message": "No approved topics found for this subsection."},
        )

    # Check if all topics have generated content
    all_topics_have_content = all(
        hasattr(topic, 'content') and topic.content.status == 'generated'
        for topic in topics
    )

    if not all_topics_have_content:
        return render(
            request,
            "error.html",
            {"message": "All topics must have generated content before creating subsection content."},
        )

    # Get or create subsection content object
    content_obj, _ = SubSectionContent.objects.get_or_create(
        subsection=subsection,
        defaults={
            "content_json": {},
            "status": "draft",
        },
    )

    # ------------------------
    # POST → Generate
    # ------------------------
    if request.method == "POST":
        action = request.POST.get("action")

        if action == "generate":
            content_obj.status = "in_progress"
            content_obj.save()

            # Collect all topics' element_progress data
            topics_progress = {}
            for topic in topics:
                if hasattr(topic, 'content') and topic.content.content_json:
                    element_progress = topic.content.content_json.get('element_progress', {})
                    topics_progress[topic.title] = element_progress

            # Generate subsection content
            result = generate_subsection_content(
                project_id=project.id,
                industry=report.industry,
                report_type=report.report_type,
                audience=report.audience,
                purpose=report.purpose,
                report_title=report.title,
                section_title=subsection.section.title,
                subsection_title=subsection.title,
                topics_progress=topics_progress,
            )

            content_obj.content_json = result
            content_obj.status = "generated"
            content_obj.save()

            messages.success(
                request,
                "Subsection content generated successfully.",
            )

            return redirect(request.path)

    # ------------------------
    # GET → Render
    # ------------------------
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
    project = get_object_or_404(Project, id=project_id)
    report = get_object_or_404(Report, id=report_id)
    section = get_object_or_404(Section, id=section_id, report=report)

    # ------------------------
    # Guardrails
    # ------------------------
    subsections = section.sub_sections.all()

    if not subsections.exists():
        return render(
            request,
            "error.html",
            {"message": "No subsections found for this section."},
        )

    # Check if all subsections have generated content
    all_subsections_have_content = all(
        hasattr(subsection, 'content') and subsection.content.status == 'generated'
        for subsection in subsections
    )

    if not all_subsections_have_content:
        return render(
            request,
            "error.html",
            {"message": "All subsections must have generated content before creating section content."},
        )

    # Get or create section content object
    content_obj, _ = SectionContent.objects.get_or_create(
        section=section,
        defaults={
            "content_json": {},
            "status": "draft",
        },
    )

    # ------------------------
    # POST → Generate
    # ------------------------
    if request.method == "POST":
        action = request.POST.get("action")

        if action == "generate":
            content_obj.status = "in_progress"
            content_obj.save()

            # Collect all subsections' key_themes data
            subsections_themes = {}
            for subsection in subsections:
                if hasattr(subsection, 'content') and subsection.content.content_json:
                    key_themes = subsection.content.content_json.get('key_themes', [])
                    subsections_themes[subsection.title] = key_themes

            # Generate section content
            result = generate_section_content(
                project_id=project.id,
                industry=report.industry,
                report_type=report.report_type,
                audience=report.audience,
                purpose=report.purpose,
                report_title=report.title,
                section_title=section.title,
                subsections_themes=subsections_themes,
            )

            content_obj.content_json = result
            content_obj.status = "generated"
            content_obj.save()

            messages.success(
                request,
                "Section content generated successfully.",
            )

            return redirect(request.path)

    # ------------------------
    # GET → Render
    # ------------------------
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
