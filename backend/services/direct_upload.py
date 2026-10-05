"""Authorize one private storage object, then process only that server-selected object."""
from io import BytesIO
from pathlib import PurePath
from urllib.parse import quote

import httpx
from fastapi import HTTPException, UploadFile
from starlette.datastructures import Headers

from .demo_limits import MAX_UPLOAD_BYTES, SMALLER_FILE_MESSAGE, UPLOAD_BUCKET, operation
from .document_lifecycle import upload_document
from .persistence.common import _base_headers, _get_supabase_url, get_storage_client


def initialize_upload(user_id: str, filename: str, size: int):
    if size > MAX_UPLOAD_BYTES:
        raise HTTPException(413, SMALLER_FILE_MESSAGE)
    extension = PurePath(filename).suffix.lower()
    if extension not in ('.pdf', '.md'):
        raise HTTPException(400, 'Only PDF and Markdown files are supported.')
    content_type = 'application/pdf' if extension == '.pdf' else 'text/markdown'
    reservation = operation('reserve', user_id, 'upload', payload={
        'signed_upload': True, 'filename': PurePath(filename.replace('\\', '/')).name, 'size': size, 'content_type': content_type})
    upload_id = reservation['id']
    path = f'{user_id}/{upload_id}/document{extension}'
    try:
        signed = get_storage_client().from_(UPLOAD_BUCKET).create_signed_upload_url(path)
    except Exception as exc:
        operation('fail', user_id, 'upload', upload_id)
        raise HTTPException(503, 'Unable to start the upload. Please try again later.') from exc
    return {'upload_id': upload_id, 'signed_url': signed['signed_url'], 'content_type': content_type}


def download_upload(path: str) -> bytes:
    # Stream with a hard cap; never trust the browser's declared size or Content-Length.
    url = f'{_get_supabase_url()}/storage/v1/object/authenticated/{UPLOAD_BUCKET}/{quote(path, safe="/")}'
    data = bytearray()
    with httpx.stream('GET', url, headers=_base_headers(), timeout=60) as response:
        response.raise_for_status()
        for chunk in response.iter_bytes(chunk_size=65536):
            if len(data) + len(chunk) > MAX_UPLOAD_BYTES:
                raise HTTPException(413, SMALLER_FILE_MESSAGE)
            data.extend(chunk)
    return bytes(data)


def complete_upload(user_id: str, upload_id: str):
    reservation = operation('claim', user_id, 'upload', upload_id)
    if reservation['state'] == 'completed':
        return reservation['result']
    metadata = reservation['payload']
    extension = '.pdf' if metadata['content_type'] == 'application/pdf' else '.md'
    path = f'{user_id}/{upload_id}/document{extension}'
    try:
        data = download_upload(path)
        if len(data) != metadata['size']:
            raise HTTPException(400, 'The uploaded file size did not match. Please select the file again.')
        file = UploadFile(filename=metadata['filename'], file=BytesIO(data),
            headers=Headers({'content-type': metadata['content_type']}))
        result = upload_document(file, user_id, document_id=upload_id,
            existing_storage_url=f'{UPLOAD_BUCKET}/{path}')
        if result.status != 'completed':
            raise result.to_http_exception()
        response = result.to_response().model_dump()
    except HTTPException:
        operation('fail', user_id, 'upload', upload_id)
        raise
    except Exception as exc:
        operation('fail', user_id, 'upload', upload_id)
        raise HTTPException(502, 'Upload processing failed. Please try again later.') from exc
    operation('complete', user_id, 'upload', upload_id, response)
    return response
