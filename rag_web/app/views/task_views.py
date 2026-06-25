from django.http import FileResponse, Http404, JsonResponse
from django.shortcuts import get_object_or_404, render
from django.urls import reverse

from app.models import BackgroundTask
from app.services.document_export_job import resolve_export_path
from app.services.task_tracker import recent_tasks_queryset, running_tasks_queryset
from app.views.access import get_user_background_task, user_background_tasks


def background_task_list(request):
    return render(
        request,
        "background_tasks.html",
        {
            "running_tasks": user_background_tasks(request.user).filter(status__in=["pending", "running"]),
            "recent_tasks": user_background_tasks(request.user).exclude(status__in=["pending", "running"])[:30],
        },
    )


def background_task_detail(request, task_id):
    task = get_user_background_task(request.user, task_id)
    child_tasks = task.children.select_related("topic", "subsection").all()
    initial_logs = list(task.logs.order_by("-id")[:120])
    initial_logs.reverse()

    return render(
        request,
        "background_task_detail.html",
        {
            "task": task,
            "child_tasks": child_tasks,
            "initial_logs": initial_logs,
        },
    )


def background_task_logs_api(request, task_id):
    task = get_user_background_task(request.user, task_id)
    after_id = request.GET.get("after_id")
    logs = task.logs.all()

    if after_id:
        logs = logs.filter(id__gt=after_id)

    payload = {
        "task": {
            "id": task.id,
            "title": task.title,
            "status": task.status,
            "task_type": task.task_type,
            "last_message": task.last_message,
            "started_at": task.started_at.isoformat() if task.started_at else None,
            "finished_at": task.finished_at.isoformat() if task.finished_at else None,
            "download_url": _task_download_url(task),
        },
        "logs": [
            {
                "id": log.id,
                "level": log.level,
                "message": log.message,
                "created_at": log.created_at.isoformat(),
            }
            for log in logs
        ],
    }
    return JsonResponse(payload)


def background_task_download(request, task_id):
    task = get_user_background_task(request.user, task_id)
    download_url = _task_download_url(task)

    if not download_url:
        raise Http404("No download is available for this task.")

    export_path = resolve_export_path(task.id, task.report.title if task.report else None)
    if not export_path.exists():
        raise Http404("The exported file could not be found.")

    return FileResponse(
        export_path.open("rb"),
        as_attachment=True,
        filename=export_path.name,
        content_type="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    )


def _task_download_url(task):
    if task.task_type != "document_export" or task.status != "completed":
        return None

    export_path = resolve_export_path(task.id, task.report.title if task.report else None)
    if not export_path.exists():
        return None

    return reverse("background_task_download", args=[task.id])

