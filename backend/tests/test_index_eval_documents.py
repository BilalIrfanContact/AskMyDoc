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
        manifest = {"documents": [{"path": known, "sha256": hashlib.sha256(b"known").hexdigest()}]}
        indexed = []
        saves = []

        def fake_index(data):
            indexed.append(data)
            return {"document_id": "doc-new", "chunk_count": 3, "stored_count": 3}

        failures = self._run([known, new], manifest, index_fn=fake_index, save=saves.append)

        self.assertEqual(failures, [])
        self.assertEqual(indexed, [b"new"])
        self.assertEqual(len(saves), 1)
        self.assertEqual(manifest["documents"][1]["document_id"], "doc-new")
        self.assertEqual(manifest["documents"][1]["origin"], "indexed")

    def test_reuses_an_existing_collection_without_embedding_again(self):
        path = self._pdf("amazon.pdf", b"amazon")
        manifest = {}

        def must_not_index(data):
            raise AssertionError("reused PDFs must not be re-embedded")

        failures = self._run(
            [path],
            manifest,
            reuse={path: "doc-amazon"},
            index_fn=must_not_index,
            count_fn=lambda document_id: 197,
        )

        self.assertEqual(failures, [])
        self.assertEqual(
            manifest["documents"][0],
            {
                "path": path,
                "sha256": hashlib.sha256(b"amazon").hexdigest(),
                "origin": "reused",
                "document_id": "doc-amazon",
                "chunk_count": 197,
                "stored_count": 197,
            },
        )

    def test_records_failures_without_adding_them_to_the_manifest(self):
        empty_reuse = self._pdf("empty.pdf", b"empty")
        broken = self._pdf("broken.pdf", b"broken")
        manifest = {}

        def failing_index(data):
            raise ValueError("chunks were created but none were stored")

        failures = self._run(
            [empty_reuse, broken],
            manifest,
            reuse={empty_reuse: "doc-empty"},
            index_fn=failing_index,
            count_fn=lambda document_id: 0,
        )

        self.assertEqual([failure["path"] for failure in failures], [empty_reuse, broken])
        self.assertEqual(manifest["documents"], [])


if __name__ == "__main__":
    unittest.main()
