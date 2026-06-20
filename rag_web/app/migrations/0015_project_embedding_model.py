from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("app", "0014_selectedtable_object_type_and_more"),
    ]

    operations = [
        migrations.AddField(
            model_name="project",
            name="embedding_model",
            field=models.CharField(
                default="gemini-embedding-001",
                max_length=255,
            ),
        ),
    ]
