import json
import uuid
from typing import Any, Dict, List

from .common import PersistenceError, get_postgrest_client, map_persistence_error
from ..conversation_history import ConversationExchange, bounded_history


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
            .select("id, conversation_id, role, content, created_at, request_id")
            .eq("conversation_id", conversation_id)
            .order("created_at")
            .execute()
        )
    except Exception as exc:
        raise map_persistence_error("Failed to load conversation history", exc) from exc

    return [_decode_message(row) for row in (response.data or [])]


def load_turn_history(conversation_id: str, request_id: str) -> tuple[ConversationExchange, ...]:
    """Read completed exchanges before this turn, excluding failed and later submissions.

    The caller must authorize the conversation first. The original question timestamp
    keeps a failed turn's retry from seeing questions submitted after it.
    """
    try:
        client = get_postgrest_client()
        current = (client.from_("messages").select("created_at")
                   .eq("conversation_id", conversation_id).eq("request_id", request_id)
                   .eq("role", "user").limit(1).execute()).data
        if not current:
            raise PersistenceError("Current turn question was not persisted")
        rows = (client.from_("messages")
                .select("role, content, request_id, created_at")
                .eq("conversation_id", conversation_id)
                .lt("created_at", current[0]["created_at"])
                .order("created_at", desc=True).limit(24).execute()).data or []
    except Exception as exc:
        raise map_persistence_error("Failed to load turn history", exc) from exc

    pending: dict[str, str] = {}
    legacy_question: str | None = None
    exchanges = []
    for row in reversed(rows):
        message = _decode_message(row)
        content = message.get("content")
        if not isinstance(content, str):
            continue
        turn_id = message.get("request_id")
        if message.get("role") == "user":
            if turn_id:
                pending[turn_id] = content
            legacy_question = content if not turn_id else None
        elif message.get("role") == "assistant":
            question = pending.pop(turn_id, None) if turn_id else legacy_question
            if question is not None:
                exchanges.append(ConversationExchange(question=question, answer=content))
            legacy_question = None
    return bounded_history(exchanges)


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
