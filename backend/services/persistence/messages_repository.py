import json
import uuid
from typing import Any, Dict, List

from .common import get_postgrest_client, map_persistence_error


_ANSWER_ENVELOPE_PREFIX = "askmydoc:answer:v1:"


def insert_message(
    conversation_id: str,
    role: str,
    content: str,
    *,
    answer_status: str | None = None,
    citations: List[Dict[str, str]] | None = None,
) -> Dict[str, Any]:
    stored_content = content
    if role == "assistant" and answer_status:
        stored_content = _ANSWER_ENVELOPE_PREFIX + json.dumps(
            {
                "content": content,
                "answer_status": answer_status,
                "citations": citations or [],
            },
            separators=(",", ":"),
        )

    payload = {
        "id": str(uuid.uuid4()),
        "conversation_id": conversation_id,
        "role": role,
        "content": stored_content,
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

    return [_decode_message(row) for row in (response.data or [])]


def _decode_message(row: Dict[str, Any]) -> Dict[str, Any]:
    if row.get("role") != "assistant":
        return row

    content = row.get("content")
    if not isinstance(content, str) or not content.startswith(_ANSWER_ENVELOPE_PREFIX):
        return row

    try:
        envelope = json.loads(content.removeprefix(_ANSWER_ENVELOPE_PREFIX))
    except (json.JSONDecodeError, TypeError):
        return row

    answer_status = envelope.get("answer_status") if isinstance(envelope, dict) else None
    citations = envelope.get("citations") if isinstance(envelope, dict) else None
    if (
        not isinstance(envelope, dict)
        or not isinstance(envelope.get("content"), str)
        or answer_status not in {"answered", "insufficient_context"}
        or not isinstance(citations, list)
        or any(
            not isinstance(citation, dict)
            or not isinstance(citation.get("chunk_id"), str)
            or not isinstance(citation.get("excerpt"), str)
            for citation in citations
        )
    ):
        return row

    return {
        **row,
        "content": envelope["content"],
        "answer_status": answer_status,
        "citations": citations,
    }


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
