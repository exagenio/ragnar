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

class Report(models.Model):
    project = models.ForeignKey(
        Project, on_delete=models.CASCADE, related_name="reports"
    )
    title = models.CharField(max_length=255)
    industry = models.CharField(max_length=100)
    report_type = models.CharField(max_length=150)
    audience = models.CharField(max_length=150)
    purpose = models.TextField()
    focus_areas = models.TextField(blank=True)
    additional_notes = models.TextField(blank=True)

    STATUS_CHOICES = [
        ("outline_generated", "Outline Generated"),
        ("outline_approved", "Outline Approved"),
    ]

    status = models.CharField(
        max_length=50, choices=STATUS_CHOICES, default="outline_generated"
    )
    outline_approved = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return self.title


class ReportOutline(models.Model):
    report = models.OneToOneField(
        Report, on_delete=models.CASCADE, related_name="outline"
    )
    outline_json = models.JSONField()
    approved = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)


class Section(models.Model):
    report = models.ForeignKey(
        Report, on_delete=models.CASCADE, related_name="sections"
    )
    title = models.CharField(max_length=255)
    is_sub_sec_appvroved = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)


class SubSection(models.Model):
    report = models.ForeignKey(
        Report, on_delete=models.CASCADE, related_name="sub_sections"
    )
    section = models.ForeignKey(
        Section, on_delete=models.CASCADE, related_name="sub_sections"
    )
    title = models.CharField(max_length=255)
    is_topics_approved = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)


class TopicAnalysisPlan(models.Model):
    report = models.ForeignKey(
        Report, on_delete=models.CASCADE, related_name="topic_plans"
    )
    topic = models.OneToOneField(
        "Topic",
        on_delete=models.CASCADE,
        related_name="analysis_plan",
    )
    plan_json = models.JSONField()
    is_approved = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)


class Topic(models.Model):
    subsection = models.ForeignKey(
        SubSection, on_delete=models.CASCADE, related_name="topics"
    )
    report = models.ForeignKey(
        Report, on_delete=models.CASCADE, related_name="topics"
    )
    title = models.CharField(max_length=255)
    is_approved = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)


class TopicContent(models.Model):
    topic = models.OneToOneField(
        Topic,
        on_delete=models.CASCADE,
        related_name="content"
    )
    status = models.CharField(
        max_length=30,
        choices=[
            ("draft", "Draft"),
            ("in_progress", "In Progress"),
            ("generated", "Generated"),
            ("approved", "Approved"),
        ],
        default="draft"
    )
    iteration_count = models.IntegerField(default=0)
    content_json = models.JSONField()
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

