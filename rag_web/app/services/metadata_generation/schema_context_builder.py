from app.models import SelectedTable
from app.services.metadata_generation.column_introspector import get_table_columns
from app.services.metadata_generation.schema_introspector import get_table_relationships


def build_schema_context(project):
    """Build schema context for both single-table and multi-table datasets."""

    selected_tables = list(
        SelectedTable.objects.filter(project=project, object_type="table").order_by(
            "created_at",
            "display_name",
            "table_name",
        )
    )
    table_names = [table.object_name for table in selected_tables]
    dataset_mode = "single_table" if len(table_names) <= 1 else "multi_table"

    tables = []
    for table in selected_tables:
        columns = get_table_columns(project.db_connection, table.object_name)
        tables.append(
            {
                "table": table.object_name,
                "columns": columns,
            }
        )

    relationships = get_table_relationships(project.db_connection, table_names)

    return {
        "dataset_mode": dataset_mode,
        "tables": tables,
        "relationships": relationships,
    }
