import uuid
from typing import Any, Dict, List

from .common import get_postgrest_client, map_persistence_error


def create_conversation(user_id: str, document_id: str) -> str:
    conversation_id = str(uuid.uuid4())
    payload = {
        "id": conversation_id,
        "user_id": user_id,
        "document_id": document_id,
    }

    try:
        get_postgrest_client().from_("conversations").insert(payload).execute()
    except Exception as exc:
        raise map_persistence_error("Failed to create conversation", exc) from exc

    return conversation_id


def get_user_conversation(conversation_id: str, user_id: str) -> Dict[str, Any] | None:
    try:
        response = (
            get_postgrest_client()
            .from_("conversations")
            .select("id, user_id, document_id, created_at")
            .eq("id", conversation_id)
            .eq("user_id", user_id)
            .limit(1)
            .execute()
        )
    except Exception as exc:
        raise map_persistence_error("Failed to load conversation", exc) from exc

    return (response.data or [None])[0]


def get_conversation(conversation_id: str) -> Dict[str, Any] | None:
    try:
        response = (
            get_postgrest_client()
            .from_("conversations")
            .select("id, user_id, document_id, created_at")
            .eq("id", conversation_id)
            .limit(1)
            .execute()
        )
    except Exception as exc:
        raise map_persistence_error("Failed to load conversation", exc) from exc

    return (response.data or [None])[0]


def list_user_conversations(user_id: str, document_id: str | None = None) -> List[Dict[str, Any]]:
    try:
        query = (
            get_postgrest_client()
            .from_("conversations")
            .select("id, user_id, document_id, created_at")
            .eq("user_id", user_id)
        )
        if document_id:
            query = query.eq("document_id", document_id)
        response = query.order("created_at", desc=True).execute()
    except Exception as exc:
        raise map_persistence_error("Failed to load conversations", exc) from exc

    return response.data or []


def list_document_conversation_ids(user_id: str, document_id: str) -> List[str]:
    try:
        response = (
            get_postgrest_client()
            .from_("conversations")
            .select("id")
            .eq("user_id", user_id)
            .eq("document_id", document_id)
            .execute()
        )
    except Exception as exc:
        raise map_persistence_error("Failed to load document conversations", exc) from exc

    return [item["id"] for item in (response.data or []) if item.get("id")]


def delete_user_document_conversations(user_id: str, document_id: str) -> None:
    try:
        (
            get_postgrest_client()
            .from_("conversations")
            .delete()
            .eq("user_id", user_id)
            .eq("document_id", document_id)
            .execute()
        )
    except Exception as exc:
        raise map_persistence_error("Failed to delete document conversations", exc) from exc
