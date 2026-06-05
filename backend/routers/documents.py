from fastapi import APIRouter, Depends, HTTPException

from ..models.schemas import DeleteDocumentResponse, DocumentsResponse
from ..services.internal_auth import require_authenticated_user
from ..services.persistence import PersistenceError
from ..services.persistence.documents_repository import delete_document, list_user_documents
from ..services.vector_store import delete_vector_store

router = APIRouter()


@router.get("/documents", response_model=DocumentsResponse)
async def get_user_documents(user_id: str = Depends(require_authenticated_user)):
    try:
        documents = list_user_documents(user_id=user_id)
    except PersistenceError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc

    return DocumentsResponse(documents=documents)


@router.delete("/documents/{document_id}", response_model=DeleteDocumentResponse)
async def delete_user_document(
    document_id: str,
    user_id: str = Depends(require_authenticated_user),
):
    try:
        deleted = delete_document(document_id=document_id, user_id=user_id)
        if not deleted:
            raise HTTPException(status_code=404, detail="Document not found.")
    except HTTPException:
        raise
    except PersistenceError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc

    try:
        delete_vector_store(document_id=document_id)
    except Exception:
        pass

    return DeleteDocumentResponse(deleted=True)
