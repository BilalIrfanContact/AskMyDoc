import uuid
from typing import Any, Dict, List

from .common import get_postgrest_client, map_persistence_error


def insert_message(conversation_id: str, role: str, content: str) -> Dict[str, Any]:
    payload = {
        "id": str(uuid.uuid4()),
        "conversation_id": conversation_id,
        "role": role,
        "content": content,
    }

    try:
        response = get_postgrest_client().from_("messages").insert(payload).execute()
    except Exception as exc:
        raise map_persistence_error(f"Failed to save {role} message", exc) from exc

    return (response.data or [{}])[0]


def list_conversation_messages(conversation_id: str) -> List[Dict[str, Any]]:
    try:
        response = (
            get_postgrest_client()
            .from_("messages")
            .select("id, conversation_id, role, content, created_at")
            .eq("conversation_id", conversation_id)
            .order("created_at")
            .execute()
        )
    except Exception as exc:
        raise map_persistence_error("Failed to load conversation history", exc) from exc

    return response.data or []


def delete_messages_for_conversation(conversation_id: str) -> None:
    try:
        (
            get_postgrest_client()
            .from_("messages")
            .delete()
            .eq("conversation_id", conversation_id)
            .execute()
        )
    except Exception as exc:
        raise map_persistence_error("Failed to delete conversation messages", exc) from exc
