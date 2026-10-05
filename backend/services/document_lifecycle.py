import logging

import uuid
from dataclasses import dataclass
from os.path import splitext
from typing import Callable, Literal

from fastapi import HTTPException, UploadFile

from ..models.schemas import DeleteDocumentResponse, UploadResponse
from .demo_limits import MAX_UPLOAD_BYTES, SMALLER_FILE_MESSAGE
from .markdown_extractor import extract_text_from_markdown
from .pdf_extractor import extract_text_from_pdf
from .persistence import PersistenceError
from .persistence.conversations_repository import (
    delete_user_document_conversations,
    list_document_conversation_ids,
)
from .persistence.documents_repository import delete_document_record, insert_document
from .persistence.messages_repository import delete_messages_for_conversation
from .persistence.storage_repository import delete_storage_object, upload_file_to_storage
from .text_chunker import chunk_text
from .vector_store import build_vector_store, delete_vector_store

logger = logging.getLogger(__name__)

UploadFailureStage = Literal["validation", "indexing", "storage", "metadata"]
UploadCleanupStatus = Literal["not-needed", "completed", "failed"]
UploadLifecycleStatus = Literal["completed", "rejected", "failed"]
UploadReasonCode = Literal[
    "file_too_large",
    "invalid_file_type",
    "unreadable_document",
    "no_extractable_text",
    "no_usable_chunks",
    "indexing_failed",
    "no_chunks_stored",
    "storage_upload_failed",
    "metadata_persist_failed",
]
DeleteFailureStage = Literal["conversations", "indexing", "storage", "metadata"]
DeleteCleanupStatus = Literal["not-started", "partial", "completed"]
DeleteLifecycleStatus = Literal["completed", "failed"]
DeleteReasonCode = Literal[
    "conversation_lookup_failed",
    "storage_delete_failed",
    "metadata_delete_failed",
    "conversation_cleanup_failed",
    "indexing_cleanup_failed",
]


@dataclass(frozen=True)
class UploadLifecycleResult:
    status: UploadLifecycleStatus
    http_status: int
    document_id: str | None = None
    chunk_count: int = 0
    stored_count: int = 0
    detail: str | None = None
    failure_stage: UploadFailureStage | None = None
    reason_code: UploadReasonCode | None = None
    cleanup_status: UploadCleanupStatus = "not-needed"

    def to_response(self) -> UploadResponse:
        if self.status != "completed" or not self.document_id:
            raise ValueError("Only completed upload lifecycle results can be converted to responses.")

        return UploadResponse(
            status="success",
            lifecycle_status="ready",
            document_id=self.document_id,
            chunk_count=self.chunk_count,
            stored_count=self.stored_count,
        )

    def to_http_exception(self) -> HTTPException:
        if self.status == "completed":
            raise ValueError("Completed upload lifecycle results cannot be converted to errors.")

        return HTTPException(status_code=self.http_status, detail=self.to_error_detail())

    def to_error_detail(self) -> dict[str, str]:
        return {
            "message": self.detail or "Upload failed.",
            "lifecycle_status": "rejected" if self.status == "rejected" else "failed",
            "failure_stage": self.failure_stage or "validation",
            "reason_code": self.reason_code or "invalid_file_type",
            "cleanup_status": self.cleanup_status,
        }


@dataclass(frozen=True)
class DeleteLifecycleResult:
    status: DeleteLifecycleStatus
    http_status: int
    detail: str | None = None
    failure_stage: DeleteFailureStage | None = None
    reason_code: DeleteReasonCode | None = None
    cleanup_status: DeleteCleanupStatus = "not-started"

    def to_response(self) -> DeleteDocumentResponse:
        if self.status != "completed":
            raise ValueError("Only completed delete lifecycle results can be converted to responses.")

        return DeleteDocumentResponse(
            deleted=True,
            lifecycle_status="deleted",
            cleanup_status="completed",
        )

    def to_http_exception(self) -> HTTPException:
        if self.status == "completed":
            raise ValueError("Completed delete lifecycle results cannot be converted to errors.")

        return HTTPException(status_code=self.http_status, detail=self.to_error_detail())

    def to_error_detail(self) -> dict[str, str]:
        return {
            "message": self.detail or "Delete failed.",
            "lifecycle_status": "failed",
            "failure_stage": self.failure_stage or "metadata",
            "reason_code": self.reason_code or "metadata_delete_failed",
            "cleanup_status": self.cleanup_status,
        }


@dataclass(frozen=True)
class SupportedUploadKind:
    label: str
    content_type: str
    fallback_filename: str
    extract_text: Callable[[bytes], str]


def _resolve_upload_kind(file: UploadFile) -> SupportedUploadKind | None:
    filename = (file.filename or "").lower()
    extension = splitext(filename)[1]
    content_type = (file.content_type or "").lower()

    if content_type == "application/pdf" or extension == ".pdf":
        return SupportedUploadKind(
            label="PDF",
            content_type="application/pdf",
            fallback_filename="document.pdf",
            extract_text=extract_text_from_pdf,
        )

    if content_type == "text/markdown" or extension == ".md":
        return SupportedUploadKind(
            label="Markdown",
            content_type="text/markdown",
            fallback_filename="document.md",
            extract_text=extract_text_from_markdown,
        )

    return None


def _cleanup_failed_upload(document_id: str, storage_url: str | None = None) -> UploadCleanupStatus:
    cleanup_failed = False

    try:
        delete_vector_store(document_id)
    except Exception:
        logger.exception("Failed upload index cleanup failed")
        cleanup_failed = True

    if storage_url:
        try:
            delete_storage_object(storage_url)
        except PersistenceError:
            logger.exception("Failed upload storage cleanup failed")
            cleanup_failed = True

    return "failed" if cleanup_failed else "completed"


def _delete_failure(
    *,
    detail: str,
    failure_stage: DeleteFailureStage,
    reason_code: DeleteReasonCode,
    cleanup_status: DeleteCleanupStatus,
    http_status: int = 502,
) -> DeleteLifecycleResult:
    return DeleteLifecycleResult(
        status="failed",
        http_status=http_status,
        detail=detail,
        failure_stage=failure_stage,
        reason_code=reason_code,
        cleanup_status=cleanup_status,
    )


def upload_document(
    file: UploadFile,
    user_id: str,
    *,
    document_id: str | None = None,
    existing_storage_url: str | None = None,
) -> UploadLifecycleResult:
    """Process an upload synchronously; the FastAPI sync route runs this in a worker thread."""
    upload_kind = _resolve_upload_kind(file)
    if upload_kind is None:
        return UploadLifecycleResult(
            status="rejected",
            http_status=400,
            detail="Only PDF and Markdown files are supported.",
            failure_stage="validation",
            reason_code="invalid_file_type",
        )

    data = file.file.read(MAX_UPLOAD_BYTES + 1)
    if len(data) > MAX_UPLOAD_BYTES:
        return UploadLifecycleResult(
            status="rejected",
            http_status=413,
            detail=SMALLER_FILE_MESSAGE,
            failure_stage="validation",
            reason_code="file_too_large",
        )
    try:
        text = upload_kind.extract_text(data)
    except Exception:
        logger.exception("Document extraction failed")
        return UploadLifecycleResult(
            status="rejected",
            http_status=400,
            detail=f"The {upload_kind.label} file could not be read.",
            failure_stage="validation",
            reason_code="unreadable_document",
        )

    if not text:
        return UploadLifecycleResult(
            status="rejected",
            http_status=400,
            detail=f"No extractable text found in the {upload_kind.label} file.",
            failure_stage="validation",
            reason_code="no_extractable_text",
        )

    chunks = [chunk.strip() for chunk in chunk_text(text) if chunk and chunk.strip()]
    if not chunks:
        return UploadLifecycleResult(
            status="rejected",
            http_status=400,
            detail=f"No usable text chunks were created from the {upload_kind.label} file.",
            failure_stage="validation",
            reason_code="no_usable_chunks",
        )

    document_id = document_id or str(uuid.uuid4())
    try:
        stored_count = build_vector_store(document_id=document_id, chunks=chunks)
    except Exception:
        logger.exception("Document indexing failed")
        cleanup_status = _cleanup_failed_upload(document_id)
        detail = "Unable to process this document. Please try again later."
        if cleanup_status == "failed":
            detail = f"{detail} Cleanup may be required for partially indexed chunks."

        return UploadLifecycleResult(
            status="failed",
            http_status=500,
            document_id=document_id,
            chunk_count=len(chunks),
            detail=detail,
            failure_stage="indexing",
            reason_code="indexing_failed",
            cleanup_status=cleanup_status,
        )

    if stored_count == 0:
        cleanup_status = _cleanup_failed_upload(document_id)
        logger.error("Document indexing stored no chunks")
        detail = "Unable to process this document. Please try again later."
        if cleanup_status == "failed":
            detail = f"{detail} Cleanup may be required for partially indexed chunks."

        return UploadLifecycleResult(
            status="failed",
            http_status=500,
            document_id=document_id,
            chunk_count=len(chunks),
            detail=detail,
            failure_stage="indexing",
            reason_code="no_chunks_stored",
            cleanup_status=cleanup_status,
        )

    filename = file.filename or upload_kind.fallback_filename

    try:
        storage_url = existing_storage_url or upload_file_to_storage(
            user_id=user_id,
            document_id=document_id,
            filename=filename,
            data=data,
            content_type=upload_kind.content_type,
        )
    except PersistenceError:
        logger.exception("Document storage upload failed")
        cleanup_status = _cleanup_failed_upload(document_id)
        detail = "Unable to store this document. Please try again later."
        if cleanup_status == "failed":
            detail = f"{detail} Cleanup may be required for indexed chunks."

        return UploadLifecycleResult(
            status="failed",
            http_status=502,
            document_id=document_id,
            chunk_count=len(chunks),
            stored_count=stored_count,
            detail=detail,
            failure_stage="storage",
            reason_code="storage_upload_failed",
            cleanup_status=cleanup_status,
        )

    try:
        insert_document(
            document_id=document_id,
            user_id=user_id,
            filename=filename,
            storage_url=storage_url,
        )
    except PersistenceError:
        logger.exception("Document metadata persistence failed")
        cleanup_status = _cleanup_failed_upload(document_id, storage_url=storage_url)
        detail = "Unable to save this document. Please try again later."
        if cleanup_status == "failed":
            detail = f"{detail} Cleanup may be required for uploaded document artifacts."

        return UploadLifecycleResult(
            status="failed",
            http_status=502,
            document_id=document_id,
            chunk_count=len(chunks),
            stored_count=stored_count,
            detail=detail,
            failure_stage="metadata",
            reason_code="metadata_persist_failed",
            cleanup_status=cleanup_status,
        )

    return UploadLifecycleResult(
        status="completed",
        http_status=200,
        document_id=document_id,
        chunk_count=len(chunks),
        stored_count=stored_count,
    )


def delete_document(document_id: str, user_id: str, storage_url: str | None = None) -> DeleteLifecycleResult:
    try:
        conversation_ids = list_document_conversation_ids(user_id=user_id, document_id=document_id)
    except PersistenceError:
        logger.exception("Document conversation lookup failed")
        return _delete_failure(
            detail="Unable to remove this document. Please try again later.",
            failure_stage="conversations",
            reason_code="conversation_lookup_failed",
            cleanup_status="not-started",
        )

    try:
        for conversation_id in conversation_ids:
            delete_messages_for_conversation(conversation_id)
        delete_user_document_conversations(user_id=user_id, document_id=document_id)
    except PersistenceError:
        logger.exception("Document conversation cleanup failed")
        return _delete_failure(
            detail="Unable to remove this document. Please try again later.",
            failure_stage="conversations",
            reason_code="conversation_cleanup_failed",
            cleanup_status="partial",
        )

    try:
        delete_vector_store(document_id)
    except Exception:
        logger.exception("Document index cleanup failed")
        return _delete_failure(
            detail="Unable to remove this document. Please try again later.",
            failure_stage="indexing",
            reason_code="indexing_cleanup_failed",
            cleanup_status="partial",
            http_status=500,
        )

    if storage_url:
        try:
            delete_storage_object(storage_url)
        except PersistenceError:
            logger.exception("Document storage cleanup failed")
            return _delete_failure(
                detail="Unable to remove this document. Please try again later.",
                failure_stage="storage",
                reason_code="storage_delete_failed",
                cleanup_status="partial",
            )

    # Delete metadata last so the document remains the retry identity after a partial cleanup.
    try:
        delete_document_record(document_id=document_id, user_id=user_id)
    except PersistenceError:
        logger.exception("Document metadata deletion failed")
        return _delete_failure(
            detail="Unable to remove this document. Please try again later.",
            failure_stage="metadata",
            reason_code="metadata_delete_failed",
            cleanup_status="partial",
        )

    return DeleteLifecycleResult(
        status="completed",
        http_status=200,
        cleanup_status="completed",
    )
