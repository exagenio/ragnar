from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("app", "0013_backgroundtask_backgroundtasklog"),
    ]

    operations = [
        migrations.AddField(
            model_name="selectedtable",
            name="display_name",
            field=models.CharField(blank=True, default="", max_length=255),
        ),
        migrations.AddField(
            model_name="selectedtable",
            name="object_type",
            field=models.CharField(
                choices=[("table", "Table"), ("enum", "Enum")],
                default="table",
                max_length=16,
            ),
        ),
        migrations.AddField(
            model_name="selectedtable",
            name="source_column",
            field=models.CharField(blank=True, default="", max_length=255),
        ),
        migrations.AddField(
            model_name="selectedtable",
            name="source_table",
            field=models.CharField(blank=True, default="", max_length=255),
        ),
        migrations.AddField(
            model_name="tablemetadata",
            name="display_name",
            field=models.CharField(blank=True, default="", max_length=255),
        ),
        migrations.AddField(
            model_name="tablemetadata",
            name="object_type",
            field=models.CharField(
                choices=[("table", "Table"), ("enum", "Enum")],
                default="table",
                max_length=16,
            ),
        ),
        migrations.AddField(
            model_name="tablemetadata",
            name="source_column",
            field=models.CharField(blank=True, default="", max_length=255),
        ),
        migrations.AddField(
            model_name="tablemetadata",
            name="source_table",
            field=models.CharField(blank=True, default="", max_length=255),
        ),
        migrations.RunSQL(
            sql="""
            UPDATE app_selectedtable
            SET display_name = table_name
            WHERE display_name = '';
            """,
            reverse_sql=migrations.RunSQL.noop,
        ),
        migrations.RunSQL(
            sql="""
            UPDATE app_tablemetadata
            SET display_name = table_name
            WHERE display_name = '';
            """,
            reverse_sql=migrations.RunSQL.noop,
        ),
        migrations.AlterUniqueTogether(
            name="tablemetadata",
            unique_together={("project", "table_name", "object_type")},
        ),
    ]
