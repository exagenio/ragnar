from pathlib import Path
from threading import Thread

from django.conf import settings
from django.utils.text import slugify

from app.agents.content_agent import ContentAgent
from app.models import BackgroundTask, Report
from app.services.task_tracker import (
    complete_background_task,
    create_background_task,
    fail_background_task,
    log_background_task,
    start_background_task,
)


EXPORT_DIRECTORY = Path(settings.MEDIA_ROOT) / "exports"


def create_document_export_task(*, project, report):
    task = create_background_task(
        task_type="document_export",
        title=f"Export report document: {report.title}",
        description="Generate the final DOCX report in the background.",
        project=project,
        report=report,
    )

    worker = Thread(
        target=run_document_export,
        kwargs={"task_id": task.id, "report_id": report.id},
        daemon=True,
    )
    worker.start()
    return task


def run_document_export(*, task_id, report_id):
    task = BackgroundTask.objects.get(id=task_id)
    report = Report.objects.select_related("project").get(id=report_id)

    try:
        start_background_task(task, "Preparing report content for document export.")
        log_background_task(task, "Loading report sections, subsections, and approved topics.")

        content_agent = ContentAgent()
        document_buffer, filename = content_agent.generate_report_document(
            report,
            progress_callback=lambda message: log_background_task(task, message),
        )

        log_background_task(task, "Rendering DOCX package and writing export file.")

        export_path = get_export_path(task.id, filename)
        export_path.parent.mkdir(parents=True, exist_ok=True)
        export_path.write_bytes(document_buffer.getvalue())

        complete_background_task(
            task,
            f"Document export complete. File ready: {export_path.name}",
        )
    except Exception as exc:
        fail_background_task(task, f"Document export failed: {exc}")


def get_export_path(task_id, filename=None):
    safe_name = slugify(Path(filename or f"report-export-{task_id}.docx").stem)
    final_name = f"task-{task_id}-{safe_name or 'report-export'}.docx"
    return EXPORT_DIRECTORY / final_name


def resolve_export_path(task_id, filename=None):
    exact_path = get_export_path(task_id, filename)
    if exact_path.exists():
        return exact_path

    matches = sorted(EXPORT_DIRECTORY.glob(f"task-{task_id}-*.docx"))
    if matches:
        return matches[0]

    return exact_path
