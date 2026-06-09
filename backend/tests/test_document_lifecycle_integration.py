import unittest
from unittest.mock import AsyncMock, patch

from fastapi import HTTPException

from backend.routers.documents import delete_user_document
from backend.routers.upload import upload_pdf
from backend.services.persistence.common import PersistenceError


class DocumentLifecycleRouteIntegrationTestCase(unittest.IsolatedAsyncioTestCase):
    async def test_upload_route_returns_ready_contract_on_success(self):
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
            response = await upload_pdf(file=file, user_id="user-a")

        self.assertEqual(
            response.model_dump(),
            {
                "status": "success",
                "lifecycle_status": "ready",
                "document_id": "doc-1",
                "chunk_count": 2,
                "stored_count": 2,
            },
        )
        insert_document_mock.assert_called_once_with(
            document_id="doc-1",
            user_id="user-a",
            filename="report.pdf",
            storage_url="documents/user-a/doc-1/report.pdf",
        )

    async def test_upload_route_returns_structured_storage_failure_and_rolls_back_index(self):
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
            with self.assertRaises(HTTPException) as exc:
                await upload_pdf(file=file, user_id="user-a")

        self.assertEqual(exc.exception.status_code, 502)
        self.assertEqual(
            exc.exception.detail,
            {
                "message": "Failed to upload PDF to Supabase Storage",
                "lifecycle_status": "failed",
                "failure_stage": "storage",
                "reason_code": "storage_upload_failed",
                "cleanup_status": "completed",
            },
        )
        delete_vector_store_mock.assert_called_once_with("doc-1")

    async def test_upload_route_cleans_up_storage_and_index_when_metadata_persist_fails(self):
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
            with self.assertRaises(HTTPException) as exc:
                await upload_pdf(file=file, user_id="user-a")

        self.assertEqual(exc.exception.status_code, 502)
        self.assertEqual(
            exc.exception.detail,
            {
                "message": "Failed to persist document metadata",
                "lifecycle_status": "failed",
                "failure_stage": "metadata",
                "reason_code": "metadata_persist_failed",
                "cleanup_status": "completed",
            },
        )
        delete_vector_store_mock.assert_called_once_with("doc-1")
        delete_storage_object_mock.assert_called_once_with("documents/user-a/doc-1/report.pdf")

    async def test_delete_route_returns_deleted_contract_on_success(self):
        with (
            patch(
                "backend.routers.documents.require_user_document",
                return_value={"id": "doc-1", "user_id": "user-a", "storage_url": "documents/user-a/doc-1/report.pdf"},
            ),
            patch(
                "backend.services.document_lifecycle.list_document_conversation_ids",
                return_value=["convo-1"],
            ),
            patch("backend.services.document_lifecycle.delete_storage_object") as delete_storage_object_mock,
            patch("backend.services.document_lifecycle.delete_document_record") as delete_document_record_mock,
            patch("backend.services.document_lifecycle.delete_messages_for_conversation") as delete_messages_mock,
            patch("backend.services.document_lifecycle.delete_user_document_conversations") as delete_conversations_mock,
            patch("backend.services.document_lifecycle.delete_vector_store") as delete_vector_store_mock,
        ):
            response = await delete_user_document(document_id="doc-1", user_id="user-a")

        self.assertEqual(
            response.model_dump(),
            {
                "deleted": True,
                "lifecycle_status": "deleted",
                "cleanup_status": "completed",
            },
        )
        delete_storage_object_mock.assert_called_once_with("documents/user-a/doc-1/report.pdf")
        delete_document_record_mock.assert_called_once_with(document_id="doc-1", user_id="user-a")
        delete_messages_mock.assert_called_once_with("convo-1")
        delete_conversations_mock.assert_called_once_with(user_id="user-a", document_id="doc-1")
        delete_vector_store_mock.assert_called_once_with("doc-1")

    async def test_delete_route_returns_structured_storage_failure_without_metadata_delete(self):
        with (
            patch(
                "backend.routers.documents.require_user_document",
                return_value={"id": "doc-1", "user_id": "user-a", "storage_url": "documents/user-a/doc-1/report.pdf"},
            ),
            patch(
                "backend.services.document_lifecycle.list_document_conversation_ids",
                return_value=["convo-1"],
            ),
            patch(
                "backend.services.document_lifecycle.delete_storage_object",
                side_effect=PersistenceError("Failed to delete PDF from Supabase Storage"),
            ),
            patch("backend.services.document_lifecycle.delete_document_record") as delete_document_record_mock,
            patch("backend.services.document_lifecycle.delete_messages_for_conversation") as delete_messages_mock,
            patch("backend.services.document_lifecycle.delete_user_document_conversations") as delete_conversations_mock,
            patch("backend.services.document_lifecycle.delete_vector_store") as delete_vector_store_mock,
        ):
            with self.assertRaises(HTTPException) as exc:
                await delete_user_document(document_id="doc-1", user_id="user-a")

        self.assertEqual(exc.exception.status_code, 502)
        self.assertEqual(
            exc.exception.detail,
            {
                "message": "Failed to delete PDF from Supabase Storage",
                "lifecycle_status": "failed",
                "failure_stage": "storage",
                "reason_code": "storage_delete_failed",
                "cleanup_status": "partial",
            },
        )
        delete_document_record_mock.assert_not_called()
        delete_messages_mock.assert_not_called()
        delete_conversations_mock.assert_not_called()
        delete_vector_store_mock.assert_not_called()

    async def test_delete_route_returns_partial_index_cleanup_failure_after_document_removal(self):
        with (
            patch(
                "backend.routers.documents.require_user_document",
                return_value={"id": "doc-1", "user_id": "user-a", "storage_url": "documents/user-a/doc-1/report.pdf"},
            ),
            patch(
                "backend.services.document_lifecycle.list_document_conversation_ids",
                return_value=["convo-1"],
            ),
            patch("backend.services.document_lifecycle.delete_storage_object"),
            patch("backend.services.document_lifecycle.delete_document_record"),
            patch("backend.services.document_lifecycle.delete_messages_for_conversation"),
            patch("backend.services.document_lifecycle.delete_user_document_conversations"),
            patch(
                "backend.services.document_lifecycle.delete_vector_store",
                side_effect=RuntimeError("Failed to delete indexed document chunks."),
            ),
        ):
            with self.assertRaises(HTTPException) as exc:
                await delete_user_document(document_id="doc-1", user_id="user-a")

        self.assertEqual(exc.exception.status_code, 500)
        self.assertEqual(
            exc.exception.detail,
            {
                "message": "Failed to delete indexed document chunks.",
                "lifecycle_status": "failed",
                "failure_stage": "indexing",
                "reason_code": "indexing_cleanup_failed",
                "cleanup_status": "partial",
            },
        )


if __name__ == "__main__":
    unittest.main()
