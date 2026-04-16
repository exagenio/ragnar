from django import forms
from django.contrib.auth.forms import UserCreationForm
from django.contrib.auth.models import User

from app.services.llm_config.llm_provider import (
    CUSTOM_MODEL_CHOICE,
    DEFAULT_PROVIDER,
    LLM_PROVIDER_CHOICES,
    PROVIDER_MODEL_CHOICES,
)


def _build_model_choice_list():
    values = []

    for provider_choices in PROVIDER_MODEL_CHOICES.values():
        for model_list in provider_choices.values():
            values.extend(model_list)

    unique_values = list(dict.fromkeys(values))
    return [(value, value) for value in unique_values] + [
        (CUSTOM_MODEL_CHOICE, "Custom model code"),
    ]


ALL_MODEL_CHOICES = _build_model_choice_list()


class RegisterForm(UserCreationForm):
    email = forms.EmailField(required=False)

    class Meta(UserCreationForm.Meta):
        model = User
        fields = ("username", "email", "password1", "password2")


class ProjectLLMSettingsBaseForm(forms.Form):
    provider_model_map = PROVIDER_MODEL_CHOICES
    llm_provider = forms.ChoiceField(
        choices=LLM_PROVIDER_CHOICES,
        initial=DEFAULT_PROVIDER,
        label="Model Provider",
    )
    primary_model_selection = forms.ChoiceField(
        choices=ALL_MODEL_CHOICES,
        initial=PROVIDER_MODEL_CHOICES[DEFAULT_PROVIDER]["primary"][0],
        label="Primary Model",
    )
    primary_model_custom = forms.CharField(
        required=False,
        label="Primary Custom Model Code",
        help_text="Use this only when the primary model is set to custom.",
    )
    secondary_model_selection = forms.ChoiceField(
        choices=ALL_MODEL_CHOICES,
        initial=PROVIDER_MODEL_CHOICES[DEFAULT_PROVIDER]["secondary"][0],
        label="Secondary Model",
    )
    secondary_model_custom = forms.CharField(
        required=False,
        label="Secondary Custom Model Code",
        help_text="Use this only when the secondary model is set to custom.",
    )
    use_custom_openrouter_api_key = forms.BooleanField(
        required=False,
        label="Use a custom OpenRouter API key",
    )
    openrouter_api_key = forms.CharField(
        required=False,
        label="OpenRouter API Key",
        widget=forms.PasswordInput(render_value=False),
        help_text="Leave blank to keep the current saved key when editing.",
    )

    custom_model_choice = CUSTOM_MODEL_CHOICE

    def __init__(self, *args, project=None, **kwargs):
        self.project = project
        super().__init__(*args, **kwargs)

        requested_provider = self._get_requested_provider()
        self._apply_provider_choices(requested_provider)

        if project:
            self.fields["llm_provider"].initial = project.llm_provider
            self._set_model_initial(
                "primary",
                project.llm_provider,
                project.primary_llm_model,
            )
            self._set_model_initial(
                "secondary",
                project.llm_provider,
                project.secondary_llm_model,
            )
            self.fields["use_custom_openrouter_api_key"].initial = (
                project.has_custom_openrouter_api_key
            )
        else:
            self._set_default_model_initials(DEFAULT_PROVIDER)

    def _get_requested_provider(self):
        if self.is_bound:
            raw_provider = self.data.get(self.add_prefix("llm_provider"))
            if raw_provider in PROVIDER_MODEL_CHOICES:
                return raw_provider

        if self.project and self.project.llm_provider in PROVIDER_MODEL_CHOICES:
            return self.project.llm_provider

        return DEFAULT_PROVIDER

    def _apply_provider_choices(self, provider):
        self.fields["primary_model_selection"].choices = [
            (value, value)
            for value in PROVIDER_MODEL_CHOICES[provider]["primary"]
        ] + [(CUSTOM_MODEL_CHOICE, "Custom model code")]

        self.fields["secondary_model_selection"].choices = [
            (value, value)
            for value in PROVIDER_MODEL_CHOICES[provider]["secondary"]
        ] + [(CUSTOM_MODEL_CHOICE, "Custom model code")]

    def _set_default_model_initials(self, provider):
        self.fields["primary_model_selection"].initial = PROVIDER_MODEL_CHOICES[
            provider
        ]["primary"][0]
        self.fields["secondary_model_selection"].initial = PROVIDER_MODEL_CHOICES[
            provider
        ]["secondary"][0]

    def _set_model_initial(self, slot, provider, current_value):
        preset_values = PROVIDER_MODEL_CHOICES.get(provider, {}).get(slot, [])
        selection_field = f"{slot}_model_selection"
        custom_field = f"{slot}_model_custom"

        if current_value in preset_values:
            self.fields[selection_field].initial = current_value
            self.fields[custom_field].initial = ""
        else:
            self.fields[selection_field].initial = CUSTOM_MODEL_CHOICE
            self.fields[custom_field].initial = current_value

    def _resolve_model_value(self, provider, slot, cleaned_data):
        selection = cleaned_data.get(f"{slot}_model_selection", "").strip()
        custom_value = cleaned_data.get(f"{slot}_model_custom", "").strip()
        preset_values = PROVIDER_MODEL_CHOICES.get(provider, {}).get(slot, [])

        if selection == CUSTOM_MODEL_CHOICE:
            if not custom_value:
                self.add_error(
                    f"{slot}_model_custom",
                    "Enter a custom model code.",
                )
                return ""
            return custom_value

        if selection not in preset_values:
            self.add_error(
                f"{slot}_model_selection",
                "Select a valid model for the chosen provider, or choose custom.",
            )
            return ""

        return selection

    def clean(self):
        cleaned_data = super().clean()

        provider = cleaned_data.get("llm_provider")
        if not provider:
            return cleaned_data

        cleaned_data["resolved_primary_model"] = self._resolve_model_value(
            provider,
            "primary",
            cleaned_data,
        )
        cleaned_data["resolved_secondary_model"] = self._resolve_model_value(
            provider,
            "secondary",
            cleaned_data,
        )

        use_custom_key = cleaned_data.get("use_custom_openrouter_api_key")
        key_input = (cleaned_data.get("openrouter_api_key") or "").strip()
        has_existing_custom_key = bool(
            self.project and self.project.has_custom_openrouter_api_key
        )

        if provider == "openrouter" and use_custom_key:
            if not key_input and not has_existing_custom_key:
                self.add_error(
                    "openrouter_api_key",
                    "Enter an OpenRouter API key or disable the custom key option.",
                )
            cleaned_data["resolved_openrouter_api_key"] = key_input or None
            cleaned_data["clear_openrouter_api_key"] = False
        else:
            cleaned_data["resolved_openrouter_api_key"] = None
            cleaned_data["clear_openrouter_api_key"] = True

        return cleaned_data


class ProjectDBConnectionForm(ProjectLLMSettingsBaseForm):
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


class ProjectLLMSettingsForm(ProjectLLMSettingsBaseForm):
    pass


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
