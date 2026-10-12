import json
import logging
import queue
import threading
from typing import Callable, Iterator
from uuid import UUID

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile
from fastapi.responses import StreamingResponse

from ..models.schemas import ErrorDetailResponse, UploadErrorResponse, UploadResponse, UploadInitRequest, UploadInitResponse
from ..services.internal_auth import require_authenticated_user
from ..services.document_lifecycle import UploadProgress, upload_document
from ..services.demo_limits import operation
from ..services.direct_upload import initialize_upload, complete_upload

router = APIRouter()
logger = logging.getLogger(__name__)


@router.post('/uploads', response_model=UploadInitResponse)
def start_upload(request: UploadInitRequest, user_id: str = Depends(require_authenticated_user)):
    return initialize_upload(user_id, request.filename, request.size)


@router.post('/uploads/{upload_id}/complete')
def finish_upload(upload_id: UUID, user_id: str = Depends(require_authenticated_user)):
    """Index an uploaded file, streaming its progress as JSON lines.

    Each `{"type": "progress", "step", "done", "total"}` line reports one finished page or batch. The last line is
    `{"type": "result", "status", "body"}`, carrying the HTTP status and JSON body this call would otherwise have
    returned (an `UploadResponse`, or an error `detail`), because the stream has already started with a 200.
    """
    return StreamingResponse(
        _stream_progress(lambda report: complete_upload(user_id, str(upload_id), report)),
        media_type='application/x-ndjson',
    )


def _stream_progress(work: Callable[[UploadProgress], dict]) -> Iterator[str]:
    """Run `work` in a thread and yield its progress, then its outcome, as JSON lines."""
    events: queue.Queue[dict] = queue.Queue()

    def run():
        try:
            outcome = {'status': 200, 'body': work(
                lambda step, done, total: events.put({'type': 'progress', 'step': step, 'done': done, 'total': total}))}
        except HTTPException as exc:
            outcome = {'status': exc.status_code, 'body': {'detail': exc.detail}}
        except Exception:
            logger.exception('Upload completion failed')
            outcome = {'status': 500, 'body': {'detail': 'Upload processing failed. Please try again later.'}}
        events.put({'type': 'result', **outcome})

    threading.Thread(target=run, daemon=True).start()
    while True:
        event = events.get()
        yield json.dumps(event) + '\n'
        if event['type'] == 'result':
            return


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
