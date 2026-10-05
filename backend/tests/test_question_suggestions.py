import unittest
from types import SimpleNamespace
from unittest.mock import patch

from backend.routers.documents import get_document_question_suggestions
from backend.services.question_suggestions import (
    QuestionSuggestionDependencies,
    SuggestionGenerationError,
    generate_question_suggestions,
)
from backend.services.rag_pipeline import RetrievedContext


class FakeRetriever:
    def __init__(self, text: str):
        self.text = text

    def count(self):
        return 2

    def retrieve(self, mode, question, limit):
        self.request = (mode, question, limit)
        return RetrievedContext(text=self.text, citations=[], retrieved_document_count=2)


class FakeGenerator:
    def __init__(self, response: str):
        self.response = response
        self.prompt = ""

    def invoke(self, prompt: str):
        self.prompt = prompt
        return SimpleNamespace(content=self.response)


class QuestionSuggestionTests(unittest.TestCase):
    def test_generates_document_specific_questions_from_head_context(self):
        retriever = FakeRetriever("The policy allows cancellation within 30 days. Enterprise plans require notice.")
        generator = FakeGenerator(
            '{"questions":["What is the cancellation window?","Which plans require notice","What does the policy require?"]}'
        )

        questions = generate_question_suggestions(
            "doc-1",
            dependencies=QuestionSuggestionDependencies(
                retrieval_factory=lambda _document_id: retriever,
                generation=generator,
            ),
        )

        self.assertEqual(
            questions,
            [
                "What is the cancellation window?",
                "Which plans require notice?",
                "What does the policy require?",
            ],
        )
        self.assertEqual(retriever.request, ("head", "", 2))
        self.assertIn("cancellation within 30 days", generator.prompt)

    def test_returns_no_suggestions_when_the_document_has_no_context(self):
        retriever = FakeRetriever("")
        generator = FakeGenerator('{"questions":["Should not run?"]}')

        questions = generate_question_suggestions(
            "doc-1",
            dependencies=QuestionSuggestionDependencies(
                retrieval_factory=lambda _document_id: retriever,
                generation=generator,
            ),
        )

        self.assertEqual(questions, [])
        self.assertEqual(generator.prompt, "")

    def test_rejects_an_invalid_generation_contract(self):
        retriever = FakeRetriever("Useful document context")
        generator = FakeGenerator("not-json")

        with self.assertRaises(SuggestionGenerationError):
            generate_question_suggestions(
                "doc-1",
                dependencies=QuestionSuggestionDependencies(
                    retrieval_factory=lambda _document_id: retriever,
                    generation=generator,
                ),
            )


class QuestionSuggestionRouteTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        limits = patch("backend.routers.documents.cached_suggestions", side_effect=lambda user, doc, generate: generate(doc))
        limits.start()
        self.addCleanup(limits.stop)

    @patch("backend.routers.documents.generate_question_suggestions")
    @patch("backend.routers.documents.require_user_document")
    async def test_route_authorizes_the_document_before_generating_questions(
        self,
        require_document,
        generate_suggestions,
    ):
        generate_suggestions.return_value = ["What is the cancellation window?"]

        response = await get_document_question_suggestions("doc-1", user_id="user-1")

        require_document.assert_called_once_with(document_id="doc-1", user_id="user-1")
        generate_suggestions.assert_called_once_with("doc-1")
        self.assertEqual(response.suggestions, ["What is the cancellation window?"])

    async def test_concurrent_request_waits_for_the_existing_suggestion_result(self):
        from backend.services.demo_limits import SuggestionsPendingError
        with (
            patch("backend.routers.documents.require_user_document"),
            patch("backend.routers.documents.cached_suggestions", side_effect=[
                SuggestionsPendingError(), SuggestionsPendingError(), ["What is the cancellation window?"],
            ]) as cached,
            patch("backend.routers.documents.generate_question_suggestions") as generate,
        ):
            response = await get_document_question_suggestions("doc-1", user_id="user-1")
        self.assertEqual(response.suggestions, ["What is the cancellation window?"])
        self.assertEqual(cached.call_count, 3)
        generate.assert_not_called()


if __name__ == "__main__":
    unittest.main()
