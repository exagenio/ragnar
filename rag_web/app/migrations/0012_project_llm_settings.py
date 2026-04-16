from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("app", "0011_alter_topicevaluation_issues_and_more"),
    ]

    operations = [
        migrations.AddField(
            model_name="project",
            name="llm_provider",
            field=models.CharField(
                choices=[("vertex_ai", "Vertex AI"), ("openrouter", "OpenRouter")],
                default="openrouter",
                max_length=32,
            ),
        ),
        migrations.AddField(
            model_name="project",
            name="openrouter_api_key_encrypted",
            field=models.TextField(blank=True),
        ),
        migrations.AddField(
            model_name="project",
            name="primary_llm_model",
            field=models.CharField(default="openai/gpt-5.4", max_length=255),
        ),
        migrations.AddField(
            model_name="project",
            name="secondary_llm_model",
            field=models.CharField(default="openai/gpt-5.4-mini", max_length=255),
        ),
    ]
