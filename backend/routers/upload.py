from fastapi import APIRouter, Depends, File, UploadFile

from ..models.schemas import ErrorDetailResponse, UploadErrorResponse, UploadResponse
from ..services.internal_auth import require_authenticated_user
from ..services.document_lifecycle import upload_document

router = APIRouter()


@router.post(
    "/upload",
    response_model=UploadResponse,
    responses={
        400: {"model": UploadErrorResponse},
        401: {"model": ErrorDetailResponse},
        500: {"model": UploadErrorResponse},
        502: {"model": UploadErrorResponse},
    },
)
async def upload_pdf(
    file: UploadFile = File(...),
    user_id: str = Depends(require_authenticated_user),
):
    result = await upload_document(file=file, user_id=user_id)
    if result.status != "completed":
        raise result.to_http_exception()

    return result.to_response()
