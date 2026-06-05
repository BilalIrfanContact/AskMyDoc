import uuid

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile

from ..models.schemas import UploadResponse
from ..services.internal_auth import require_authenticated_user
from ..services.pdf_extractor import extract_text_from_pdf
from ..services.persistence import PersistenceError
from ..services.persistence.documents_repository import insert_document
from ..services.persistence.storage_repository import upload_pdf_to_storage
from ..services.text_chunker import chunk_text
from ..services.vector_store import build_vector_store

router = APIRouter()


@router.post("/upload", response_model=UploadResponse)
async def upload_pdf(
    file: UploadFile = File(...),
    user_id: str = Depends(require_authenticated_user),
):
    if file.content_type not in {"application/pdf"}:
        raise HTTPException(status_code=400, detail="Only PDF files are supported.")

    data = await file.read()
    text = extract_text_from_pdf(data)

    if not text:
        raise HTTPException(status_code=400, detail="No extractable text found in the PDF.")

    chunks = [chunk.strip() for chunk in chunk_text(text) if chunk and chunk.strip()]
    if not chunks:
        raise HTTPException(status_code=400, detail="No usable text chunks were created from the PDF.")

    document_id = str(uuid.uuid4())
    stored_count = build_vector_store(document_id=document_id, chunks=chunks)
    if stored_count == 0:
        raise HTTPException(
            status_code=500,
            detail="Chunks were created but not stored. Check OpenAI key and embedding setup.",
        )

    try:
        filename = file.filename or "document.pdf"
        storage_url = upload_pdf_to_storage(
            user_id=user_id,
            document_id=document_id,
            filename=filename,
            data=data,
        )
        insert_document(
            document_id=document_id,
            user_id=user_id,
            filename=filename,
            storage_url=storage_url,
        )
    except PersistenceError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc

    return UploadResponse(
        status="success",
        document_id=document_id,
        chunk_count=len(chunks),
        stored_count=stored_count,
    )
