from langchain_ollama import OllamaEmbeddings


def get_embedding_model():
    return OllamaEmbeddings(
        model="llama3.1:8b",
        base_url="http://localhost:11434",
    )
