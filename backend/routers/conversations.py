from fastapi import APIRouter, Depends, HTTPException, Query

from ..models.schemas import (
    ConversationCreateRequest,
    ConversationCreateResponse,
    ConversationsResponse,
    ConversationMessagesResponse,
)
from ..services.internal_auth import require_authenticated_user
from ..services.supabase_store import (
    SupabasePersistenceError,
    create_conversation,
    get_user_document,
    get_user_conversation,
    list_conversation_messages,
    list_user_conversations,
)

router = APIRouter()


@router.get("/conversations", response_model=ConversationsResponse)
async def get_user_conversations(
    document_id: str | None = Query(None, description="Filter by document UUID"),
    user_id: str = Depends(require_authenticated_user),
):
    try:
        conversations = list_user_conversations(user_id=user_id, document_id=document_id)
    except SupabasePersistenceError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc

    return ConversationsResponse(conversations=conversations)


@router.post("/conversations", response_model=ConversationCreateResponse)
async def create_conversation_endpoint(
    request: ConversationCreateRequest,
    user_id: str = Depends(require_authenticated_user),
):
    try:
        document = get_user_document(document_id=request.document_id, user_id=user_id)
    except SupabasePersistenceError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc

    if not document:
        raise HTTPException(status_code=404, detail="Document not found.")

    try:
        conversation_id = create_conversation(
            user_id=user_id,
            document_id=request.document_id,
        )
    except SupabasePersistenceError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc

    return ConversationCreateResponse(conversation_id=conversation_id)


@router.get("/conversations/{conversation_id}/messages", response_model=ConversationMessagesResponse)
async def get_conversation_messages(
    conversation_id: str,
    user_id: str = Depends(require_authenticated_user),
):
    try:
        conversation = get_user_conversation(conversation_id=conversation_id, user_id=user_id)
    except SupabasePersistenceError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc

    if not conversation:
        raise HTTPException(status_code=404, detail="Conversation not found.")

    try:
        messages = list_conversation_messages(conversation_id=conversation_id)
    except SupabasePersistenceError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc

    return ConversationMessagesResponse(messages=messages)
