import os
from dataclasses import dataclass
from typing import Callable, List

import chromadb
from chromadb.config import Settings
from langchain_chroma import Chroma

from ..bootstrap import apply_runtime_defaults
from .chunk_labels import DocumentLabels, embedding_text, label_document
from .embedder import get_embedding_model


PERSIST_DIRECTORY = os.path.join(os.path.dirname(__file__), "..", "chroma_db")
# Labelled chunks run ~800 tokens, so 100 per request stays well under the 300k-token cap.
EMBED_BATCH_SIZE = 100


def _disable_chroma_telemetry() -> None:
    apply_runtime_defaults()


def _client_settings() -> Settings:
    return Settings(
        anonymized_telemetry=False,
        is_persistent=True,
        persist_directory=PERSIST_DIRECTORY,
    )


@dataclass(frozen=True)
class IndexPayload:
    """Everything needed to write one document's chunks into Chroma."""

    ids: list[str]
    documents: list[str]
    embeddings: list[list[float]]
    metadatas: list[dict]


def prepare_index_payload(
    document_id: str,
    chunks: List[str],
    label_fn: Callable[[List[str]], DocumentLabels] = label_document,
) -> IndexPayload:
    """Label and embed chunks without touching the store.

    Chroma keeps each chunk's original text; the embedding is of the chunk with its document title
    and label (see `chunk_labels`). The label is kept in metadata for the evidence reranker.
    """
    labels = label_fn(chunks)
    ids = [f"{document_id}:chunk:{index}" for index, _ in enumerate(chunks)]
    texts = [
        embedding_text(labels.title, label, chunk)
        for label, chunk in zip(labels.labels, chunks)
    ]
    metadatas = [
        {"chunk_id": chunk_id, "chunk_index": index, "label": label}
        for index, (chunk_id, label) in enumerate(zip(ids, labels.labels))
    ]
    return IndexPayload(
        ids=ids,
        documents=list(chunks),
        embeddings=_embed_in_batches(texts),
        metadatas=metadatas,
    )


def _embed_in_batches(texts: List[str]) -> list[list[float]]:
    """Embed in batches small enough to stay under OpenAI's per-request token cap."""
    model = get_embedding_model()
    vectors: list[list[float]] = []
    for start in range(0, len(texts), EMBED_BATCH_SIZE):
        vectors.extend(model.embed_documents(texts[start : start + EMBED_BATCH_SIZE]))
    return vectors


def write_index_payload(document_id: str, payload: IndexPayload) -> int:
    """Create the document's collection from a prepared payload and return its stored count."""
    _disable_chroma_telemetry()
    client = chromadb.PersistentClient(path=PERSIST_DIRECTORY, settings=_client_settings())
    collection = client.create_collection(name=document_id)
    collection.add(
        ids=payload.ids,
        documents=payload.documents,
        embeddings=payload.embeddings,
        metadatas=payload.metadatas,
    )
    return collection.count()


def replace_index_payload(document_id: str, payload: IndexPayload) -> int:
    """Replace a document's collection with one built from `payload` and return its stored count.

    The payload is written to a staging collection first. Once it holds every chunk, the old collection is
    renamed aside, the staging one takes its name, and only then is the old one deleted; if the swap fails,
    the old collection gets its name back. Any failure leaves the document searchable as before.
    """
    staging, previous = f"{document_id}-reindex", f"{document_id}-previous"
    delete_vector_store(staging)
    try:
        stored_count = write_index_payload(staging, payload)
        if stored_count != len(payload.ids):
            raise ValueError(f"stored {stored_count} of {len(payload.ids)} chunks")
    except Exception:
        delete_vector_store(staging)
        raise
    delete_vector_store(previous)
    get_persisted_collection(document_id).modify(name=previous)
    try:
        get_persisted_collection(staging).modify(name=document_id)
    except Exception:
        get_persisted_collection(previous).modify(name=document_id)
        raise
    delete_vector_store(previous)
    return stored_count


def build_vector_store(
    document_id: str,
    chunks: List[str],
    label_fn: Callable[[List[str]], DocumentLabels] = label_document,
) -> int:
    """Label, embed and store a document's chunks under `<document_id>:chunk:<index>` IDs."""
    return write_index_payload(document_id, prepare_index_payload(document_id, chunks, label_fn))


def get_vector_store(document_id: str) -> Chroma:
    _disable_chroma_telemetry()
    embeddings = get_embedding_model()
    return Chroma(
        collection_name=document_id,
        embedding_function=embeddings,
        persist_directory=PERSIST_DIRECTORY,
        client_settings=_client_settings(),
    )


def get_persisted_collection(document_id: str):
    """Open a Chroma collection without constructing an embedding model."""
    _disable_chroma_telemetry()
    client = chromadb.PersistentClient(path=PERSIST_DIRECTORY, settings=_client_settings())
    return client.get_collection(name=document_id)


def delete_vector_store(document_id: str) -> None:
    _disable_chroma_telemetry()
    client = chromadb.PersistentClient(path=PERSIST_DIRECTORY, settings=_client_settings())
    try:
        client.delete_collection(name=document_id)
    except Exception as exc:
        if "does not exist" not in str(exc).lower():
            raise


def list_document_ids() -> list[str]:
    """Every document collection in the local store."""
    _disable_chroma_telemetry()
    client = chromadb.PersistentClient(path=PERSIST_DIRECTORY, settings=_client_settings())
    return sorted(getattr(collection, "name", collection) for collection in client.list_collections())
