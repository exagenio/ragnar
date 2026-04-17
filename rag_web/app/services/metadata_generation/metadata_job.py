from .llm_metadata_generator import generate_table_metadata
from .column_introspector import get_table_columns
from .row_sampler import sample_table_rows
from ...models import Project, SelectedTable, TableMetadata
from app.services.task_tracker import (
    complete_background_task,
    fail_background_task,
    log_background_task,
    start_background_task,
)


def run_metadata_generation(project_id, task_id=None):
    """Run metadata generation"""

    project = Project.objects.get(id=project_id)
    db_conn = project.db_connection
    selected_tables = list(SelectedTable.objects.filter(project=project))

    if task_id:
        start_background_task(
            task_id,
            f"Metadata generation started for {len(selected_tables)} selected table(s).",
        )

    try:
        if not selected_tables:
            message = "No selected tables were found for metadata generation."
            if task_id:
                fail_background_task(task_id, message)
            return

        for table in selected_tables[:1]:
            if task_id:
                log_background_task(
                    task_id,
                    f"Preparing schema context for table '{table.table_name}'.",
                )

            columns = get_table_columns(db_conn, table.table_name)
            rows = sample_table_rows(db_conn, table.table_name, limit=5)

            if task_id:
                log_background_task(
                    task_id,
                    f"Fetched {len(columns)} column definitions and {len(rows)} sample row(s) for '{table.table_name}'.",
                )

            metadata = generate_table_metadata(
                project=project,
                table_name=table.table_name,
                columns=columns,
                rows=rows,
            )

            TableMetadata.objects.update_or_create(
                project=project,
                table_name=table.table_name,
                defaults={
                    "generated_metadata": metadata,
                    "status": "completed",
                },
            )

            if task_id:
                log_background_task(
                    task_id,
                    f"Metadata saved for table '{table.table_name}'.",
                    level="success",
                )

        if task_id:
            complete_background_task(task_id, "Metadata generation completed.")
    except Exception as exc:
        if task_id:
            fail_background_task(task_id, f"Metadata generation failed: {exc}")
        raise
