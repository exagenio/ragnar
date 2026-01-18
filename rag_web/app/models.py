from django.db import models


class Project(models.Model):
    name = models.CharField(max_length=255)
    description = models.TextField(blank=True)
    is_initialized = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return self.name


class DBConnection(models.Model):
    DB_TYPE_CHOICES = [
        ("postgres", "PostgreSQL"),
        ("mysql", "MySQL"),
    ]

    project = models.OneToOneField(
        Project, on_delete=models.CASCADE, related_name="db_connection"
    )

    db_type = models.CharField(
        max_length=20, choices=DB_TYPE_CHOICES, default="postgres"
    )

    host = models.CharField(max_length=255)
    port = models.IntegerField(default=5432)
    database_name = models.CharField(max_length=255)
    username = models.CharField(max_length=255)

    # For FYP / localhost usage
    password = models.TextField()

    schema = models.CharField(
        max_length=255, default="public", help_text="Database schema to inspect"
    )

    is_active = models.BooleanField(default=True)

    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"{self.project.name} → {self.database_name}"


class SelectedTable(models.Model):
    project = models.ForeignKey(
        Project, on_delete=models.CASCADE, related_name="selected_tables"
    )

    table_name = models.CharField(max_length=255)

    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"{self.project.name} → {self.table_name}"


class TableMetadata(models.Model):
    project = models.ForeignKey(
        Project, on_delete=models.CASCADE, related_name="metadata"
    )
    table_name = models.CharField(max_length=255)

    # AI-generated draft
    generated_metadata = models.JSONField()

    # User-edited / approved version
    approved_metadata = models.JSONField(null=True, blank=True)

    status = models.CharField(
        max_length=20,
        choices=[
            ("pending", "Pending"),
            ("completed", "Completed"),
            ("approved", "Approved"),
        ],
        default="pending",
    )

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        unique_together = ("project", "table_name")

    def __str__(self):
        return f"{self.project.name} - {self.table_name} ({self.status})"
