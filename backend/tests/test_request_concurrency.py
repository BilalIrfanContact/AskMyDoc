import asyncio
import threading
import unittest
from contextlib import ExitStack
from unittest.mock import patch

import httpx
from fastapi import FastAPI

from backend.routers import chat, conversations, documents, upload
from backend.services.document_lifecycle import DeleteLifecycleResult
from backend.services.internal_auth import require_authenticated_user
from backend.services.rag_pipeline import AnswerDecision


class RequestConcurrencyTestCase(unittest.IsolatedAsyncioTestCase):
    async def test_unrelated_requests_finish_while_blocking_work_is_pending(self):
        app = FastAPI()
        for router in (chat.router, conversations.router, documents.router, upload.router):
            app.include_router(router)
        app.dependency_overrides[require_authenticated_user] = lambda: "user-a"

        @app.get("/health")
        async def health():
            return {"status": "ok"}

        document = {
            "id": "doc-a", "user_id": "user-a", "filename": "report.pdf",
            "storage_url": "pdfs/user-a/doc-a/report.pdf",
        }
        conversation = {"id": "convo-a", "user_id": "user-a", "document_id": "doc-a"}
        results = {
            "backend.services.conversation_turn.require_user_conversation": conversation,
            "backend.services.conversation_turn.load_turn_history": (),
            "backend.services.conversation_turn.answer_question": AnswerDecision(
                answer="The refund window is 30 days.", intent="qa", retrieval_mode="semantic",
                answer_status="answered", citations=[],
            ),
            "backend.services.document_lifecycle.extract_text_from_pdf": "Refunds within 30 days.",
            "backend.services.document_lifecycle.chunk_text": ["Refunds within 30 days."],
            "backend.services.document_lifecycle.build_vector_store": 1,
            "backend.services.document_lifecycle.upload_file_to_storage": document["storage_url"],
            "backend.services.document_lifecycle.insert_document": document,
            "backend.routers.documents.list_user_documents": [document],
            "backend.routers.documents.require_user_document": document,
            "backend.routers.documents.delete_document_lifecycle": DeleteLifecycleResult(
                status="completed", http_status=200, cleanup_status="completed",
            ),
            "backend.routers.documents.generate_question_suggestions": ["What is the refund window?"],
            "backend.routers.conversations.require_user_document": document,
            "backend.routers.conversations.require_user_conversation": conversation,
            "backend.routers.conversations.list_user_conversations": [conversation],
            "backend.routers.conversations.create_conversation": "convo-a",
            "backend.routers.conversations.list_conversation_messages": [],
        }
        cases = [
            ("chat generation", "backend.services.conversation_turn.answer_question", "POST", "/chat", {
                "json": {"request_id": "00000000-0000-4000-8000-000000000001", "document_id": "doc-a", "conversation_id": "convo-a", "message": "Refund window?"},
            }),
            ("upload extraction", "backend.services.document_lifecycle.extract_text_from_pdf", "POST", "/upload", {
                "files": {"file": ("report.pdf", b"%PDF-test", "application/pdf")},
            }),
            ("upload indexing", "backend.services.document_lifecycle.build_vector_store", "POST", "/upload", {
                "files": {"file": ("report.pdf", b"%PDF-test", "application/pdf")},
            }),
            ("document listing", "backend.routers.documents.list_user_documents", "GET", "/documents", {}),
            ("document deletion", "backend.routers.documents.delete_document_lifecycle", "DELETE", "/documents/doc-a", {}),
            ("conversation listing", "backend.routers.conversations.list_user_conversations", "GET", "/conversations?document_id=doc-a", {}),
            ("conversation creation", "backend.routers.conversations.create_conversation", "POST", "/conversations", {
                "json": {"document_id": "doc-a"},
            }),
            ("message history", "backend.routers.conversations.list_conversation_messages", "GET", "/conversations/convo-a/messages", {}),
            ("suggestion ownership", "backend.routers.documents.require_user_document", "GET", "/documents/doc-a/suggestions", {}),
            ("suggestion generation", "backend.routers.documents.generate_question_suggestions", "GET", "/documents/doc-a/suggestions", {}),
        ]

        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://testserver") as client:
            for label, blocked_call, method, path, kwargs in cases:
                with self.subTest(workflow=label), ExitStack() as stack:
                    stack.enter_context(patch("backend.routers.upload.operation", return_value={"id": "upload-a"}))
                    stack.enter_context(patch("backend.routers.documents.cached_suggestions", side_effect=lambda user, doc, generate: generate(doc)))
                    for target, result in results.items():
                        stack.enter_context(patch(target, return_value=result))

                    def transition(action, **kwargs):
                        if action == "claim":
                            return {"state": "generating"}
                        if action == "save":
                            return {"state": "generated", "result": kwargs["result"]}
                        return {"state": "completed", "result": vars(results["backend.services.conversation_turn.answer_question"])}
                    stack.enter_context(patch("backend.services.conversation_turn.transition_turn", side_effect=transition))
                    started = threading.Event()
                    release = threading.Event()
                    expired = threading.Event()

                    def blocking_call(*args, **kwargs):
                        started.set()
                        # A safety deadline makes the unfixed implementation fail instead of deadlocking.
                        if not release.wait(timeout=5):
                            expired.set()
                        return results[blocked_call]

                    stack.enter_context(patch(blocked_call, side_effect=blocking_call))
                    request = asyncio.create_task(client.request(method, path, **kwargs))
                    try:
                        began = await asyncio.wait_for(asyncio.to_thread(started.wait, 10), timeout=12)
                        self.assertTrue(began, "The request did not reach the blocking operation")
                        probe = await asyncio.wait_for(client.get("/health"), timeout=2)
                        self.assertEqual(probe.status_code, 200)
                        self.assertEqual(probe.json(), {"status": "ok"})
                        self.assertFalse(expired.is_set(), "The event loop stalled until the blocking work expired")
                        self.assertFalse(request.done(), "The unrelated request must finish before the blocked request")
                    finally:
                        release.set()
                        response = await asyncio.wait_for(request, timeout=5)
                    self.assertEqual(response.status_code, 200, response.text)


if __name__ == "__main__":
    unittest.main()
