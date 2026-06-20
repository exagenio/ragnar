from langchain_postgres import PGVector
from django.conf import settings

from app.services.llm_config.llm_provider import (
    get_embeddings,
    LLMBackend,
)
from .vector_db_config import VECTOR_DB_CONNECTION_STRING


COLLECTION_NAME = "metadata_embeddings"


def get_vector_store(backend: LLMBackend | None = None, project=None):
    """
    Returns a PGVector store using embeddings from the unified LLM provider.
    """

    backend = backend or LLMBackend(settings.DEFAULT_LLM_BACKEND)

    embeddings = get_embeddings(backend=backend, project=project)

    return PGVector(
        connection=VECTOR_DB_CONNECTION_STRING,
        collection_name=COLLECTION_NAME,
        embeddings=embeddings,
        use_jsonb=True,
    )
