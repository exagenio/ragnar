from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("app", "0015_project_embedding_model"),
    ]

    operations = [
        migrations.AlterField(
            model_name="project",
            name="llm_provider",
            field=models.CharField(
                choices=[
                    ("vertex_ai", "Vertex AI"),
                    ("openrouter", "OpenRouter"),
                    ("ollama", "Ollama (Local)"),
                ],
                default="openrouter",
                max_length=32,
            ),
        ),
    ]
