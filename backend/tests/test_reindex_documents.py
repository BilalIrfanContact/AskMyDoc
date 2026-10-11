import unittest
from unittest.mock import Mock, patch

from backend.scripts.reindex_documents import reindex_document
from backend.services.vector_store import IndexPayload, open_index, write_index_payload
from backend.tests.fake_supabase import FakeSupabase


class ReembedTestCase(unittest.TestCase):
    def test_reembedding_keeps_existing_metadata_and_records_the_current_model(self):
        metadatas = [
            {"chunk_id": "doc:chunk:0", "chunk_index": 0, "label": "Balance sheet", "document_title": "Acme 10-K"},
            {"chunk_id": "doc:chunk:1", "chunk_index": 1},
        ]
        database = FakeSupabase()
        embeddings = Mock()
        embeddings.embed_documents.return_value = [[1.0, 0.0], [0.0, 1.0]]
        with (
            patch("backend.services.vector_store.get_postgrest_client", return_value=database),
            patch("backend.services.vector_store.embedding_model_name", return_value="test-embedding-model"),
            patch("backend.services.vector_store.get_embedding_model", return_value=embeddings),
        ):
            write_index_payload(
                "doc",
                IndexPayload(
                    ids=["doc:chunk:0", "doc:chunk:1"],
                    documents=["text 0", "text 1"],
                    embeddings=[[0.5, 0.5], [0.5, 0.5]],
                    metadatas=metadatas,
                ),
                embedding_model="old-model",
            )
            outcome = reindex_document("doc")
            store = open_index("doc")
            stored = store.get(include=["documents", "metadatas"])

        self.assertEqual(outcome, "reembedded")
        embeddings.embed_documents.assert_called_once_with(["text 0", "text 1"])
        self.assertEqual(stored["ids"], ["doc:chunk:0", "doc:chunk:1"])
        self.assertEqual(stored["documents"], ["text 0", "text 1"])
        self.assertEqual(stored["metadatas"], metadatas)
        self.assertEqual(
            [row["embedding"] for row in database.tables["document_chunks"]], [[1.0, 0.0], [0.0, 1.0]]
        )
        self.assertEqual(store.metadata["embedding_model"], "test-embedding-model")


if __name__ == "__main__":
    unittest.main()
