import unittest
from unittest.mock import Mock, patch

from backend.services.chunk_labels import DocumentLabels
from backend.services.vector_store import build_vector_store


class VectorStoreTestCase(unittest.TestCase):
    def test_build_vector_store_embeds_labelled_text_but_stores_original_chunks(self):
        embeddings = Mock()
        embeddings.embed_documents.return_value = [[0.1], [0.2]]
        collection = Mock()
        collection.count.return_value = 2
        client = Mock()
        client.create_collection.return_value = collection

        with (
            patch("backend.services.vector_store.get_embedding_model", return_value=embeddings),
            patch("backend.services.vector_store.chromadb.PersistentClient", return_value=client),
        ):
            stored_count = build_vector_store(
                "doc-1",
                ["alpha", "beta"],
                label_fn=lambda chunks: DocumentLabels(title="Acme 10-K", labels=["Balance sheet", ""]),
            )

        self.assertEqual(stored_count, 2)
        embeddings.embed_documents.assert_called_once_with(
            ["Acme 10-K\nBalance sheet\n\nalpha", "Acme 10-K\n\nbeta"]
        )
        added = collection.add.call_args.kwargs
        self.assertEqual(added["ids"], ["doc-1:chunk:0", "doc-1:chunk:1"])
        self.assertEqual(added["documents"], ["alpha", "beta"])
        self.assertEqual(
            added["metadatas"],
            [
                {"chunk_id": "doc-1:chunk:0", "chunk_index": 0, "label": "Balance sheet"},
                {"chunk_id": "doc-1:chunk:1", "chunk_index": 1, "label": ""},
            ],
        )


if __name__ == "__main__":
    unittest.main()
