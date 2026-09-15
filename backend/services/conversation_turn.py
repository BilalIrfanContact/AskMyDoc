from dataclasses import dataclass

from .authz import require_user_conversation, require_user_document
from .persistence.messages_repository import insert_message
from .rag_pipeline import AnswerDecision, answer_question


class ConversationTurnValidationError(ValueError):
    """The caller did not provide enough information to start a conversation turn."""


@dataclass(frozen=True)
class ConversationTurnInput:
    document_id: str
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

    insert_message(
        conversation_id=request.conversation_id,
        role="user",
        content=question,
    )
    decision = answer_question(document_id=conversation["document_id"], question=question)
    insert_message(
        conversation_id=request.conversation_id,
        role="assistant",
        content=decision.answer,
    )
    return decision
