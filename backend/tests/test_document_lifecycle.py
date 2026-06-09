import unittest
from unittest.mock import AsyncMock, patch

from backend.services.document_lifecycle import upload_document
from backend.services.persistence.common import PersistenceError


class DocumentLifecycleTestCase(unittest.IsolatedAsyncioTestCase):
    async def test_upload_document_returns_completed_result_on_success(self):
        file = AsyncMock()
        file.content_type = "application/pdf"
        file.filename = "report.pdf"
        file.read.return_value = b"%PDF"

        with (
            patch("backend.services.document_lifecycle.extract_text_from_pdf", return_value="alpha beta"),
            patch("backend.services.document_lifecycle.chunk_text", return_value=["alpha", "beta"]),
            patch("backend.services.document_lifecycle.build_vector_store", return_value=2),
            patch(
                "backend.services.document_lifecycle.upload_pdf_to_storage",
                return_value="documents/user-a/doc-1/report.pdf",
            ),
            patch("backend.services.document_lifecycle.insert_document") as insert_document_mock,
            patch("backend.services.document_lifecycle.uuid.uuid4", return_value="doc-1"),
        ):
            result = await upload_document(file=file, user_id="user-a")

        self.assertEqual(result.status, "completed")
        self.assertEqual(result.document_id, "doc-1")
        self.assertEqual(result.chunk_count, 2)
        self.assertEqual(result.stored_count, 2)
        self.assertEqual(result.cleanup_status, "not-needed")
        self.assertEqual(result.to_response().lifecycle_status, "ready")
        insert_document_mock.assert_called_once_with(
            document_id="doc-1",
            user_id="user-a",
            filename="report.pdf",
            storage_url="documents/user-a/doc-1/report.pdf",
        )

    async def test_upload_document_cleans_up_indexed_chunks_when_storage_upload_fails(self):
        file = AsyncMock()
        file.content_type = "application/pdf"
        file.filename = "report.pdf"
        file.read.return_value = b"%PDF"

        with (
            patch("backend.services.document_lifecycle.extract_text_from_pdf", return_value="alpha beta"),
            patch("backend.services.document_lifecycle.chunk_text", return_value=["alpha", "beta"]),
            patch("backend.services.document_lifecycle.build_vector_store", return_value=2),
            patch(
                "backend.services.document_lifecycle.upload_pdf_to_storage",
                side_effect=PersistenceError("Failed to upload PDF to Supabase Storage"),
            ),
            patch("backend.services.document_lifecycle.delete_vector_store") as delete_vector_store_mock,
            patch("backend.services.document_lifecycle.uuid.uuid4", return_value="doc-1"),
        ):
            result = await upload_document(file=file, user_id="user-a")

        self.assertEqual(result.status, "failed")
        self.assertEqual(result.failure_stage, "storage")
        self.assertEqual(result.http_status, 502)
        self.assertEqual(result.cleanup_status, "completed")
        self.assertEqual(result.detail, "Failed to upload PDF to Supabase Storage")
        self.assertEqual(
            result.to_error_detail(),
            {
                "message": "Failed to upload PDF to Supabase Storage",
                "lifecycle_status": "failed",
                "failure_stage": "storage",
                "cleanup_status": "completed",
            },
        )
        delete_vector_store_mock.assert_called_once_with("doc-1")

    async def test_upload_document_returns_structured_failure_when_indexing_raises(self):
        file = AsyncMock()
        file.content_type = "application/pdf"
        file.filename = "report.pdf"
        file.read.return_value = b"%PDF"

        with (
            patch("backend.services.document_lifecycle.extract_text_from_pdf", return_value="alpha beta"),
            patch("backend.services.document_lifecycle.chunk_text", return_value=["alpha", "beta"]),
            patch(
                "backend.services.document_lifecycle.build_vector_store",
                side_effect=RuntimeError("Embedding provider unavailable"),
            ),
            patch("backend.services.document_lifecycle.delete_vector_store") as delete_vector_store_mock,
            patch("backend.services.document_lifecycle.uuid.uuid4", return_value="doc-1"),
        ):
            result = await upload_document(file=file, user_id="user-a")

        self.assertEqual(result.status, "failed")
        self.assertEqual(result.failure_stage, "indexing")
        self.assertEqual(result.http_status, 500)
        self.assertEqual(result.cleanup_status, "completed")
        self.assertEqual(result.detail, "Embedding provider unavailable")
        delete_vector_store_mock.assert_called_once_with("doc-1")

    async def test_upload_document_cleans_up_storage_and_index_when_metadata_persist_fails(self):
        file = AsyncMock()
        file.content_type = "application/pdf"
        file.filename = "report.pdf"
        file.read.return_value = b"%PDF"

        with (
            patch("backend.services.document_lifecycle.extract_text_from_pdf", return_value="alpha beta"),
            patch("backend.services.document_lifecycle.chunk_text", return_value=["alpha", "beta"]),
            patch("backend.services.document_lifecycle.build_vector_store", return_value=2),
            patch(
                "backend.services.document_lifecycle.upload_pdf_to_storage",
                return_value="documents/user-a/doc-1/report.pdf",
            ),
            patch(
                "backend.services.document_lifecycle.insert_document",
                side_effect=PersistenceError("Failed to persist document metadata"),
            ),
            patch("backend.services.document_lifecycle.delete_vector_store") as delete_vector_store_mock,
            patch("backend.services.document_lifecycle.delete_storage_object") as delete_storage_object_mock,
            patch("backend.services.document_lifecycle.uuid.uuid4", return_value="doc-1"),
        ):
            result = await upload_document(file=file, user_id="user-a")

        self.assertEqual(result.status, "failed")
        self.assertEqual(result.failure_stage, "metadata")
        self.assertEqual(result.http_status, 502)
        self.assertEqual(result.cleanup_status, "completed")
        self.assertEqual(result.detail, "Failed to persist document metadata")
        delete_vector_store_mock.assert_called_once_with("doc-1")
        delete_storage_object_mock.assert_called_once_with("documents/user-a/doc-1/report.pdf")

    async def test_upload_document_rejects_non_pdf_files_before_processing(self):
        file = AsyncMock()
        file.content_type = "text/plain"
        file.filename = "notes.txt"

        with (
            patch("backend.services.document_lifecycle.extract_text_from_pdf") as extract_text_mock,
            patch("backend.services.document_lifecycle.build_vector_store") as build_vector_store_mock,
        ):
            result = await upload_document(file=file, user_id="user-a")

        self.assertEqual(result.status, "rejected")
        self.assertEqual(result.failure_stage, "validation")
        self.assertEqual(result.http_status, 400)
        self.assertEqual(result.detail, "Only PDF files are supported.")
        extract_text_mock.assert_not_called()
        build_vector_store_mock.assert_not_called()


if __name__ == "__main__":
    unittest.main()
