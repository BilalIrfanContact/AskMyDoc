from io import BytesIO
import unittest
from unittest.mock import Mock, patch

from fastapi import HTTPException, UploadFile
from starlette.datastructures import Headers

from backend.services import demo_limits, direct_upload
from backend.services.document_lifecycle import UploadLifecycleResult, upload_document


class DemoLimitsTestCase(unittest.TestCase):
    def test_database_outage_fails_closed(self):
        with patch.object(demo_limits, 'get_postgrest_client', side_effect=RuntimeError('offline')):
            with self.assertRaises(HTTPException) as error:
                demo_limits.operation('reserve', 'user', 'question')
        self.assertEqual(error.exception.status_code, 503)

    def test_over_limit_file_is_rejected_before_reservation_or_storage(self):
        with patch.object(direct_upload, 'operation') as reserve, patch.object(direct_upload, 'get_storage_client') as storage:
            with self.assertRaises(HTTPException) as error:
                direct_upload.initialize_upload('user', 'report.pdf', 15_000_001)
        self.assertEqual(error.exception.status_code, 413)
        self.assertIn('Please select a smaller file', error.exception.detail)
        reserve.assert_not_called()
        storage.assert_not_called()

    def test_ten_mb_file_receives_permission_for_server_selected_path(self):
        storage = Mock()
        storage.from_.return_value.create_signed_upload_url.return_value = {'signed_url': 'https://storage.test/upload?token=test'}
        with patch.object(direct_upload, 'operation', return_value={'id': 'upload-id'}) as op, patch.object(direct_upload, 'get_storage_client', return_value=storage):
            response = direct_upload.initialize_upload('user', '../../report.pdf', 10_000_000)
        self.assertEqual(response['upload_id'], 'upload-id')
        self.assertEqual(op.call_args.kwargs['payload']['filename'], 'report.pdf')
        storage.from_.return_value.create_signed_upload_url.assert_called_once_with('user/upload-id/document.pdf')

    def test_completed_upload_returns_receipt_without_paid_processing(self):
        receipt = {'document_id': 'upload-id', 'chunk_count': 10}
        with patch.object(direct_upload, 'operation', return_value={'state': 'completed', 'result': receipt}), patch.object(direct_upload, 'download_upload') as download, patch.object(direct_upload, 'upload_document') as process:
            self.assertEqual(direct_upload.complete_upload('user', 'upload-id'), receipt)
        download.assert_not_called()
        process.assert_not_called()

    def test_finalization_uses_actual_size_and_never_indexes_mismatched_object(self):
        reservation = {'state': 'running', 'payload': {'filename': 'a.pdf', 'content_type': 'application/pdf', 'size': 5}}
        with patch.object(direct_upload, 'operation', return_value=reservation) as op, patch.object(direct_upload, 'download_upload', return_value=b'too long'), patch.object(direct_upload, 'upload_document') as process:
            with self.assertRaises(HTTPException) as error:
                direct_upload.complete_upload('user', 'upload-id')
        self.assertEqual(error.exception.status_code, 400)
        process.assert_not_called()
        self.assertEqual(op.call_args.args[:4], ('fail', 'user', 'upload', 'upload-id'))

    def test_finalization_preserves_account_and_object_identity(self):
        reservation = {'state': 'running', 'payload': {'filename': 'a.md', 'content_type': 'text/markdown', 'size': 5}}
        result = UploadLifecycleResult(status='completed', http_status=200, document_id='upload-id', chunk_count=1, stored_count=1)
        with patch.object(direct_upload, 'operation', return_value=reservation), patch.object(direct_upload, 'download_upload', return_value=b'hello'), patch.object(direct_upload, 'upload_document', return_value=result) as process:
            response = direct_upload.complete_upload('user', 'upload-id')
        self.assertEqual(response['document_id'], 'upload-id')
        self.assertEqual(process.call_args.kwargs['existing_storage_url'], 'askmydoc-uploads/user/upload-id/document.md')
        self.assertEqual(process.call_args.args[1], 'user')

    def test_receipt_write_failure_does_not_refund_a_processed_document(self):
        reservation = {'state': 'running', 'payload': {'filename': 'a.md', 'content_type': 'text/markdown', 'size': 5}}
        result = UploadLifecycleResult(status='completed', http_status=200, document_id='upload-id', chunk_count=1, stored_count=1)
        def op(action, *args):
            if action == 'complete': raise HTTPException(503, 'database unavailable')
            return reservation
        with patch.object(direct_upload, 'operation', side_effect=op) as operation, patch.object(direct_upload, 'download_upload', return_value=b'hello'), patch.object(direct_upload, 'upload_document', return_value=result):
            with self.assertRaises(HTTPException): direct_upload.complete_upload('user', 'upload-id')
        self.assertNotIn('fail', [call.args[0] for call in operation.call_args_list])

    def test_stream_download_rejects_oversized_content_with_no_content_length(self):
        response = Mock()
        response.iter_bytes.return_value = iter([b'x' * 10_000_000, b'x' * 5_000_001])
        context = Mock()
        context.__enter__ = Mock(return_value=response)
        context.__exit__ = Mock(return_value=False)
        with patch.object(direct_upload.httpx, 'stream', return_value=context), patch.object(direct_upload, '_get_supabase_url', return_value='https://storage.test'), patch.object(direct_upload, '_base_headers', return_value={}):
            with self.assertRaises(HTTPException) as error: direct_upload.download_upload('user/upload/document.pdf')
        self.assertEqual(error.exception.status_code, 413)

    def test_legacy_upload_reads_with_bound_before_parsing(self):
        file = UploadFile(file=BytesIO(b'x' * 15_000_001), filename='a.pdf', headers=Headers({'content-type': 'application/pdf'}))
        with patch('backend.services.document_lifecycle.extract_text_from_pdf') as extract:
            result = upload_document(file, 'user')
        self.assertEqual(result.http_status, 413)
        self.assertEqual(result.reason_code, 'file_too_large')
        extract.assert_not_called()

    def test_cached_suggestions_do_not_call_model(self):
        generate = Mock()
        with patch.object(demo_limits, 'rpc', return_value={'generate': False, 'suggestions': ['Question?']}):
            self.assertEqual(demo_limits.cached_suggestions('user', 'doc', generate), ['Question?'])
        generate.assert_not_called()

    def test_failed_suggestions_are_saved_as_empty_to_prevent_refresh_retries(self):
        with patch.object(demo_limits, 'rpc', return_value={'generate': True, 'id': 'reservation'}), patch.object(demo_limits, 'operation') as op:
            with self.assertRaisesRegex(RuntimeError, 'model unavailable'):
                demo_limits.cached_suggestions('user', 'doc', Mock(side_effect=RuntimeError('model unavailable')))
        op.assert_called_once_with('complete', 'user', 'suggestions', 'reservation', [])

    def test_running_suggestions_signal_pending_without_calling_the_model(self):
        generate = Mock()
        with patch.object(demo_limits, 'rpc', return_value={'generate': False, 'pending': True, 'suggestions': []}):
            with self.assertRaises(demo_limits.SuggestionsPendingError):
                demo_limits.cached_suggestions('user', 'doc', generate)
        generate.assert_not_called()

    def test_failed_legacy_claim_is_in_the_refund_path(self):
        from backend.routers.upload import upload_pdf
        calls = []
        def op(action, *args):
            calls.append(action)
            if action == 'claim': raise HTTPException(503, 'Temporary database failure')
            return {'id': 'reservation'}
        file = UploadFile(file=BytesIO(b'PDF'), filename='a.pdf')
        with patch('backend.routers.upload.operation', side_effect=op), patch('backend.routers.upload.upload_document') as process:
            with self.assertRaises(HTTPException) as error:
                upload_pdf(file, 'user')
        self.assertEqual(error.exception.status_code, 503)
        self.assertEqual(calls, ['reserve', 'claim', 'fail'])
        process.assert_not_called()
