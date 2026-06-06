import unittest
from unittest.mock import patch

from fastapi import HTTPException

from backend.services.authz import require_user_conversation, require_user_document
from backend.services.persistence import PersistenceError


class AuthorizationServiceTestCase(unittest.TestCase):
    def test_require_user_document_returns_owned_document(self):
        owned_document = {"id": "doc-a", "user_id": "user-a"}

        with (
            patch(
                "backend.services.authz.get_user_document",
                return_value=owned_document,
            ) as get_user_document_mock,
            patch("backend.services.authz.get_document") as get_document_mock,
        ):
            result = require_user_document(document_id="doc-a", user_id="user-a")

        self.assertEqual(result, owned_document)
        get_user_document_mock.assert_called_once_with(document_id="doc-a", user_id="user-a")
        get_document_mock.assert_not_called()

    def test_require_user_document_raises_403_for_cross_user_document(self):
        with (
            patch("backend.services.authz.get_user_document", return_value=None),
            patch(
                "backend.services.authz.get_document",
                return_value={"id": "doc-b", "user_id": "user-b"},
            ),
        ):
            with self.assertRaises(HTTPException) as exc:
                require_user_document(document_id="doc-b", user_id="user-a")

        self.assertEqual(exc.exception.status_code, 403)
        self.assertEqual(
            exc.exception.detail,
            "You are not authorized to access this document.",
        )

    def test_require_user_document_raises_404_for_missing_document(self):
        with (
            patch("backend.services.authz.get_user_document", return_value=None),
            patch("backend.services.authz.get_document", return_value=None),
        ):
            with self.assertRaises(HTTPException) as exc:
                require_user_document(document_id="doc-missing", user_id="user-a")

        self.assertEqual(exc.exception.status_code, 404)
        self.assertEqual(exc.exception.detail, "Document not found.")

    def test_require_user_document_maps_persistence_error_to_502(self):
        with patch(
            "backend.services.authz.get_user_document",
            side_effect=PersistenceError("database unavailable"),
        ):
            with self.assertRaises(HTTPException) as exc:
                require_user_document(document_id="doc-a", user_id="user-a")

        self.assertEqual(exc.exception.status_code, 502)
        self.assertEqual(exc.exception.detail, "database unavailable")

    def test_require_user_conversation_raises_403_for_cross_user_conversation(self):
        with (
            patch("backend.services.authz.get_user_conversation", return_value=None),
            patch(
                "backend.services.authz.get_conversation",
                return_value={"id": "convo-b", "user_id": "user-b"},
            ),
        ):
            with self.assertRaises(HTTPException) as exc:
                require_user_conversation(conversation_id="convo-b", user_id="user-a")

        self.assertEqual(exc.exception.status_code, 403)
        self.assertEqual(
            exc.exception.detail,
            "You are not authorized to access this conversation.",
        )

    def test_require_user_conversation_raises_404_for_missing_conversation(self):
        with (
            patch("backend.services.authz.get_user_conversation", return_value=None),
            patch("backend.services.authz.get_conversation", return_value=None),
        ):
            with self.assertRaises(HTTPException) as exc:
                require_user_conversation(conversation_id="convo-missing", user_id="user-a")

        self.assertEqual(exc.exception.status_code, 404)
        self.assertEqual(exc.exception.detail, "Conversation not found.")

    def test_require_user_conversation_maps_persistence_error_to_502(self):
        with patch(
            "backend.services.authz.get_user_conversation",
            side_effect=PersistenceError("database unavailable"),
        ):
            with self.assertRaises(HTTPException) as exc:
                require_user_conversation(conversation_id="convo-a", user_id="user-a")

        self.assertEqual(exc.exception.status_code, 502)
        self.assertEqual(exc.exception.detail, "database unavailable")


if __name__ == "__main__":
    unittest.main()
