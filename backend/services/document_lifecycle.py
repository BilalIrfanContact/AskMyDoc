import uuid
from dataclasses import dataclass
from typing import Literal

from fastapi import HTTPException, UploadFile

from ..models.schemas import UploadResponse
from .pdf_extractor import extract_text_from_pdf
from .persistence import PersistenceError
from .persistence.documents_repository import insert_document
from .persistence.storage_repository import delete_storage_object, upload_pdf_to_storage
from .text_chunker import chunk_text
from .vector_store import build_vector_store, delete_vector_store

UploadFailureStage = Literal["validation", "indexing", "storage", "metadata"]
UploadCleanupStatus = Literal["not-needed", "completed", "failed"]
UploadLifecycleStatus = Literal["completed", "rejected", "failed"]


@dataclass(frozen=True)
class UploadLifecycleResult:
    status: UploadLifecycleStatus
    http_status: int
    document_id: str | None = None
    chunk_count: int = 0
    stored_count: int = 0
    detail: str | None = None
    failure_stage: UploadFailureStage | None = None
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
            "cleanup_status": self.cleanup_status,
        }


def _cleanup_failed_upload(document_id: str, storage_url: str | None = None) -> UploadCleanupStatus:
    cleanup_failed = False

    try:
        delete_vector_store(document_id)
    except Exception:
        cleanup_failed = True

    if storage_url:
        try:
            delete_storage_object(storage_url)
        except PersistenceError:
            cleanup_failed = True

    return "failed" if cleanup_failed else "completed"


async def upload_document(file: UploadFile, user_id: str) -> UploadLifecycleResult:
    if file.content_type not in {"application/pdf"}:
        return UploadLifecycleResult(
            status="rejected",
            http_status=400,
            detail="Only PDF files are supported.",
            failure_stage="validation",
        )

    data = await file.read()
    text = extract_text_from_pdf(data)

    if not text:
        return UploadLifecycleResult(
            status="rejected",
            http_status=400,
            detail="No extractable text found in the PDF.",
            failure_stage="validation",
        )

    chunks = [chunk.strip() for chunk in chunk_text(text) if chunk and chunk.strip()]
    if not chunks:
        return UploadLifecycleResult(
            status="rejected",
            http_status=400,
            detail="No usable text chunks were created from the PDF.",
            failure_stage="validation",
        )

    document_id = str(uuid.uuid4())
    stored_count = build_vector_store(document_id=document_id, chunks=chunks)
    if stored_count == 0:
        return UploadLifecycleResult(
            status="failed",
            http_status=500,
            document_id=document_id,
            chunk_count=len(chunks),
            detail="Chunks were created but not stored. Check OpenAI key and embedding setup.",
            failure_stage="indexing",
        )

    filename = file.filename or "document.pdf"

    try:
        storage_url = upload_pdf_to_storage(
            user_id=user_id,
            document_id=document_id,
            filename=filename,
            data=data,
        )
    except PersistenceError as exc:
        cleanup_status = _cleanup_failed_upload(document_id)
        detail = str(exc)
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
            cleanup_status=cleanup_status,
        )

    try:
        insert_document(
            document_id=document_id,
            user_id=user_id,
            filename=filename,
            storage_url=storage_url,
        )
    except PersistenceError as exc:
        cleanup_status = _cleanup_failed_upload(document_id, storage_url=storage_url)
        detail = str(exc)
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
            cleanup_status=cleanup_status,
        )

    return UploadLifecycleResult(
        status="completed",
        http_status=200,
        document_id=document_id,
        chunk_count=len(chunks),
        stored_count=stored_count,
    )
