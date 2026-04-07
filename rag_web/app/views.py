from django.shortcuts import render, redirect
from django.contrib import messages
from django.http import HttpResponse
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
    TopicReadability
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
from .services.document_generator import generate_report_document

from .services.schema_introspector import get_tables
from .services.column_introspector import get_table_columns
from app.services.sql_result_interpreter import interpret_sql_result
from app.services.visual_agent import generate_visual_plan
from app.services.visual_renderer import render_visual
from app.services.sql_agent import generate_sql_from_visual_plan
from pathlib import Path
from django.conf import settings
from app.services.project_service import ProjectService
from app.agents.manager_agent import ManagerAgent
from django.http import JsonResponse
from app.services.evaluation_service import evaluate_project
from app.services.readability_service import evaluate_project_readability
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


from .services.llm_metadata_generator import generate_table_metadata
from .services.column_introspector import get_table_columns
from .services.row_sampler import sample_table_rows
from .services.background_tasks import run_in_background
from .services.metadata_job import run_metadata_generation


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

from .models import TableMetadata
import json

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
                "subtopic_dashboard",
                project_id=project_id,
                report_id=report_id,
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

    if request.method == "POST":

        action = request.POST.get("action")

        plan_obj = get_object_or_404(
            TopicAnalysisPlan,
            report=report,
            topic=topic,
        )

        try:
            manager.update_topic_analysis_plan(
                plan_obj,
                topic,
                request.POST,
                approve=(action == "approve"),
            )

        except json.JSONDecodeError:
            messages.error(request, "Invalid JSON in data requirements.")
            return redirect(request.path)

        return redirect(
            "subtopic_dashboard",
            project_id=project.id,
            report_id=report.id,
        )

    plan_obj = manager.generate_topic_analysis_plan(
        project,
        report,
        topic,
    )

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
                plan.get("data_requirements", []),
                indent=2,
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

from .models import Project, Report, Topic

def generate_topic_content_view(
    request,
    project_id,
    report_id,
    topic_id,
):

    project = get_object_or_404(Project, id=project_id)
    report = get_object_or_404(Report, id=report_id)
    topic = get_object_or_404(Topic, id=topic_id, report=report)

    try:
        content_obj = manager.content_agent.get_topic_content(topic)
    except ValueError as e:
        return render(request, "error.html", {"message": str(e)})

    if request.method == "POST":

        action = request.POST.get("action")

        if action == "generate":

            content_obj = manager.generate_topic_content(
                project,
                report,
                topic,
                content_obj,
            )

            messages.success(
                request,
                f"Content generation iteration {content_obj.iteration_count} completed.",
            )

            return redirect(request.path)


        if action == "regenerate":

            existing_content = content_obj.content_json or {}

            # Preserve SQL placeholders
            preserved_sql = existing_content.get("precomputed_sql_placeholders", [])

            # Reset content BUT keep SQL placeholders
            content_obj.content_json = {
                "sections": [],
                "element_progress": {},
                "completed_elements": [],
                "limitations": [],
                "status": "in_progress",
                "precomputed_sql_placeholders": preserved_sql,
            }
            content_obj.iteration_count = 0
            content_obj.status = "draft"
            content_obj.save()

            # Generate fresh content
            content_obj = manager.generate_topic_content(
                project,
                report,
                topic,
                content_obj,
            )

            messages.success(request, "Topic content regenerated successfully.")

            return redirect(request.path)


        if action == "compute_sql":

            try:
                manager.compute_sql_block(
                    project,
                    report,
                    topic,
                    content_obj,
                    int(request.POST.get("section_index")),
                    int(request.POST.get("block_index")),
                )
                messages.success(request, "SQL calculation completed.")

            except ValueError as e:
                messages.error(request, str(e))

            return redirect(request.path)

        if action == "compute_visual":

            try:
                manager.compute_visual_block(
                    project,
                    report,
                    topic,
                    content_obj,
                    int(request.POST.get("section_index")),
                    int(request.POST.get("block_index")),
                )

                messages.success(request, "Visual data prepared successfully.")

            except ValueError as e:
                messages.error(request, str(e))

            return redirect(request.path)

    limitations = (
        content_obj.content_json.get("limitations", [])
        if content_obj.content_json
        else []
    )

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

                # 🔥 RESET CONTENT
                content_obj.content_json = {}
                content_obj.status = "pending"
                content_obj.save()

                # 🔥 GENERATE AGAIN
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

        document_buffer, filename = manager.generate_report_document(report)

        response = HttpResponse(
            document_buffer.getvalue(),
            content_type="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        )

        response["Content-Disposition"] = f'attachment; filename="{filename}"'

        return response

    except Exception as e:

        messages.error(request, f"Error generating document: {str(e)}")

        return redirect(
            "subtopic_dashboard",
            project_id=project.id,
            report_id=report.id,
        )
    
def trigger_auto_generate_subsection(request, project_id, report_id, subsection_id):

    project = get_object_or_404(Project, id=project_id)
    report = get_object_or_404(Report, id=report_id)
    subsection = get_object_or_404(SubSection, id=subsection_id)

    started = manager.trigger_subsection_auto_generation(
        project,
        report,
        subsection,
    )

    return JsonResponse({
        "started": started
    })


from app.models import Project, Report, ReportEvaluation, TopicEvaluation
from app.services.evaluation_service import evaluate_project

def evaluation_dashboard_view(request, project_id):

    project = get_object_or_404(Project, id=project_id)

    reports = Report.objects.filter(project=project)

    selected_report = None
    report_eval = None
    topic_evals = None

    try:

        # -----------------------------
        # HANDLE REPORT SELECTION
        # -----------------------------
        report_id = request.GET.get("report_id")

        if report_id:
            selected_report = get_object_or_404(Report, id=report_id, project=project)

        # -----------------------------
        # RUN EVALUATION
        # -----------------------------
        if request.method == "POST":

            report_id = request.POST.get("report_id")
            action = request.POST.get("action")

            if not report_id:
                messages.error(request, "Please select a report.")
                return redirect("evaluation_dashboard", project_id=project.id)

            if action == "readability":
                evaluate_project_readability(project.id, report_id)

                messages.success(request, "Flesch-Kincaid readability computed.")

                return redirect(
                    f"/projects/{project.id}/evaluation/?report_id={report_id}"
                )

            evaluate_project(project_id, report_id)

            messages.success(request, "Evaluation completed successfully.")

            return redirect(
                f"/projects/{project.id}/evaluation/?report_id={report_id}"
            )

        # -----------------------------
        # LOAD RESULTS
        # -----------------------------

        readability_scores = None
        if selected_report:
            report_eval = ReportEvaluation.objects.filter(
                report=selected_report
            ).first()

            topic_evals = TopicEvaluation.objects.filter(
                topic__subsection__section__report=selected_report
            ).select_related("topic")

            readability_scores = TopicReadability.objects.filter(
                report=selected_report
            ).select_related("topic")

            # -----------------------------
            # 🔥 COMPUTE OVERALL SCORE (NEW)
            # -----------------------------
            for eval_obj in topic_evals:

                scores = eval_obj.scores or {}

                hallucination = float(scores.get("hallucination", 0))
                correctness = float(scores.get("correctness", 0))
                relevance = float(scores.get("relevance", 0))

                # Simple average
                overall = (hallucination + relevance) / 2

                # Optional: round
                eval_obj.overall_score = round(overall, 2)

        context = {
            "project": project,
            "reports": reports,
            "selected_report": selected_report,
            "report_eval": report_eval,
            "topic_evals": topic_evals,
            "readability_scores": readability_scores,
        }

        return render(request, "evaluation/dashboard.html", context)

    except Exception as e:

        messages.error(request, f"Evaluation failed: {str(e)}")

        return redirect("evaluation_dashboard", project_id=project.id)