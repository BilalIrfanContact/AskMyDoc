import unittest
from unittest.mock import Mock, patch

from backend.services.vector_store import build_vector_store


class VectorStoreTestCase(unittest.TestCase):
    def test_build_vector_store_persists_chunk_ids_in_metadata(self):
        vectordb = Mock()
        vectordb._collection.count.return_value = 2

        with (
            patch("backend.services.vector_store.get_embedding_model", return_value=Mock()),
            patch("backend.services.vector_store.Chroma.from_texts", return_value=vectordb) as from_texts_mock,
        ):
            stored_count = build_vector_store("doc-1", ["alpha", "beta"])

        self.assertEqual(stored_count, 2)
        from_texts_mock.assert_called_once()
        self.assertEqual(
            from_texts_mock.call_args.kwargs["ids"],
            ["doc-1:chunk:0", "doc-1:chunk:1"],
        )
        self.assertEqual(
            from_texts_mock.call_args.kwargs["metadatas"],
            [
                {"chunk_id": "doc-1:chunk:0", "chunk_index": 0},
                {"chunk_id": "doc-1:chunk:1", "chunk_index": 1},
            ],
        )


if __name__ == "__main__":
    unittest.main()
