from django.conf import settings
from django.contrib.auth.hashers import make_password
from django.db import migrations, models
import django.db.models.deletion


DEFAULT_PROJECT_OWNER_EMAIL = "dabarera99@gmail.com"


def assign_existing_projects(apps, schema_editor):
    Project = apps.get_model("app", "Project")
    User = apps.get_model("auth", "User")

    user, created = User.objects.get_or_create(
        username=DEFAULT_PROJECT_OWNER_EMAIL,
        defaults={"email": DEFAULT_PROJECT_OWNER_EMAIL},
    )
    if not user.email:
        user.email = DEFAULT_PROJECT_OWNER_EMAIL
        user.save(update_fields=["email"])
    if created:
        user.password = make_password(None)
        user.save(update_fields=["password"])

    Project.objects.filter(owner__isnull=True).update(owner=user)


def unassign_existing_projects(apps, schema_editor):
    Project = apps.get_model("app", "Project")
    Project.objects.update(owner=None)


class Migration(migrations.Migration):

    dependencies = [
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
        ("app", "0016_alter_project_llm_provider_choices"),
    ]

    operations = [
        migrations.AddField(
            model_name="project",
            name="owner",
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.CASCADE,
                related_name="projects",
                to=settings.AUTH_USER_MODEL,
            ),
        ),
        migrations.RunPython(assign_existing_projects, unassign_existing_projects),
        migrations.AlterField(
            model_name="project",
            name="owner",
            field=models.ForeignKey(
                on_delete=django.db.models.deletion.CASCADE,
                related_name="projects",
                to=settings.AUTH_USER_MODEL,
            ),
        ),
    ]

