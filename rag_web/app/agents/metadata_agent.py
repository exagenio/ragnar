from app.services.metadata_generation.schema_introspector import (
    get_enums,
    get_tables,
    get_table_relationships,
)
from app.services.metadata_generation.column_introspector import get_table_columns
from app.services.metadata_generation.row_sampler import sample_table_rows
from app.services.metadata_generation.metadata_job import run_metadata_generation
from app.services.metadata_generation.metadata_to_documents import metadata_to_documents
from app.services.vector_db_config.vector_store import get_vector_store
from app.services.task_tracker import create_background_task

from app.models import SelectedTable
from app.services.background_tasks import run_in_background


class MetadataAgent:

    def discover_tables(self, db_connection):
        """Discover selectable tables and enums."""

        table_items = [
            {
                "value": f"table__{table_name}",
                "label": f"Table: {table_name}",
                "object_type": "table",
                "object_name": table_name,
                "source_table": "",
                "source_column": "",
            }
            for table_name in get_tables(db_connection)
        ]

        enum_items = []
        for enum_info in get_enums(db_connection):
            usages = enum_info.get("usages", [])
            usage = usages[0] if usages else {"table_name": "", "column_name": ""}
            usage_label = ""
            if usage["table_name"] and usage["column_name"]:
                usage_label = f" ({usage['table_name']}.{usage['column_name']})"

            enum_items.append(
                {
                    "value": f"enum__{enum_info['enum_name']}",
                    "label": f"Enum: {enum_info['enum_name']}{usage_label}",
                    "object_type": "enum",
                    "object_name": enum_info["enum_name"],
                    "source_table": usage["table_name"],
                    "source_column": usage["column_name"],
                }
            )

        return table_items + enum_items

    def save_selected_tables(self, project, selected_tables):
        """Save selected schema objects."""

        SelectedTable.objects.filter(project=project).delete()
        enum_lookup = {
            item["enum_name"]: item
            for item in get_enums(project.db_connection)
        }

        for item in selected_tables:
            object_type, object_name = item.split("__", 1)
            source_table = ""
            source_column = ""
            if object_type == "enum":
                enum_info = enum_lookup.get(object_name, {})
                usage = (enum_info.get("usages") or [{}])[0]
                source_table = usage.get("table_name", "")
                source_column = usage.get("column_name", "")
            SelectedTable.objects.create(
                project=project,
                table_name=item,
                object_type=object_type,
                display_name=object_name,
                source_table=source_table,
                source_column=source_column,
            )

        project.is_initialized = True
        project.save()

    def get_schema_info(self, project):
        """Get schema info."""

        if not project.is_initialized:
            raise ValueError("Project is not initialized yet.")

        db_conn = project.db_connection
        selected_tables = SelectedTable.objects.filter(project=project, object_type="table")
        selected_enums = SelectedTable.objects.filter(project=project, object_type="enum")
        selected_table_names = [table.object_name for table in selected_tables]

        schema_info = []
        for table in selected_tables:
            columns = get_table_columns(db_conn, table.object_name)
            schema_info.append(
                {
                    "table_name": table.object_name,
                    "columns": columns,
                }
            )

        relationships = get_table_relationships(db_conn, selected_table_names)
        selected_enum_names = {item.object_name for item in selected_enums}
        enums = [
            enum_info
            for enum_info in get_enums(db_conn)
            if enum_info["enum_name"] in selected_enum_names
        ]

        return {
            "tables": schema_info,
            "relationships": relationships,
            "enums": enums,
        }

    def sample_rows(self, project, limit=10):
        """Sample rows."""

        if not project.is_initialized:
            raise ValueError("Project is not initialized yet.")

        db_conn = project.db_connection
        selected_tables = SelectedTable.objects.filter(project=project, object_type="table")

        sampled_data = []
        for table in selected_tables:
            rows = sample_table_rows(db_conn, table.object_name, limit)
            sampled_data.append(
                {
                    "table_name": table.object_name,
                    "rows": rows,
                }
            )

        return sampled_data

    def start_metadata_generation(self, project):
        """Start metadata generation."""

        if not project.is_initialized:
            raise ValueError("Project is not initialized yet.")

        task = create_background_task(
            task_type="metadata_generation",
            title=f"Metadata generation for {project.name}",
            description="Generate metadata from the selected database schema objects.",
            project=project,
        )

        run_in_background(run_metadata_generation, project.id, task.id)

        return {
            "message": "Metadata generation started in background. Please wait.",
            "task": task,
        }

    def approve_metadata(self, metadata_obj, approved_metadata):
        """Approve metadata."""

        metadata_obj.approved_metadata = approved_metadata
        metadata_obj.status = "approved"
        metadata_obj.save()

        vector_store = get_vector_store()
        docs = metadata_to_documents(metadata_obj)
        vector_store.add_documents(docs)
