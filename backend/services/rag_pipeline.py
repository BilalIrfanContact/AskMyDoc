import json
import logging
import os
import re
from dataclasses import dataclass
from typing import Callable, Iterable, Literal, Protocol, Sequence

from pydantic import BaseModel, ValidationError

from .answer_grounding import find_grounding_failure
from .vector_store import get_vector_store


logger = logging.getLogger(__name__)


SYSTEM_PROMPT = (
    "You answer questions using only the provided document excerpts. "
    "Do not invent facts that are not supported by the excerpts. "
    "A figure may appear under a standard equivalent name, and you may calculate "
    "a value from figures shown in the excerpts."
)

INSUFFICIENT_CONTEXT_ANSWER = (
    "I couldn't find enough information in the document to answer that question."
)
_STRUCTURED_OUTPUT_RETRY_LIMIT = 2
# The most chunks a QA question may send to the answer model; the evidence reranker picks how many.
DEFAULT_QA_CONTEXT_LIMIT = 10
_ANSWER_JSON_SHAPE = '{"found_in_excerpts": boolean, "answer": string}'
_STRUCTURED_OUTPUT_INSTRUCTION = (
    f"Return only valid JSON with this exact shape: {_ANSWER_JSON_SHAPE}. "
    "Set found_in_excerpts to false when the excerpts do not contain what is needed "
    "to answer; the answer may then be empty. "
    "Do not include markdown, code fences, or any extra keys."
)

Intent = Literal["summary", "qa"]
RouteIntent = Literal["summary", "qa", "off_topic"]
RetrievalMode = Literal["head", "semantic"]
FallbackReasonCode = Literal[
    "model_reported_not_found",
    "empty_context",
    "structured_output_invalid",
    "answer_not_grounded",
]


@dataclass(frozen=True)
class RetrievalPolicy:
    intent: Intent
    mode: RetrievalMode
    limit: int


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
    retrieved_document_count: int


@dataclass(frozen=True)
class StructuredAnswerResult:
    """The model's parsed reply; `answer` is None when it never matched the JSON contract."""

    answer: str | None
    found_in_excerpts: bool
    invalid_attempt_count: int


class RetrievalAdapter(Protocol):
    def count(self) -> int | None: ...

    def retrieve(self, mode: RetrievalMode, question: str, limit: int) -> RetrievedContext: ...


class GenerationAdapter(Protocol):
    def invoke(self, prompt: str) -> object: ...


@dataclass(frozen=True)
class RagDependencies:
    retrieval_factory: Callable[[str], RetrievalAdapter]
    generation: GenerationAdapter


class LlmAnswerPayload(BaseModel):
    """The answer model's JSON contract. `found_in_excerpts` is how it says "not in the document"."""

    found_in_excerpts: bool
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
        f"Reply again with only valid JSON matching exactly {_ANSWER_JSON_SHAPE}."
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


def _parse_structured_answer(response_text: str, question: str) -> LlmAnswerPayload:
    payload = LlmAnswerPayload.model_validate_json(response_text)
    if not payload.found_in_excerpts:
        return payload
    normalized_answer = _normalize_answer_text(payload.answer, question)
    if not normalized_answer:
        raise ValueError("answer must not be empty when found_in_excerpts is true")
    return LlmAnswerPayload(found_in_excerpts=True, answer=normalized_answer)


def _question_requests_literal_formatting(question: str) -> bool:
    q = question.lower()
    formatting_triggers = (
        "code",
        "command",
        "commands",
        "snippet",
        "script",
        "json",
        "yaml",
        "sql",
        "regex",
        "markdown",
        "example output",
    )
    return any(trigger in q for trigger in formatting_triggers)


def _answer_looks_like_code(answer: str) -> bool:
    stripped = answer.strip()
    if not stripped:
        return False

    stripped = re.sub(r"```[a-zA-Z0-9_-]*\n?", "", stripped)
    stripped = stripped.replace("```", "")

    code_markers = (
        "import ",
        "from ",
        "def ",
        "class ",
        "SELECT ",
        "INSERT ",
        "UPDATE ",
        "DELETE ",
        "npm ",
        "pip ",
        "python ",
        "curl ",
        "{",
        "[",
    )
    lines = [line.strip() for line in stripped.splitlines() if line.strip()]
    return any(
        any(line.startswith(marker) for marker in code_markers)
        for line in lines
    )


def _normalize_answer_text(answer: str, question: str) -> str:
    text = answer.replace("\r\n", "\n").strip()
    if not text:
        return ""

    if _question_requests_literal_formatting(question) or _answer_looks_like_code(text):
        return text

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


def _generate_structured_answer(
    generator: GenerationAdapter,
    question: str,
    context: str,
) -> StructuredAnswerResult:
    prompt = _build_generation_prompt(question, context)
    invalid_attempt_count = 0

    for attempt in range(_STRUCTURED_OUTPUT_RETRY_LIMIT):
        response = generator.invoke(prompt)
        response_text = _coerce_response_text(response)

        try:
            payload = _parse_structured_answer(response_text, question)
            return StructuredAnswerResult(
                answer=payload.answer,
                found_in_excerpts=payload.found_in_excerpts,
                invalid_attempt_count=invalid_attempt_count,
            )
        except (ValidationError, ValueError) as exc:
            invalid_attempt_count += 1
            if attempt == _STRUCTURED_OUTPUT_RETRY_LIMIT - 1:
                return StructuredAnswerResult(
                    answer=None,
                    found_in_excerpts=False,
                    invalid_attempt_count=invalid_attempt_count,
                )
            prompt = _build_retry_prompt(question, context, response_text, str(exc))

    return StructuredAnswerResult(
        answer=None, found_in_excerpts=False, invalid_attempt_count=invalid_attempt_count
    )


def _default_generation_adapter() -> GenerationAdapter:
    from .ai_providers import chat_adapter

    return chat_adapter("answer")


def _default_dependencies() -> RagDependencies:
    from .rag_adapters import ChromaRetrievalAdapter

    from .ai_providers import chat_adapter

    return RagDependencies(
        retrieval_factory=lambda document_id: ChromaRetrievalAdapter(
            get_vector_store(document_id=document_id),
            reranker=chat_adapter("rerank"),
        ),
        generation=_default_generation_adapter(),
    )


def _route_intent(
    question: str,
    generator: GenerationAdapter | None = None,
) -> RouteIntent:
    prompt = (
        "Classify the user's question for a document Q&A app.\n"
        "Return exactly one label: summary, qa, or off_topic.\n"
        "summary = asking what the uploaded document is about.\n"
        "qa = asking for specific information from the uploaded document.\n"
        "off_topic = not about the uploaded document.\n\n"
        f"Question: {question}\n"
        "Label:"
    )

    try:
        active_generator = generator or _default_generation_adapter()
        response_text = _coerce_response_text(active_generator.invoke(prompt)).lower()
    except Exception:
        return "qa"

    match = re.search(r"\b(summary|qa|off_topic)\b", response_text)
    if match:
        return match.group(1)  # type: ignore[return-value]
    return "qa"


def _select_retrieval_policy(
    question: str,
    total_chunks: int,
    generator: GenerationAdapter | None = None,
    qa_limit: int = DEFAULT_QA_CONTEXT_LIMIT,
) -> RetrievalPolicy:
    limit = min(8, max(1, total_chunks))
    routed_intent = _route_intent(question, generator=generator)
    if routed_intent == "summary":
        return RetrievalPolicy(
            intent="summary",
            mode="head",
            limit=limit,
        )

    return RetrievalPolicy(
        intent="qa",
        mode="semantic",
        limit=min(qa_limit, max(1, total_chunks)),
    )


def _retrieve_context(
    retriever: RetrievalAdapter,
    question: str,
    policy: RetrievalPolicy,
) -> RetrievedContext:
    return retriever.retrieve(policy.mode, question, policy.limit)


def _citation_completeness_ratio(context: RetrievedContext) -> float | None:
    if context.retrieved_document_count == 0:
        return None
    return len(context.citations) / context.retrieved_document_count


def _emit_answer_policy_telemetry(
    *,
    document_id: str,
    total_chunks: int | None,
    policy: RetrievalPolicy,
    context: RetrievedContext,
    answer_status: Literal["answered", "insufficient_context"],
    fallback_reason_code: FallbackReasonCode | None,
    structured_output_retry_count: int,
    answer_grounded: bool | None,
    answer_model_called: bool,
    grounding_failure: dict[str, object] | None = None,
) -> None:
    citation_count = len(context.citations)
    citation_completeness_ratio = _citation_completeness_ratio(context)
    event = {
        "event": "answer_policy_decision",
        "document_id": document_id,
        "intent": policy.intent,
        "retrieval_mode": policy.mode,
        "answer_status": answer_status,
        "fallback_reason_code": fallback_reason_code,
        "total_chunk_count": total_chunks,
        "chunk_count_available": total_chunks is not None,
        "retrieved_document_count": context.retrieved_document_count,
        "retrieved_chunk_ids": [citation.chunk_id for citation in context.citations],
        "retrieved_context_char_count": len(context.text),
        "answer_model_called": answer_model_called,
        "citation_count": citation_count,
        "missing_citation_count": context.retrieved_document_count - citation_count,
        "citation_completeness_ratio": citation_completeness_ratio,
        "structured_output_retry_count": structured_output_retry_count,
        "answer_grounded": answer_grounded,
        "grounding_failure": grounding_failure,
    }
    logger.info(
        json.dumps(event, sort_keys=True),
    )


def _insufficient_context_decision(policy: RetrievalPolicy) -> AnswerDecision:
    return AnswerDecision(
        answer=INSUFFICIENT_CONTEXT_ANSWER,
        intent=policy.intent,
        retrieval_mode=policy.mode,
        answer_status="insufficient_context",
        citations=[],
    )


def answer_question(
    document_id: str,
    question: str,
    *,
    dependencies: RagDependencies | None = None,
    qa_limit: int = DEFAULT_QA_CONTEXT_LIMIT,
) -> AnswerDecision:
    """Answer a question about one document.

    `qa_limit` is the most semantic chunks a QA question may send to the answer model.
    The app uses the default; evaluation scripts override it to compare context sizes.
    """
    active_dependencies = dependencies or _default_dependencies()
    retriever = active_dependencies.retrieval_factory(document_id)
    total_chunks = retriever.count()
    total = total_chunks if total_chunks is not None else 4

    policy = _select_retrieval_policy(
        question,
        total,
        generator=active_dependencies.generation,
        qa_limit=qa_limit,
    )
    context = _retrieve_context(retriever, question, policy)

    if not context.text:
        decision = _insufficient_context_decision(policy)
        _emit_answer_policy_telemetry(
            document_id=document_id,
            total_chunks=total_chunks,
            policy=policy,
            context=context,
            answer_status=decision.answer_status,
            fallback_reason_code="empty_context",
            structured_output_retry_count=0,
            answer_grounded=None,
            answer_model_called=False,
        )
        return decision

    structured_answer = _generate_structured_answer(
        active_dependencies.generation,
        question,
        context.text,
    )
    if structured_answer.answer is None:
        decision = _insufficient_context_decision(policy)
        _emit_answer_policy_telemetry(
            document_id=document_id,
            total_chunks=total_chunks,
            policy=policy,
            context=context,
            answer_status=decision.answer_status,
            fallback_reason_code="structured_output_invalid",
            structured_output_retry_count=structured_answer.invalid_attempt_count,
            answer_grounded=None,
            answer_model_called=True,
        )
        return decision
    if not structured_answer.found_in_excerpts:
        # The model's own "not in the document" skips grounding: there is no claim to check.
        decision = _insufficient_context_decision(policy)
        _emit_answer_policy_telemetry(
            document_id=document_id,
            total_chunks=total_chunks,
            policy=policy,
            context=context,
            answer_status=decision.answer_status,
            fallback_reason_code="model_reported_not_found",
            structured_output_retry_count=structured_answer.invalid_attempt_count,
            answer_grounded=None,
            answer_model_called=True,
        )
        return decision
    grounding_failure = find_grounding_failure(
        structured_answer.answer, (citation.excerpt for citation in context.citations), question
    )
    answer_grounded = grounding_failure is None
    if not answer_grounded:
        decision = _insufficient_context_decision(policy)
        _emit_answer_policy_telemetry(
            document_id=document_id,
            total_chunks=total_chunks,
            policy=policy,
            context=context,
            answer_status=decision.answer_status,
            fallback_reason_code="answer_not_grounded",
            structured_output_retry_count=structured_answer.invalid_attempt_count,
            answer_grounded=answer_grounded,
            answer_model_called=True,
            grounding_failure=grounding_failure,
        )
        return decision

    decision = AnswerDecision(
        answer=structured_answer.answer,
        intent=policy.intent,
        retrieval_mode=policy.mode,
        answer_status="answered",
        citations=context.citations,
    )
    _emit_answer_policy_telemetry(
        document_id=document_id,
        total_chunks=total_chunks,
        policy=policy,
        context=context,
        answer_status=decision.answer_status,
        fallback_reason_code=None,
        structured_output_retry_count=structured_answer.invalid_attempt_count,
        answer_grounded=answer_grounded,
        answer_model_called=True,
    )
    return decision
