import os

from langchain_openai import OpenAIEmbeddings


def get_embedding_model() -> OpenAIEmbeddings:
    model = os.getenv("OPENAI_EMBEDDING_MODEL", "text-embedding-3-large")
    return OpenAIEmbeddings(model=model)
