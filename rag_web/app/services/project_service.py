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

    def create_project_with_db(self, data):
        """Create project with database connection"""

        # Create project entity
        project = Project.objects.create(
            name=data["project_name"],
            description=data["project_description"],
            is_initialized=False,
        )

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
