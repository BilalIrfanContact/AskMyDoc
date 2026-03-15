from typing import Iterable, List, Sequence

from langchain_openai import ChatOpenAI

from .vector_store import get_vector_store


SYSTEM_PROMPT = (
    "You are a helpful assistant that answers questions based strictly on the provided "
    "document excerpts. If the user asks for a summary or what the document is about, "
    "summarize the excerpts. If the answer is not found in the excerpts, say \"I couldn't "
    "find that information in the document.\" Do not make up information. Be concise and accurate."
)


def _format_context(docs: List) -> str:
    return "\n\n".join(doc.page_content for doc in docs if doc.page_content).strip()


def _format_texts(texts: Iterable[str]) -> str:
    return "\n\n".join(text for text in texts if text).strip()


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

    if not context:
        context = _head_context(vectordb, limit=min(8, max(1, total)))

    if not context:
        return "I couldn't find that information in the document."

    llm = ChatOpenAI(model="gpt-4o-mini", temperature=0)
    prompt = (
        f"{SYSTEM_PROMPT}\n\n"
        f"Context:\n{context}\n\n"
        f"Question: {question}\n"
        "Answer:"
    )
    response = llm.invoke(prompt)
    return response.content.strip()
