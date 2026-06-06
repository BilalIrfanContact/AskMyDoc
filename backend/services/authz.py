from fastapi import HTTPException

from .persistence import PersistenceError
from .persistence.conversations_repository import get_conversation, get_user_conversation
from .persistence.documents_repository import get_document, get_user_document


def require_user_document(document_id: str, user_id: str) -> dict:
    try:
        document = get_user_document(document_id=document_id, user_id=user_id)
    except PersistenceError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc

    if document:
        return document

    try:
        existing_document = get_document(document_id=document_id)
    except PersistenceError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc

    if existing_document:
        raise HTTPException(
            status_code=403,
            detail="You are not authorized to access this document.",
        )

    raise HTTPException(status_code=404, detail="Document not found.")


def require_user_conversation(conversation_id: str, user_id: str) -> dict:
    try:
        conversation = get_user_conversation(conversation_id=conversation_id, user_id=user_id)
    except PersistenceError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc

    if conversation:
        return conversation

    try:
        existing_conversation = get_conversation(conversation_id=conversation_id)
    except PersistenceError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc

    if existing_conversation:
        raise HTTPException(
            status_code=403,
            detail="You are not authorized to access this conversation.",
        )

    raise HTTPException(status_code=404, detail="Conversation not found.")
