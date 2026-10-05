"""Public responses hide provider diagnostics while logs retain the failure."""
import json
import unittest
from contextlib import ExitStack
from unittest.mock import patch

from backend.services.persistence import PersistenceError
from backend.services.question_suggestions import SuggestionGenerationError
from backend.tests.test_app_integration import _build_test_app, _request_asgi


DIAGNOSTIC = 'database table private_users at /internal/data; provider token test-secret'


class SafeErrorResponseTestCase(unittest.IsolatedAsyncioTestCase):
    async def test_failed_requests_hide_diagnostics_and_log_the_exception(self):
        cases = [
            ('POST', '/chat', {'request_id': '00000000-0000-4000-8000-000000000001', 'document_id': 'doc-a', 'question': 'What changed?'},
             'backend.routers.chat.execute_conversation_turn', RuntimeError,
             'backend.routers.chat', 'Unable to answer your question. Please try again later.'),
            ('POST', '/chat', {'request_id': '00000000-0000-4000-8000-000000000001', 'document_id': 'doc-a', 'question': 'What changed?'},
             'backend.routers.chat.execute_conversation_turn', PersistenceError,
             'backend.routers.chat', 'Unable to answer your question. Please try again later.'),
            ('GET', '/documents', None, 'backend.routers.documents.list_user_documents', PersistenceError,
             'backend.routers.documents', 'Unable to load your documents. Please try again later.'),
            ('GET', '/conversations', None, 'backend.routers.conversations.list_user_conversations', PersistenceError,
             'backend.routers.conversations', 'Unable to load your conversations. Please try again later.'),
            ('POST', '/conversations', {'document_id': 'doc-a'},
             'backend.routers.conversations.create_conversation', PersistenceError,
             'backend.routers.conversations', 'Unable to create a conversation. Please try again later.'),
            ('GET', '/conversations/convo-a/messages', None,
             'backend.routers.conversations.list_conversation_messages', PersistenceError,
             'backend.routers.conversations', 'Unable to load your messages. Please try again later.'),
            ('GET', '/documents/doc-a/suggestions', None,
             'backend.routers.documents.cached_suggestions', SuggestionGenerationError,
             'backend.routers.documents', 'Failed to load question suggestions.'),
            ('GET', '/documents/doc-a/suggestions', None,
             'backend.routers.documents.cached_suggestions', RuntimeError,
             'backend.routers.documents', 'Failed to load question suggestions.'),
            ('DELETE', '/documents/doc-a', None,
             'backend.routers.documents.delete_document_lifecycle', PersistenceError,
             'backend.routers.documents', 'Unable to delete this document. Please try again later.'),
        ]
        for method, path, body, target, error_type, logger, expected in cases:
            with self.subTest(method=method, path=path, error=error_type):
                with ExitStack() as stack:
                    stack.enter_context(patch(target, side_effect=error_type(DIAGNOSTIC)))
                    for auth_target in (
                        'backend.routers.documents.require_user_document',
                        'backend.routers.conversations.require_user_document',
                        'backend.routers.conversations.require_user_conversation',
                    ):
                        stack.enter_context(patch(auth_target, return_value={'id': 'doc-a'}))
                    logs = stack.enter_context(self.assertLogs(logger, level='ERROR'))
                    status, _, response = await _request_asgi(
                        _build_test_app(), method=method, path=path,
                        body=json.dumps(body).encode() if body else b'',
                        headers=[(b'content-type', b'application/json')],
                    )
                self.assertEqual(status, 502)
                self.assertEqual(json.loads(response), {'detail': expected})
                self.assertNotIn(DIAGNOSTIC, response.decode())
                self.assertIn(DIAGNOSTIC, '\n'.join(logs.output))

    async def test_ownership_lookup_failures_hide_diagnostics(self):
        cases = [
            ('/documents/doc-a/suggestions', 'get_user_document', 'Unable to verify document access. Please try again later.'),
            ('/documents/doc-a/suggestions', 'get_document', 'Unable to verify document access. Please try again later.'),
            ('/conversations/convo-a/messages', 'get_user_conversation', 'Unable to verify conversation access. Please try again later.'),
            ('/conversations/convo-a/messages', 'get_conversation', 'Unable to verify conversation access. Please try again later.'),
        ]
        for path, lookup, expected in cases:
            with self.subTest(lookup=lookup), ExitStack() as stack:
                for name in ('get_user_document', 'get_document', 'get_user_conversation', 'get_conversation'):
                    stack.enter_context(patch('backend.services.authz.' + name, return_value=None))
                stack.enter_context(patch('backend.services.authz.' + lookup, side_effect=PersistenceError(DIAGNOSTIC)))
                logs = stack.enter_context(self.assertLogs('backend.services.authz', level='ERROR'))
                status, _, response = await _request_asgi(_build_test_app(), method='GET', path=path)
                self.assertEqual(status, 502)
                self.assertEqual(json.loads(response), {'detail': expected})
                self.assertIn(DIAGNOSTIC, '\n'.join(logs.output))


class SafeLifecycleErrorTestCase(unittest.TestCase):
    def test_upload_and_delete_failure_stages_hide_diagnostics_and_keep_recovery_fields(self):
        from io import BytesIO
        from fastapi import UploadFile
        from backend.services.document_lifecycle import upload_document, delete_document

        cases = [
            ('upload', 'build_vector_store', RuntimeError, 'indexing_failed', 500),
            ('upload', 'upload_file_to_storage', PersistenceError, 'storage_upload_failed', 502),
            ('upload', 'insert_document', PersistenceError, 'metadata_persist_failed', 502),
            ('delete', 'list_document_conversation_ids', PersistenceError, 'conversation_lookup_failed', 502),
            ('delete', 'delete_messages_for_conversation', PersistenceError, 'conversation_cleanup_failed', 502),
            ('delete', 'delete_vector_store', RuntimeError, 'indexing_cleanup_failed', 500),
            ('delete', 'delete_storage_object', PersistenceError, 'storage_delete_failed', 502),
            ('delete', 'delete_document_record', PersistenceError, 'metadata_delete_failed', 502),
        ]
        defaults = {
            'extract_text_from_pdf': 'Example document', 'chunk_text': ['Example chunk'],
            'build_vector_store': 1, 'upload_file_to_storage': 'bucket/document.pdf',
            'insert_document': None, 'list_document_conversation_ids': ['convo-a'],
            'delete_messages_for_conversation': None, 'delete_user_document_conversations': None,
            'delete_vector_store': None, 'delete_storage_object': None, 'delete_document_record': None,
        }
        for action, target, error_type, reason, expected_status in cases:
            with self.subTest(action=action, stage=target), ExitStack() as stack:
                for name, result in defaults.items():
                    stack.enter_context(patch('backend.services.document_lifecycle.' + name, return_value=result))
                stack.enter_context(patch('backend.services.document_lifecycle.' + target, side_effect=error_type(DIAGNOSTIC)))
                logs = stack.enter_context(self.assertLogs('backend.services.document_lifecycle', level='ERROR'))
                if action == 'upload':
                    result = upload_document(UploadFile(filename='example.pdf', file=BytesIO(b'%PDF')), 'user-a')
                else:
                    result = delete_document('doc-a', 'user-a', 'bucket/document.pdf')
                detail = result.to_http_exception().detail
                self.assertEqual(result.http_status, expected_status)
                self.assertEqual(detail['reason_code'], reason)
                self.assertEqual(detail['lifecycle_status'], 'failed')
                self.assertIn('cleanup_status', detail)
                self.assertNotIn(DIAGNOSTIC, json.dumps(detail))
                self.assertIn(DIAGNOSTIC, '\n'.join(logs.output))
