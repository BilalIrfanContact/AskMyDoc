import os
import re
from typing import Iterable, List, Sequence

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


def _format_context(docs: List) -> str:
    return "\n\n".join(doc.page_content for doc in docs if doc.page_content).strip()


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


def _is_summary_question(question: str) -> bool:
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
    return any(trigger in q for trigger in triggers)


def _head_context(vectordb, limit: int = 6) -> str:
    result = vectordb.get(limit=limit, include=["documents"])
    documents: Sequence[str] = result.get("documents") or []
    return _format_texts(documents)


def answer_question(document_id: str, question: str) -> str:
    vectordb = get_vector_store(document_id=document_id)
    try:
        total = vectordb._collection.count()
    except Exception:
        total = 4

    k = min(4, max(1, total))

    if _is_summary_question(question):
        context = _head_context(vectordb, limit=min(8, max(1, total)))
    else:
        docs = vectordb.similarity_search(question, k=k)
        context = _format_context(docs)
        if not _has_sufficient_context(question, context):
            return INSUFFICIENT_CONTEXT_ANSWER

    if not context:
        context = _head_context(vectordb, limit=min(8, max(1, total)))

    if not context:
        return INSUFFICIENT_CONTEXT_ANSWER

    model = os.getenv("OPENAI_CHAT_MODEL", "gpt-5.4-nano")
    llm = ChatOpenAI(model=model, temperature=0)
    prompt = (
        f"{SYSTEM_PROMPT}\n\n"
        f"Context:\n{context}\n\n"
        f"Question: {question}\n"
        "Answer:"
    )
    response = llm.invoke(prompt)
    return response.content.strip()
