import json
import unittest
from contextlib import redirect_stdout
from io import StringIO
from unittest.mock import patch

from backend.scripts.evaluate_answers import evaluate_cases, main
from backend.services import rag_pipeline
from backend.services.rag_pipeline import INSUFFICIENT_CONTEXT_ANSWER, AnswerDecision


class AnswerEvaluatorTestCase(unittest.TestCase):
    def test_reports_fallback_reason_and_gold_context_for_each_limit(self):
        shown_chunks = {
            4: ["doc:chunk:95", "doc:chunk:1"],
            8: ["doc:chunk:95", "doc:chunk:1", "doc:chunk:93"],
        }

        def fake_answer(document_id, question, limit):
            rag_pipeline.logger.info(
                json.dumps(
                    {
                        "event": "answer_policy_decision",
                        "fallback_reason_code": "answer_not_grounded",
                        "retrieved_chunk_ids": shown_chunks[limit],
                        "retrieved_context_char_count": 1000 * limit,
                        "answer_model_called": True,
                    }
                )
            )
            return AnswerDecision(
                answer=INSUFFICIENT_CONTEXT_ANSWER,
                intent="qa",
                retrieval_mode="semantic",
                answer_status="insufficient_context",
                citations=[],
            )

        report = evaluate_cases(
            [
                {
                    "case_id": "amazon",
                    "document_id": "doc",
                    "question": "What is DPO?",
                    "expected_answer": "93.86",
                    "gold_chunk_ids": ["doc:chunk:93", "doc:chunk:95"],
                }
            ],
            answer_fn=fake_answer,
            limits=[8, 4],
        )

        results = report["cases"][0]["results"]
        self.assertEqual(results["limit_4"]["gold_chunk_ids_in_context"], ["doc:chunk:95"])
        self.assertFalse(results["limit_4"]["all_gold_in_context"])
        self.assertTrue(results["limit_8"]["all_gold_in_context"])
        self.assertEqual(results["limit_8"]["fallback_reason_code"], "answer_not_grounded")
        self.assertEqual(report["summary"]["limit_8"]["answered_count"], 0)
        self.assertEqual(report["summary"]["limit_8"]["all_gold_in_context_count"], 1)
        self.assertEqual(report["summary"]["limit_4"]["mean_context_char_count"], 4000)

    def test_quality_gate_fallback_keeps_retrieved_evidence_separate(self):
        def fake_answer(document_id, question, limit):
            rag_pipeline.logger.info(json.dumps({
                "event": "answer_policy_decision",
                "fallback_reason_code": "retrieval_quality_gate_failed",
                "retrieved_chunk_ids": ["gold"],
                "retrieved_context_char_count": 100,
                "answer_model_called": False,
            }))
            return AnswerDecision(
                answer=INSUFFICIENT_CONTEXT_ANSWER, intent="qa", retrieval_mode="semantic",
                answer_status="insufficient_context", citations=[],
            )

        report = evaluate_cases(
            [{"document_id": "doc", "question": "Why?", "gold_chunk_ids": ["gold"]}],
            answer_fn=fake_answer, limits=[4],
        )
        run = report["cases"][0]["results"]["limit_4"]
        self.assertEqual(run["retrieved_chunk_ids"], ["gold"])
        self.assertEqual(run["context_chunk_ids"], [])
        self.assertFalse(run["all_gold_in_context"])
        self.assertEqual(run["context_char_count"], 0)

    def test_missing_gold_labels_are_invalid(self):
        report = evaluate_cases(
            [{"document_id": "doc", "question": "Why?"}],
            answer_fn=lambda *_: self.fail("invalid case must not run"), limits=[4],
        )
        self.assertEqual(report["cases"][0]["status"], "invalid")

    def test_cli_fails_when_answer_runs_fail(self):
        with patch("backend.scripts.evaluate_answers.initialize_backend_environment"), \
             patch("backend.scripts.evaluate_answers._load_cases", return_value=[
                 {"document_id": "doc", "question": "Why?", "gold_chunk_ids": ["gold"]}
             ]), \
             patch("backend.scripts.evaluate_answers.rag_pipeline.answer_question", side_effect=RuntimeError):
            with redirect_stdout(StringIO()):
                self.assertEqual(main(["--cases", "ignored", "--limits", "4"]), 1)


if __name__ == "__main__":
    unittest.main()
