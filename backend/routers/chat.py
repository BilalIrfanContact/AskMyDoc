from fastapi import APIRouter, Depends, HTTPException

from ..models.schemas import ChatRequest, ChatResponse, ErrorDetailResponse
from ..services.authz import require_user_conversation, require_user_document
from ..services.internal_auth import require_authenticated_user
from ..services.persistence import PersistenceError
from ..services.persistence.messages_repository import insert_message
from ..services.rag_pipeline import answer_question

router = APIRouter()


@router.post(
    "/chat",
    response_model=ChatResponse,
    responses={
        400: {"model": ErrorDetailResponse},
        401: {"model": ErrorDetailResponse},
        404: {"model": ErrorDetailResponse},
        502: {"model": ErrorDetailResponse},
    },
)
async def chat(request: ChatRequest, user_id: str = Depends(require_authenticated_user)):
    question = (request.message or request.question or "").strip()
    if not question:
        raise HTTPException(status_code=400, detail="Question cannot be empty.")

    if not request.conversation_id:
        raise HTTPException(
            status_code=400,
            detail="conversation_id is required to persist chat messages.",
        )

    conversation = require_user_conversation(
        conversation_id=request.conversation_id,
        user_id=user_id,
    )

    if conversation["document_id"] != request.document_id:
        require_user_document(document_id=request.document_id, user_id=user_id)
        raise HTTPException(
            status_code=400,
            detail="Conversation does not belong to the provided document.",
        )

    try:
        insert_message(
            conversation_id=request.conversation_id,
            role="user",
            content=question,
        )
    except PersistenceError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc

    answer = answer_question(document_id=conversation["document_id"], question=question)

    try:
        insert_message(
            conversation_id=request.conversation_id,
            role="assistant",
            content=answer,
        )
    except PersistenceError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc

    return ChatResponse(answer=answer)
