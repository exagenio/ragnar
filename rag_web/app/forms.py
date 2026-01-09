from django import forms

class ProjectDBConnectionForm(forms.Form):
    # 🔹 Project info
    project_name = forms.CharField(
        max_length=255,
        label="Project Name"
    )

    project_description = forms.CharField(
        required=False,
        widget=forms.Textarea,
        label="Project Description"
    )

    # 🔹 Database info
    DB_TYPE_CHOICES = [
        ("postgres", "PostgreSQL"),
        ("mysql", "MySQL"),
    ]

    db_type = forms.ChoiceField(
        choices=DB_TYPE_CHOICES,
        initial="postgres",
        label="Database Type"
    )

    host = forms.CharField(
        max_length=255,
        initial="localhost",
        label="Host"
    )

    port = forms.IntegerField(
        initial=5432,
        label="Port"
    )

    database_name = forms.CharField(
        max_length=255,
        label="Database Name"
    )

    username = forms.CharField(
        max_length=255,
        label="Username"
    )

    password = forms.CharField(
        widget=forms.PasswordInput,
        label="Password"
    )

    schema = forms.CharField(
        max_length=255,
        initial="public",
        label="Schema"
    )

    from django import forms

class TableSelectionForm(forms.Form):
    tables = forms.MultipleChoiceField(
        widget=forms.CheckboxSelectMultiple,
        label="Select Tables for This Project"
    )

    def __init__(self, *args, **kwargs):
        table_choices = kwargs.pop("table_choices", [])
        super().__init__(*args, **kwargs)
        self.fields["tables"].choices = table_choices

