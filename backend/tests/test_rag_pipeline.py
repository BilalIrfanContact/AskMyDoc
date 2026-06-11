import unittest
from types import SimpleNamespace
from unittest.mock import Mock, patch

from backend.services.rag_pipeline import (
    AnswerCitation,
    INSUFFICIENT_CONTEXT_ANSWER,
    _route_intent,
    _select_retrieval_policy,
    answer_question,
)


class RagPipelineTestCase(unittest.TestCase):
    def _build_vector_store(self, *, count: int = 4, docs=None, head_documents=None):
        vectordb = Mock()
        vectordb._collection.count.return_value = count
        vectordb.similarity_search.return_value = docs or []
        vectordb.get.return_value = {"documents": head_documents or []}
        return vectordb

    def test_answer_question_uses_llm_for_grounded_retrieval(self):
        vectordb = self._build_vector_store(
            docs=[
                SimpleNamespace(
                    page_content="The refund window is 30 days from the purchase date.",
                    metadata={"chunk_id": "doc-1:chunk:0"},
                )
            ]
        )
        llm = Mock()
        llm.invoke.return_value = SimpleNamespace(content="The refund window is 30 days.")

        with (
            patch("backend.services.rag_pipeline.get_vector_store", return_value=vectordb),
            patch("backend.services.rag_pipeline.ChatOpenAI", return_value=llm) as chat_openai_mock,
        ):
            answer = answer_question("doc-1", "What is the refund window?")

        self.assertEqual(answer.answer, "The refund window is 30 days.")
        self.assertEqual(answer.intent, "qa")
        self.assertEqual(answer.retrieval_mode, "semantic")
        self.assertEqual(answer.answer_status, "answered")
        self.assertEqual(
            answer.citations,
            [
                AnswerCitation(
                    chunk_id="doc-1:chunk:0",
                    excerpt="The refund window is 30 days from the purchase date.",
                )
            ],
        )
        vectordb.similarity_search.assert_called_once_with("What is the refund window?", k=4)
        chat_openai_mock.assert_called_once()
        llm.invoke.assert_called_once()

    def test_qa_questions_route_to_semantic_retrieval_policy(self):
        policy = _select_retrieval_policy("What is the refund window?", total_chunks=12)

        self.assertEqual(policy.intent, "qa")
        self.assertEqual(policy.mode, "semantic")
        self.assertEqual(policy.limit, 4)
        self.assertTrue(policy.enforce_quality_gate)

    def test_summary_questions_route_to_head_retrieval_policy(self):
        policy = _select_retrieval_policy("What is this document about?", total_chunks=12)

        self.assertEqual(policy.intent, "summary")
        self.assertEqual(policy.mode, "head")
        self.assertEqual(policy.limit, 8)
        self.assertFalse(policy.enforce_quality_gate)

    def test_route_intent_treats_main_points_as_summary(self):
        self.assertEqual(_route_intent("What are the main points of this PDF?"), "summary")

    def test_answer_question_returns_deterministic_fallback_for_low_evidence_retrieval(self):
        vectordb = self._build_vector_store(
            docs=[
                SimpleNamespace(
                    page_content="The onboarding checklist covers payroll setup and laptop pickup.",
                    metadata={"chunk_id": "doc-1:chunk:3"},
                )
            ]
        )

        with (
            patch("backend.services.rag_pipeline.get_vector_store", return_value=vectordb),
            patch("backend.services.rag_pipeline.ChatOpenAI") as chat_openai_mock,
        ):
            answer = answer_question("doc-1", "What is the refund window?")

        self.assertEqual(answer.answer, INSUFFICIENT_CONTEXT_ANSWER)
        self.assertEqual(answer.intent, "qa")
        self.assertEqual(answer.retrieval_mode, "semantic")
        self.assertEqual(answer.answer_status, "insufficient_context")
        self.assertEqual(answer.citations, [])
        chat_openai_mock.assert_not_called()

    def test_answer_question_returns_deterministic_fallback_when_retrieval_is_empty(self):
        vectordb = self._build_vector_store(docs=[])

        with (
            patch("backend.services.rag_pipeline.get_vector_store", return_value=vectordb),
            patch("backend.services.rag_pipeline.ChatOpenAI") as chat_openai_mock,
        ):
            answer = answer_question("doc-1", "What is the refund window?")

        self.assertEqual(answer.answer, INSUFFICIENT_CONTEXT_ANSWER)
        self.assertEqual(answer.intent, "qa")
        self.assertEqual(answer.retrieval_mode, "semantic")
        self.assertEqual(answer.answer_status, "insufficient_context")
        self.assertEqual(answer.citations, [])
        chat_openai_mock.assert_not_called()

    def test_answer_question_returns_fallback_when_semantic_retrieval_has_no_chunk_ids(self):
        vectordb = self._build_vector_store(
            docs=[
                SimpleNamespace(
                    page_content="The refund window is 30 days from the purchase date.",
                    metadata={},
                )
            ]
        )

        with (
            patch("backend.services.rag_pipeline.get_vector_store", return_value=vectordb),
            patch("backend.services.rag_pipeline.ChatOpenAI") as chat_openai_mock,
        ):
            answer = answer_question("doc-1", "What is the refund window?")

        self.assertEqual(answer.answer, INSUFFICIENT_CONTEXT_ANSWER)
        self.assertEqual(answer.answer_status, "insufficient_context")
        self.assertEqual(answer.citations, [])
        chat_openai_mock.assert_not_called()

    def test_summary_questions_still_use_head_context(self):
        vectordb = self._build_vector_store(
            docs=[],
            head_documents=["This handbook explains the benefits policy and time-off rules."],
        )
        vectordb.get.return_value = {
            "documents": ["This handbook explains the benefits policy and time-off rules."],
            "metadatas": [{"chunk_id": "doc-1:chunk:0"}],
        }
        llm = Mock()
        llm.invoke.return_value = SimpleNamespace(content="It explains benefits and time off.")

        with (
            patch("backend.services.rag_pipeline.get_vector_store", return_value=vectordb),
            patch("backend.services.rag_pipeline.ChatOpenAI", return_value=llm),
        ):
            answer = answer_question("doc-1", "Summarize this document.")

        self.assertEqual(answer.answer, "It explains benefits and time off.")
        self.assertEqual(answer.intent, "summary")
        self.assertEqual(answer.retrieval_mode, "head")
        self.assertEqual(answer.answer_status, "answered")
        self.assertEqual(len(answer.citations), 1)
        self.assertEqual(answer.citations[0].chunk_id, "doc-1:chunk:0")
        vectordb.similarity_search.assert_not_called()
        vectordb.get.assert_called_once_with(limit=4, include=["documents", "metadatas"])

    def test_summary_questions_return_fallback_when_head_context_has_no_chunk_ids(self):
        vectordb = self._build_vector_store(
            docs=[],
            head_documents=["This handbook explains the benefits policy and time-off rules."],
        )
        vectordb.get.return_value = {
            "documents": ["This handbook explains the benefits policy and time-off rules."],
            "metadatas": [{}],
        }

        with (
            patch("backend.services.rag_pipeline.get_vector_store", return_value=vectordb),
            patch("backend.services.rag_pipeline.ChatOpenAI") as chat_openai_mock,
        ):
            answer = answer_question("doc-1", "Summarize this document.")

        self.assertEqual(answer.answer, INSUFFICIENT_CONTEXT_ANSWER)
        self.assertEqual(answer.intent, "summary")
        self.assertEqual(answer.retrieval_mode, "head")
        self.assertEqual(answer.answer_status, "insufficient_context")
        self.assertEqual(answer.citations, [])
        chat_openai_mock.assert_not_called()

    def test_qa_questions_do_not_fall_back_to_head_context(self):
        vectordb = self._build_vector_store(
            docs=[],
            head_documents=["The refund window is 30 days from the purchase date."],
        )

        with (
            patch("backend.services.rag_pipeline.get_vector_store", return_value=vectordb),
            patch("backend.services.rag_pipeline.ChatOpenAI") as chat_openai_mock,
        ):
            answer = answer_question("doc-1", "What is the refund window?")

        self.assertEqual(answer.answer, INSUFFICIENT_CONTEXT_ANSWER)
        self.assertEqual(answer.intent, "qa")
        self.assertEqual(answer.retrieval_mode, "semantic")
        self.assertEqual(answer.answer_status, "insufficient_context")
        self.assertEqual(answer.citations, [])
        vectordb.similarity_search.assert_called_once_with("What is the refund window?", k=4)
        vectordb.get.assert_not_called()
        chat_openai_mock.assert_not_called()


if __name__ == "__main__":
    unittest.main()
