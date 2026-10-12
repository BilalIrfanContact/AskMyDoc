"""Searchable document chunks, stored in Supabase Postgres with pgvector.

See `supabase/migrations/202610110001_document_chunks.sql`. Each indexed document has a `document_indexes` row
naming its current generation and embedding model, and its chunks in `document_chunks` under that generation.
Writing inserts a new generation, then `commit_document_index` switches to it and deletes the old one in one
transaction, so a failed re-index keeps the previous chunks searchable.

`ChunkStore` answers the Chroma-style `get`/`query`/`count` calls (and result shapes) that retrieval, the chunk
inspector and the eval scripts were written against.
"""

from dataclasses import dataclass
from typing import Any, Callable, List, Sequence
from uuid import uuid4

from postgrest.types import ReturnMethod

from .ai_providers import VoyageEmbeddings, embedding_model_name
from .embedder import get_embedding_model
from .persistence.common import get_postgrest_client


# 100 chunks per request stays below the embedding provider's token caps.
EMBED_BATCH_SIZE = 100
# Each row carries a full vector as JSON (~20 KB), so inserts go 50 rows (~1 MB) at a time.
INSERT_BATCH_SIZE = 50
# Supabase's API returns at most 1,000 rows per request.
PAGE_SIZE = 1000
EMBEDDING_INPUT = "plain"

# Called with (batches done, total batches) after each embedding request or chunk insert.
BatchProgress = Callable[[int, int], None]


@dataclass(frozen=True)
class IndexPayload:
    """Everything needed to write one document's chunks."""

    ids: list[str]
    documents: list[str]
    embeddings: list[list[float]]
    metadatas: list[dict]


class MissingIndex(LookupError):
    """The document has no stored search index."""


class StaleEmbeddings(RuntimeError):
    """The document was embedded with a different model or an older input format."""


class ChunkStore:
    """One document's current chunks. `embeddings` is set only when opened for search (`get_vector_store`)."""

    def __init__(self, document_id: str, index_row: dict, embeddings: VoyageEmbeddings | None = None):
        self.document_id = document_id
        self.generation = index_row["generation"]
        self.metadata = {
            "embedding_model": index_row["embedding_model"],
            "embedding_input": index_row["embedding_input"],
        }
        self._count = index_row["chunk_count"]
        self.embeddings = embeddings

    def count(self) -> int:
        return self._count

    def get(
        self,
        ids: Sequence[str] | None = None,
        limit: int | None = None,
        include: Sequence[str] = ("documents", "metadatas"),
    ) -> dict[str, list]:
        """Chunks in document order, optionally only `ids` or the first `limit`, as Chroma's `get` shapes them."""
        if ids is not None and not ids:
            return _shape([], include)
        rows: list[dict] = []
        while True:
            wanted = PAGE_SIZE if limit is None else min(PAGE_SIZE, limit - len(rows))
            if wanted <= 0:
                break
            request = (
                get_postgrest_client()
                .from_("document_chunks")
                .select("chunk_id, content, metadata")
                .eq("document_id", self.document_id)
                .eq("generation", self.generation)
            )
            if ids is not None:
                request = request.in_("chunk_id", list(ids))
            page = request.order("chunk_index").range(len(rows), len(rows) + wanted - 1).execute().data or []
            rows.extend(page)
            if len(page) < wanted:
                break
        return _shape(rows, include)

    def query(
        self,
        query_embeddings: Sequence[Sequence[float]],
        n_results: int,
        include: Sequence[str] = ("documents", "metadatas"),
    ) -> dict[str, list]:
        """The `n_results` nearest chunks for each query embedding, as Chroma's `query` shapes them (one list per query)."""
        groups = [
            _shape(
                get_postgrest_client()
                .rpc(
                    "match_document_chunks",
                    {
                        "p_document_id": self.document_id,
                        "p_generation": self.generation,
                        "p_query": list(embedding),
                        "p_count": n_results,
                    },
                )
                .execute()
                .data
                or [],
                include,
            )
            for embedding in query_embeddings
        ]
        return {key: [group[key] for group in groups] for key in ("ids", *include)}


def _shape(rows: Sequence[dict], include: Sequence[str]) -> dict[str, list]:
    shaped: dict[str, list] = {"ids": [row["chunk_id"] for row in rows]}
    if "documents" in include:
        shaped["documents"] = [row["content"] for row in rows]
    if "metadatas" in include:
        shaped["metadatas"] = [row["metadata"] for row in rows]
    return shaped


def prepare_index_payload(
    document_id: str,
    chunks: List[str],
    kept_metadata: Sequence[dict] | None = None,
    on_batch: BatchProgress | None = None,
) -> IndexPayload:
    """Embed chunks without touching the store.

    Only the chunk text is embedded, with no chat model calls. `kept_metadata` carries what a document already
    has when it is re-embedded, such as labels from the earlier labelling experiment, which the eval
    scripts' evidence picker still reads.
    """
    ids = [f"{document_id}:chunk:{index}" for index, _ in enumerate(chunks)]
    metadatas = [
        {**(kept_metadata[index] if kept_metadata else {}), "chunk_id": chunk_id, "chunk_index": index}
        for index, chunk_id in enumerate(ids)
    ]
    return IndexPayload(
        ids=ids,
        documents=list(chunks),
        embeddings=_embed_in_batches(list(chunks), on_batch),
        metadatas=metadatas,
    )


def _embed_in_batches(texts: List[str], on_batch: BatchProgress | None = None) -> list[list[float]]:
    """Embed in batches of `EMBED_BATCH_SIZE`, keeping each request well under provider token caps."""
    model = get_embedding_model()
    vectors: list[list[float]] = []
    starts = range(0, len(texts), EMBED_BATCH_SIZE)
    for done, start in enumerate(starts, 1):
        vectors.extend(model.embed_documents(texts[start : start + EMBED_BATCH_SIZE]))
        if on_batch:
            on_batch(done, len(starts))
    return vectors


def write_index_payload(
    document_id: str,
    payload: IndexPayload,
    embedding_model: str | None = None,
    embedding_input: str = EMBEDDING_INPUT,
    on_batch: BatchProgress | None = None,
) -> int:
    """Make `payload` the document's chunks, replacing any it had, and return the stored count.

    The old chunks stay searchable until every new one is stored. `embedding_model` defaults to the current
    model; the one-time Chroma copy passes the model that actually produced the vectors.
    """
    client = get_postgrest_client()
    generation = str(uuid4())
    rows = [
        {
            "document_id": document_id,
            "generation": generation,
            "chunk_index": index,
            "chunk_id": chunk_id,
            # Some PDFs extract with NUL characters, which Postgres text cannot hold; they carry no meaning.
            "content": document.replace("\x00", ""),
            "metadata": metadata,
            "embedding": embedding,
        }
        for index, (chunk_id, document, metadata, embedding) in enumerate(
            zip(payload.ids, payload.documents, payload.metadatas, payload.embeddings, strict=True)
        )
    ]
    try:
        starts = range(0, len(rows), INSERT_BATCH_SIZE)
        for done, start in enumerate(starts, 1):
            client.from_("document_chunks").insert(rows[start : start + INSERT_BATCH_SIZE], returning=ReturnMethod.minimal).execute()
            if on_batch:
                on_batch(done, len(starts))
    except Exception:
        # Nothing has been committed, so this generation can't be the current one.
        client.from_("document_chunks").delete().eq("document_id", document_id).eq("generation", generation).execute()
        raise
    try:
        stored: Any = client.rpc(
            "commit_document_index",
            {
                "p_document_id": document_id,
                "p_generation": generation,
                "p_embedding_model": embedding_model or embedding_model_name(),
                "p_embedding_input": embedding_input,
                "p_expected_count": len(rows),
            },
        ).execute().data
    except Exception:
        # The commit may have gone through even though its reply was lost, and it has then already deleted the
        # old chunks, so this generation is never deleted here. If it isn't current, reads ignore it, and the
        # document's next write or `delete_vector_store` removes it.
        if _current_generation(document_id) == generation:
            return len(rows)
        raise
    return int(stored)


def _current_generation(document_id: str) -> str | None:
    """The document's committed generation, or None if it has none or it can't be read right now."""
    try:
        rows = (
            get_postgrest_client()
            .from_("document_indexes")
            .select("generation")
            .eq("document_id", document_id)
            .limit(1)
            .execute()
            .data
        )
    except Exception:
        return None
    return rows[0]["generation"] if rows else None


def build_vector_store(
    document_id: str,
    chunks: List[str],
    on_embed: BatchProgress | None = None,
    on_save: BatchProgress | None = None,
) -> int:
    """Embed and store a document's chunks under `<document_id>:chunk:<index>` IDs."""
    payload = prepare_index_payload(document_id, chunks, on_batch=on_embed)
    return write_index_payload(document_id, payload, on_batch=on_save)


def open_index(document_id: str) -> ChunkStore:
    """Open a document's stored chunks for reading, without an embedding model or a model check."""
    rows = (
        get_postgrest_client()
        .from_("document_indexes")
        .select("generation, embedding_model, embedding_input, chunk_count")
        .eq("document_id", document_id)
        .limit(1)
        .execute()
        .data
    )
    if not rows:
        raise MissingIndex(f"Document {document_id} has no search index.")
    return ChunkStore(document_id, rows[0])


def get_vector_store(document_id: str) -> ChunkStore:
    """Open a document's chunks for search, requiring the current model and plain input format.

    Vectors from different embedding models can't be compared, so such a document must be re-embedded
    first (`backend/scripts/reindex_documents.py`).
    """
    store = open_index(document_id)
    stored_model = store.metadata["embedding_model"]
    stored_input = store.metadata["embedding_input"]
    if stored_model != embedding_model_name() or stored_input != EMBEDDING_INPUT:
        raise StaleEmbeddings(
            f"This document was indexed with {stored_model} ({stored_input} chunks), "
            f"but search now uses {embedding_model_name()} ({EMBEDDING_INPUT} chunks). "
            f"Re-embed it: python -m backend.scripts.reindex_documents {document_id}"
        )
    store.embeddings = get_embedding_model()
    return store


def delete_vector_store(document_id: str) -> None:
    """Remove a document's index and chunks; a document with none is left as is."""
    client = get_postgrest_client()
    client.from_("document_indexes").delete().eq("document_id", document_id).execute()
    client.from_("document_chunks").delete().eq("document_id", document_id).execute()


def list_document_ids() -> list[str]:
    """Every document with a stored search index."""
    ids: list[str] = []
    while True:
        page = (
            get_postgrest_client()
            .from_("document_indexes")
            .select("document_id")
            .order("document_id")
            .range(len(ids), len(ids) + PAGE_SIZE - 1)
            .execute()
            .data
            or []
        )
        ids.extend(row["document_id"] for row in page)
        if len(page) < PAGE_SIZE:
            return ids
