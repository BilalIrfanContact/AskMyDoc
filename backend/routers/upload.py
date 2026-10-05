from uuid import UUID

from fastapi import APIRouter, Depends, File, UploadFile

from ..models.schemas import ErrorDetailResponse, UploadErrorResponse, UploadResponse, UploadInitRequest, UploadInitResponse
from ..services.internal_auth import require_authenticated_user
from ..services.document_lifecycle import upload_document
from ..services.demo_limits import operation
from ..services.direct_upload import initialize_upload, complete_upload

router = APIRouter()


@router.post('/uploads', response_model=UploadInitResponse)
def start_upload(request: UploadInitRequest, user_id: str = Depends(require_authenticated_user)):
    return initialize_upload(user_id, request.filename, request.size)


@router.post('/uploads/{upload_id}/complete', response_model=UploadResponse)
def finish_upload(upload_id: UUID, user_id: str = Depends(require_authenticated_user)):
    return complete_upload(user_id, str(upload_id))


@router.post('/upload', response_model=UploadResponse, responses={
    400: {'model': UploadErrorResponse}, 401: {'model': ErrorDetailResponse},
    413: {'model': UploadErrorResponse}, 429: {'model': ErrorDetailResponse},
    500: {'model': UploadErrorResponse}, 502: {'model': UploadErrorResponse},
})
def upload_pdf(file: UploadFile = File(...), user_id: str = Depends(require_authenticated_user)):
    # The legacy endpoint remains usable by trusted clients, with the same lifetime allowance.
    reservation = operation('reserve', user_id, 'upload')
    try:
        operation('claim', user_id, 'upload', reservation['id'])
        result = upload_document(file=file, user_id=user_id)
        if result.status != 'completed':
            raise result.to_http_exception()
    except Exception:
        operation('fail', user_id, 'upload', reservation['id'])
        raise
    operation('complete', user_id, 'upload', reservation['id'], result.to_response().model_dump())
    return result.to_response()
