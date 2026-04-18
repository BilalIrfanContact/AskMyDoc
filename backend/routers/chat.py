from fastapi import APIRouter, HTTPException

from ..models.schemas import ChatRequest, ChatResponse
from ..services.rag_pipeline import answer_question
from ..services.supabase_store import SupabasePersistenceError, insert_message

router = APIRouter()


@router.post("/chat", response_model=ChatResponse)
async def chat(request: ChatRequest):
    question = (request.message or request.question or "").strip()
    if not question:
        raise HTTPException(status_code=400, detail="Question cannot be empty.")

    if bool(request.user_id) != bool(request.conversation_id):
        raise HTTPException(
            status_code=400,
            detail="Both user_id and conversation_id are required to persist chat messages.",
        )

    if request.conversation_id:
        try:
            insert_message(
                conversation_id=request.conversation_id,
                role="user",
                content=question,
            )
        except SupabasePersistenceError as exc:
            raise HTTPException(status_code=502, detail=str(exc)) from exc

    answer = answer_question(document_id=request.document_id, question=question)

    if request.conversation_id:
        try:
            insert_message(
                conversation_id=request.conversation_id,
                role="assistant",
                content=answer,
            )
        except SupabasePersistenceError as exc:
            raise HTTPException(status_code=502, detail=str(exc)) from exc

    return ChatResponse(answer=answer)
