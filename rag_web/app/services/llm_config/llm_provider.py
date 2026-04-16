from enum import Enum
from typing import Literal

from langchain_core.language_models import BaseChatModel
from langchain_core.embeddings import Embeddings
from langchain_ollama import ChatOllama, OllamaEmbeddings
from langchain_google_genai import (
    ChatGoogleGenerativeAI,
    GoogleGenerativeAIEmbeddings,
)

from django.conf import settings
from langchain_openrouter import ChatOpenRouter
from langchain_google_vertexai import ChatVertexAI
from langchain_google_vertexai import VertexAIEmbeddings


# ENUMS
class LLMBackend(str, Enum):
    LOCAL = "local"
    CLOUD = "cloud"


class ModelSize(str, Enum):
    PRIMARY = "primary"   # High quality
    SMALL = "small"       # Cheaper / faster



# MODEL REGISTRY
CLOUD_MODELS = {
    ModelSize.PRIMARY: "openai/gpt-5.4",
    ModelSize.SMALL: "openai/gpt-5.4-mini",
}
# CLOUD_MODELS = {
#     ModelSize.PRIMARY: "gemini-2.5-pro",
#     ModelSize.SMALL: "gemini-2.5-flash",
# }

LOCAL_MODEL = "llama3.1:8b"


# LLM FACTORY

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
        return ChatOpenRouter(
            model=CLOUD_MODELS[model_size],
            temperature=temperature,
            api_key=settings.OPENROUTER_API_KEY,
            max_retries=2,
        )
        # return ChatGoogleGenerativeAI(
        #     model=CLOUD_MODELS[model_size],
        #     google_api_key=settings.GOOGLE_API_KEY,
        #     temperature=temperature,
        #     max_retries=2,
        # )
        # return ChatVertexAI(
        #     model=CLOUD_MODELS[model_size],
        #     temperature=temperature,
        #     max_retries=2,
        #     project="project-08491770-bd93-473e-a10",
        # )

    raise ValueError(f"Unsupported LLM backend: {backend}")


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
        # return GoogleGenerativeAIEmbeddings(
        #     model="gemini-embedding-001",
        #     google_api_key=settings.GOOGLE_API_KEY,
        # )
        return VertexAIEmbeddings(
            model_name="gemini-embedding-001",
             project="project-08491770-bd93-473e-a10"
        )

    raise ValueError(f"Unsupported embeddings backend: {backend}")
