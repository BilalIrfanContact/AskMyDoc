from typing import Callable, Literal, Sequence

from .evidence_reranker import RERANK_POOL, Candidate, pick_evidence
from .keyword_search import bm25_rank, reciprocal_rank_fusion
from .rag_pipeline import AnswerCitation, GenerationAdapter, RetrievedContext


RetrievalMode = Literal["head", "semantic"]


HYBRID_CANDIDATES = 50
PLANNED_CANDIDATES = 20
Planner = Callable[[str], list[str]]


def select_with_reserved_slots(question_ranking: Sequence[str], need_rankings: Sequence[Sequence[str]], limit: int) -> list[str]:
    """Pick `limit` chunk IDs: first each need's best chunk not already picked (one reserved slot per
    need, in order), then fill the rest by fusing every ranking, the original question's included.
    """
    picked: list[str] = []
    for ranking in need_rankings:
        if len(picked) >= limit:
            break
        best = next((chunk_id for chunk_id in ranking if chunk_id not in picked), None)
        if best is not None:
            picked.append(best)
    for chunk_id in reciprocal_rank_fusion([question_ranking, *need_rankings]):
        if len(picked) >= limit:
            break
        if chunk_id not in picked:
            picked.append(chunk_id)
    return picked


class ChromaRetrievalAdapter:
    """Keep Chroma's concrete and private details outside the answer policy.

    `hybrid`, `reranker` and `planner` are separate search strategies; pass at most one.

    With `hybrid=True`, semantic retrieval merges the embedding ranking with a BM25 keyword ranking
    over the document's chunks (reciprocal rank fusion), so exact financial terms count.

    With a `reranker` model, semantic retrieval shortlists `RERANK_POOL` chunks by embedding and lets
    the model pick the ones the question needs, up to `limit` (see `evidence_reranker`). If the model's
    reply is unusable, the top `limit` chunks by embedding are returned instead. A document small enough
    to fit within `limit` skips the model call and returns everything.

    With a `planner`, semantic retrieval also searches for each piece of evidence the planner says the
    question needs, and reserves a result slot per need (see `select_with_reserved_slots`). The plan is
    cached per question and the last one is kept in `last_plan`.
    """

    def __init__(
        self,
        vectordb,
        hybrid: bool = False,
        planner: Planner | None = None,
        reranker: GenerationAdapter | None = None,
    ):
        if sum([hybrid, planner is not None, reranker is not None]) > 1:
            raise ValueError("use one of hybrid, planner or reranker; they don't combine")
        self._vectordb = vectordb
        self._reranker = reranker
        self._hybrid = hybrid
        self._planner = planner
        self._plans: dict[str, list[str]] = {}
        self.last_plan: list[str] | None = None

    def count(self) -> int | None:
        try:
            return self._vectordb._collection.count()
        except Exception:
            return None

    def retrieve(self, mode: RetrievalMode, question: str, limit: int) -> RetrievedContext:
        if mode == "head":
            return self._head_context(limit)
        if self._planner is not None:
            return self._planned_context(question, limit)
        if self._hybrid:
            return self._hybrid_context(question, limit)
        if self._reranker is not None:
            return self._reranked_context(question, limit)
        return self._semantic_context(question, limit)

    def _head_context(self, limit: int) -> RetrievedContext:
        result = self._vectordb.get(limit=limit, include=["documents", "metadatas"])
        documents: Sequence[str] = result.get("documents") or []
        metadatas: Sequence[dict | None] = result.get("metadatas") or []
        ids: Sequence[str | None] = result.get("ids") or []
        citations = []
        cited_documents = []
        for index, document in enumerate(documents):
            if not document:
                continue
            citation = self._citation_from_metadata(metadatas, ids, index, document)
            if citation is None:
                continue
            citations.append(citation)
            cited_documents.append(document)
        return RetrievedContext(
            text="\n\n".join(cited_documents).strip(),
            citations=citations,
            retrieved_document_count=len([document for document in documents if document]),
        )

    def _semantic_context(self, question: str, limit: int) -> RetrievedContext:
        embedding_function = getattr(self._vectordb, "embeddings", None)
        if embedding_function is None:
            raise ValueError("Vector store is missing an embedding function.")
        query_embedding = embedding_function.embed_query(question)
        result = self._vectordb._collection.query(
            query_embeddings=[query_embedding],
            n_results=limit,
            include=["documents", "metadatas"],
        )
        documents_groups: Sequence[Sequence[str | None]] = result.get("documents") or []
        metadatas_groups: Sequence[Sequence[dict | None]] = result.get("metadatas") or []
        ids_groups: Sequence[Sequence[str | None]] = result.get("ids") or []

        documents = documents_groups[0] if documents_groups else []
        metadatas = metadatas_groups[0] if metadatas_groups else []
        ids = ids_groups[0] if ids_groups else []

        citations = []
        cited_texts = []
        for index, document in enumerate(documents):
            if not document:
                continue
            citation = self._citation_from_metadata(metadatas, ids, index, document)
            if citation is None:
                continue
            citations.append(citation)
            cited_texts.append(document)
        return RetrievedContext(
            text="\n\n".join(cited_texts).strip(),
            citations=citations,
            retrieved_document_count=len([document for document in documents if document]),
        )

    def _reranked_context(self, question: str, limit: int) -> RetrievedContext:
        shortlist = self._semantic_context(question, max(RERANK_POOL, limit))
        if len(shortlist.citations) <= limit:
            return shortlist
        labels = self._labels([citation.chunk_id for citation in shortlist.citations])
        candidates = [
            Candidate(label=labels.get(citation.chunk_id, ""), text=citation.excerpt)
            for citation in shortlist.citations
        ]
        picked = pick_evidence(question, candidates, limit, self._reranker) or list(range(min(limit, len(candidates))))
        citations = [shortlist.citations[index] for index in picked]
        return RetrievedContext(
            text="\n\n".join(citation.excerpt for citation in citations).strip(),
            citations=citations,
            retrieved_document_count=len(citations),
        )

    def _labels(self, chunk_ids: Sequence[str]) -> dict[str, str]:
        """Chunk labels written at indexing time; documents indexed before labelling have none."""
        if not chunk_ids:
            return {}
        stored = self._vectordb._collection.get(ids=list(chunk_ids), include=["metadatas"])
        return {
            chunk_id: (metadata or {}).get("label") or ""
            for chunk_id, metadata in zip(stored.get("ids") or [], stored.get("metadatas") or [])
        }

    def _planned_context(self, question: str, limit: int) -> RetrievedContext:
        if question not in self._plans:
            self._plans[question] = self._planner(question)
        needs = self._plans[question]
        self.last_plan = needs
        embedding_function = getattr(self._vectordb, "embeddings", None)
        if embedding_function is None:
            raise ValueError("Vector store is missing an embedding function.")
        collection = self._vectordb._collection
        queries = [question, *needs]
        found = collection.query(
            query_embeddings=embedding_function.embed_documents(queries),
            n_results=max(PLANNED_CANDIDATES, limit),
            include=[],
        )
        rankings = found.get("ids") or [[] for _ in queries]
        chosen = select_with_reserved_slots(rankings[0], rankings[1:], limit)
        stored = collection.get(ids=chosen, include=["documents", "metadatas"])
        by_id = {
            chunk_id: (document, metadata)
            for chunk_id, document, metadata in zip(stored.get("ids") or [], stored.get("documents") or [], stored.get("metadatas") or [])
        }
        citations = []
        cited_texts = []
        for chunk_id in chosen:
            document, metadata = by_id.get(chunk_id, (None, None))
            if not document:
                continue
            citation = self._citation_from_metadata([metadata], [chunk_id], 0, document)
            if citation is None:
                continue
            citations.append(citation)
            cited_texts.append(document)
        return RetrievedContext(
            text="\n\n".join(cited_texts).strip(),
            citations=citations,
            retrieved_document_count=len(citations),
        )

    def _hybrid_context(self, question: str, limit: int) -> RetrievedContext:
        embedding_function = getattr(self._vectordb, "embeddings", None)
        if embedding_function is None:
            raise ValueError("Vector store is missing an embedding function.")
        collection = self._vectordb._collection
        semantic = collection.query(
            query_embeddings=[embedding_function.embed_query(question)],
            n_results=HYBRID_CANDIDATES,
            include=[],
        )
        semantic_ids = (semantic.get("ids") or [[]])[0]
        stored = collection.get(include=["documents", "metadatas"])
        ids: Sequence[str] = stored.get("ids") or []
        documents: Sequence[str | None] = stored.get("documents") or []
        metadatas: Sequence[dict | None] = stored.get("metadatas") or []
        keyword_ids = [ids[index] for index in bm25_rank(question, [document or "" for document in documents])]

        position = {chunk_id: index for index, chunk_id in enumerate(ids)}
        citations = []
        cited_texts = []
        for chunk_id in reciprocal_rank_fusion([semantic_ids, keyword_ids[:HYBRID_CANDIDATES]])[:limit]:
            index = position.get(chunk_id)
            if index is None or not documents[index]:
                continue
            citation = self._citation_from_metadata(metadatas, ids, index, documents[index])
            if citation is None:
                continue
            citations.append(citation)
            cited_texts.append(documents[index])
        return RetrievedContext(
            text="\n\n".join(cited_texts).strip(),
            citations=citations,
            retrieved_document_count=len(citations),
        )

    @staticmethod
    def _citation_from_metadata(
        metadatas: Sequence[dict | None],
        ids: Sequence[str | None],
        index: int,
        document_text: str,
    ) -> AnswerCitation | None:
        metadata = metadatas[index] if index < len(metadatas) else None
        chunk_id = metadata.get("chunk_id") if isinstance(metadata, dict) else None
        if not chunk_id and index < len(ids):
            chunk_id = ids[index]
        if not chunk_id:
            return None
        return AnswerCitation(chunk_id=chunk_id, excerpt=document_text)
