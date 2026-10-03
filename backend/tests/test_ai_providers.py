import os
import tempfile
import unittest
from types import SimpleNamespace
from unittest.mock import Mock, patch

import openai

from backend.services import usage_ledger
from backend.services.ai_providers import MeteredChat, VoyageEmbeddings


class UsageTestCase(unittest.TestCase):
    def setUp(self):
        self._dir = tempfile.TemporaryDirectory()
        self._env = patch.dict(os.environ, {"AI_USAGE_DIR": self._dir.name, "AI_MONTHLY_BUDGET_USD": "5"})
        self._env.start()

    def tearDown(self):
        self._env.stop()
        self._dir.cleanup()


class MeteredChatTestCase(UsageTestCase):
    def test_records_the_tokens_groq_reported(self):
        llm = Mock()
        llm.invoke.return_value = SimpleNamespace(content="ok", usage_metadata={"input_tokens": 1200, "output_tokens": 30})

        with patch("backend.services.ai_providers.ChatOpenAI", return_value=llm):
            MeteredChat("rerank", "openai/gpt-oss-20b").invoke("pick the chunks")

        [entry] = usage_ledger.read_entries()
        self.assertEqual((entry["task"], entry["input_tokens"], entry["output_tokens"]), ("rerank", 1200, 30))

    def test_labels_use_low_reasoning_effort_and_other_jobs_keep_the_default(self):
        llm = Mock()
        llm.invoke.return_value = SimpleNamespace(content="ok", usage_metadata={"input_tokens": 10, "output_tokens": 5})

        with patch("backend.services.ai_providers.ChatOpenAI", return_value=llm) as chat_openai:
            MeteredChat("label").invoke("label this chunk")
            MeteredChat("answer").invoke("answer this")

        label_call, answer_call = chat_openai.call_args_list
        self.assertEqual(label_call.kwargs["model_kwargs"], {"reasoning_effort": "low"})
        self.assertEqual(answer_call.kwargs["model_kwargs"], {})

    def test_tool_calls_pass_the_tools_and_are_metered(self):
        llm = Mock()
        llm.invoke.return_value = SimpleNamespace(content="ok", usage_metadata={"input_tokens": 900, "output_tokens": 40})
        tools = [{"type": "function", "function": {"name": "calculate"}}]

        with patch("backend.services.ai_providers.ChatOpenAI", return_value=llm):
            MeteredChat("answer").invoke_with_tools(["question"], tools)

        self.assertEqual(llm.invoke.call_args.kwargs["tools"], tools)
        [entry] = usage_ledger.read_entries()
        self.assertEqual((entry["task"], entry["input_tokens"]), ("answer", 900))

    def test_a_rejected_tool_call_is_sent_again(self):
        rejected = openai.BadRequestError("tool_use_failed", response=Mock(status_code=400, request=Mock()), body=None)
        llm = Mock()
        llm.invoke.side_effect = [rejected, SimpleNamespace(content="ok", usage_metadata={"input_tokens": 9, "output_tokens": 1})]

        with patch("backend.services.ai_providers.ChatOpenAI", return_value=llm):
            reply = MeteredChat("answer").invoke_with_tools(["question"], [])

        self.assertEqual(reply.content, "ok")
        self.assertEqual(llm.invoke.call_count, 2)

    def test_a_reply_sent_as_a_call_to_an_unknown_json_tool_is_recovered(self):
        # The error Groq returned in the first calculator run, trimmed.
        error = {
            "message": "attempted to call tool 'json' which was not in request.tools",
            "code": "tool_use_failed",
            "failed_generation": '{"name": "json", "arguments": {"found_in_excerpts": true, "answer": "It fell 3.0 points."}}',
        }
        rejected = openai.BadRequestError("tool_use_failed", response=Mock(status_code=400, request=Mock()), body=error)
        llm = Mock()
        llm.invoke.side_effect = rejected
        tools = [{"type": "function", "function": {"name": "calculate"}}]

        with patch("backend.services.ai_providers.ChatOpenAI", return_value=llm):
            reply = MeteredChat("answer").invoke_with_tools(["question"], tools)

        self.assertEqual(reply.content, '{"found_in_excerpts": true, "answer": "It fell 3.0 points."}')
        self.assertEqual(llm.invoke.call_count, 1)
        self.assertEqual(len(usage_ledger.read_entries()), 1)

    def test_does_not_call_the_model_once_the_budget_is_spent(self):
        usage_ledger.record("groq", "openai/gpt-oss-120b", "answer", 40_000_000)

        with patch("backend.services.ai_providers.ChatOpenAI") as chat_openai:
            with self.assertRaises(usage_ledger.BudgetExceeded):
                MeteredChat("answer").invoke("question")
        chat_openai.assert_not_called()


class VoyageEmbeddingsTestCase(UsageTestCase):
    def test_embeds_questions_as_queries_and_records_the_tokens(self):
        response = Mock(status_code=200)
        response.json.return_value = {"data": [{"index": 0, "embedding": [0.1, 0.2]}], "usage": {"total_tokens": 12}}

        with patch("backend.services.ai_providers.httpx.post", return_value=response) as post:
            vector = VoyageEmbeddings("voyage-4-lite").embed_query("What were total assets?")

        self.assertEqual(vector, [0.1, 0.2])
        self.assertEqual(post.call_args.kwargs["json"]["input_type"], "query")
        [entry] = usage_ledger.read_entries()
        self.assertEqual((entry["task"], entry["input_tokens"]), ("embed-query", 12))


if __name__ == "__main__":
    unittest.main()
