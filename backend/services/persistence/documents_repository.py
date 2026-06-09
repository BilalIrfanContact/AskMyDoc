from typing import Any, Dict, List

from .common import get_postgrest_client, map_persistence_error


def insert_document(document_id: str, user_id: str, filename: str, storage_url: str) -> Dict[str, Any]:
    payload = {
        "id": document_id,
        "user_id": user_id,
        "filename": filename,
        "storage_url": storage_url,
    }

    try:
        response = get_postgrest_client().from_("documents").insert(payload).execute()
    except Exception as exc:
        raise map_persistence_error("Failed to persist document metadata", exc) from exc

    return (response.data or [{}])[0]


def list_user_documents(user_id: str) -> List[Dict[str, Any]]:
    try:
        response = (
            get_postgrest_client()
            .from_("documents")
            .select("id, user_id, filename, storage_url, uploaded_at")
            .eq("user_id", user_id)
            .order("uploaded_at", desc=True)
            .execute()
        )
    except Exception as exc:
        raise map_persistence_error("Failed to load user documents", exc) from exc

    return response.data or []


def get_user_document(document_id: str, user_id: str) -> Dict[str, Any] | None:
    try:
        response = (
            get_postgrest_client()
            .from_("documents")
            .select("id, user_id, filename, storage_url, uploaded_at")
            .eq("id", document_id)
            .eq("user_id", user_id)
            .limit(1)
            .execute()
        )
    except Exception as exc:
        raise map_persistence_error("Failed to load document", exc) from exc

    return (response.data or [None])[0]


def get_document(document_id: str) -> Dict[str, Any] | None:
    try:
        response = (
            get_postgrest_client()
            .from_("documents")
            .select("id, user_id, filename, storage_url, uploaded_at")
            .eq("id", document_id)
            .limit(1)
            .execute()
        )
    except Exception as exc:
        raise map_persistence_error("Failed to load document", exc) from exc

    return (response.data or [None])[0]


def delete_document_record(document_id: str, user_id: str) -> None:
    try:
        (
            get_postgrest_client()
            .from_("documents")
            .delete()
            .eq("id", document_id)
            .eq("user_id", user_id)
            .execute()
        )
    except Exception as exc:
        raise map_persistence_error("Failed to delete document metadata", exc) from exc
