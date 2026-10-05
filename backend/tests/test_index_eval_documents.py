import hashlib
import tempfile
import unittest
from contextlib import redirect_stderr
from io import StringIO
from pathlib import Path

from backend.scripts.index_eval_documents import index_documents


class IndexEvalDocumentsTestCase(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)

    def _pdf(self, name: str, content: bytes) -> str:
        path = Path(self.tmp.name) / name
        path.write_bytes(content)
        return str(path)

    def _run(self, paths, manifest, **kwargs):
        with redirect_stderr(StringIO()):
            return index_documents(paths, manifest, **kwargs)

    def test_indexes_new_pdfs_and_skips_ones_already_in_the_manifest(self):
        known = self._pdf("known.pdf", b"known")
        new = self._pdf("new.pdf", b"new")
        manifest = {"documents": [{"path": known, "sha256": hashlib.sha256(b"known").hexdigest(), "document_id": "doc-known"}]}
        indexed = []
        saves = []

        def fake_index(data):
            indexed.append(data)
            return {"document_id": "doc-new", "chunk_count": 3, "stored_count": 3}

        failures = self._run([known, new], manifest, index_fn=fake_index, count_fn=lambda document_id: 197, save=saves.append)

        self.assertEqual(failures, [])
        self.assertEqual(indexed, [b"new"])
        self.assertEqual(len(saves), 1)
        self.assertEqual(manifest["documents"][1]["document_id"], "doc-new")
        self.assertEqual(manifest["documents"][1]["origin"], "indexed")

    def test_a_manifest_entry_whose_collection_is_gone_is_indexed_again(self):
        path = self._pdf("amazon.pdf", b"amazon")
        manifest = {"documents": [{"path": path, "sha256": hashlib.sha256(b"amazon").hexdigest(), "document_id": "doc-cleared"}]}

        self._run(
            [path],
            manifest,
            index_fn=lambda data: {"document_id": "doc-new", "chunk_count": 3, "stored_count": 3},
            count_fn=lambda document_id: 0,
        )

        self.assertEqual([entry["document_id"] for entry in manifest["documents"]], ["doc-new"])

    def test_a_failed_collection_check_fails_only_that_pdf(self):
        first = self._pdf("first.pdf", b"first")
        second = self._pdf("second.pdf", b"second")
        manifest = {"documents": [{"path": first, "sha256": hashlib.sha256(b"first").hexdigest(), "document_id": "doc-first"}]}

        def count(document_id):
            raise RuntimeError("database is locked")

        failures = self._run(
            [first, second],
            manifest,
            index_fn=lambda data: {"document_id": "doc-second", "chunk_count": 3, "stored_count": 3},
            count_fn=count,
        )

        self.assertEqual([failure["path"] for failure in failures], [first])
        self.assertEqual([entry["document_id"] for entry in manifest["documents"]], ["doc-first", "doc-second"])

    def test_records_failures_without_adding_them_to_the_manifest(self):
        broken = self._pdf("broken.pdf", b"broken")
        manifest = {}

        def failing_index(data):
            raise ValueError("chunks were created but none were stored")

        failures = self._run([broken], manifest, index_fn=failing_index)

        self.assertEqual([failure["path"] for failure in failures], [broken])
        self.assertEqual(manifest["documents"], [])


if __name__ == "__main__":
    unittest.main()
