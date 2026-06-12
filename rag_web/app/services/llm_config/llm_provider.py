from enum import Enum
import threading

from django.conf import settings
from langchain_core.embeddings import Embeddings
from langchain_core.language_models import BaseChatModel
from langchain_google_vertexai import ChatVertexAI, VertexAIEmbeddings
from langchain_ollama import ChatOllama
from langchain_openrouter import ChatOpenRouter
from sentence_transformers import SentenceTransformer


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
    (LLMProvider.OPENROUTER.value, "OpenRouter"),
    (LLMProvider.VERTEX_AI.value, "Vertex AI"),
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

DEFAULT_PROVIDER = LLMProvider.OPENROUTER.value
DEFAULT_MODELS = {
    ModelSize.PRIMARY: PROVIDER_MODEL_CHOICES[DEFAULT_PROVIDER]["primary"][0],
    ModelSize.SMALL: PROVIDER_MODEL_CHOICES[DEFAULT_PROVIDER]["secondary"][0],
}
LOCAL_MODEL = "llama3.1:8b"
LOCAL_EMBEDDING_MODEL = "all-MiniLM-L6-v2"
_sentence_transformer_models = {}
_sentence_transformer_lock = threading.Lock()


class SentenceTransformersEmbeddings(Embeddings):
    def __init__(self, model_name: str):
        self.model_name = model_name
        self.model = get_sentence_transformer_model(model_name)

    def embed_documents(self, texts, **kwargs):
        embeddings = self.model.encode(
            texts,
            show_progress_bar=False,
            convert_to_numpy=True,
        )
        return [emb.tolist() for emb in embeddings]

    def embed_query(self, text, **kwargs):
        embedding = self.model.encode(
            text,
            show_progress_bar=False,
            convert_to_numpy=True,
        )
        return embedding.tolist()


def get_sentence_transformer_model(model_name: str):
    """Return one shared SentenceTransformer instance per model and process."""

    model = _sentence_transformer_models.get(model_name)
    if model is not None:
        return model

    with _sentence_transformer_lock:
        model = _sentence_transformer_models.get(model_name)
        if model is None:
            model = SentenceTransformer(model_name)
            _sentence_transformer_models[model_name] = model
        return model


def _get_vertex_project():
    return getattr(settings, "VERTEX_AI_PROJECT", None)


def _get_vertex_location():
    return getattr(settings, "VERTEX_AI_LOCATION", "us-central1")


def _resolve_provider(project=None, provider=None):
    if provider:
        return LLMProvider(provider)

    if project and getattr(project, "llm_provider", None):
        project_provider = LLMProvider(project.llm_provider)
        if project_provider == LLMProvider.VERTEX_AI and not _get_vertex_project():
            return LLMProvider.OPENROUTER
        return project_provider

    return LLMProvider(DEFAULT_PROVIDER)


def _resolve_model_name(model_size, project=None, provider=None, model=None):
    if model:
        return model

    if project and provider and getattr(project, "llm_provider", None) == provider:
        if model_size == ModelSize.PRIMARY:
            return project.primary_llm_model
        return project.secondary_llm_model

    provider_models = PROVIDER_MODEL_CHOICES.get(provider or DEFAULT_PROVIDER)
    if provider_models:
        if model_size == ModelSize.PRIMARY:
            return provider_models["primary"][0]
        return provider_models["secondary"][0]

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
        vertex_project = _get_vertex_project()
        if not vertex_project:
            raise ValueError(
                "Vertex AI project is not configured. Set VERTEX_AI_PROJECT or choose OpenRouter."
            )

        return ChatVertexAI(
            model=model_name,
            temperature=temperature,
            max_retries=2,
            project=vertex_project,
            location=_get_vertex_location(),
        )

    raise ValueError(f"Unsupported model provider: {effective_provider}")


def get_embeddings(
    *,
    backend: LLMBackend | str,
    project=None,
) -> Embeddings:
    backend = LLMBackend(backend)

    if backend == LLMBackend.LOCAL:
        return SentenceTransformersEmbeddings(
            model_name=getattr(settings, "LOCAL_EMBEDDING_MODEL", LOCAL_EMBEDDING_MODEL)
        )

    if backend == LLMBackend.CLOUD:
        return VertexAIEmbeddings(
            model_name="gemini-embedding-001",
            project=_get_vertex_project(),
            location=_get_vertex_location(),
        )

    raise ValueError(f"Unsupported embeddings backend: {backend}")
