from django.db.models import Q
from django.utils.timezone import now

from app.models import BackgroundTask, BackgroundTaskLog


RUNNING_TASK_STATUSES = ["pending", "running"]


def create_background_task(
    *,
    task_type,
    title,
    description="",
    project=None,
    report=None,
    subsection=None,
    topic=None,
    parent=None,
    parent_id=None,
):
    return BackgroundTask.objects.create(
        task_type=task_type,
        title=title,
        description=description,
        project=project,
        report=report,
        subsection=subsection,
        topic=topic,
        parent=parent,
        parent_id=parent_id,
    )


def log_background_task(task_or_id, message, level="info"):
    task = _resolve_task(task_or_id)
    BackgroundTaskLog.objects.create(
        task=task,
        level=level,
        message=message,
    )
    BackgroundTask.objects.filter(id=task.id).update(
        last_message=message,
        updated_at=now(),
    )


def start_background_task(task_or_id, message=None):
    task = _resolve_task(task_or_id)
    updates = {
        "status": "running",
        "last_message": message or task.last_message,
    }
    if not task.started_at:
        updates["started_at"] = now()
    BackgroundTask.objects.filter(id=task.id).update(**updates)
    if message:
        log_background_task(task.id, message, level="info")


def complete_background_task(task_or_id, message=None):
    task = _resolve_task(task_or_id)
    finished_at = now()
    BackgroundTask.objects.filter(id=task.id).update(
        status="completed",
        finished_at=finished_at,
        last_message=message or task.last_message or "Task completed.",
    )
    if message:
        BackgroundTaskLog.objects.create(
            task=task,
            level="success",
            message=message,
        )


def fail_background_task(task_or_id, message):
    task = _resolve_task(task_or_id)
    finished_at = now()
    BackgroundTask.objects.filter(id=task.id).update(
        status="failed",
        finished_at=finished_at,
        last_message=message,
    )
    BackgroundTaskLog.objects.create(
        task=task,
        level="error",
        message=message,
    )


def has_running_task(*, project=None, task_type=None, subsection=None, topic=None):
    queryset = BackgroundTask.objects.filter(status__in=RUNNING_TASK_STATUSES)
    if project is not None:
        queryset = queryset.filter(project=project)
    if task_type is not None:
        queryset = queryset.filter(task_type=task_type)
    if subsection is not None:
        queryset = queryset.filter(subsection=subsection)
    if topic is not None:
        queryset = queryset.filter(topic=topic)
    return queryset.exists()


def running_tasks_queryset():
    return BackgroundTask.objects.filter(status__in=RUNNING_TASK_STATUSES).select_related(
        "project",
        "report",
        "subsection",
        "topic",
        "parent",
    )


def recent_tasks_queryset(limit=20):
    return BackgroundTask.objects.filter(
        ~Q(status__in=RUNNING_TASK_STATUSES)
    ).select_related(
        "project",
        "report",
        "subsection",
        "topic",
        "parent",
    )[:limit]


def _resolve_task(task_or_id):
    if isinstance(task_or_id, BackgroundTask):
        return task_or_id
    return BackgroundTask.objects.get(id=task_or_id)
