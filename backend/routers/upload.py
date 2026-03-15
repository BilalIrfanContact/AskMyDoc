import uuid

from fastapi import APIRouter, File, HTTPException, UploadFile

from ..services.pdf_extractor import extract_text_from_pdf
from ..services.text_chunker import chunk_text
from ..services.vector_store import build_vector_store
from ..models.schemas import UploadResponse

router = APIRouter()


@router.post("/upload", response_model=UploadResponse)
async def upload_pdf(file: UploadFile = File(...)):
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

    return UploadResponse(
        status="success",
        document_id=document_id,
        chunk_count=len(chunks),
        stored_count=stored_count,
    )
