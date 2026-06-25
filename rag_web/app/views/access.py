from django.db.models import Q
from django.shortcuts import get_object_or_404

from app.models import BackgroundTask, Project, Report


def get_user_project(user, project_id):
    return get_object_or_404(Project, id=project_id, owner=user)


def get_user_report(user, report_id, project=None):
    queryset = Report.objects.filter(project__owner=user)
    if project is not None:
        queryset = queryset.filter(project=project)
    return get_object_or_404(queryset, id=report_id)


def user_background_tasks(user):
    return BackgroundTask.objects.filter(
        Q(project__owner=user)
        | Q(report__project__owner=user)
        | Q(subsection__report__project__owner=user)
        | Q(topic__report__project__owner=user)
        | Q(parent__project__owner=user)
        | Q(parent__report__project__owner=user)
    ).distinct()


def get_user_background_task(user, task_id):
    return get_object_or_404(user_background_tasks(user), id=task_id)
