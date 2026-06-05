import os
import re
import uuid
from functools import lru_cache
from typing import Any, Dict, List

from postgrest import SyncPostgrestClient
from storage3 import SyncStorageClient


class SupabasePersistenceError(RuntimeError):
    pass


def _require_env(name: str) -> str:
    value = os.getenv(name)
    if not value:
        raise SupabasePersistenceError(f"Missing required environment variable: {name}")
    return value


JWT_KEY_PATTERN = re.compile(r"^[A-Za-z0-9-_=]+\.[A-Za-z0-9-_=]+\.?[A-Za-z0-9-_.+/=]*$")


def _get_supabase_url() -> str:
    return _require_env("SUPABASE_URL")


def _get_supabase_key() -> str:
    return _require_env("SUPABASE_SERVICE_ROLE_KEY")


def _base_headers() -> Dict[str, str]:
    key = _get_supabase_key()
    headers = {"apikey": key}
    if JWT_KEY_PATTERN.match(key):
        headers["Authorization"] = f"Bearer {key}"
    return headers


@lru_cache(maxsize=1)
def get_postgrest_client() -> SyncPostgrestClient:
    return SyncPostgrestClient(
        base_url=f"{_get_supabase_url()}/rest/v1",
        headers=_base_headers(),
    )


@lru_cache(maxsize=1)
def get_storage_client() -> SyncStorageClient:
    return SyncStorageClient(
        url=f"{_get_supabase_url()}/storage/v1",
        headers=_base_headers(),
    )


def get_storage_bucket() -> str:
    return os.getenv("SUPABASE_STORAGE_BUCKET", "pdfs")


def upload_pdf_to_storage(user_id: str, document_id: str, filename: str, data: bytes) -> str:
    bucket = get_storage_bucket()
    safe_name = os.path.basename(filename) or "document.pdf"
    storage_path = f"{user_id}/{document_id}/{safe_name}"

    try:
        storage = get_storage_client().from_(bucket)
        try:
            storage.upload(
                storage_path,
                data,
                file_options={"content-type": "application/pdf", "upsert": "false"},
            )
        except TypeError:
            storage.upload(
                storage_path,
                data,
                {"content-type": "application/pdf", "upsert": "false"},
            )
    except Exception as exc:
        raise SupabasePersistenceError(f"Failed to upload PDF to Supabase Storage: {exc}") from exc

    return f"{bucket}/{storage_path}"


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
        raise SupabasePersistenceError(f"Failed to persist document metadata: {exc}") from exc

    return (response.data or [{}])[0]


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
        raise SupabasePersistenceError(f"Failed to create conversation: {exc}") from exc

    return conversation_id


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
        raise SupabasePersistenceError(f"Failed to save {role} message: {exc}") from exc

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
        raise SupabasePersistenceError(f"Failed to load conversation history: {exc}") from exc

    return response.data or []


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
        raise SupabasePersistenceError(f"Failed to load conversation: {exc}") from exc

    return (response.data or [None])[0]


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
        raise SupabasePersistenceError(f"Failed to load document: {exc}") from exc

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
        raise SupabasePersistenceError(f"Failed to load conversations: {exc}") from exc

    return response.data or []


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
        raise SupabasePersistenceError(f"Failed to load user documents: {exc}") from exc

    return response.data or []


def delete_storage_object(storage_url: str) -> None:
    bucket, _, object_path = storage_url.partition("/")
    if not bucket or not object_path:
        return

    try:
        get_storage_client().from_(bucket).remove([object_path])
    except Exception as exc:
        if "not found" not in str(exc).lower():
            raise SupabasePersistenceError(f"Failed to delete PDF from Supabase Storage: {exc}") from exc


def delete_document(document_id: str, user_id: str) -> bool:
    try:
        document_response = (
            get_postgrest_client()
            .from_("documents")
            .select("id, storage_url")
            .eq("id", document_id)
            .eq("user_id", user_id)
            .limit(1)
            .execute()
        )
    except Exception as exc:
        raise SupabasePersistenceError(f"Failed to load document for deletion: {exc}") from exc

    document = (document_response.data or [None])[0]
    if not document:
        return False

    try:
        conversations_response = (
            get_postgrest_client()
            .from_("conversations")
            .select("id")
            .eq("user_id", user_id)
            .eq("document_id", document_id)
            .execute()
        )
        conversation_ids = [item["id"] for item in (conversations_response.data or []) if item.get("id")]

        for conversation_id in conversation_ids:
            (
                get_postgrest_client()
                .from_("messages")
                .delete()
                .eq("conversation_id", conversation_id)
                .execute()
            )

        (
            get_postgrest_client()
            .from_("conversations")
            .delete()
            .eq("user_id", user_id)
            .eq("document_id", document_id)
            .execute()
        )

        (
            get_postgrest_client()
            .from_("documents")
            .delete()
            .eq("id", document_id)
            .eq("user_id", user_id)
            .execute()
        )
    except Exception as exc:
        raise SupabasePersistenceError(f"Failed to delete document data: {exc}") from exc

    storage_url = document.get("storage_url")
    if storage_url:
        try:
            delete_storage_object(storage_url)
        except SupabasePersistenceError:
            pass

    return True
