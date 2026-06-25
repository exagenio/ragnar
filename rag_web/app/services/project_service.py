import psycopg2
from app.models import Project, DBConnection


class ProjectService:
    """Service for project operations"""

    def test_db_connection(self, data):
        """Test database connection"""

        # Attempt to connect using provided credentials
        psycopg2.connect(
            host=data["host"],
            port=data["port"],
            dbname=data["database_name"],
            user=data["username"],
            password=data["password"],
        )

    def create_project_with_db(self, data, owner):
        """Create project with database connection"""

        # Create project entity
        project = Project.objects.create(
            owner=owner,
            name=data["project_name"],
            description=data["project_description"],
            is_initialized=False,
            llm_provider=data["llm_provider"],
            primary_llm_model=data["resolved_primary_model"],
            secondary_llm_model=data["resolved_secondary_model"],
            embedding_model=data["resolved_embedding_model"],
        )

        if data.get("resolved_openrouter_api_key"):
            project.set_openrouter_api_key(data["resolved_openrouter_api_key"])
            project.save(update_fields=["openrouter_api_key_encrypted"])

        # Create database connection linked to project
        DBConnection.objects.create(
            project=project,
            db_type=data["db_type"],
            host=data["host"],
            port=data["port"],
            database_name=data["database_name"],
            username=data["username"],
            password=data["password"],
            schema=data["schema"],
            is_active=True,
        )

        return project

    def update_project_llm_settings(self, project, data):
        """Update model provider and model settings for a project."""

        project.llm_provider = data["llm_provider"]
        project.primary_llm_model = data["resolved_primary_model"]
        project.secondary_llm_model = data["resolved_secondary_model"]
        project.embedding_model = data["resolved_embedding_model"]

        if data.get("clear_openrouter_api_key"):
            project.set_openrouter_api_key("")
        elif data.get("resolved_openrouter_api_key"):
            project.set_openrouter_api_key(data["resolved_openrouter_api_key"])

        project.save()

        return project

