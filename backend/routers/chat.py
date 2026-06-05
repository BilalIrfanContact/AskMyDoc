from fastapi import APIRouter, Depends, HTTPException

from ..models.schemas import ChatRequest, ChatResponse
from ..services.internal_auth import require_authenticated_user
from ..services.rag_pipeline import answer_question
from ..services.supabase_store import (
    SupabasePersistenceError,
    get_user_conversation,
    insert_message,
)

router = APIRouter()


@router.post("/chat", response_model=ChatResponse)
async def chat(request: ChatRequest, user_id: str = Depends(require_authenticated_user)):
    question = (request.message or request.question or "").strip()
    if not question:
        raise HTTPException(status_code=400, detail="Question cannot be empty.")

    if not request.conversation_id:
        raise HTTPException(
            status_code=400,
            detail="conversation_id is required to persist chat messages.",
        )

    try:
        conversation = get_user_conversation(
            conversation_id=request.conversation_id,
            user_id=user_id,
        )
    except SupabasePersistenceError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc

    if not conversation:
        raise HTTPException(status_code=404, detail="Conversation not found.")

    try:
        insert_message(
            conversation_id=request.conversation_id,
            role="user",
            content=question,
        )
    except SupabasePersistenceError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc

    answer = answer_question(document_id=request.document_id, question=question)

    try:
        insert_message(
            conversation_id=request.conversation_id,
            role="assistant",
            content=answer,
        )
    except SupabasePersistenceError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc

    return ChatResponse(answer=answer)
