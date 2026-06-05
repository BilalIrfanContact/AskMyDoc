import hmac
import os
import time
from hashlib import sha256

from fastapi import Header, HTTPException

USER_ID_HEADER = "x-askmydoc-user-id"
TIMESTAMP_HEADER = "x-askmydoc-timestamp"
SIGNATURE_HEADER = "x-askmydoc-signature"
MAX_REQUEST_AGE_SECONDS = 300


def _get_internal_auth_secret() -> str:
    secret = (
        os.getenv("INTERNAL_API_SECRET")
        or os.getenv("NEXTAUTH_SECRET")
        or os.getenv("AUTH_SECRET")
    )
    if not secret:
        raise HTTPException(
            status_code=500,
            detail="Missing INTERNAL_API_SECRET or NEXTAUTH_SECRET for backend authentication.",
        )
    return secret


def require_authenticated_user(
    user_id: str | None = Header(None, alias=USER_ID_HEADER),
    timestamp: str | None = Header(None, alias=TIMESTAMP_HEADER),
    signature: str | None = Header(None, alias=SIGNATURE_HEADER),
) -> str:
    if not user_id or not timestamp or not signature:
        raise HTTPException(status_code=401, detail="Authentication required.")

    try:
        request_time = int(timestamp)
    except ValueError as exc:
        raise HTTPException(status_code=401, detail="Invalid authentication timestamp.") from exc

    if abs(int(time.time()) - request_time) > MAX_REQUEST_AGE_SECONDS:
        raise HTTPException(status_code=401, detail="Authentication expired.")

    expected_signature = hmac.new(
        _get_internal_auth_secret().encode("utf-8"),
        f"{user_id}:{timestamp}".encode("utf-8"),
        sha256,
    ).hexdigest()

    if not hmac.compare_digest(signature, expected_signature):
        raise HTTPException(status_code=401, detail="Invalid authentication signature.")

    return user_id
