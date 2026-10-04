import tempfile
import unittest
from unittest.mock import Mock, patch

from backend.scripts.reindex_documents import reindex_document
from backend.services.vector_store import IndexPayload, get_persisted_collection, write_index_payload


class ReembedTestCase(unittest.TestCase):
    def test_reembedding_keeps_existing_metadata_and_replaces_the_collection(self):
        metadatas = [
            {"chunk_id": "doc:chunk:0", "chunk_index": 0, "label": "Balance sheet", "document_title": "Acme 10-K"},
            {"chunk_id": "doc:chunk:1", "chunk_index": 1},
        ]
        embeddings = Mock()
        embeddings.embed_documents.return_value = [[1.0, 0.0], [0.0, 1.0]]
        with (
            tempfile.TemporaryDirectory() as store,
            patch("backend.services.vector_store.PERSIST_DIRECTORY", store),
            patch("backend.services.vector_store.embedding_model_name", return_value="test-embedding-model"),
            patch("backend.services.vector_store.get_embedding_model", return_value=embeddings),
        ):
            write_index_payload(
                "doc",
                IndexPayload(
                    ids=["doc:chunk:1", "doc:chunk:0"],
                    documents=["text 1", "text 0"],
                    embeddings=[[0.5, 0.5], [0.5, 0.5]],
                    metadatas=list(reversed(metadatas)),
                ),
            )
            outcome = reindex_document("doc")
            collection = get_persisted_collection("doc")
            stored = collection.get(include=["documents", "metadatas", "embeddings"])

        self.assertEqual(outcome, "reembedded")
        embeddings.embed_documents.assert_called_once_with(["text 0", "text 1"])
        self.assertEqual(stored["ids"], ["doc:chunk:0", "doc:chunk:1"])
        self.assertEqual(stored["documents"], ["text 0", "text 1"])
        self.assertEqual(stored["metadatas"], metadatas)
        self.assertEqual([list(vector) for vector in stored["embeddings"]], [[1.0, 0.0], [0.0, 1.0]])
        self.assertEqual(collection.metadata["embedding_model"], "test-embedding-model")


if __name__ == "__main__":
    unittest.main()
