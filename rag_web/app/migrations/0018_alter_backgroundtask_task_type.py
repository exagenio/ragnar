from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("app", "0017_project_owner"),
    ]

    operations = [
        migrations.AlterField(
            model_name="backgroundtask",
            name="task_type",
            field=models.CharField(
                choices=[
                    ("metadata_generation", "Metadata Generation"),
                    ("subsection_pipeline", "Subsection Pipeline"),
                    ("topic_pipeline", "Topic Pipeline"),
                    ("document_export", "Document Export"),
                ],
                max_length=64,
            ),
        ),
    ]
