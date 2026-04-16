from app.services.metadata_generation.schema_introspector import get_tables
from app.services.metadata_generation.column_introspector import get_table_columns
from app.services.metadata_generation.row_sampler import sample_table_rows
from app.services.metadata_generation.metadata_job import run_metadata_generation
from app.services.metadata_generation.metadata_to_documents import metadata_to_documents
from app.services.vector_db_config.vector_store import get_vector_store

from app.models import SelectedTable
from app.services.background_tasks import run_in_background


class MetadataAgent:

    def discover_tables(self, db_connection):
        """Discover tables"""
        return get_tables(db_connection)

    def save_selected_tables(self, project, selected_tables):
        """Save selected tables"""

        # Remove old selections and store new ones
        SelectedTable.objects.filter(project=project).delete()

        for table in selected_tables:
            SelectedTable.objects.create(
                project=project,
                table_name=table
            )

        project.is_initialized = True
        project.save()

    def get_schema_info(self, project):
        """Get schema info"""

        if not project.is_initialized:
            raise ValueError("Project is not initialized yet.")

        db_conn = project.db_connection
        selected_tables = SelectedTable.objects.filter(project=project)

        schema_info = []

        # Build schema info for selected tables
        for table in selected_tables:
            columns = get_table_columns(db_conn, table.table_name)

            schema_info.append(
                {
                    "table_name": table.table_name,
                    "columns": columns,
                }
            )

        return schema_info
    
    def sample_rows(self, project, limit=10):
        """Sample rows"""

        if not project.is_initialized:
            raise ValueError("Project is not initialized yet.")

        db_conn = project.db_connection
        selected_tables = SelectedTable.objects.filter(project=project)

        sampled_data = []

        # Sample rows for each selected table
        for table in selected_tables:
            rows = sample_table_rows(db_conn, table.table_name, limit)

            sampled_data.append(
                {
                    "table_name": table.table_name,
                    "rows": rows,
                }
            )

        return sampled_data
    
    def start_metadata_generation(self, project):
        """Start metadata generation"""

        if not project.is_initialized:
            raise ValueError("Project is not initialized yet.")

        # Run metadata generation in background
        run_in_background(run_metadata_generation, project.id)

        return {
            "message": "Metadata generation started in background. Please wait."
        }
    

    def approve_metadata(
        self,
        metadata_obj,
        table_description,
        columns,
        confidence_notes,
    ):
        """Approve metadata"""

        # Build approved metadata and save
        approved_metadata = {
            "table_description": table_description,
            "columns": columns,
            "confidence_notes": confidence_notes,
        }

        metadata_obj.approved_metadata = approved_metadata
        metadata_obj.status = "approved"
        metadata_obj.save()

        # Convert metadata to documents and store in vector db
        vector_store = get_vector_store()
        docs = metadata_to_documents(metadata_obj)

        vector_store.add_documents(docs)