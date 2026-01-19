from langchain_postgres import PGVector
from .ollama_embeddings import get_embedding_model
from .vector_db_config import VECTOR_DB_CONNECTION_STRING


COLLECTION_NAME = "metadata_embeddings"


def get_vector_store():
    return PGVector(
        connection=VECTOR_DB_CONNECTION_STRING,
        collection_name=COLLECTION_NAME,
        embeddings=get_embedding_model(),
        use_jsonb=True,
    )
