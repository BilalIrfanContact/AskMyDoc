import json
import unittest
from unittest.mock import patch
from uuid import uuid4

import httpx
from fastapi import FastAPI, HTTPException

from backend.routers import chat, upload
from backend.services.internal_auth import require_authenticated_user
from backend.services.request_body_limit import RequestBodyLimitMiddleware


class UploadLimitsHttpTestCase(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.app = FastAPI()
        self.app.add_middleware(RequestBodyLimitMiddleware)
        self.app.include_router(upload.router)
        self.app.include_router(chat.router)
        self.client = httpx.AsyncClient(transport=httpx.ASGITransport(app=self.app), base_url='http://test')
        self.addAsyncCleanup(self.client.aclose)

    async def test_upload_authorization_and_completion_require_signed_identity(self):
        with patch('backend.services.direct_upload.operation') as operation:
            start = await self.client.post('/uploads', json={'filename': 'a.pdf', 'size': 10})
            finish = await self.client.post(f'/uploads/{uuid4()}/complete')
        self.assertEqual(start.status_code, 401)
        self.assertEqual(finish.status_code, 401)
        operation.assert_not_called()

    async def test_completion_streams_progress_then_the_result(self):
        self.app.dependency_overrides[require_authenticated_user] = lambda: 'user'
        def complete(user_id, upload_id, report):
            report('reading', 1, 2)
            report('reading', 2, 2)
            report('embedding', 1, 1)
            return {'document_id': upload_id, 'chunk_count': 3}
        upload_id = str(uuid4())
        with patch('backend.routers.upload.complete_upload', side_effect=complete):
            result = await self.client.post(f'/uploads/{upload_id}/complete')
        lines = [json.loads(line) for line in result.text.splitlines()]
        self.assertEqual(result.headers['content-type'], 'application/x-ndjson')
        self.assertEqual([(line['step'], line['done'], line['total']) for line in lines[:-1]],
            [('reading', 1, 2), ('reading', 2, 2), ('embedding', 1, 1)])
        self.assertEqual(lines[-1], {'type': 'result', 'status': 200, 'body': {'document_id': upload_id, 'chunk_count': 3}})

    async def test_a_failed_completion_reports_its_status_in_the_last_line(self):
        self.app.dependency_overrides[require_authenticated_user] = lambda: 'user'
        with patch('backend.routers.upload.complete_upload', side_effect=HTTPException(410, 'This upload has expired.')):
            result = await self.client.post(f'/uploads/{uuid4()}/complete')
        self.assertEqual(json.loads(result.text), {'type': 'result', 'status': 410, 'body': {'detail': 'This upload has expired.'}})

    async def test_oversized_metadata_returns_clear_message_without_reserving(self):
        self.app.dependency_overrides[require_authenticated_user] = lambda: str(uuid4())
        with patch('backend.services.direct_upload.operation') as operation:
            result = await self.client.post('/uploads', json={'filename': 'a.pdf', 'size': 15_000_001})
        self.assertEqual(result.status_code, 413)
        self.assertIn('Please select a smaller file', result.json()['detail'])
        operation.assert_not_called()

    async def test_actual_oversized_legacy_body_is_rejected_before_parsing_or_reserving(self):
        with patch('backend.routers.upload.operation') as operation:
            result = await self.client.post('/upload', content=b'x' * 15_100_000)
        self.assertEqual(result.status_code, 413)
        self.assertIn('Please select a smaller file', result.json()['detail'])
        operation.assert_not_called()

    async def test_chunked_body_without_content_length_is_also_bounded(self):
        async def chunks():
            yield b'{"filename":"'
            yield b'x' * 17_000
            yield b'","size":1}'
        self.app.dependency_overrides[require_authenticated_user] = lambda: str(uuid4())
        result = await self.client.post('/uploads', content=chunks(), headers={'content-type': 'application/json'})
        self.assertEqual(result.status_code, 413)

    async def test_question_length_rejected_before_ai_or_quota_reservation(self):
        self.app.dependency_overrides[require_authenticated_user] = lambda: str(uuid4())
        with patch('backend.routers.chat.execute_conversation_turn') as execute:
            result = await self.client.post('/chat', json={'document_id': 'doc', 'conversation_id': 'conversation', 'message': 'x' * 2001})
        self.assertEqual(result.status_code, 422)
        execute.assert_not_called()
