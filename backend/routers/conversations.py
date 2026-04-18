from fastapi import APIRouter, HTTPException, Query

from ..models.schemas import (
    ConversationCreateRequest,
    ConversationCreateResponse,
    ConversationsResponse,
    ConversationMessagesResponse,
)
from ..services.supabase_store import (
    SupabasePersistenceError,
    create_conversation,
    list_conversation_messages,
    list_user_conversations,
)

router = APIRouter()


@router.get("/conversations", response_model=ConversationsResponse)
async def get_user_conversations(
    user_id: str = Query(..., description="Supabase user UUID"),
    document_id: str | None = Query(None, description="Filter by document UUID"),
):
    try:
        conversations = list_user_conversations(user_id=user_id, document_id=document_id)
    except SupabasePersistenceError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc

    return ConversationsResponse(conversations=conversations)


@router.post("/conversations", response_model=ConversationCreateResponse)
async def create_conversation_endpoint(request: ConversationCreateRequest):
    try:
        conversation_id = create_conversation(
            user_id=request.user_id,
            document_id=request.document_id,
        )
    except SupabasePersistenceError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc

    return ConversationCreateResponse(conversation_id=conversation_id)


@router.get("/conversations/{conversation_id}/messages", response_model=ConversationMessagesResponse)
async def get_conversation_messages(conversation_id: str):
    try:
        messages = list_conversation_messages(conversation_id=conversation_id)
    except SupabasePersistenceError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc

    return ConversationMessagesResponse(messages=messages)
