import json
import unittest
from contextlib import ExitStack
from types import SimpleNamespace
from urllib.parse import urlsplit
from unittest.mock import patch

from fastapi import FastAPI, Request

from backend.routers import chat, conversations, documents, upload
from backend.services.internal_auth import require_authenticated_user
from backend.services.rag_pipeline import AnswerDecision


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


class FakeResponse:
    def __init__(self, data):
        self.data = data


class FakePostgrestQuery:
    def __init__(self, state: "InMemoryAppState", table: str):
        self.state = state
        self.table = table
        self._action = "select"
        self._filters: list[tuple[str, object]] = []
        self._selected_fields: list[str] | None = None
        self._limit: int | None = None
        self._order_field: str | None = None
        self._order_desc = False
        self._insert_payload: dict | None = None

    def select(self, fields: str):
        self._action = "select"
        self._selected_fields = [field.strip() for field in fields.split(",")]
        return self

    def eq(self, field: str, value):
        self._filters.append((field, value))
        return self

    def limit(self, value: int):
        self._limit = value
        return self

    def order(self, field: str, desc: bool = False):
        self._order_field = field
        self._order_desc = desc
        return self

    def insert(self, payload: dict):
        self._action = "insert"
        self._insert_payload = dict(payload)
        return self

    def delete(self):
        self._action = "delete"
        return self

    def execute(self):
        if self._action == "insert":
            return FakeResponse(self.state.insert_row(self.table, self._insert_payload or {}))

        if self._action == "delete":
            self.state.delete_rows(self.table, self._filters)
            return FakeResponse([])

        rows = self.state.select_rows(
            self.table,
            filters=self._filters,
            selected_fields=self._selected_fields,
            order_field=self._order_field,
            order_desc=self._order_desc,
            limit=self._limit,
        )
        return FakeResponse(rows)


class FakePostgrestClient:
    def __init__(self, state: "InMemoryAppState"):
        self.state = state

    def from_(self, table: str) -> FakePostgrestQuery:
        return FakePostgrestQuery(self.state, table)


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
        self.storage_uploaded: list[str] = []
        self.vector_deleted: list[str] = []
        self.conversation_counter = 0
        self.message_counter = 0
        self.upload_counter = 0
        self.document_counter = 0

    @staticmethod
    def _matches_filters(row: dict, filters: list[tuple[str, object]]) -> bool:
        return all(row.get(field) == value for field, value in filters)

    @staticmethod
    def _project_row(row: dict, selected_fields: list[str] | None) -> dict:
        if not selected_fields:
            return dict(row)
        return {field: row.get(field) for field in selected_fields}

    def select_rows(
        self,
        table: str,
        *,
        filters: list[tuple[str, object]],
        selected_fields: list[str] | None,
        order_field: str | None,
        order_desc: bool,
        limit: int | None,
    ) -> list[dict]:
        if table == "documents":
            rows = list(self.documents.values())
        elif table == "conversations":
            rows = list(self.conversations.values())
        elif table == "messages":
            rows = list(self.messages)
        else:
            raise AssertionError(f"Unexpected table: {table}")

        rows = [row for row in rows if self._matches_filters(row, filters)]
        if order_field:
            rows = sorted(rows, key=lambda item: item.get(order_field) or "", reverse=order_desc)
        if limit is not None:
            rows = rows[:limit]
        return [self._project_row(row, selected_fields) for row in rows]

    def insert_row(self, table: str, payload: dict) -> list[dict]:
        row = dict(payload)

        if table == "documents":
            self.document_counter += 1
            row.setdefault("uploaded_at", f"2026-06-11T13:{self.document_counter:02d}:00Z")
            self.documents[row["id"]] = row
        elif table == "conversations":
            self.conversation_counter += 1
            self.conversations[row["id"]] = {
                **row,
                "created_at": f"2026-06-11T11:{self.conversation_counter:02d}:00Z",
            }
            row = self.conversations[row["id"]]
        elif table == "messages":
            self.message_counter += 1
            self.messages.append(
                {
                    **row,
                    "created_at": f"2026-06-11T12:{self.message_counter:02d}:00Z",
                }
            )
            row = self.messages[-1]
        else:
            raise AssertionError(f"Unexpected table: {table}")

        return [dict(row)]

    def delete_rows(self, table: str, filters: list[tuple[str, object]]) -> None:
        if table == "documents":
            for document_id, row in list(self.documents.items()):
                if self._matches_filters(row, filters):
                    del self.documents[document_id]
            return

        if table == "conversations":
            for conversation_id, row in list(self.conversations.items()):
                if self._matches_filters(row, filters):
                    del self.conversations[conversation_id]
            return

        if table == "messages":
            self.messages = [row for row in self.messages if not self._matches_filters(row, filters)]
            return

        raise AssertionError(f"Unexpected table: {table}")

    def upload_storage_object(self, user_id: str, document_id: str, filename: str, data: bytes) -> str:
        self.upload_counter += 1
        storage_url = f"documents/{user_id}/{document_id}/{filename}"
        self.storage_uploaded.append(storage_url)
        return storage_url

    def delete_storage_object(self, storage_url: str) -> None:
        self.storage_deleted.append(storage_url)

    def delete_vector_store(self, document_id: str) -> None:
        self.vector_deleted.append(document_id)


class AppIntegrationTestCase(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.app = _build_test_app()
        self.state = InMemoryAppState()
        self.postgrest_client = FakePostgrestClient(self.state)
        self.exit_stack = ExitStack()

        for target in (
            "backend.services.persistence.documents_repository.get_postgrest_client",
            "backend.services.persistence.conversations_repository.get_postgrest_client",
            "backend.services.persistence.messages_repository.get_postgrest_client",
        ):
            self.exit_stack.enter_context(patch(target, return_value=self.postgrest_client))
        self.exit_stack.enter_context(
            patch(
                "backend.services.persistence.conversations_repository.uuid",
                new=SimpleNamespace(uuid4=lambda: f"convo-{self.state.conversation_counter + 1}"),
            )
        )
        self.exit_stack.enter_context(
            patch(
                "backend.services.persistence.messages_repository.uuid",
                new=SimpleNamespace(uuid4=lambda: f"msg-{self.state.message_counter + 1}"),
            )
        )

        self.exit_stack.enter_context(
            patch(
                "backend.routers.chat.answer_question",
                return_value=AnswerDecision(
                    answer="Document summary answer",
                    intent="summary",
                    retrieval_mode="head",
                    answer_status="answered",
                    citations=[],
                ),
            )
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
                side_effect=self.state.upload_storage_object,
            )
        )
        self.exit_stack.enter_context(
            patch(
                "backend.services.document_lifecycle.uuid",
                new=SimpleNamespace(uuid4=lambda: f"doc-upload-{self.state.upload_counter + 1}"),
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
        self.assertIn(document_id, self.state.documents)
        self.assertIn(f"documents/user-a/{document_id}/report.pdf", self.state.storage_uploaded)

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
        self.assertEqual(
            json.loads(response_body),
            {
                "answer": "Document summary answer",
                "intent": "summary",
                "retrieval_mode": "head",
                "answer_status": "answered",
                "citations": [],
            },
        )

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
