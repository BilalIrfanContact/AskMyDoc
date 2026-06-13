import os
import re
from dataclasses import dataclass
from typing import Iterable, List, Literal, Sequence

from langchain_openai import ChatOpenAI
from pydantic import BaseModel, ValidationError

from .vector_store import get_vector_store


SYSTEM_PROMPT = (
    "You answer questions using only the provided document excerpts. "
    "Do not invent facts that are not supported by the excerpts."
)

INSUFFICIENT_CONTEXT_ANSWER = (
    "I couldn't find enough information in the document to answer that question."
)
_STRUCTURED_OUTPUT_RETRY_LIMIT = 2
_STRUCTURED_OUTPUT_INSTRUCTION = (
    'Return only valid JSON with this exact shape: {"answer": string}. '
    "Do not include markdown, code fences, or any extra keys."
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


class LlmAnswerPayload(BaseModel):
    answer: str


def _build_generation_prompt(question: str, context: str) -> str:
    return (
        f"{SYSTEM_PROMPT}\n\n"
        f"{_STRUCTURED_OUTPUT_INSTRUCTION}\n\n"
        f"Context:\n{context}\n\n"
        f"Question: {question}\n"
        "JSON Response:"
    )


def _build_retry_prompt(question: str, context: str, invalid_response: str, error: str) -> str:
    return (
        f"{_build_generation_prompt(question, context)}\n\n"
        "Your previous response did not match the required JSON contract.\n"
        f"Validation error: {error}\n"
        f"Previous response:\n{invalid_response}\n\n"
        'Reply again with only valid JSON matching exactly {"answer": string}.'
    )


def _coerce_response_text(response) -> str:
    content = getattr(response, "content", "")
    if isinstance(content, str):
        return content.strip()

    if isinstance(content, list):
        parts = []
        for item in content:
            if isinstance(item, str):
                parts.append(item)
                continue
            if isinstance(item, dict) and isinstance(item.get("text"), str):
                parts.append(item["text"])
        return "".join(parts).strip()

    return str(content).strip()


def _parse_structured_answer(response_text: str) -> LlmAnswerPayload:
    payload = LlmAnswerPayload.model_validate_json(response_text)
    normalized_answer = _normalize_answer_text(payload.answer)
    if not normalized_answer:
        raise ValueError("answer must not be empty")
    return LlmAnswerPayload(answer=normalized_answer)


def _normalize_answer_text(answer: str) -> str:
    text = answer.replace("\r\n", "\n").strip()
    if not text:
        return ""

    text = re.sub(r"```[a-zA-Z0-9_-]*\n?", "", text)
    text = text.replace("```", "")
    text = re.sub(r"`([^`]+)`", r"\1", text)
    text = re.sub(r"(\*\*|__)(.*?)\1", r"\2", text)
    text = re.sub(r"(^|[\s(])(\*|_)([^*_]+?)\2(?=[\s).,!?]|$)", r"\1\3", text)

    normalized_lines = []
    for raw_line in text.split("\n"):
        line = raw_line.strip()
        if not line:
            normalized_lines.append("")
            continue

        line = re.sub(r"^#{1,6}\s*", "", line)
        line = re.sub(r"^>\s?", "", line)
        line = re.sub(r"^[-*+]\s+", "- ", line)
        normalized_lines.append(line)

    normalized_text = "\n".join(normalized_lines)
    normalized_text = re.sub(r"\n{3,}", "\n\n", normalized_text)
    return normalized_text.strip()


def _generate_structured_answer(llm, question: str, context: str) -> str | None:
    prompt = _build_generation_prompt(question, context)

    for attempt in range(_STRUCTURED_OUTPUT_RETRY_LIMIT):
        response = llm.invoke(prompt)
        response_text = _coerce_response_text(response)

        try:
            return _parse_structured_answer(response_text).answer
        except (ValidationError, ValueError) as exc:
            if attempt == _STRUCTURED_OUTPUT_RETRY_LIMIT - 1:
                return None
            prompt = _build_retry_prompt(question, context, response_text, str(exc))

    return None


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
    ids: Sequence[str | None] = result.get("ids") or []
    citations = []
    cited_documents = []
    for index, document in enumerate(documents):
        if not document:
            continue
        citation = _citation_from_metadata(metadatas, ids, index, document)
        if citation is None:
            continue
        citations.append(citation)
        cited_documents.append(document)
    return RetrievedContext(text=_format_texts(cited_documents), citations=citations)


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


def _cited_context_from_query_result(result: dict) -> RetrievedContext:
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
        citation = _citation_from_metadata(metadatas, ids, index, document)
        if citation is None:
            continue
        citations.append(citation)
        cited_texts.append(document)
    return RetrievedContext(text=_format_texts(cited_texts), citations=citations)


def _semantic_context(vectordb, question: str, limit: int) -> RetrievedContext:
    result = vectordb._collection.query(
        query_texts=[question],
        n_results=limit,
        include=["documents", "metadatas"],
    )
    return _cited_context_from_query_result(result)


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
    return _semantic_context(vectordb, question, policy.limit)


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
    answer = _generate_structured_answer(llm, question, context.text)
    if answer is None:
        return _insufficient_context_decision(policy)

    return AnswerDecision(
        answer=answer,
        intent=policy.intent,
        retrieval_mode=policy.mode,
        answer_status="answered",
        citations=context.citations,
    )
