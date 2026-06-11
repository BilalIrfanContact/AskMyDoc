import os
from typing import List

import chromadb
from chromadb.config import Settings
from langchain_chroma import Chroma

from ..bootstrap import apply_runtime_defaults
from .embedder import get_embedding_model


PERSIST_DIRECTORY = os.path.join(os.path.dirname(__file__), "..", "chroma_db")


def _disable_chroma_telemetry() -> None:
    apply_runtime_defaults()


def _client_settings() -> Settings:
    return Settings(
        anonymized_telemetry=False,
        is_persistent=True,
        persist_directory=PERSIST_DIRECTORY,
    )


def build_vector_store(document_id: str, chunks: List[str]) -> int:
    _disable_chroma_telemetry()
    embeddings = get_embedding_model()
    ids = [f"{document_id}:chunk:{index}" for index, _ in enumerate(chunks)]
    metadatas = [
        {"chunk_id": chunk_id, "chunk_index": index}
        for index, chunk_id in enumerate(ids)
    ]
    vectordb = Chroma.from_texts(
        texts=chunks,
        ids=ids,
        metadatas=metadatas,
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
