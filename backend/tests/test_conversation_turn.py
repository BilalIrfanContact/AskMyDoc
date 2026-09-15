import unittest
from unittest.mock import Mock, call, patch

from fastapi import HTTPException

from backend.services.conversation_turn import (
    ConversationTurnInput,
    ConversationTurnValidationError,
    execute_conversation_turn,
)
from backend.services.persistence import PersistenceError
from backend.services.rag_pipeline import AnswerDecision


class ConversationTurnTestCase(unittest.TestCase):
    def setUp(self):
        self.request = ConversationTurnInput(
            document_id="doc-a",
            conversation_id="convo-a",
            message="  What is the refund window?  ",
        )
        self.conversation = {
            "id": "convo-a",
            "user_id": "user-a",
            "document_id": "doc-a",
        }
        self.decision = AnswerDecision(
            answer="The refund window is 30 days.",
            intent="qa",
            retrieval_mode="semantic",
            answer_status="answered",
            citations=[],
        )

    def test_executes_and_persists_one_complete_conversation_turn(self):
        with (
            patch(
                "backend.services.conversation_turn.require_user_conversation",
                return_value=self.conversation,
            ),
            patch("backend.services.conversation_turn.insert_message") as insert_message,
            patch(
                "backend.services.conversation_turn.answer_question",
                return_value=self.decision,
            ) as answer_question,
        ):
            result = execute_conversation_turn(user_id="user-a", request=self.request)

        self.assertEqual(result, self.decision)
        answer_question.assert_called_once_with(
            document_id="doc-a",
            question="What is the refund window?",
        )
        self.assertEqual(
            insert_message.call_args_list,
            [
                call(
                    conversation_id="convo-a",
                    role="user",
                    content="What is the refund window?",
                ),
                call(
                    conversation_id="convo-a",
                    role="assistant",
                    content="The refund window is 30 days.",
                ),
            ],
        )

    def test_does_not_persist_assistant_message_when_answering_fails(self):
        with (
            patch(
                "backend.services.conversation_turn.require_user_conversation",
                return_value=self.conversation,
            ),
            patch("backend.services.conversation_turn.insert_message") as insert_message,
            patch(
                "backend.services.conversation_turn.answer_question",
                side_effect=RuntimeError("model unavailable"),
            ),
        ):
            with self.assertRaises(RuntimeError):
                execute_conversation_turn(user_id="user-a", request=self.request)

        insert_message.assert_called_once_with(
            conversation_id="convo-a",
            role="user",
            content="What is the refund window?",
        )

    def test_rejects_empty_questions_before_authorization(self):
        with patch("backend.services.conversation_turn.require_user_conversation") as authorize:
            with self.assertRaisesRegex(
                ConversationTurnValidationError,
                "Question cannot be empty",
            ):
                execute_conversation_turn(
                    user_id="user-a",
                    request=ConversationTurnInput(
                        document_id="doc-a",
                        conversation_id="convo-a",
                        message="   ",
                    ),
                )

        authorize.assert_not_called()

    def test_rejects_missing_conversation_before_authorization(self):
        with patch("backend.services.conversation_turn.require_user_conversation") as authorize:
            with self.assertRaisesRegex(
                ConversationTurnValidationError,
                "conversation_id is required",
            ):
                execute_conversation_turn(
                    user_id="user-a",
                    request=ConversationTurnInput(
                        document_id="doc-a",
                        conversation_id=None,
                        message="What is in the document?",
                    ),
                )

        authorize.assert_not_called()

    def test_checks_the_requested_document_when_conversation_points_elsewhere(self):
        other_conversation = {**self.conversation, "document_id": "doc-b"}
        with (
            patch(
                "backend.services.conversation_turn.require_user_conversation",
                return_value=other_conversation,
            ),
            patch(
                "backend.services.conversation_turn.require_user_document",
                side_effect=HTTPException(status_code=403, detail="Forbidden"),
            ) as authorize_document,
        ):
            with self.assertRaises(HTTPException):
                execute_conversation_turn(user_id="user-a", request=self.request)

        authorize_document.assert_called_once_with(document_id="doc-a", user_id="user-a")

    def test_preserves_persistence_failures_for_the_route_to_translate(self):
        with (
            patch(
                "backend.services.conversation_turn.require_user_conversation",
                return_value=self.conversation,
            ),
            patch(
                "backend.services.conversation_turn.insert_message",
                side_effect=PersistenceError("save failed"),
            ),
        ):
            with self.assertRaisesRegex(PersistenceError, "save failed"):
                execute_conversation_turn(user_id="user-a", request=self.request)


if __name__ == "__main__":
    unittest.main()
