import os
import re
from functools import lru_cache
from typing import Dict

from postgrest import SyncPostgrestClient
from storage3 import SyncStorageClient


class PersistenceError(RuntimeError):
    pass


JWT_KEY_PATTERN = re.compile(r"^[A-Za-z0-9-_=]+\.[A-Za-z0-9-_=]+\.?[A-Za-z0-9-_.+/=]*$")


def _require_env(name: str) -> str:
    value = os.getenv(name)
    if not value:
        raise PersistenceError(f"Missing required environment variable: {name}")
    return value


def map_persistence_error(action: str, exc: Exception) -> PersistenceError:
    return PersistenceError(f"{action}: {exc}")


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
