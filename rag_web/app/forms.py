from django import forms
from django.contrib.auth.forms import UserCreationForm
from django.contrib.auth.models import User


class RegisterForm(UserCreationForm):
    email = forms.EmailField(required=False)

    class Meta(UserCreationForm.Meta):
        model = User
        fields = ("username", "email", "password1", "password2")


class ProjectDBConnectionForm(forms.Form):
    project_name = forms.CharField(max_length=255, label="Project Name")
    project_description = forms.CharField(
        required=False,
        widget=forms.Textarea,
        label="Project Description",
    )

    DB_TYPE_CHOICES = [
        ("postgres", "PostgreSQL"),
        ("mysql", "MySQL"),
    ]

    db_type = forms.ChoiceField(
        choices=DB_TYPE_CHOICES,
        initial="postgres",
        label="Database Type",
    )
    host = forms.CharField(
        max_length=255,
        initial="localhost",
        label="Host",
    )
    port = forms.IntegerField(initial=5432, label="Port")
    database_name = forms.CharField(max_length=255, label="Database Name")
    username = forms.CharField(max_length=255, label="Username")
    password = forms.CharField(widget=forms.PasswordInput, label="Password")
    schema = forms.CharField(
        max_length=255,
        initial="public",
        label="Schema",
    )


class TableSelectionForm(forms.Form):
    tables = forms.MultipleChoiceField(
        widget=forms.CheckboxSelectMultiple,
        label="Select Tables for This Project",
    )

    def __init__(self, *args, **kwargs):
        table_choices = kwargs.pop("table_choices", [])
        super().__init__(*args, **kwargs)
        self.fields["tables"].choices = table_choices


class ReportIntentForm(forms.Form):
    industry = forms.CharField(max_length=100)
    report_type = forms.CharField(max_length=150)
    audience = forms.CharField(max_length=150)
    purpose = forms.CharField(widget=forms.Textarea)
    focus_areas = forms.CharField(widget=forms.Textarea, required=False)
    additional_notes = forms.CharField(
        widget=forms.Textarea,
        required=False,
    )
