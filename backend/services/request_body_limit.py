"""Bound ingestion requests before FastAPI parses JSON or spools multipart data."""
from fastapi import HTTPException
from starlette.responses import JSONResponse
from starlette.types import ASGIApp, Receive, Scope, Send

from .demo_limits import MAX_UPLOAD_BYTES, SMALLER_FILE_MESSAGE


class RequestBodyLimitMiddleware:
    def __init__(self, app: ASGIApp):
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send):
        if scope['type'] != 'http':
            return await self.app(scope, receive, send)
        path = scope['path']
        if path == '/upload':
            limit, message = MAX_UPLOAD_BYTES + 65536, SMALLER_FILE_MESSAGE
        elif path in ('/chat', '/uploads') or path.startswith('/uploads/'):
            limit, message = 16384, 'This request is too large. Please send a smaller request.'
        else:
            return await self.app(scope, receive, send)
        headers = dict(scope.get('headers', []))
        try:
            declared_size = int(headers.get(b'content-length', b'0'))
        except ValueError:
            declared_size = 0
        if declared_size > limit:
            return await JSONResponse({'detail': message}, status_code=413)(scope, receive, send)
        received = 0

        async def bounded_receive():
            nonlocal received
            event = await receive()
            received += len(event.get('body', b''))
            if received > limit:
                raise HTTPException(413, message)
            return event

        await self.app(scope, bounded_receive, send)
