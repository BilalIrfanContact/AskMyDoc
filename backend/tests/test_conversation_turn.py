import unittest
from dataclasses import asdict, replace
from unittest.mock import patch

from fastapi import HTTPException

from backend.services.conversation_turn import (
    ConversationTurnInput, ConversationTurnValidationError, execute_conversation_turn,
)
from backend.services.rag_pipeline import AnswerCitation, AnswerDecision


class ConversationTurnTestCase(unittest.TestCase):
    def setUp(self):
        self.request = ConversationTurnInput(
            document_id='doc-a', conversation_id='convo-a',
            request_id='00000000-0000-4000-8000-000000000001', message='  Refund window?  ',
        )
        self.decision = AnswerDecision(
            answer='30 days', intent='qa', retrieval_mode='semantic', answer_status='answered',
            citations=[AnswerCitation(chunk_id='chunk-1', excerpt='Refunds within 30 days.')],
        )
        authorize = patch('backend.services.conversation_turn.require_user_conversation',
                          return_value={'document_id': 'doc-a'})
        authorize.start()
        self.addCleanup(authorize.stop)

    def execute(self, request=None):
        return execute_conversation_turn(user_id='user-a', request=request or self.request)

    def test_generates_saves_and_completes_one_turn(self):
        receipt = {'state': 'completed', 'result': asdict(self.decision)}
        with patch('backend.services.conversation_turn.transition_turn', side_effect=[
                {'state': 'generating'}, {'state': 'generated'}, receipt]) as transition, \
             patch('backend.services.conversation_turn.answer_question', return_value=self.decision) as answer:
            self.assertEqual(self.execute(), self.decision)
        answer.assert_called_once_with(document_id='doc-a', question='Refund window?')
        self.assertEqual([c.args[0] for c in transition.call_args_list], ['claim', 'save', 'complete'])
        self.assertEqual(transition.call_args_list[1].kwargs['result'], asdict(self.decision))

    def test_completed_retry_returns_identical_answer_without_generation(self):
        with patch('backend.services.conversation_turn.transition_turn', return_value={
                'state': 'completed', 'result': asdict(self.decision)}) as transition, \
             patch('backend.services.conversation_turn.answer_question') as answer:
            self.assertEqual(self.execute(), self.decision)
        answer.assert_not_called()
        self.assertEqual(transition.call_count, 1)

    def test_saved_answer_resumes_completion_without_generation(self):
        with patch('backend.services.conversation_turn.transition_turn', side_effect=[
                {'state': 'generated'}, {'state': 'completed', 'result': asdict(self.decision)}]) as transition, \
             patch('backend.services.conversation_turn.answer_question') as answer:
            self.assertEqual(self.execute(), self.decision)
        answer.assert_not_called()
        self.assertEqual([c.args[0] for c in transition.call_args_list], ['claim', 'complete'])

    def test_generation_failure_marks_turn_failed_for_safe_retry(self):
        with patch('backend.services.conversation_turn.transition_turn', return_value={'state': 'generating'}) as transition, \
             patch('backend.services.conversation_turn.answer_question', side_effect=RuntimeError('model unavailable')):
            with self.assertRaisesRegex(RuntimeError, 'model unavailable'):
                self.execute()
        self.assertEqual([c.args[0] for c in transition.call_args_list], ['claim', 'fail'])

    def test_uncertain_save_or_completion_does_not_refund_or_regenerate(self):
        for failure_stage in ('save', 'complete'):
            calls = [{'state': 'generating'}, RuntimeError('database offline')]
            if failure_stage == 'complete':
                calls.insert(1, {'state': 'generated'})
            with self.subTest(stage=failure_stage), \
                 patch('backend.services.conversation_turn.transition_turn', side_effect=calls) as transition, \
                 patch('backend.services.conversation_turn.answer_question', return_value=self.decision):
                with self.assertRaisesRegex(RuntimeError, 'database offline'):
                    self.execute()
                self.assertNotIn('fail', [c.args[0] for c in transition.call_args_list])

    def test_busy_turn_never_starts_generation(self):
        with patch('backend.services.conversation_turn.transition_turn', side_effect=HTTPException(409, 'Busy')), \
             patch('backend.services.conversation_turn.answer_question') as answer:
            with self.assertRaises(HTTPException):
                self.execute()
        answer.assert_not_called()

    def test_invalid_input_never_claims_a_turn(self):
        for request in (replace(self.request, message=' '), replace(self.request, conversation_id=None),
                        replace(self.request, request_id='invalid'), replace(self.request, message='x' * 2001)):
            with self.subTest(request=request), patch('backend.services.conversation_turn.transition_turn') as claim:
                with self.assertRaises(ConversationTurnValidationError):
                    self.execute(request)
                claim.assert_not_called()

    def test_authorization_runs_before_receipt_lookup(self):
        with patch('backend.services.conversation_turn.require_user_conversation', side_effect=HTTPException(403)), \
             patch('backend.services.conversation_turn.transition_turn') as claim:
            with self.assertRaises(HTTPException):
                self.execute()
        claim.assert_not_called()

    def test_mismatched_document_is_rejected_before_claim(self):
        with patch('backend.services.conversation_turn.require_user_document') as authorize, \
             patch('backend.services.conversation_turn.transition_turn') as claim:
            with self.assertRaises(ConversationTurnValidationError):
                self.execute(replace(self.request, document_id='doc-b'))
        authorize.assert_called_once_with(document_id='doc-b', user_id='user-a')
        claim.assert_not_called()
