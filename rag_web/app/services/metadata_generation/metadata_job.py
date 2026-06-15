from .llm_metadata_generator import generate_enum_metadata, generate_table_metadata
from .column_introspector import get_table_columns
from .schema_introspector import get_enums, get_table_relationships
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
    selected_objects = list(SelectedTable.objects.filter(project=project))

    if task_id:
        start_background_task(
            task_id,
            f"Metadata generation started for {len(selected_objects)} selected schema object(s).",
        )

    try:
        if not selected_objects:
            message = "No selected schema objects were found for metadata generation."
            if task_id:
                fail_background_task(task_id, message)
            return

        selected_table_names = sorted(
            {
                item.object_name
                for item in selected_objects
                if item.object_type == "table"
            }
        )
        referenced_source_tables = {
            item.source_table
            for item in selected_objects
            if item.object_type == "enum" and item.source_table
        }
        tables_to_introspect = sorted(set(selected_table_names) | referenced_source_tables)
        schema_by_table = {
            table_name: get_table_columns(db_conn, table_name)
            for table_name in tables_to_introspect
        }

        relationships = get_table_relationships(db_conn, selected_table_names)
        enums_by_name = {item["enum_name"]: item for item in get_enums(db_conn)}
        selected_tables_schema = [
            {
                "table_name": current_table_name,
                "columns": current_columns,
            }
            for current_table_name, current_columns in schema_by_table.items()
        ]

        for selected_object in selected_objects:
            if task_id:
                log_background_task(
                    task_id,
                    (
                        f"Preparing schema context for {selected_object.object_type} "
                        f"'{selected_object.object_name}'."
                    ),
                )

            if selected_object.object_type == "table":
                object_name = selected_object.object_name
                columns = schema_by_table[object_name]
                rows = sample_table_rows(db_conn, object_name, limit=5)
                table_relationships = _build_table_relationship_context(
                    object_name,
                    relationships,
                )

                if task_id:
                    log_background_task(
                        task_id,
                        (
                            f"Fetched {len(columns)} column definitions, "
                            f"{len(rows)} sample row(s), and "
                            f"{len(table_relationships)} relationship hint(s) "
                            f"for table '{object_name}'."
                        ),
                    )

                metadata = generate_table_metadata(
                    project=project,
                    table_name=object_name,
                    columns=columns,
                    rows=rows,
                    selected_tables_schema=selected_tables_schema,
                    relationships=table_relationships,
                )
            else:
                object_name = selected_object.object_name
                enum_info = enums_by_name.get(
                    object_name,
                    {"enum_name": object_name, "values": [], "usages": []},
                )
                usage_contexts = []
                for usage in enum_info.get("usages", []):
                    usage_table = usage["table_name"]
                    usage_column = usage["column_name"]
                    column_details = next(
                        (
                            column
                            for column in schema_by_table.get(usage_table, [])
                            if column["name"] == usage_column
                        ),
                        None,
                    )
                    usage_contexts.append(
                        {
                            "table_name": usage_table,
                            "column_name": usage_column,
                            "column_type": column_details.get("type") if column_details else None,
                            "accepted_values": column_details.get("accepted_values", []) if column_details else [],
                            "is_nullable": column_details.get("nullable") if column_details else None,
                        }
                    )

                if task_id:
                    log_background_task(
                        task_id,
                        (
                            f"Fetched {len(enum_info.get('values', []))} enum value(s) and "
                            f"{len(usage_contexts)} usage context(s) for enum '{object_name}'."
                        ),
                    )

                metadata = generate_enum_metadata(
                    project=project,
                    enum_name=object_name,
                    enum_values=enum_info.get("values", []),
                    usage_contexts=usage_contexts,
                    selected_tables_schema=selected_tables_schema,
                )

            TableMetadata.objects.update_or_create(
                project=project,
                table_name=selected_object.table_name,
                object_type=selected_object.object_type,
                defaults={
                    "display_name": selected_object.object_name,
                    "source_table": selected_object.source_table,
                    "source_column": selected_object.source_column,
                    "generated_metadata": metadata,
                    "status": "completed",
                },
            )

            if task_id:
                log_background_task(
                    task_id,
                    (
                        f"Metadata saved for {selected_object.object_type} "
                        f"'{selected_object.object_name}'."
                    ),
                    level="success",
                )

        if task_id:
            complete_background_task(task_id, "Metadata generation completed.")
    except Exception as exc:
        if task_id:
            fail_background_task(task_id, f"Metadata generation failed: {exc}")
        raise
