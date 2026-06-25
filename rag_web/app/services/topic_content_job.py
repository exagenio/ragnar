from django.db import close_old_connections, connections

from app.agents.manager_agent import ManagerAgent
from app.models import Project, Report, Topic, TopicContent
from app.services.background_tasks import run_in_background
from app.services.task_tracker import (
    complete_background_task,
    create_background_task,
    fail_background_task,
    log_background_task,
    start_background_task,
)


def create_topic_content_task(project, report, topic, *, regenerate=False):
    """Create and start a background job for single-topic content generation."""

    task = create_background_task(
        task_type="topic_pipeline",
        title=f"Topic content generation for {topic.title}",
        description="Generate or regenerate content for a single topic.",
        project=project,
        report=report,
        subsection=topic.subsection,
        topic=topic,
    )
    run_in_background(
        run_topic_content_generation,
        project.id,
        report.id,
        topic.id,
        task.id,
        regenerate,
    )
    return task


def run_topic_content_generation(project_id, report_id, topic_id, task_id, regenerate=False):
    """Run the existing single-topic content generation flow in the background."""

    close_old_connections()
    manager = ManagerAgent()

    try:
        start_background_task(task_id, "Starting topic content generation.")

        project = Project.objects.get(id=project_id)
        report = Report.objects.get(id=report_id, project=project)
        topic = Topic.objects.select_related("subsection__section").get(
            id=topic_id,
            report=report,
        )
        content_obj = manager.content_agent.get_topic_content(topic)

        if regenerate:
            log_background_task(task_id, "Resetting existing topic content.")
            _reset_topic_content(content_obj)

        manager.generate_topic_content(project, report, topic, content_obj)
        complete_background_task(task_id, "Topic content generation completed.")

    except Exception as exc:
        fail_background_task(task_id, f"Topic content generation failed: {exc}")
        raise
    finally:
        connections.close_all()


def _reset_topic_content(content_obj: TopicContent):
    existing_content = content_obj.content_json or {}
    preserved_sql = existing_content.get("precomputed_sql_placeholders", [])

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
