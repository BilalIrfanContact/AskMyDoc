import json
import unittest
from contextlib import ExitStack
from urllib.parse import urlsplit
from unittest.mock import patch

from fastapi import FastAPI, Request

from backend.routers import chat, conversations, documents, upload
from backend.services.internal_auth import require_authenticated_user


def _build_test_app() -> FastAPI:
    app = FastAPI()
    app.include_router(upload.router)
    app.include_router(chat.router)
    app.include_router(conversations.router)
    app.include_router(documents.router)

    async def override_user(request: Request) -> str:
        return request.headers.get("x-test-user", "user-a")

    app.dependency_overrides[require_authenticated_user] = override_user
    return app


def _multipart_request_body(
    *,
    field_name: str,
    filename: str,
    content_type: str,
    payload: bytes,
    boundary: str,
) -> bytes:
    lines = [
        f"--{boundary}\r\n".encode("utf-8"),
        (
            f'Content-Disposition: form-data; name="{field_name}"; filename="{filename}"\r\n'
        ).encode("utf-8"),
        f"Content-Type: {content_type}\r\n\r\n".encode("utf-8"),
        payload,
        b"\r\n",
        f"--{boundary}--\r\n".encode("utf-8"),
    ]
    return b"".join(lines)


async def _request_asgi(
    app: FastAPI,
    *,
    method: str,
    path: str,
    body: bytes = b"",
    headers: list[tuple[bytes, bytes]] | None = None,
) -> tuple[int, dict[str, str], bytes]:
    response_status = 500
    response_headers: dict[str, str] = {}
    response_body = bytearray()
    sent = False

    async def receive():
        nonlocal sent
        if sent:
            return {"type": "http.disconnect"}

        sent = True
        return {
            "type": "http.request",
            "body": body,
            "more_body": False,
        }

    async def send(message):
        nonlocal response_status
        if message["type"] == "http.response.start":
            response_status = message["status"]
            response_headers.update(
                {
                    key.decode("latin-1"): value.decode("latin-1")
                    for key, value in message.get("headers", [])
                }
            )
            return

        if message["type"] == "http.response.body":
            response_body.extend(message.get("body", b""))

    split = urlsplit(path)
    scope = {
        "type": "http",
        "asgi": {"version": "3.0"},
        "http_version": "1.1",
        "method": method,
        "scheme": "http",
        "path": split.path,
        "raw_path": split.path.encode("utf-8"),
        "query_string": split.query.encode("utf-8"),
        "headers": headers or [],
        "client": ("127.0.0.1", 12345),
        "server": ("testserver", 80),
    }

    await app(scope, receive, send)
    return response_status, response_headers, bytes(response_body)


class InMemoryAppState:
    def __init__(self):
        self.documents: dict[str, dict] = {
            "doc-a": {
                "id": "doc-a",
                "user_id": "user-a",
                "filename": "alpha.pdf",
                "storage_url": "documents/user-a/doc-a/alpha.pdf",
                "uploaded_at": "2026-06-11T10:00:00Z",
            },
            "doc-b": {
                "id": "doc-b",
                "user_id": "user-b",
                "filename": "beta.pdf",
                "storage_url": "documents/user-b/doc-b/beta.pdf",
                "uploaded_at": "2026-06-11T10:05:00Z",
            },
        }
        self.conversations: dict[str, dict] = {
            "convo-b": {
                "id": "convo-b",
                "user_id": "user-b",
                "document_id": "doc-b",
                "created_at": "2026-06-11T10:10:00Z",
            }
        }
        self.messages: list[dict] = [
            {
                "id": "msg-b-1",
                "conversation_id": "convo-b",
                "role": "user",
                "content": "private question",
                "created_at": "2026-06-11T10:11:00Z",
            }
        ]
        self.storage_deleted: list[str] = []
        self.vector_deleted: list[str] = []
        self.conversation_counter = 0
        self.message_counter = 0
        self.upload_counter = 0

    def list_user_documents(self, user_id: str) -> list[dict]:
        return sorted(
            [document for document in self.documents.values() if document["user_id"] == user_id],
            key=lambda item: item.get("uploaded_at") or "",
            reverse=True,
        )

    def get_user_document(self, document_id: str, user_id: str) -> dict | None:
        document = self.documents.get(document_id)
        if document and document["user_id"] == user_id:
            return document
        return None

    def get_document(self, document_id: str) -> dict | None:
        return self.documents.get(document_id)

    def create_conversation(self, user_id: str, document_id: str) -> str:
        self.conversation_counter += 1
        conversation_id = f"convo-{self.conversation_counter}"
        self.conversations[conversation_id] = {
            "id": conversation_id,
            "user_id": user_id,
            "document_id": document_id,
            "created_at": f"2026-06-11T11:0{self.conversation_counter}:00Z",
        }
        return conversation_id

    def get_user_conversation(self, conversation_id: str, user_id: str) -> dict | None:
        conversation = self.conversations.get(conversation_id)
        if conversation and conversation["user_id"] == user_id:
            return conversation
        return None

    def get_conversation(self, conversation_id: str) -> dict | None:
        return self.conversations.get(conversation_id)

    def list_user_conversations(self, user_id: str, document_id: str | None = None) -> list[dict]:
        conversations = [
            conversation
            for conversation in self.conversations.values()
            if conversation["user_id"] == user_id
            and (document_id is None or conversation["document_id"] == document_id)
        ]
        return sorted(conversations, key=lambda item: item.get("created_at") or "", reverse=True)

    def insert_message(self, conversation_id: str, role: str, content: str) -> dict:
        self.message_counter += 1
        message = {
            "id": f"msg-{self.message_counter}",
            "conversation_id": conversation_id,
            "role": role,
            "content": content,
            "created_at": f"2026-06-11T12:0{self.message_counter}:00Z",
        }
        self.messages.append(message)
        return message

    def list_conversation_messages(self, conversation_id: str) -> list[dict]:
        return [message for message in self.messages if message["conversation_id"] == conversation_id]

    def upload_document(self, user_id: str, filename: str) -> tuple[str, str]:
        self.upload_counter += 1
        document_id = f"doc-upload-{self.upload_counter}"
        storage_url = f"documents/{user_id}/{document_id}/{filename}"
        self.documents[document_id] = {
            "id": document_id,
            "user_id": user_id,
            "filename": filename,
            "storage_url": storage_url,
            "uploaded_at": f"2026-06-11T13:0{self.upload_counter}:00Z",
        }
        return document_id, storage_url

    def list_document_conversation_ids(self, user_id: str, document_id: str) -> list[str]:
        return [
            conversation["id"]
            for conversation in self.conversations.values()
            if conversation["user_id"] == user_id and conversation["document_id"] == document_id
        ]

    def delete_storage_object(self, storage_url: str) -> None:
        self.storage_deleted.append(storage_url)

    def delete_document_record(self, document_id: str, user_id: str) -> None:
        document = self.documents.get(document_id)
        if document and document["user_id"] == user_id:
            del self.documents[document_id]

    def delete_messages_for_conversation(self, conversation_id: str) -> None:
        self.messages = [
            message for message in self.messages if message["conversation_id"] != conversation_id
        ]

    def delete_user_document_conversations(self, user_id: str, document_id: str) -> None:
        to_delete = [
            conversation_id
            for conversation_id, conversation in self.conversations.items()
            if conversation["user_id"] == user_id and conversation["document_id"] == document_id
        ]
        for conversation_id in to_delete:
            del self.conversations[conversation_id]

    def delete_vector_store(self, document_id: str) -> None:
        self.vector_deleted.append(document_id)


class AppIntegrationTestCase(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.app = _build_test_app()
        self.state = InMemoryAppState()
        self.exit_stack = ExitStack()

        self.exit_stack.enter_context(
            patch("backend.services.authz.get_user_document", side_effect=self.state.get_user_document)
        )
        self.exit_stack.enter_context(
            patch("backend.services.authz.get_document", side_effect=self.state.get_document)
        )
        self.exit_stack.enter_context(
            patch(
                "backend.services.authz.get_user_conversation",
                side_effect=self.state.get_user_conversation,
            )
        )
        self.exit_stack.enter_context(
            patch("backend.services.authz.get_conversation", side_effect=self.state.get_conversation)
        )

        self.exit_stack.enter_context(
            patch("backend.routers.documents.list_user_documents", side_effect=self.state.list_user_documents)
        )
        self.exit_stack.enter_context(
            patch(
                "backend.routers.conversations.create_conversation",
                side_effect=self.state.create_conversation,
            )
        )
        self.exit_stack.enter_context(
            patch(
                "backend.routers.conversations.list_user_conversations",
                side_effect=self.state.list_user_conversations,
            )
        )
        self.exit_stack.enter_context(
            patch(
                "backend.routers.conversations.list_conversation_messages",
                side_effect=self.state.list_conversation_messages,
            )
        )
        self.exit_stack.enter_context(
            patch("backend.routers.chat.insert_message", side_effect=self.state.insert_message)
        )
        self.exit_stack.enter_context(
            patch("backend.routers.chat.answer_question", return_value="Document summary answer")
        )

        self.exit_stack.enter_context(
            patch("backend.services.document_lifecycle.extract_text_from_pdf", return_value="alpha beta")
        )
        self.exit_stack.enter_context(
            patch("backend.services.document_lifecycle.chunk_text", return_value=["alpha", "beta"])
        )
        self.exit_stack.enter_context(
            patch("backend.services.document_lifecycle.build_vector_store", return_value=2)
        )
        self.exit_stack.enter_context(
            patch(
                "backend.services.document_lifecycle.upload_pdf_to_storage",
                side_effect=lambda user_id, document_id, filename, data: (
                    self.state.upload_document(user_id, filename)[1]
                ),
            )
        )
        self.exit_stack.enter_context(
            patch(
                "backend.services.document_lifecycle.insert_document",
                side_effect=lambda document_id, user_id, filename, storage_url: (
                    self.state.documents.setdefault(
                        document_id,
                        {
                            "id": document_id,
                            "user_id": user_id,
                            "filename": filename,
                            "storage_url": storage_url,
                            "uploaded_at": "2026-06-11T13:59:00Z",
                        },
                    )
                ),
            )
        )
        self.exit_stack.enter_context(
            patch(
                "backend.services.document_lifecycle.uuid.uuid4",
                side_effect=lambda: f"doc-upload-{self.state.upload_counter + 1}",
            )
        )
        self.exit_stack.enter_context(
            patch(
                "backend.services.document_lifecycle.list_document_conversation_ids",
                side_effect=self.state.list_document_conversation_ids,
            )
        )
        self.exit_stack.enter_context(
            patch(
                "backend.services.document_lifecycle.delete_storage_object",
                side_effect=self.state.delete_storage_object,
            )
        )
        self.exit_stack.enter_context(
            patch(
                "backend.services.document_lifecycle.delete_document_record",
                side_effect=self.state.delete_document_record,
            )
        )
        self.exit_stack.enter_context(
            patch(
                "backend.services.document_lifecycle.delete_messages_for_conversation",
                side_effect=self.state.delete_messages_for_conversation,
            )
        )
        self.exit_stack.enter_context(
            patch(
                "backend.services.document_lifecycle.delete_user_document_conversations",
                side_effect=self.state.delete_user_document_conversations,
            )
        )
        self.exit_stack.enter_context(
            patch(
                "backend.services.document_lifecycle.delete_vector_store",
                side_effect=self.state.delete_vector_store,
            )
        )

    def tearDown(self):
        self.exit_stack.close()
        self.app.dependency_overrides.clear()

    async def test_auth_ownership_constraints_are_enforced_at_http_boundary(self):
        status, _, response_body = await _request_asgi(
            self.app,
            method="GET",
            path="/conversations?document_id=doc-b",
            headers=[(b"x-test-user", b"user-a")],
        )
        self.assertEqual(status, 403)
        self.assertEqual(
            json.loads(response_body),
            {"detail": "You are not authorized to access this document."},
        )

        status, _, response_body = await _request_asgi(
            self.app,
            method="GET",
            path="/conversations/convo-b/messages",
            headers=[(b"x-test-user", b"user-a")],
        )
        self.assertEqual(status, 403)
        self.assertEqual(
            json.loads(response_body),
            {"detail": "You are not authorized to access this conversation."},
        )

        status, _, response_body = await _request_asgi(
            self.app,
            method="DELETE",
            path="/documents/doc-b",
            headers=[(b"x-test-user", b"user-a")],
        )
        self.assertEqual(status, 403)
        self.assertEqual(
            json.loads(response_body),
            {"detail": "You are not authorized to access this document."},
        )

    async def test_upload_delete_consistency_is_visible_across_documents_and_conversations(self):
        boundary = "boundary123"
        body = _multipart_request_body(
            field_name="file",
            filename="report.pdf",
            content_type="application/pdf",
            payload=b"%PDF-1.4",
            boundary=boundary,
        )

        status, _, response_body = await _request_asgi(
            self.app,
            method="POST",
            path="/upload",
            body=body,
            headers=[
                (b"x-test-user", b"user-a"),
                (b"content-type", f"multipart/form-data; boundary={boundary}".encode("utf-8")),
                (b"content-length", str(len(body)).encode("utf-8")),
            ],
        )
        self.assertEqual(status, 200)
        upload_payload = json.loads(response_body)
        document_id = upload_payload["document_id"]

        status, _, response_body = await _request_asgi(
            self.app,
            method="POST",
            path="/conversations",
            body=json.dumps({"document_id": document_id}).encode("utf-8"),
            headers=[
                (b"x-test-user", b"user-a"),
                (b"content-type", b"application/json"),
            ],
        )
        self.assertEqual(status, 200)
        conversation_id = json.loads(response_body)["conversation_id"]

        status, _, response_body = await _request_asgi(
            self.app,
            method="DELETE",
            path=f"/documents/{document_id}",
            headers=[(b"x-test-user", b"user-a")],
        )
        self.assertEqual(status, 200)
        self.assertEqual(
            json.loads(response_body),
            {
                "deleted": True,
                "lifecycle_status": "deleted",
                "cleanup_status": "completed",
            },
        )

        status, _, response_body = await _request_asgi(
            self.app,
            method="GET",
            path="/documents",
            headers=[(b"x-test-user", b"user-a")],
        )
        self.assertEqual(status, 200)
        self.assertNotIn(
            document_id,
            [document["id"] for document in json.loads(response_body)["documents"]],
        )

        status, _, response_body = await _request_asgi(
            self.app,
            method="GET",
            path=f"/conversations/{conversation_id}/messages",
            headers=[(b"x-test-user", b"user-a")],
        )
        self.assertEqual(status, 404)
        self.assertEqual(json.loads(response_body), {"detail": "Conversation not found."})
        self.assertIn(document_id, self.state.vector_deleted)

    async def test_chat_persistence_and_retrieval_work_across_requests(self):
        status, _, response_body = await _request_asgi(
            self.app,
            method="POST",
            path="/conversations",
            body=json.dumps({"document_id": "doc-a"}).encode("utf-8"),
            headers=[
                (b"x-test-user", b"user-a"),
                (b"content-type", b"application/json"),
            ],
        )
        self.assertEqual(status, 200)
        conversation_id = json.loads(response_body)["conversation_id"]

        status, _, response_body = await _request_asgi(
            self.app,
            method="POST",
            path="/chat",
            body=json.dumps(
                {
                    "document_id": "doc-a",
                    "conversation_id": conversation_id,
                    "message": "Summarize the document",
                }
            ).encode("utf-8"),
            headers=[
                (b"x-test-user", b"user-a"),
                (b"content-type", b"application/json"),
            ],
        )
        self.assertEqual(status, 200)
        self.assertEqual(json.loads(response_body), {"answer": "Document summary answer"})

        status, _, response_body = await _request_asgi(
            self.app,
            method="GET",
            path="/conversations?document_id=doc-a",
            headers=[(b"x-test-user", b"user-a")],
        )
        self.assertEqual(status, 200)
        self.assertEqual(
            [conversation["id"] for conversation in json.loads(response_body)["conversations"]],
            [conversation_id],
        )

        status, _, response_body = await _request_asgi(
            self.app,
            method="GET",
            path=f"/conversations/{conversation_id}/messages",
            headers=[(b"x-test-user", b"user-a")],
        )
        self.assertEqual(status, 200)
        self.assertEqual(
            json.loads(response_body)["messages"],
            [
                {
                    "id": "msg-1",
                    "conversation_id": conversation_id,
                    "role": "user",
                    "content": "Summarize the document",
                    "created_at": "2026-06-11T12:01:00Z",
                },
                {
                    "id": "msg-2",
                    "conversation_id": conversation_id,
                    "role": "assistant",
                    "content": "Document summary answer",
                    "created_at": "2026-06-11T12:02:00Z",
                },
            ],
        )


if __name__ == "__main__":
    unittest.main()
