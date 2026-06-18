import base64
import hashlib

from cryptography.fernet import Fernet, InvalidToken
from django.conf import settings
from django.db import models


class Project(models.Model):
    LLM_PROVIDER_CHOICES = [
        ("vertex_ai", "Vertex AI"),
        ("openrouter", "OpenRouter"),
    ]

    name = models.CharField(max_length=255)
    description = models.TextField(blank=True)
    is_initialized = models.BooleanField(default=False)
    llm_provider = models.CharField(
        max_length=32,
        choices=LLM_PROVIDER_CHOICES,
        default="openrouter",
    )
    primary_llm_model = models.CharField(
        max_length=255,
        default="openai/gpt-5.4",
    )
    secondary_llm_model = models.CharField(
        max_length=255,
        default="openai/gpt-5.4-mini",
    )
    openrouter_api_key_encrypted = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return self.name

    @staticmethod
    def _get_fernet():
        key_material = hashlib.sha256(settings.SECRET_KEY.encode("utf-8")).digest()
        return Fernet(base64.urlsafe_b64encode(key_material))

    @property
    def has_custom_openrouter_api_key(self):
        return bool(self.openrouter_api_key_encrypted)

    def set_openrouter_api_key(self, api_key):
        if not api_key:
            self.openrouter_api_key_encrypted = ""
            return

        cipher = self._get_fernet()
        self.openrouter_api_key_encrypted = cipher.encrypt(
            api_key.encode("utf-8")
        ).decode("utf-8")

    def get_openrouter_api_key(self):
        if not self.openrouter_api_key_encrypted:
            return ""

        cipher = self._get_fernet()

        try:
            return cipher.decrypt(
                self.openrouter_api_key_encrypted.encode("utf-8")
            ).decode("utf-8")
        except InvalidToken as exc:
            raise ValueError("Unable to decrypt the stored OpenRouter API key.") from exc


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
    OBJECT_TYPE_CHOICES = [
        ("table", "Table"),
        ("enum", "Enum"),
    ]

    project = models.ForeignKey(
        Project, on_delete=models.CASCADE, related_name="selected_tables"
    )

    table_name = models.CharField(max_length=255)
    object_type = models.CharField(
        max_length=16,
        choices=OBJECT_TYPE_CHOICES,
        default="table",
    )
    display_name = models.CharField(max_length=255, blank=True, default="")
    source_table = models.CharField(max_length=255, blank=True, default="")
    source_column = models.CharField(max_length=255, blank=True, default="")

    created_at = models.DateTimeField(auto_now_add=True)

    @property
    def object_name(self):
        raw_name = self.display_name or self.table_name
        if raw_name.startswith("table__"):
            return raw_name.split("__", 1)[1]
        if raw_name.startswith("enum__"):
            return raw_name.split("__", 1)[1]
        return raw_name

    @property
    def object_label(self):
        if self.object_type == "enum":
            usage = ""
            if self.source_table and self.source_column:
                usage = f" ({self.source_table}.{self.source_column})"
            return f"Enum: {self.object_name}{usage}"
        return f"Table: {self.object_name}"

    def __str__(self):
        return f"{self.project.name} → {self.object_label}"


class TableMetadata(models.Model):
    OBJECT_TYPE_CHOICES = [
        ("table", "Table"),
        ("enum", "Enum"),
    ]

    project = models.ForeignKey(
        Project, on_delete=models.CASCADE, related_name="metadata"
    )
    table_name = models.CharField(max_length=255)
    object_type = models.CharField(
        max_length=16,
        choices=OBJECT_TYPE_CHOICES,
        default="table",
    )
    display_name = models.CharField(max_length=255, blank=True, default="")
    source_table = models.CharField(max_length=255, blank=True, default="")
    source_column = models.CharField(max_length=255, blank=True, default="")

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
        unique_together = ("project", "table_name", "object_type")

    @property
    def object_name(self):
        raw_name = self.display_name or self.table_name
        if raw_name.startswith("table__"):
            return raw_name.split("__", 1)[1]
        if raw_name.startswith("enum__"):
            return raw_name.split("__", 1)[1]
        return raw_name

    @property
    def object_label(self):
        if self.object_type == "enum":
            usage = ""
            if self.source_table and self.source_column:
                usage = f" ({self.source_table}.{self.source_column})"
            return f"Enum: {self.object_name}{usage}"
        return f"Table: {self.object_name}"

    def __str__(self):
        return f"{self.project.name} - {self.object_label} ({self.status})"

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
    is_generating = models.BooleanField(default=False)


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


class SubSectionContent(models.Model):
    subsection = models.OneToOneField(
        SubSection,
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
    content_json = models.JSONField()
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)


class SectionContent(models.Model):
    section = models.OneToOneField(
        Section,
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
    content_json = models.JSONField()
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)


class TopicEvaluation(models.Model):
    topic = models.OneToOneField(
        "Topic",
        on_delete=models.CASCADE,
        related_name="evaluation"
    )

    report = models.ForeignKey(
        Report,
        on_delete=models.CASCADE,
        related_name="topic_evaluations"
    )

    scores = models.JSONField(null=True, blank=True)
    issues = models.JSONField(null=True, blank=True)
    summary = models.TextField(null=True, blank=True)
    overall_score = models.FloatField(null=True, blank=True)

    created_at = models.DateTimeField(auto_now_add=True)
        # ===== GEVAL =====
    geval_scores = models.JSONField(null=True, blank=True)
    geval_issues = models.JSONField(default=list, blank=True)
    geval_summary = models.TextField(null=True, blank=True)
    geval_overall_score = models.FloatField(null=True, blank=True)

    class Meta:
        unique_together = ("topic", "report")

class ReportEvaluation(models.Model):
    report = models.OneToOneField(
        Report,
        on_delete=models.CASCADE,
        related_name="evaluation"
    )

    average_scores = models.JSONField()  # aggregated metrics
    overall_score = models.FloatField()

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return f"Evaluation - {self.report.title}"
    

class TopicGenerateTime(models.Model):
    topic = models.ForeignKey("Topic", on_delete=models.CASCADE)
    subsection = models.ForeignKey("SubSection", on_delete=models.CASCADE)
    report = models.ForeignKey("Report", on_delete=models.CASCADE)

    start_time = models.DateTimeField()
    end_time = models.DateTimeField()
    duration_seconds = models.FloatField()

    status = models.CharField(max_length=20, default="success")  # success / failed
    error_message = models.TextField(blank=True)

    created_at = models.DateTimeField(auto_now_add=True)


class SubSectionGenerateTime(models.Model):
    subsection = models.ForeignKey("SubSection", on_delete=models.CASCADE)
    report = models.ForeignKey("Report", on_delete=models.CASCADE)

    start_time = models.DateTimeField()
    end_time = models.DateTimeField()
    duration_seconds = models.FloatField()

    topics_count = models.IntegerField()

    status = models.CharField(max_length=20, default="success")
    error_message = models.TextField(blank=True)

    created_at = models.DateTimeField(auto_now_add=True)


class TopicReadability(models.Model):
    topic = models.OneToOneField(
        "Topic",
        on_delete=models.CASCADE,
        related_name="readability"
    )

    report = models.ForeignKey(
        "Report",
        on_delete=models.CASCADE,
        related_name="readability_scores"
    )

    flesch_kincaid_grade = models.FloatField()

    created_at = models.DateTimeField(auto_now_add=True)


class BackgroundTask(models.Model):
    TASK_TYPE_CHOICES = [
        ("metadata_generation", "Metadata Generation"),
        ("subsection_pipeline", "Subsection Pipeline"),
        ("topic_pipeline", "Topic Pipeline"),
        ("document_export", "Document Export"),
    ]

    STATUS_CHOICES = [
        ("pending", "Pending"),
        ("running", "Running"),
        ("completed", "Completed"),
        ("failed", "Failed"),
    ]

    task_type = models.CharField(max_length=64, choices=TASK_TYPE_CHOICES)
    title = models.CharField(max_length=255)
    description = models.TextField(blank=True)
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default="pending")
    project = models.ForeignKey(
        Project,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="background_tasks",
    )
    report = models.ForeignKey(
        Report,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="background_tasks",
    )
    subsection = models.ForeignKey(
        SubSection,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="background_tasks",
    )
    topic = models.ForeignKey(
        Topic,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="background_tasks",
    )
    parent = models.ForeignKey(
        "self",
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        related_name="children",
    )
    started_at = models.DateTimeField(null=True, blank=True)
    finished_at = models.DateTimeField(null=True, blank=True)
    last_message = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self):
        return f"{self.title} ({self.status})"


class BackgroundTaskLog(models.Model):
    LEVEL_CHOICES = [
        ("info", "Info"),
        ("success", "Success"),
        ("warning", "Warning"),
        ("error", "Error"),
    ]

    task = models.ForeignKey(
        BackgroundTask,
        on_delete=models.CASCADE,
        related_name="logs",
    )
    level = models.CharField(max_length=20, choices=LEVEL_CHOICES, default="info")
    message = models.TextField()
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["id"]

    def __str__(self):
        return f"{self.task.title}: {self.message[:60]}"
