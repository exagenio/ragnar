from .llm_metadata_generator import generate_table_metadata
from .column_introspector import get_table_columns
from .row_sampler import sample_table_rows
from ...models import Project, SelectedTable, TableMetadata


def run_metadata_generation(project_id):
    """Run metadata generation"""

    project = Project.objects.get(id=project_id)
    db_conn = project.db_connection

    # Iterate selected tables and generate metadata
    # TODO: add all tables later
    for table in SelectedTable.objects.filter(project=project)[:1]:
        columns = get_table_columns(db_conn, table.table_name)
        rows = sample_table_rows(db_conn, table.table_name, limit=5)

        # Generate metadata using small input sample
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
