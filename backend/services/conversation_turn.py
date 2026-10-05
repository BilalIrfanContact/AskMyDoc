from dataclasses import asdict, dataclass
from uuid import UUID

from .demo_limits import MAX_QUESTION_CHARS
from .authz import require_user_conversation, require_user_document
from .persistence.turns_repository import transition_turn
from .rag_pipeline import AnswerCitation, AnswerDecision, answer_question


class ConversationTurnValidationError(ValueError):
    """The caller did not provide enough information to start a conversation turn."""


@dataclass(frozen=True)
class ConversationTurnInput:
    document_id: str
    request_id: str
    conversation_id: str | None
    message: str | None = None
    question: str | None = None


def execute_conversation_turn(
    *,
    user_id: str,
    request: ConversationTurnInput,
) -> AnswerDecision:
    question = (request.message or request.question or "").strip()
    if not question:
        raise ConversationTurnValidationError("Question cannot be empty.")

    if len(question) > MAX_QUESTION_CHARS:
        raise ConversationTurnValidationError("Please keep your question within 2,000 characters.")

    if not request.conversation_id:
        raise ConversationTurnValidationError(
            "conversation_id is required to persist chat messages."
        )

    conversation = require_user_conversation(
        conversation_id=request.conversation_id,
        user_id=user_id,
    )

    if conversation["document_id"] != request.document_id:
        require_user_document(document_id=request.document_id, user_id=user_id)
        raise ConversationTurnValidationError(
            "Conversation does not belong to the provided document."
        )

    try:
        request_id = str(UUID(request.request_id))
    except (ValueError, TypeError, AttributeError) as exc:
        raise ConversationTurnValidationError("A valid request_id is required.") from exc

    params = dict(user_id=user_id, conversation_id=request.conversation_id,
                  request_id=request_id, question=question)
    turn = transition_turn("claim", **params)
    if turn["state"] == "generating":
        try:
            decision = answer_question(document_id=conversation["document_id"], question=question)
        except Exception:
            transition_turn("fail", **params)
            raise
        # An uncertain save must stay blocked: the model may already have charged.
        turn = transition_turn("save", **params, result=asdict(decision))
    if turn["state"] == "generated":
        turn = transition_turn("complete", **params)
    result = turn["result"]
    return AnswerDecision(
        answer=result["answer"], intent=result["intent"],
        retrieval_mode=result["retrieval_mode"], answer_status=result["answer_status"],
        citations=[AnswerCitation(**citation) for citation in result["citations"]],
    )
