import os
from dataclasses import dataclass
from typing import Callable, List

import chromadb
from chromadb.config import Settings
from langchain_chroma import Chroma

from ..bootstrap import apply_runtime_defaults
from .chunk_labels import DocumentLabels, label_document
from .ai_providers import embedding_model_name
from .embedder import get_embedding_model


PERSIST_DIRECTORY = os.path.join(os.path.dirname(__file__), "..", "chroma_db")
# 100 chunks per request stays below the embedding provider's token caps.
EMBED_BATCH_SIZE = 100
EMBEDDING_INPUT = "plain"


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

    Embed only the original text: adding titles and labels reduced Voyage retrieval coverage in the
    working-set experiment. Keep labels and titles as metadata for reranking and later re-embedding.
    """
    labels = label_fn(chunks)
    ids = [f"{document_id}:chunk:{index}" for index, _ in enumerate(chunks)]
    metadatas = [
        {"chunk_id": chunk_id, "chunk_index": index, "label": label, "document_title": labels.title}
        for index, (chunk_id, label) in enumerate(zip(ids, labels.labels))
    ]
    return IndexPayload(
        ids=ids,
        documents=list(chunks),
        embeddings=_embed_in_batches(list(chunks)),
        metadatas=metadatas,
    )


def _embed_in_batches(texts: List[str]) -> list[list[float]]:
    """Embed in batches of `EMBED_BATCH_SIZE`, keeping each request well under provider token caps."""
    model = get_embedding_model()
    vectors: list[list[float]] = []
    for start in range(0, len(texts), EMBED_BATCH_SIZE):
        vectors.extend(model.embed_documents(texts[start : start + EMBED_BATCH_SIZE]))
    return vectors


def write_index_payload(document_id: str, payload: IndexPayload) -> int:
    """Create the document's collection from a prepared payload and return its stored count."""
    _disable_chroma_telemetry()
    client = chromadb.PersistentClient(path=PERSIST_DIRECTORY, settings=_client_settings())
    collection = client.create_collection(
        name=document_id,
        metadata={"embedding_model": embedding_model_name(), "embedding_input": EMBEDDING_INPUT},
    )
    collection.add(
        ids=payload.ids,
        documents=payload.documents,
        embeddings=payload.embeddings,
        metadatas=payload.metadatas,
    )
    return collection.count()


_STAGING, _PREVIOUS = "-reindex", "-previous"


def restore_interrupted_swap(document_id: str) -> bool:
    """Give the document back its set-aside collection if a swap stopped between its two renames.

    Returns True if it did. Without this, the document would stay unsearchable until fixed by hand.
    """
    names = set(_collection_names())
    previous = f"{document_id}{_PREVIOUS}"
    if document_id in names or previous not in names:
        return False
    get_persisted_collection(previous).modify(name=document_id)
    return True


def replace_index_payload(document_id: str, payload: IndexPayload) -> int:
    """Replace a document's collection with one built from `payload` and return its stored count.

    The payload is written to a staging collection first. Once it holds every chunk, the old collection is
    renamed aside, the staging one takes its name, and only then is the old one deleted; if the swap fails,
    the old collection gets its name back. A swap the process never finished is undone first (see
    `restore_interrupted_swap`), so the set-aside copy is only deleted while the document has its own.
    """
    staging, previous = f"{document_id}{_STAGING}", f"{document_id}{_PREVIOUS}"
    restore_interrupted_swap(document_id)
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


class StaleEmbeddings(RuntimeError):
    """The document was embedded with a different model or an older input format."""


def get_vector_store(document_id: str) -> Chroma:
    """Open a document's collection for search, requiring the current model and plain input format.

    Vectors from different embedding models can't be compared, so such a document must be re-embedded
    first (`backend/scripts/reindex_documents.py --reembed`). Older labelled-input collections must also
    be re-embedded. Collections created before the model was recorded used OpenAI's `text-embedding-3-large`.
    """
    _disable_chroma_telemetry()
    metadata = get_persisted_collection(document_id).metadata or {}
    stored_model = metadata.get("embedding_model", "text-embedding-3-large")
    stored_input = metadata.get("embedding_input", "labelled")
    if stored_model != embedding_model_name() or stored_input != EMBEDDING_INPUT:
        raise StaleEmbeddings(
            f"This document was indexed with {stored_model} ({stored_input} chunks), "
            f"but search now uses {embedding_model_name()} ({EMBEDDING_INPUT} chunks). "
            f"Re-embed it: python -m backend.scripts.reindex_documents --reembed {document_id}"
        )
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


def _collection_names() -> list[str]:
    _disable_chroma_telemetry()
    client = chromadb.PersistentClient(path=PERSIST_DIRECTORY, settings=_client_settings())
    return [getattr(collection, "name", collection) for collection in client.list_collections()]


def list_document_ids() -> list[str]:
    """Every document collection in the local store, without the temporary ones a re-index swap uses."""
    return sorted(name for name in _collection_names() if not name.endswith((_STAGING, _PREVIOUS)))
