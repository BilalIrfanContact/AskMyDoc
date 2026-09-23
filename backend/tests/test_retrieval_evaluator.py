import unittest
from unittest.mock import Mock

from backend.services.rag_pipeline import AnswerCitation, RetrievedContext
from backend.scripts.evaluate_retrieval import evaluate_cases, evaluate_chunk_ids


class RetrievalEvaluatorTestCase(unittest.TestCase):
    def test_evaluate_chunk_ids_reports_partial_and_complete_evidence(self):
        result = evaluate_chunk_ids(
            ["doc:chunk:9", "doc:chunk:95", "doc:chunk:93"],
            ["doc:chunk:93", "doc:chunk:95"],
            2,
        )

        self.assertEqual(result["gold_chunk_ids_found"], ["doc:chunk:95"])
        self.assertEqual(result["gold_chunk_recall"], 0.5)
        self.assertTrue(result["any_gold_chunk_found"])
        self.assertFalse(result["all_gold_chunks_found"])

    def test_evaluate_cases_uses_one_retrieval_call_for_the_largest_limit(self):
        retriever = Mock()
        retriever.retrieve.return_value = RetrievedContext(
            text="context",
            citations=[
                AnswerCitation(chunk_id="doc:chunk:1", excerpt="one"),
                AnswerCitation(chunk_id="doc:chunk:2", excerpt="two"),
                AnswerCitation(chunk_id="doc:chunk:3", excerpt="three"),
                AnswerCitation(chunk_id="doc:chunk:4", excerpt="four"),
            ],
            retrieved_document_count=4,
        )

        report = evaluate_cases(
            [
                {
                    "case_id": "case-a",
                    "document_id": "doc",
                    "question": "What is the answer?",
                    "gold_chunk_ids": ["doc:chunk:4"],
                }
            ],
            retriever_factory=lambda _: retriever,
            limits=(4, 8),
        )

        retriever.retrieve.assert_called_once_with("semantic", "What is the answer?", 8)
        self.assertTrue(report["cases"][0]["results"]["top_4"]["any_gold_chunk_found"])
        self.assertEqual(report["summary"]["top_8"]["all_gold_chunks_hit_rate"], 1.0)

    def test_evaluate_cases_marks_missing_required_fields_invalid(self):
        report = evaluate_cases(
            [{"case_id": "incomplete", "document_id": "doc"}],
            retriever_factory=Mock(),
        )

        self.assertEqual(report["cases"][0]["status"], "invalid")
        self.assertEqual(report["completed_case_count"], 0)


if __name__ == "__main__":
    unittest.main()
