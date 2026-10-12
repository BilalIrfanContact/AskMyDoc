import unittest
from unittest.mock import Mock, patch

from backend.services.vector_store import (
    IndexPayload,
    MissingIndex,
    StaleEmbeddings,
    build_vector_store,
    delete_vector_store,
    get_vector_store,
    list_document_ids,
    open_index,
    write_index_payload,
)
from backend.tests.fake_supabase import FakeSupabase


def _payload(document_id: str, texts: list[str], vectors: list[list[float]]) -> IndexPayload:
    ids = [f"{document_id}:chunk:{index}" for index in range(len(texts))]
    return IndexPayload(
        ids=ids,
        documents=texts,
        embeddings=vectors,
        metadatas=[{"chunk_id": chunk_id, "chunk_index": index} for index, chunk_id in enumerate(ids)],
    )


class VectorStoreTestCase(unittest.TestCase):
    def setUp(self):
        self.database = FakeSupabase()
        self.embeddings = Mock()
        for target, value in [
            ("get_postgrest_client", self.database),
            ("get_embedding_model", self.embeddings),
            ("embedding_model_name", "test-model"),
        ]:
            patcher = patch(f"backend.services.vector_store.{target}", return_value=value)
            patcher.start()
            self.addCleanup(patcher.stop)

    def test_built_document_is_searchable_nearest_first_in_chroma_shape(self):
        self.embeddings.embed_documents.return_value = [[1.0, 0.0], [0.0, 1.0], [0.7, 0.7]]

        stored = build_vector_store("doc", ["revenue", "risk factors", "both"])
        store = get_vector_store("doc")
        found = store.query(query_embeddings=[[0.0, 1.0]], n_results=2, include=["documents", "metadatas"])

        self.assertEqual(stored, 3)
        self.embeddings.embed_documents.assert_called_once_with(["revenue", "risk factors", "both"])
        self.assertEqual(store.count(), 3)
        self.assertIs(store.embeddings, self.embeddings)
        self.assertEqual(found["ids"], [["doc:chunk:1", "doc:chunk:2"]])
        self.assertEqual(found["documents"], [["risk factors", "both"]])
        self.assertEqual(found["metadatas"][0][0], {"chunk_id": "doc:chunk:1", "chunk_index": 1})

    def test_building_reports_each_embedding_request_and_chunk_insert(self):
        self.embeddings.embed_documents.side_effect = lambda texts: [[1.0]] * len(texts)
        progress = []

        with patch("backend.services.vector_store.EMBED_BATCH_SIZE", 2), patch("backend.services.vector_store.INSERT_BATCH_SIZE", 3):
            build_vector_store("doc", ["a", "b", "c", "d", "e"],
                on_embed=lambda done, total: progress.append(("embed", done, total)),
                on_save=lambda done, total: progress.append(("save", done, total)))

        self.assertEqual(progress, [("embed", 1, 3), ("embed", 2, 3), ("embed", 3, 3), ("save", 1, 2), ("save", 2, 2)])

    def test_nul_characters_from_pdf_extraction_are_dropped_before_storing(self):
        write_index_payload("doc", _payload("doc", ["Total\x00 revenue"], [[1.0]]))

        self.assertEqual(open_index("doc").get()["documents"], ["Total revenue"])

    def test_failed_reindex_keeps_the_old_chunks_and_removes_the_new_ones(self):
        write_index_payload("doc", _payload("doc", ["old"], [[1.0, 0.0]]))
        self.database.fail_commit = True

        with self.assertRaises(RuntimeError):
            write_index_payload("doc", _payload("doc", ["new 0", "new 1"], [[0.0, 1.0], [1.0, 1.0]]))

        # The uncommitted rows stay until the next write, but reads only see the committed generation.
        self.assertEqual(open_index("doc").get()["documents"], ["old"])

        self.database.fail_commit = False
        write_index_payload("doc", _payload("doc", ["new 0", "new 1"], [[0.0, 1.0], [1.0, 1.0]]))
        self.assertEqual(open_index("doc").get()["documents"], ["new 0", "new 1"])
        self.assertEqual(len(self.database.tables["document_chunks"]), 2)

    def test_a_commit_whose_reply_is_lost_keeps_the_new_chunks(self):
        write_index_payload("doc", _payload("doc", ["old"], [[1.0, 0.0]]))
        self.database.lose_commit_reply = True

        stored = write_index_payload("doc", _payload("doc", ["new 0", "new 1"], [[0.0, 1.0], [1.0, 1.0]]))

        self.assertEqual(stored, 2)
        self.assertEqual(open_index("doc").get()["documents"], ["new 0", "new 1"])

    def test_a_failed_chunk_insert_removes_what_it_wrote(self):
        self.database.failed_writes = 1

        with self.assertRaises(ConnectionError):
            write_index_payload("doc", _payload("doc", ["a"], [[1.0]]))

        self.assertEqual(self.database.tables["document_chunks"], [])

    def test_reads_page_past_the_api_row_cap_and_honor_ids_and_limit(self):
        texts = [f"chunk {index}" for index in range(5)]
        write_index_payload("doc", _payload("doc", texts, [[1.0, float(index)] for index in range(5)]))
        store = open_index("doc")

        with patch("backend.services.vector_store.PAGE_SIZE", 2):
            self.assertEqual(store.get()["documents"], texts)
            self.assertEqual(store.get(limit=3)["documents"], texts[:3])
            self.assertEqual(store.get(ids=["doc:chunk:4", "doc:chunk:1"])["ids"], ["doc:chunk:1", "doc:chunk:4"])
            self.assertEqual(store.get(ids=[]), {"ids": [], "documents": [], "metadatas": []})

    def test_search_refuses_documents_embedded_with_another_model_or_not_indexed(self):
        write_index_payload("old", _payload("old", ["text"], [[1.0]]), embedding_model="voyage-3")

        with self.assertRaises(StaleEmbeddings):
            get_vector_store("old")
        with self.assertRaises(MissingIndex):
            get_vector_store("never-indexed")

    def test_deleting_removes_the_index_and_its_chunks(self):
        write_index_payload("keep", _payload("keep", ["a"], [[1.0]]))
        write_index_payload("drop", _payload("drop", ["b", "c"], [[1.0], [0.5]]))

        delete_vector_store("drop")
        delete_vector_store("never-indexed")

        self.assertEqual(list_document_ids(), ["keep"])
        self.assertEqual({row["document_id"] for row in self.database.tables["document_chunks"]}, {"keep"})


if __name__ == "__main__":
    unittest.main()
