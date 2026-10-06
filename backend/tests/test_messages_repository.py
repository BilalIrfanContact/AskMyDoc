import unittest

from backend.services.persistence.messages_repository import _decode_message


class MessageEnvelopeTests(unittest.TestCase):
    def test_only_assistant_rows_decode_valid_answer_envelopes(self):
        encoded = (
            "askmydoc:answer:v1:"
            '{"content":"Grounded answer","answer_status":"answered",'
            '"citations":[{"chunk_id":"chunk-1","excerpt":"Evidence"}]}'
        )

        self.assertEqual(
            _decode_message({"role": "assistant", "content": encoded}),
            {
                "role": "assistant",
                "content": "Grounded answer",
                "answer_status": "answered",
                "citations": [{"chunk_id": "chunk-1", "excerpt": "Evidence"}],
            },
        )

    def test_user_prefix_and_invalid_metadata_remain_plain_messages(self):
        user_content = 'askmydoc:answer:v1:{"content":"x","answer_status":"invalid"}'
        invalid_assistant_content = (
            "askmydoc:answer:v1:"
            '{"content":"Answer","answer_status":"invalid","citations":[]}'
        )

        self.assertEqual(
            _decode_message({"role": "user", "content": user_content}),
            {"role": "user", "content": user_content},
        )
        self.assertEqual(
            _decode_message({"role": "assistant", "content": invalid_assistant_content}),
            {"role": "assistant", "content": invalid_assistant_content},
        )


class TurnHistoryTests(unittest.TestCase):
    def setUp(self):
        from unittest.mock import patch
        from backend.tests.test_app_integration import FakePostgrestClient, InMemoryAppState
        self.state = InMemoryAppState()
        self.state.messages = []
        client = patch('backend.services.persistence.messages_repository.get_postgrest_client',
                       return_value=FakePostgrestClient(self.state))
        self.client = client.start()
        self.addCleanup(client.stop)

    def message(self, role, content, timestamp, request_id=None, conversation='conv-a'):
        self.state.messages.append(dict(role=role, content=content, created_at=timestamp,
                                        request_id=request_id, conversation_id=conversation))

    def test_uses_completed_pairs_before_original_question_and_excludes_other_conversations(self):
        from backend.services.conversation_history import ConversationExchange
        from backend.services.persistence.messages_repository import load_turn_history
        self.message('user', 'What revenue?', '01', 'complete')
        self.message('user', 'Unanswered question', '02', 'unfinished')
        self.message('assistant', 'Revenue grew.', '03', 'complete')
        self.message('user', 'Private question', '04', 'other', conversation='conv-b')
        self.message('assistant', 'Private answer', '05', 'other', conversation='conv-b')
        self.message('user', 'Why did it grow?', '06', 'current')
        self.message('user', 'Later question', '07', 'later')
        self.message('assistant', 'Later answer', '08', 'later')
        self.message('assistant', 'Late answer to unfinished turn', '09', 'unfinished')
        self.assertEqual(load_turn_history('conv-a', 'current'), (
            ConversationExchange(question='What revenue?', answer='Revenue grew.'),
        ))

    def test_bounds_recent_history_and_decodes_saved_answers(self):
        import json
        from backend.services.persistence.messages_repository import load_turn_history
        for i in range(6):
            self.message('user', f'Q-{i}-' + 'x' * 2000, f'{i * 2:02}', str(i))
            envelope = 'askmydoc:answer:v1:' + json.dumps(dict(content=f'A-{i}-' + 'y' * 2000,
                                                               answer_status='answered', citations=[]))
            self.message('assistant', envelope, f'{i * 2 + 1:02}', str(i))
        self.message('user', 'Current question', '20', 'current')
        history = load_turn_history('conv-a', 'current')
        self.assertEqual(len(history), 3)
        self.assertEqual([exchange.question[:4] for exchange in history], ['Q-3-', 'Q-4-', 'Q-5-'])
        self.assertEqual([exchange.answer[:4] for exchange in history], ['A-3-', 'A-4-', 'A-5-'])
        self.assertTrue(all(len(exchange.question) <= 1000 and len(exchange.answer) <= 1000 for exchange in history))

    def test_supports_legacy_pairs_and_missing_current_turn_fails_closed(self):
        from backend.services.conversation_history import ConversationExchange
        from backend.services.persistence.common import PersistenceError
        from backend.services.persistence.messages_repository import load_turn_history
        self.message('user', 'Legacy question', '01')
        self.message('assistant', 'Legacy answer', '02')
        self.message('user', 'Current question', '03', 'current')
        self.assertEqual(load_turn_history('conv-a', 'current'), (
            ConversationExchange(question='Legacy question', answer='Legacy answer'),
        ))
        with self.assertRaises(PersistenceError):
            load_turn_history('conv-a', 'missing')


if __name__ == "__main__":
    unittest.main()
