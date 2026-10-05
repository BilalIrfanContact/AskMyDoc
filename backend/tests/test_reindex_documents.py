import unittest
from unittest.mock import Mock, patch

from backend.scripts.reindex_documents import reindex_document


def _collection(metadatas):
    collection = Mock()
    collection.get.return_value = {
        "ids": [f"doc:chunk:{index}" for index in range(len(metadatas))],
        "documents": [f"text {index}" for index in range(len(metadatas))],
        "metadatas": metadatas,
    }
    return collection


class ReembedTestCase(unittest.TestCase):
    def _run(self, metadatas, **kwargs):
        with (
            patch("backend.scripts.reindex_documents.get_persisted_collection", return_value=_collection(metadatas)),
            patch("backend.scripts.reindex_documents.prepare_index_payload") as prepare,
            patch("backend.scripts.reindex_documents.replace_index_payload") as replace,
            patch("backend.scripts.reindex_documents.restore_interrupted_swap"),
            patch("backend.scripts.reindex_documents.title_document", return_value="Generated title") as title,
        ):
            outcome = reindex_document("doc", **kwargs)
        return outcome, prepare, replace, title

    def test_reembedding_reuses_stored_labels_and_title(self):
        outcome, prepare, _, title = self._run(
            [{"label": "Balance sheet", "document_title": "Acme 10-K"}, {"label": "Risk factors", "document_title": "Acme 10-K"}],
            reembed=True,
        )

        labels = prepare.call_args.args[2](["text 0", "text 1"])
        self.assertEqual(outcome, "reembedded")
        self.assertEqual((labels.title, labels.labels), ("Acme 10-K", ["Balance sheet", "Risk factors"]))
        title.assert_not_called()

    def test_reembedding_generates_only_a_missing_title(self):
        _, prepare, _, title = self._run([{"label": "Balance sheet"}], reembed=True)

        self.assertEqual(prepare.call_args.args[2](["text 0"]).title, "Generated title")
        title.assert_called_once()

    def test_an_unlabelled_document_is_not_reembedded_or_replaced(self):
        outcome, prepare, replace, _ = self._run([{"chunk_id": "doc:chunk:0"}], reembed=True)

        self.assertEqual(outcome, "skipped")
        prepare.assert_not_called()
        replace.assert_not_called()


if __name__ == "__main__":
    unittest.main()
