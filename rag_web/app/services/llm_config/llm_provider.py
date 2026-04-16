from enum import Enum

from django.conf import settings
from langchain_core.embeddings import Embeddings
from langchain_core.language_models import BaseChatModel
from langchain_google_vertexai import ChatVertexAI, VertexAIEmbeddings
from langchain_ollama import ChatOllama, OllamaEmbeddings
from langchain_openrouter import ChatOpenRouter


class LLMBackend(str, Enum):
    LOCAL = "local"
    CLOUD = "cloud"


class LLMProvider(str, Enum):
    VERTEX_AI = "vertex_ai"
    OPENROUTER = "openrouter"


class ModelSize(str, Enum):
    PRIMARY = "primary"
    SMALL = "small"


LLM_PROVIDER_CHOICES = [
    (LLMProvider.VERTEX_AI.value, "Vertex AI"),
    (LLMProvider.OPENROUTER.value, "OpenRouter"),
]

CUSTOM_MODEL_CHOICE = "__custom__"

PROVIDER_MODEL_CHOICES = {
    LLMProvider.VERTEX_AI.value: {
        "primary": [
            "gemini-2.5-pro",
            "gemini-2.5-flash",
        ],
        "secondary": [
            "gemini-2.5-pro",
            "gemini-2.5-flash",
        ],
    },
    LLMProvider.OPENROUTER.value: {
        "primary": [
            "openai/gpt-5.4",
        ],
        "secondary": [
            "openai/gpt-5.4-mini",
        ],
    },
}

DEFAULT_PROVIDER = LLMProvider.VERTEX_AI.value
DEFAULT_MODELS = {
    ModelSize.PRIMARY: PROVIDER_MODEL_CHOICES[DEFAULT_PROVIDER]["primary"][0],
    ModelSize.SMALL: PROVIDER_MODEL_CHOICES[DEFAULT_PROVIDER]["secondary"][0],
}
LOCAL_MODEL = "llama3.1:8b"


def _get_vertex_project():
    return getattr(settings, "VERTEX_AI_PROJECT", "project-08491770-bd93-473e-a10")


def _get_vertex_location():
    return getattr(settings, "VERTEX_AI_LOCATION", "us-central1")


def _resolve_provider(project=None, provider=None):
    if provider:
        return LLMProvider(provider)

    if project and getattr(project, "llm_provider", None):
        return LLMProvider(project.llm_provider)

    return LLMProvider(DEFAULT_PROVIDER)


def _resolve_model_name(model_size, project=None, provider=None, model=None):
    if model:
        return model

    if project:
        if model_size == ModelSize.PRIMARY:
            return project.primary_llm_model
        return project.secondary_llm_model

    return DEFAULT_MODELS[model_size]


def get_llm(
    *,
    backend: LLMBackend,
    model_size: ModelSize = ModelSize.PRIMARY,
    temperature: float = 0,
    project=None,
    provider: str | None = None,
    model: str | None = None,
    api_key: str | None = None,
) -> BaseChatModel:
    if backend == LLMBackend.LOCAL:
        return ChatOllama(
            model=LOCAL_MODEL,
            base_url="http://localhost:11434",
            temperature=temperature,
        )

    if backend != LLMBackend.CLOUD:
        raise ValueError(f"Unsupported LLM backend: {backend}")

    effective_provider = _resolve_provider(project=project, provider=provider)
    model_name = _resolve_model_name(
        model_size,
        project=project,
        provider=effective_provider.value,
        model=model,
    )

    if effective_provider == LLMProvider.OPENROUTER:
        effective_api_key = api_key
        if not effective_api_key and project:
            effective_api_key = project.get_openrouter_api_key() or None
        effective_api_key = effective_api_key or getattr(settings, "OPENROUTER_API_KEY", None)

        if not effective_api_key:
            raise ValueError(
                "OpenRouter API key is not configured. Save a custom key or add OPENROUTER_API_KEY."
            )

        return ChatOpenRouter(
            model=model_name,
            temperature=temperature,
            api_key=effective_api_key,
            max_retries=2,
        )

    if effective_provider == LLMProvider.VERTEX_AI:
        return ChatVertexAI(
            model=model_name,
            temperature=temperature,
            max_retries=2,
            project=_get_vertex_project(),
            location=_get_vertex_location(),
        )

    raise ValueError(f"Unsupported model provider: {effective_provider}")


def get_embeddings(
    *,
    backend: LLMBackend,
    project=None,
) -> Embeddings:
    if backend == LLMBackend.LOCAL:
        return OllamaEmbeddings(
            model=LOCAL_MODEL,
            base_url="http://localhost:11434",
        )

    if backend == LLMBackend.CLOUD:
        return VertexAIEmbeddings(
            model_name="gemini-embedding-001",
            project=_get_vertex_project(),
            location=_get_vertex_location(),
        )

    raise ValueError(f"Unsupported embeddings backend: {backend}")
