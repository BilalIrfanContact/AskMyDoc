import os
import re
from dataclasses import dataclass
from typing import Iterable, List, Literal, Sequence

from langchain_openai import ChatOpenAI

from .vector_store import get_vector_store


SYSTEM_PROMPT = (
    "You are a helpful assistant that answers questions based strictly on the provided "
    "document excerpts. If the user asks for a summary or what the document is about, "
    "summarize the excerpts. If the answer is not found in the excerpts, say \"I couldn't "
    "find that information in the document.\" Do not make up information. Be concise and accurate. "
    "Write in clear, human-readable prose. Paraphrase instead of copying exact wording from the source. "
    "Avoid markdown formatting such as bold text, italics, or code blocks unless the user explicitly asks for it. "
    "Use short paragraphs or simple bullets only when they genuinely improve readability."
)

INSUFFICIENT_CONTEXT_ANSWER = (
    "I couldn't find enough information in the document to answer that question."
)

_QUESTION_STOPWORDS = {
    "a",
    "an",
    "and",
    "are",
    "as",
    "at",
    "be",
    "by",
    "for",
    "from",
    "how",
    "in",
    "is",
    "it",
    "of",
    "on",
    "or",
    "that",
    "the",
    "this",
    "to",
    "was",
    "what",
    "when",
    "where",
    "which",
    "who",
    "why",
    "with",
}

Intent = Literal["summary", "qa"]
RetrievalMode = Literal["head", "semantic"]


@dataclass(frozen=True)
class RetrievalPolicy:
    intent: Intent
    mode: RetrievalMode
    limit: int
    enforce_quality_gate: bool


@dataclass(frozen=True)
class AnswerDecision:
    answer: str
    intent: Intent
    retrieval_mode: RetrievalMode
    answer_status: Literal["answered", "insufficient_context"]
    citations: list["AnswerCitation"]


@dataclass(frozen=True)
class AnswerCitation:
    chunk_id: str
    excerpt: str


@dataclass(frozen=True)
class RetrievedContext:
    text: str
    citations: list[AnswerCitation]


def _format_texts(texts: Iterable[str]) -> str:
    return "\n\n".join(text for text in texts if text).strip()


def _extract_question_terms(text: str) -> set[str]:
    terms = {
        term
        for term in re.findall(r"[a-z0-9]+", text.lower())
        if len(term) > 2 and term not in _QUESTION_STOPWORDS
    }
    return terms


def _has_sufficient_context(question: str, context: str) -> bool:
    if not context:
        return False

    question_terms = _extract_question_terms(question)
    if not question_terms:
        return True

    context_terms = set(re.findall(r"[a-z0-9]+", context.lower()))
    overlap = question_terms & context_terms
    required_overlap = 1 if len(question_terms) == 1 else min(2, len(question_terms))
    return len(overlap) >= required_overlap


def _route_intent(question: str) -> Intent:
    q = question.strip().lower()
    triggers = (
        "summary",
        "summarize",
        "overview",
        "what is this about",
        "what is this document about",
        "what is the document about",
        "what is this pdf about",
        "what is the pdf about",
        "what is the uploaded pdf about",
        "describe the document",
        "describe this document",
        "main points",
        "key points",
    )
    if any(trigger in q for trigger in triggers):
        return "summary"
    return "qa"


def _select_retrieval_policy(question: str, total_chunks: int) -> RetrievalPolicy:
    limit = min(8, max(1, total_chunks))
    intent = _route_intent(question)
    if intent == "summary":
        return RetrievalPolicy(
            intent="summary",
            mode="head",
            limit=limit,
            enforce_quality_gate=False,
        )

    return RetrievalPolicy(
        intent="qa",
        mode="semantic",
        limit=min(4, max(1, total_chunks)),
        enforce_quality_gate=True,
    )


def _head_context(vectordb, limit: int = 6) -> RetrievedContext:
    result = vectordb.get(limit=limit, include=["documents", "metadatas"])
    documents: Sequence[str] = result.get("documents") or []
    metadatas: Sequence[dict | None] = result.get("metadatas") or []
    citations = [
        citation
        for index, document in enumerate(documents)
        if document and (citation := _citation_from_metadata(metadatas, index, document)) is not None
    ]
    return RetrievedContext(text=_format_texts(documents), citations=citations)


def _citation_from_metadata(
    metadatas: Sequence[dict | None],
    index: int,
    document_text: str,
) -> AnswerCitation | None:
    metadata = metadatas[index] if index < len(metadatas) else None
    chunk_id = metadata.get("chunk_id") if isinstance(metadata, dict) else None
    if not chunk_id:
        return None
    return AnswerCitation(chunk_id=chunk_id, excerpt=document_text)


def _citation_from_doc(doc) -> AnswerCitation | None:
    metadata = getattr(doc, "metadata", None)
    chunk_id = metadata.get("chunk_id") if isinstance(metadata, dict) else None
    page_content = getattr(doc, "page_content", "")
    if not chunk_id or not page_content:
        return None
    return AnswerCitation(chunk_id=chunk_id, excerpt=page_content)


def _retrieve_context(vectordb, question: str, policy: RetrievalPolicy) -> RetrievedContext:
    if policy.mode == "head":
        return _head_context(vectordb, limit=policy.limit)

    docs = vectordb.similarity_search(question, k=policy.limit)
    citations = [citation for doc in docs if (citation := _citation_from_doc(doc)) is not None]
    text = _format_texts(doc.page_content for doc in docs if getattr(doc, "page_content", None))
    return RetrievedContext(text=text, citations=citations)


def _insufficient_context_decision(policy: RetrievalPolicy) -> AnswerDecision:
    return AnswerDecision(
        answer=INSUFFICIENT_CONTEXT_ANSWER,
        intent=policy.intent,
        retrieval_mode=policy.mode,
        answer_status="insufficient_context",
        citations=[],
    )


def answer_question(document_id: str, question: str) -> AnswerDecision:
    vectordb = get_vector_store(document_id=document_id)
    try:
        total = vectordb._collection.count()
    except Exception:
        total = 4

    policy = _select_retrieval_policy(question, total)
    context = _retrieve_context(vectordb, question, policy)

    if policy.enforce_quality_gate and not _has_sufficient_context(question, context.text):
        return _insufficient_context_decision(policy)

    if not context.text:
        return _insufficient_context_decision(policy)

    model = os.getenv("OPENAI_CHAT_MODEL", "gpt-5.4-nano")
    llm = ChatOpenAI(model=model, temperature=0)
    prompt = (
        f"{SYSTEM_PROMPT}\n\n"
        f"Context:\n{context.text}\n\n"
        f"Question: {question}\n"
        "Answer:"
    )
    response = llm.invoke(prompt)
    return AnswerDecision(
        answer=response.content.strip(),
        intent=policy.intent,
        retrieval_mode=policy.mode,
        answer_status="answered",
        citations=context.citations,
    )
