import unittest
from unittest.mock import Mock, patch

from backend.scripts.cleanup_demo_uploads import cleanup_uploads


class CleanupDemoUploadsTestCase(unittest.TestCase):
    def setUp(self):
        self.client = Mock()
        self.client.rpc.return_value.execute.return_value.data = [{
            'id': 'upload-id', 'user_id': 'user-id',
            'payload': {'content_type': 'application/pdf'},
        }]

    def test_default_is_read_only(self):
        with patch('backend.scripts.cleanup_demo_uploads.get_postgrest_client', return_value=self.client), patch('backend.scripts.cleanup_demo_uploads.delete_storage_object') as remove:
            self.assertEqual(cleanup_uploads(), 1)
        self.client.rpc.assert_called_once_with('demo_expired_uploads', {})
        self.client.from_.assert_not_called()
        remove.assert_not_called()

    def test_apply_removes_the_server_selected_object_and_marks_cleanup(self):
        with patch('backend.scripts.cleanup_demo_uploads.get_postgrest_client', return_value=self.client), patch('backend.scripts.cleanup_demo_uploads.delete_storage_object') as remove:
            self.assertEqual(cleanup_uploads(apply=True), 1)
        remove.assert_called_once_with('askmydoc-uploads/user-id/upload-id/document.pdf')
        self.client.from_.assert_called_once_with('demo_operations')
        self.client.from_.return_value.update.assert_called_once_with({'storage_cleaned': True})
        self.client.from_.return_value.update.return_value.eq.assert_called_once_with('id', 'upload-id')

    def test_storage_failure_keeps_receipt_eligible_for_retry(self):
        with patch('backend.scripts.cleanup_demo_uploads.get_postgrest_client', return_value=self.client), patch('backend.scripts.cleanup_demo_uploads.delete_storage_object', side_effect=RuntimeError('storage unavailable')):
            with self.assertRaisesRegex(RuntimeError, 'storage unavailable'):
                cleanup_uploads(apply=True)
        self.client.from_.assert_not_called()
