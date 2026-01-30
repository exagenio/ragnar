from enum import Enum
from typing import Literal

from langchain_core.language_models import BaseChatModel
from langchain_core.embeddings import Embeddings

# === Local (Ollama) ===
from langchain_ollama import ChatOllama, OllamaEmbeddings

# === Cloud (Gemini) ===
from langchain_google_genai import (
    ChatGoogleGenerativeAI,
    GoogleGenerativeAIEmbeddings,
)

from django.conf import settings


# ==========================
# ENUMS
# ==========================

class LLMBackend(str, Enum):
    LOCAL = "local"
    CLOUD = "cloud"


class ModelSize(str, Enum):
    PRIMARY = "primary"   # High quality
    SMALL = "small"       # Cheaper / faster


# ==========================
# MODEL REGISTRY
# ==========================

CLOUD_MODELS = {
    ModelSize.PRIMARY: "gemini-2.5-pro",
    ModelSize.SMALL: "gemini-2.5-flash",
}

LOCAL_MODEL = "llama3.1:8b"


# ==========================
# LLM FACTORY
# ==========================

def get_llm(
    *,
    backend: LLMBackend,
    model_size: ModelSize = ModelSize.PRIMARY,
    temperature: float = 0,
) -> BaseChatModel:
    """
    Returns a LangChain ChatModel based on backend and size.
    """

    if backend == LLMBackend.LOCAL:
        return ChatOllama(
            model=LOCAL_MODEL,
            base_url="http://localhost:11434",
            temperature=temperature,
        )

    if backend == LLMBackend.CLOUD:
        return ChatGoogleGenerativeAI(
            model=CLOUD_MODELS[model_size],
            google_api_key=settings.GOOGLE_API_KEY,
            temperature=temperature,
            max_retries=2,
        )

    raise ValueError(f"Unsupported LLM backend: {backend}")


# ==========================
# EMBEDDINGS FACTORY
# ==========================

def get_embeddings(
    *,
    backend: LLMBackend,
) -> Embeddings:
    """
    Returns embeddings model based on backend.
    """

    if backend == LLMBackend.LOCAL:
        return OllamaEmbeddings(
            model=LOCAL_MODEL,
            base_url="http://localhost:11434",
        )

    if backend == LLMBackend.CLOUD:
        return GoogleGenerativeAIEmbeddings(
            model="models/embedding-001",
            google_api_key=settings.GOOGLE_API_KEY,
        )

    raise ValueError(f"Unsupported embeddings backend: {backend}")
