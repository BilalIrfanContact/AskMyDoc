from fastapi import APIRouter, Depends, HTTPException

from ..models.schemas import DeleteDocumentResponse, DeleteErrorResponse, DocumentsResponse, ErrorDetailResponse
from ..services.authz import require_user_document
from ..services.document_lifecycle import delete_document as delete_document_lifecycle
from ..services.internal_auth import require_authenticated_user
from ..services.persistence import PersistenceError
from ..services.persistence.documents_repository import list_user_documents

router = APIRouter()


@router.get(
    "/documents",
    response_model=DocumentsResponse,
    responses={
        401: {"model": ErrorDetailResponse},
        502: {"model": ErrorDetailResponse},
    },
)
async def get_user_documents(user_id: str = Depends(require_authenticated_user)):
    try:
        documents = list_user_documents(user_id=user_id)
    except PersistenceError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc

    return DocumentsResponse(documents=documents)


@router.delete(
    "/documents/{document_id}",
    response_model=DeleteDocumentResponse,
    responses={
        401: {"model": ErrorDetailResponse},
        404: {"model": ErrorDetailResponse},
        502: {"model": DeleteErrorResponse},
    },
)
async def delete_user_document(
    document_id: str,
    user_id: str = Depends(require_authenticated_user),
):
    document = require_user_document(document_id=document_id, user_id=user_id)

    try:
        result = delete_document_lifecycle(
            document_id=document_id,
            user_id=user_id,
            storage_url=document.get("storage_url"),
        )
    except HTTPException:
        raise
    except PersistenceError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc

    if result.status != "completed":
        raise result.to_http_exception()

    return result.to_response()
