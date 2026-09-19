import unittest
from unittest.mock import Mock, patch

from fastapi import HTTPException

from backend.services.chunk_inspector import inspect_document_chunks


class ChunkInspectorTestCase(unittest.TestCase):
    document = {
        "id": "doc-a",
        "user_id": "user-a",
        "filename": "report.pdf",
        "storage_url": "pdfs/user-a/doc-a/report.pdf",
        "uploaded_at": "2026-09-19T00:00:00Z",
    }

    def _collection(self, ids, documents, metadatas):
        collection = Mock()
        collection.get.return_value = {
            "ids": ids,
            "documents": documents,
            "metadatas": metadatas,
        }
        return collection

    def test_authorized_inspection_returns_source_and_stored_chunks(self):
        collection = self._collection(
            ["doc-a:chunk:0"],
            ["Revenue: $10 million"],
            [{"chunk_id": "doc-a:chunk:0", "chunk_index": 0}],
        )

        with (
            patch("backend.services.chunk_inspector.require_user_document", return_value=self.document) as authorize,
            patch("backend.services.chunk_inspector.download_storage_object", return_value=b"pdf") as download,
            patch(
                "backend.services.chunk_inspector._source_pages",
                return_value=("pdf", ["Revenue: $10 million"], [(1, "Revenue: $10 million")]),
            ),
            patch("backend.services.chunk_inspector.chunk_text", return_value=["Revenue: $10 million"]),
            patch("backend.services.chunk_inspector.get_persisted_collection", return_value=collection),
        ):
            report = inspect_document_chunks(document_id="doc-a", user_id="user-a")

        authorize.assert_called_once_with(document_id="doc-a", user_id="user-a")
        download.assert_called_once_with("pdfs/user-a/doc-a/report.pdf")
        collection.get.assert_called_once_with(include=["documents", "metadatas"])
        self.assertEqual(report["status"], "ready_with_warnings")
        self.assertEqual(report["source"]["pages"][0]["text"], "Revenue: $10 million")
        self.assertEqual(report["chunks"][0]["text"], "Revenue: $10 million")

    def test_unauthorized_document_is_rejected_before_reading_source_or_chroma(self):
        collection = self._collection([], [], [])
        with (
            patch(
                "backend.services.chunk_inspector.require_user_document",
                side_effect=HTTPException(status_code=403, detail="You are not authorized."),
            ),
            patch("backend.services.chunk_inspector.download_storage_object") as download,
            patch("backend.services.chunk_inspector.get_persisted_collection", return_value=collection) as get_collection,
        ):
            with self.assertRaises(HTTPException) as exc:
                inspect_document_chunks(document_id="doc-b", user_id="user-a")

        self.assertEqual(exc.exception.status_code, 403)
        download.assert_not_called()
        get_collection.assert_not_called()

    def test_chunks_are_sorted_by_stored_chunk_index_and_preserve_text_and_metadata(self):
        collection = self._collection(
            ["doc-a:chunk:1", "doc-a:chunk:0"],
            ["Second row: 20%", "First row: 10%"],
            [
                {"chunk_id": "doc-a:chunk:1", "chunk_index": 1},
                {"chunk_id": "doc-a:chunk:0", "chunk_index": 0},
            ],
        )

        with (
            patch("backend.services.chunk_inspector.require_user_document", return_value=self.document),
            patch("backend.services.chunk_inspector.download_storage_object", return_value=b"pdf"),
            patch(
                "backend.services.chunk_inspector._source_pages",
                return_value=(
                    "pdf",
                    ["First row: 10%\n\nSecond row: 20%"],
                    [(1, "First row: 10%\n\nSecond row: 20%")],
                ),
            ),
            patch(
                "backend.services.chunk_inspector.chunk_text",
                return_value=["First row: 10%", "Second row: 20%"],
            ),
            patch("backend.services.chunk_inspector.get_persisted_collection", return_value=collection),
        ):
            report = inspect_document_chunks(document_id="doc-a", user_id="user-a")

        self.assertEqual([chunk["id"] for chunk in report["chunks"]], ["doc-a:chunk:0", "doc-a:chunk:1"])
        self.assertEqual(report["chunks"][0]["text"], "First row: 10%")
        self.assertEqual(report["chunks"][0]["metadata"]["chunk_index"], 0)
        self.assertTrue(report["chunks"][0]["matches_current_chunking"])

    def test_missing_page_metadata_is_explicit_and_page_ranges_are_derived(self):
        collection = self._collection(
            ["doc-a:chunk:0"],
            ["Column A\nValue 10"],
            [{"chunk_id": "doc-a:chunk:0", "chunk_index": 0}],
        )

        with (
            patch("backend.services.chunk_inspector.require_user_document", return_value=self.document),
            patch("backend.services.chunk_inspector.download_storage_object", return_value=b"pdf"),
            patch(
                "backend.services.chunk_inspector._source_pages",
                return_value=(
                    "pdf",
                    ["Column A\nValue 10", "Column B\nValue 20"],
                    [(1, "Column A\nValue 10"), (2, "Column B\nValue 20")],
                ),
            ),
            patch("backend.services.chunk_inspector.chunk_text", return_value=["Column A\nValue 10"]),
            patch("backend.services.chunk_inspector.get_persisted_collection", return_value=collection),
        ):
            report = inspect_document_chunks(document_id="doc-a", user_id="user-a")

        self.assertEqual(report["chunks"][0]["page_start"], 1)
        self.assertEqual(report["chunks"][0]["page_end"], 1)
        self.assertTrue(any("no stored page locations" in warning for warning in report["warnings"]))

    def test_empty_pdf_pages_do_not_renumber_derived_locations(self):
        collection = self._collection(
            ["doc-a:chunk:0"],
            ["Page two content"],
            [{"chunk_id": "doc-a:chunk:0", "chunk_index": 0}],
        )

        with (
            patch("backend.services.chunk_inspector.require_user_document", return_value=self.document),
            patch("backend.services.chunk_inspector.download_storage_object", return_value=b"pdf"),
            patch(
                "backend.services.chunk_inspector._source_pages",
                return_value=("pdf", ["", "Page two content"], [(2, "Page two content")]),
            ),
            patch("backend.services.chunk_inspector.chunk_text", return_value=["Page two content"]),
            patch("backend.services.chunk_inspector.get_persisted_collection", return_value=collection),
        ):
            report = inspect_document_chunks(document_id="doc-a", user_id="user-a")

        self.assertEqual(report["source"]["pages"][0]["page_number"], 1)
        self.assertEqual(report["source"]["pages"][1]["page_number"], 2)
        self.assertEqual(report["chunks"][0]["page_start"], 2)
        self.assertEqual(report["chunks"][0]["page_end"], 2)

    def test_empty_extraction_is_reported_without_reindexing(self):
        collection = self._collection([], [], [])
        with (
            patch("backend.services.chunk_inspector.require_user_document", return_value=self.document),
            patch("backend.services.chunk_inspector.download_storage_object", return_value=b"pdf"),
            patch("backend.services.chunk_inspector._source_pages", return_value=("pdf", [""], [])),
            patch("backend.services.chunk_inspector.chunk_text", return_value=[]),
            patch("backend.services.chunk_inspector.get_persisted_collection", return_value=collection),
            patch("backend.services.document_lifecycle.build_vector_store") as build_vector_store,
        ):
            report = inspect_document_chunks(document_id="doc-a", user_id="user-a")

        self.assertEqual(report["source"]["extracted_text"], "")
        self.assertTrue(any("returned no text" in warning for warning in report["warnings"]))
        build_vector_store.assert_not_called()

    def test_failed_extraction_is_reported_without_exposing_exception_details(self):
        with (
            patch("backend.services.chunk_inspector.require_user_document", return_value=self.document),
            patch("backend.services.chunk_inspector.download_storage_object", return_value=b"pdf"),
            patch("backend.services.chunk_inspector._source_pages", side_effect=ValueError("secret parser detail")),
        ):
            report = inspect_document_chunks(document_id="doc-a", user_id="user-a")

        self.assertEqual(report["status"], "failed")
        self.assertIn("could not be extracted", report["warnings"][0])
        self.assertNotIn("secret parser detail", str(report))

    def test_inspection_does_not_construct_embeddings_or_call_indexing(self):
        collection = self._collection(
            ["doc-a:chunk:0"],
            ["Revenue: $10 million"],
            [{"chunk_id": "doc-a:chunk:0", "chunk_index": 0}],
        )
        with (
            patch("backend.services.chunk_inspector.require_user_document", return_value=self.document),
            patch("backend.services.chunk_inspector.download_storage_object", return_value=b"pdf"),
            patch(
                "backend.services.chunk_inspector._source_pages",
                return_value=("pdf", ["Revenue: $10 million"], [(1, "Revenue: $10 million")]),
            ),
            patch("backend.services.chunk_inspector.chunk_text", return_value=["Revenue: $10 million"]),
            patch("backend.services.chunk_inspector.get_persisted_collection", return_value=collection),
            patch("backend.services.document_lifecycle.build_vector_store") as build_vector_store,
            patch("backend.services.embedder.get_embedding_model") as get_embedding_model,
        ):
            inspect_document_chunks(document_id="doc-a", user_id="user-a")

        build_vector_store.assert_not_called()
        get_embedding_model.assert_not_called()


if __name__ == "__main__":
    unittest.main()
