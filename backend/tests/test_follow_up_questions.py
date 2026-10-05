"""Follow-up retrieval uses dialogue; answers still require document evidence."""
import unittest
from types import SimpleNamespace
from unittest.mock import Mock

from backend.services.conversation_history import ConversationExchange
from backend.services.rag_pipeline import (
    AnswerCitation, INSUFFICIENT_CONTEXT_ANSWER, RagDependencies, RetrievedContext, answer_question,
)


class FollowUpQuestionTests(unittest.TestCase):
    def dependencies(self, excerpts, responses):
        retriever = Mock()
        retriever.count.return_value = 1
        retriever.retrieve.return_value = RetrievedContext(
            text=excerpts, citations=[AnswerCitation(chunk_id='chunk-1', excerpt=excerpts)] if excerpts else [],
            retrieved_document_count=1 if excerpts else 0,
        )
        generator = Mock()
        generator.invoke.side_effect = [SimpleNamespace(content=content) for content in responses]
        return RagDependencies(retrieval_factory=lambda _: retriever, generation=generator), retriever, generator

    def test_follow_up_searches_the_prior_topic_and_answers_from_current_excerpts(self):
        history = (ConversationExchange(question='How did revenue change in 2025?', answer='Revenue increased.'),)
        evidence = 'Revenue increased because software subscriptions grew.'
        deps, retriever, generator = self.dependencies(evidence, [
            '{"intent":"qa","question":"Why did revenue increase in 2025?"}',
            '{"found_in_excerpts":true,"answer":"Revenue increased because software subscriptions grew."}',
        ])
        result = answer_question('doc-1', 'Why did that increase?', history=history, dependencies=deps)
        retriever.retrieve.assert_called_once_with('semantic', 'Why did revenue increase in 2025?', 1)
        self.assertEqual(result.answer_status, 'answered')
        self.assertEqual(result.citations, [AnswerCitation(chunk_id='chunk-1', excerpt=evidence)])
        self.assertEqual(generator.invoke.call_count, 2, 'Rewrite replaces routing rather than adding a call')
        rewrite_prompt, answer_prompt = (call.args[0] for call in generator.invoke.call_args_list)
        self.assertIn('How did revenue change in 2025?', rewrite_prompt)
        self.assertIn('not document evidence', rewrite_prompt)
        self.assertIn('Question: Why did revenue increase in 2025?', answer_prompt)
        self.assertNotIn('Revenue increased.', answer_prompt, 'Earlier answers never reach the answer model')

    def test_history_and_rewrite_numbers_cannot_supply_missing_evidence(self):
        history = (ConversationExchange(question='What was revenue?', answer='Revenue was 900 million.'),)
        deps, _, _ = self.dependencies('Revenue was 100 million.', [
            '{"intent":"qa","question":"Why did revenue of 900 million increase?"}',
            '{"found_in_excerpts":true,"answer":"Revenue increased to 900 million."}',
        ])
        result = answer_question('doc-1', 'Why did that increase?', history=history, dependencies=deps)
        self.assertEqual(result.answer_status, 'insufficient_context')
        self.assertEqual(result.answer, INSUFFICIENT_CONTEXT_ANSWER)
        self.assertEqual(result.citations, [])

    def test_empty_retrieval_does_not_answer_from_prior_dialogue(self):
        deps, _, generator = self.dependencies('', ['{"intent":"qa","question":"What was revenue in 2025?"}'])
        result = answer_question('doc-1', 'And in 2025?', history=(
            ConversationExchange(question='What was revenue in 2024?', answer='Revenue was 100 million.'),
        ), dependencies=deps)
        self.assertEqual(result.answer_status, 'insufficient_context')
        self.assertEqual(generator.invoke.call_count, 1)

    def test_topic_change_uses_the_new_question_and_history_is_bounded(self):
        history = tuple(ConversationExchange(question=f'OLD-{i}-' + 'q' * 2000, answer='a' * 2000) for i in range(5))
        question = 'What is the refund window?'
        deps, retriever, generator = self.dependencies('Refunds are allowed for 30 days.', [
            '{"intent":"qa","question":"What is the refund window?"}',
            '{"found_in_excerpts":true,"answer":"The refund window is 30 days."}',
        ])
        result = answer_question('doc-1', question, history=history, dependencies=deps)
        self.assertEqual(result.answer_status, 'answered')
        retriever.retrieve.assert_called_once_with('semantic', question, 1)
        prompt = generator.invoke.call_args_list[0].args[0]
        self.assertNotIn('OLD-0-', prompt)
        self.assertNotIn('OLD-1-', prompt)
        self.assertIn('OLD-2-', prompt)
        self.assertIn('OLD-4-', prompt)
        self.assertNotIn('a' * 1001, prompt)
        self.assertNotIn('q' * 1001, prompt)

    def test_rewrite_that_changes_a_year_the_user_typed_is_ignored(self):
        history = (ConversationExchange(question='What was revenue in fiscal 2022?', answer='It was 17.6 billion.'),)
        deps, retriever, generator = self.dependencies('Revenue was 15.8 billion in fiscal 2021.', [
            '{"intent":"qa","question":"What was revenue in fiscal 2020?"}',
            '{"found_in_excerpts":true,"answer":"Revenue was 15.8 billion in fiscal 2021."}',
        ])
        answer_question('doc-1', 'What about fiscal 2021?', history=history, dependencies=deps)
        retriever.retrieve.assert_called_once_with('semantic', 'What about fiscal 2021?', 1)
        self.assertIn('Question: What about fiscal 2021?', generator.invoke.call_args.args[0])

    def test_invalid_rewrite_falls_back_to_the_original_question_without_another_route_call(self):
        history = (ConversationExchange(question='What is the refund window?', answer='It is 30 days.'),)
        deps, retriever, generator = self.dependencies('Refunds are allowed for 30 days.', [
            'invalid routing JSON', 'invalid answer JSON',
            '{"found_in_excerpts":true,"answer":"The refund window is 30 days."}',
        ])
        result = answer_question('doc-1', 'How long is that?', history=history, dependencies=deps)
        self.assertEqual(result.answer_status, 'answered')
        retriever.retrieve.assert_called_once_with('semantic', 'How long is that?', 1)
        self.assertEqual(generator.invoke.call_count, 3)
        self.assertIn('Question: How long is that?', generator.invoke.call_args.args[0])
