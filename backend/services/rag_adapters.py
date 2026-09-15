from typing import Literal, Sequence

from .rag_pipeline import AnswerCitation, RetrievedContext


RetrievalMode = Literal["head", "semantic"]


class ChromaRetrievalAdapter:
    """Keep Chroma's concrete and private details outside the answer policy."""

    def __init__(self, vectordb):
        self._vectordb = vectordb

    def count(self) -> int | None:
        try:
            return self._vectordb._collection.count()
        except Exception:
            return None

    def retrieve(self, mode: RetrievalMode, question: str, limit: int) -> RetrievedContext:
        if mode == "head":
            return self._head_context(limit)
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


class OpenAIChatAdapter:
    """Expose only text generation while keeping the OpenAI client behind the seam."""

    def __init__(self, llm):
        self._llm = llm

    def invoke(self, prompt: str) -> object:
        return self._llm.invoke(prompt)
