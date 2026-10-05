import unittest
from types import SimpleNamespace
from unittest.mock import Mock

from backend.services.evidence_reranker import Candidate, pick_evidence
from backend.services.rag_adapters import ChromaRetrievalAdapter


def _generator(reply):
    generator = Mock()
    generator.invoke.return_value = SimpleNamespace(content=reply)
    return generator


CANDIDATES = [Candidate(label=f"label {index}", text=f"text {index}") for index in range(5)]


class PickEvidenceTestCase(unittest.TestCase):
    def test_keeps_the_models_order_without_duplicates_or_unknown_ids(self):
        picked = pick_evidence("q", CANDIDATES, 4, _generator("3, 1, 3, 17, 0"))

        self.assertEqual(picked, [3, 1, 0])

    def test_never_returns_more_than_the_limit(self):
        self.assertEqual(pick_evidence("q", CANDIDATES, 2, _generator("4, 3, 2")), [4, 3])

    def test_an_unusable_reply_picks_nothing(self):
        self.assertEqual(pick_evidence("q", CANDIDATES, 4, _generator("none of these")), [])
        self.assertEqual(pick_evidence("q", CANDIDATES, 4, _generator("3, 1 (passage 2 only covers 2021)")), [])


class RerankedRetrievalTestCase(unittest.TestCase):
    def _vectordb(self):
        ids = [f"doc:chunk:{index}" for index in range(5)]
        vectordb = Mock()
        vectordb.embeddings.embed_query.return_value = [0.1]
        vectordb._collection.query.return_value = {
            "documents": [[f"text {index}" for index in range(5)]],
            "metadatas": [[{"chunk_id": chunk_id} for chunk_id in ids]],
            "ids": [ids],
        }
        vectordb._collection.get.return_value = {
            "ids": ids,
            "metadatas": [{"chunk_id": chunk_id, "label": f"label {index}"} for index, chunk_id in enumerate(ids)],
        }
        return vectordb

    def test_returns_only_the_chunks_the_model_picked(self):
        generator = _generator("4, 2")
        adapter = ChromaRetrievalAdapter(self._vectordb(), reranker=generator)

        context = adapter.retrieve("semantic", "What were total assets?", 3)

        self.assertEqual([citation.chunk_id for citation in context.citations], ["doc:chunk:4", "doc:chunk:2"])
        self.assertEqual(context.text, "text 4\n\ntext 2")
        self.assertIn("[4] label 4", generator.invoke.call_args.args[0])

    def test_falls_back_to_embedding_order_when_the_model_reply_is_unusable(self):
        adapter = ChromaRetrievalAdapter(self._vectordb(), reranker=_generator("sorry"))

        context = adapter.retrieve("semantic", "What were total assets?", 3)

        self.assertEqual(
            [citation.chunk_id for citation in context.citations],
            ["doc:chunk:0", "doc:chunk:1", "doc:chunk:2"],
        )


if __name__ == "__main__":
    unittest.main()
