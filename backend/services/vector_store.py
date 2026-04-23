import os
from typing import List

import chromadb
from chromadb.config import Settings
from langchain_chroma import Chroma

from .embedder import get_embedding_model


PERSIST_DIRECTORY = os.path.join(os.path.dirname(__file__), "..", "chroma_db")


def _disable_chroma_telemetry() -> None:
    # Chroma may attempt telemetry in some environments; disable to avoid noisy errors.
    os.environ.setdefault("ANONYMIZED_TELEMETRY", "false")
    os.environ.setdefault("CHROMA_TELEMETRY", "false")
    os.environ.setdefault("CHROMA_ENABLE_TELEMETRY", "false")
    os.environ.setdefault("POSTHOG_DISABLED", "1")


def _client_settings() -> Settings:
    return Settings(
        anonymized_telemetry=False,
        is_persistent=True,
        persist_directory=PERSIST_DIRECTORY,
    )


def build_vector_store(document_id: str, chunks: List[str]) -> int:
    _disable_chroma_telemetry()
    embeddings = get_embedding_model()
    vectordb = Chroma.from_texts(
        texts=chunks,
        embedding=embeddings,
        collection_name=document_id,
        persist_directory=PERSIST_DIRECTORY,
        client_settings=_client_settings(),
    )
    try:
        return vectordb._collection.count()
    except Exception:
        return len(chunks)


def get_vector_store(document_id: str) -> Chroma:
    _disable_chroma_telemetry()
    embeddings = get_embedding_model()
    return Chroma(
        collection_name=document_id,
        embedding_function=embeddings,
        persist_directory=PERSIST_DIRECTORY,
        client_settings=_client_settings(),
    )


def delete_vector_store(document_id: str) -> None:
    _disable_chroma_telemetry()
    client = chromadb.PersistentClient(path=PERSIST_DIRECTORY, settings=_client_settings())
    try:
        client.delete_collection(name=document_id)
    except Exception as exc:
        if "does not exist" not in str(exc).lower():
            raise
