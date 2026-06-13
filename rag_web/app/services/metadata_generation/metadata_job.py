from .llm_metadata_generator import generate_table_metadata
from .column_introspector import get_table_columns
from .schema_introspector import get_table_relationships
from .row_sampler import sample_table_rows
from ...models import Project, SelectedTable, TableMetadata
from app.services.task_tracker import (
    complete_background_task,
    fail_background_task,
    log_background_task,
    start_background_task,
)


def _build_table_relationship_context(table_name, relationships):
    """Build direct relationship context for a single table."""

    context = []

    for relationship in relationships:
        if relationship["from_table"] == table_name:
            direction = "outbound"
            related_table = relationship["to_table"]
            related_columns = relationship["to_columns"]
            relationship_type = relationship["relationship_type"]
            through_table = relationship.get("through_table")
        elif relationship["to_table"] == table_name:
            direction = "inbound"
            related_table = relationship["from_table"]
            related_columns = relationship["from_columns"]
            relationship_type = relationship["reverse_relationship_type"]
            through_table = relationship.get("through_table")
        else:
            continue

        context.append(
            {
                "constraint_name": relationship["constraint_name"],
                "related_table": related_table,
                "relationship_type": relationship_type,
                "direction": direction,
                "local_columns": relationship["from_columns"]
                if direction == "outbound"
                else relationship["to_columns"],
                "related_columns": related_columns,
                "through_table": through_table,
                "is_bridge_table": relationship.get("is_bridge_table", False),
                "is_derived": relationship.get("is_derived", False),
            }
        )

    return context


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

        selected_table_names = [table.table_name for table in selected_tables]
        schema_by_table = {}
        for table_name in selected_table_names:
            schema_by_table[table_name] = get_table_columns(db_conn, table_name)

        relationships = get_table_relationships(db_conn, selected_table_names)
        selected_tables_schema = [
            {
                "table_name": current_table_name,
                "columns": current_columns,
            }
            for current_table_name, current_columns in schema_by_table.items()
        ]

        for table in selected_tables:
            if task_id:
                log_background_task(
                    task_id,
                    f"Preparing schema context for table '{table.table_name}'.",
                )

            columns = schema_by_table[table.table_name]
            rows = sample_table_rows(db_conn, table.table_name, limit=5)
            table_relationships = _build_table_relationship_context(
                table.table_name,
                relationships,
            )

            if task_id:
                log_background_task(
                    task_id,
                    (
                        f"Fetched {len(columns)} column definitions, "
                        f"{len(rows)} sample row(s), and "
                        f"{len(table_relationships)} relationship hint(s) "
                        f"for '{table.table_name}'."
                    ),
                )

            metadata = generate_table_metadata(
                project=project,
                table_name=table.table_name,
                columns=columns,
                rows=rows,
                selected_tables_schema=selected_tables_schema,
                relationships=table_relationships,
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
