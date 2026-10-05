"""Durable demo allowances. Only trusted servers can call the database functions."""
from contextlib import contextmanager

from fastapi import HTTPException

from .persistence.common import get_postgrest_client

MAX_UPLOAD_BYTES = 15_000_000
MAX_QUESTION_CHARS = 2_000
UPLOAD_BUCKET = 'askmydoc-uploads'
SMALLER_FILE_MESSAGE = 'Please select a smaller file. The maximum file size is 15 MB.'


def rpc(name: str, params: dict):
    try:
        return get_postgrest_client().rpc(name, params).execute().data
    except Exception as exc:
        raise HTTPException(503, 'Demo limits are temporarily unavailable. Please try again later.') from exc


def operation(action: str, user_id: str, kind: str, operation_id: str | None = None, payload=None):
    result = rpc('demo_operation', {'p_action': action, 'p_user_id': user_id,
        'p_kind': kind, 'p_id': operation_id, 'p_payload': payload if payload is not None else {}})
    error = result.get('error')
    if error == 'reserved':
        raise HTTPException(429, 'Your remaining upload slots are reserved by unfinished uploads. Please try again later.')
    if error == 'quota':
        allowance = '20 questions' if kind == 'question' else '3 documents'
        raise HTTPException(429, f'You have reached the demo allowance of {allowance} per account.')
    if error == 'rate':
        raise HTTPException(429, 'Please wait a minute before asking more questions.',
            headers={'Retry-After': str(result['retry_after'])})
    if error == 'not_found':
        raise HTTPException(404, 'Upload not found.')
    if error == 'busy':
        raise HTTPException(409, 'This upload is already being processed. Please wait.')
    if error == 'expired':
        raise HTTPException(410, 'This upload has expired. Please select the file again.')
    return result


@contextmanager
def question_allowance(user_id: str):
    reservation = operation('reserve', user_id, 'question')
    try:
        yield
    except Exception:
        operation('fail', user_id, 'question', reservation['id'])
        raise
    else:
        operation('complete', user_id, 'question', reservation['id'])


def cached_suggestions(user_id: str, document_id: str, generate):
    claim = rpc('demo_suggestions', {'p_user_id': user_id, 'p_document_id': document_id})
    if not claim['generate']:
        return claim['suggestions']
    try:
        suggestions = generate(document_id)
    except Exception:
        # Suggestions are optional. Store the empty result so refreshes cannot trigger more AI work.
        operation('complete', user_id, 'suggestions', claim['id'], [])
        raise
    operation('complete', user_id, 'suggestions', claim['id'], suggestions)
    return suggestions
