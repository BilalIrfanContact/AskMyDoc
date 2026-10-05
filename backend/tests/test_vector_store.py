import tempfile
import unittest
from unittest.mock import Mock, patch

import chromadb

from backend.services.chunk_labels import DocumentLabels
from backend.services.vector_store import (
    IndexPayload,
    build_vector_store,
    list_document_ids,
    replace_index_payload,
    write_index_payload,
)


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

    def test_replacing_a_collection_keeps_the_old_one_until_the_new_one_is_written(self):
        old = IndexPayload(ids=["doc-1:chunk:0"], documents=["old"], embeddings=[[1.0, 0.0, 0.0]], metadatas=[{"chunk_index": 0}])
        broken = IndexPayload(ids=["doc-1:chunk:0"], documents=["new"], embeddings=[], metadatas=[{"chunk_index": 0}])
        new = IndexPayload(ids=["doc-1:chunk:0"], documents=["new"], embeddings=[[0.0, 1.0]], metadatas=[{"chunk_index": 0}])

        with tempfile.TemporaryDirectory() as directory, patch("backend.services.vector_store.PERSIST_DIRECTORY", directory):
            write_index_payload("doc-1", old)
            with self.assertRaises(Exception):
                replace_index_payload("doc-1", broken)
            client = chromadb.PersistentClient(path=directory)
            self.assertEqual(client.get_collection("doc-1").get()["documents"], ["old"])
            self.assertEqual([getattr(c, "name", c) for c in client.list_collections()], ["doc-1"])

            real_get = chromadb.api.client.Client.get_collection
            def failing_swap(client, name, *args, **kwargs):
                if name == "doc-1-reindex":
                    raise RuntimeError("rename failed")
                return real_get(client, name, *args, **kwargs)
            with patch.object(chromadb.api.client.Client, "get_collection", failing_swap):
                with self.assertRaises(RuntimeError):
                    replace_index_payload("doc-1", new)
            self.assertEqual(client.get_collection("doc-1").get()["documents"], ["old"])

            self.assertEqual(replace_index_payload("doc-1", new), 1)
            self.assertEqual(client.get_collection("doc-1").get()["documents"], ["new"])
            self.assertEqual([getattr(c, "name", c) for c in client.list_collections()], ["doc-1"])

    def test_a_swap_interrupted_between_its_renames_is_undone_by_the_next_one(self):
        old = IndexPayload(ids=["doc-1:chunk:0"], documents=["old"], embeddings=[[1.0, 0.0]], metadatas=[{"chunk_index": 0}])
        new = IndexPayload(ids=["doc-1:chunk:0"], documents=["new"], embeddings=[[0.0, 1.0]], metadatas=[{"chunk_index": 0}])

        with tempfile.TemporaryDirectory() as directory, patch("backend.services.vector_store.PERSIST_DIRECTORY", directory):
            write_index_payload("doc-1-previous", old)  # The old copy was set aside, then the process stopped.
            self.assertEqual(list_document_ids(), [])

            self.assertEqual(replace_index_payload("doc-1", new), 1)
            client = chromadb.PersistentClient(path=directory)
            self.assertEqual(client.get_collection("doc-1").get()["documents"], ["new"])
            self.assertEqual(list_document_ids(), ["doc-1"])
            self.assertEqual([getattr(c, "name", c) for c in client.list_collections()], ["doc-1"])


if __name__ == "__main__":
    unittest.main()
