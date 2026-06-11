from fastapi import APIRouter, Depends, HTTPException, Query

from ..models.schemas import (
    ConversationCreateRequest,
    ConversationCreateResponse,
    ConversationMessagesResponse,
    ConversationsResponse,
    ErrorDetailResponse,
)
from ..services.internal_auth import require_authenticated_user
from ..services.authz import require_user_conversation, require_user_document
from ..services.persistence import PersistenceError
from ..services.persistence.conversations_repository import (
    create_conversation,
    list_user_conversations,
)
from ..services.persistence.messages_repository import list_conversation_messages

router = APIRouter()


@router.get(
    "/conversations",
    response_model=ConversationsResponse,
    responses={
        401: {"model": ErrorDetailResponse},
        403: {"model": ErrorDetailResponse},
        502: {"model": ErrorDetailResponse},
    },
)
async def get_user_conversations(
    document_id: str | None = Query(None, description="Filter by document UUID"),
    user_id: str = Depends(require_authenticated_user),
):
    if document_id:
        try:
            require_user_document(document_id=document_id, user_id=user_id)
        except HTTPException as exc:
            if exc.status_code != 404:
                raise

    try:
        conversations = list_user_conversations(user_id=user_id, document_id=document_id)
    except PersistenceError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc

    return ConversationsResponse(conversations=conversations)


@router.post(
    "/conversations",
    response_model=ConversationCreateResponse,
    responses={
        401: {"model": ErrorDetailResponse},
        403: {"model": ErrorDetailResponse},
        404: {"model": ErrorDetailResponse},
        502: {"model": ErrorDetailResponse},
    },
)
async def create_conversation_endpoint(
    request: ConversationCreateRequest,
    user_id: str = Depends(require_authenticated_user),
):
    require_user_document(document_id=request.document_id, user_id=user_id)

    try:
        conversation_id = create_conversation(
            user_id=user_id,
            document_id=request.document_id,
        )
    except PersistenceError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc

    return ConversationCreateResponse(conversation_id=conversation_id)


@router.get(
    "/conversations/{conversation_id}/messages",
    response_model=ConversationMessagesResponse,
    responses={
        401: {"model": ErrorDetailResponse},
        403: {"model": ErrorDetailResponse},
        404: {"model": ErrorDetailResponse},
        502: {"model": ErrorDetailResponse},
    },
)
async def get_conversation_messages(
    conversation_id: str,
    user_id: str = Depends(require_authenticated_user),
):
    require_user_conversation(conversation_id=conversation_id, user_id=user_id)

    try:
        messages = list_conversation_messages(conversation_id=conversation_id)
    except PersistenceError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc

    return ConversationMessagesResponse(messages=messages)
