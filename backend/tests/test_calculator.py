import unittest
from types import SimpleNamespace

from backend.services.calculator import MAX_ROUNDS, answer_with_calculator, evaluate


FINAL = SimpleNamespace(content='{"found_in_excerpts": true, "answer": "34.6%"}', tool_calls=[])


def asks(*expressions):
    return SimpleNamespace(
        content="",
        tool_calls=[{"id": f"call-{i}", "name": "calculate", "args": {"expression": e}} for i, e in enumerate(expressions)],
    )


class ToolModel:
    """A fake tool-calling model that replies from a script and records what it was sent."""

    supports_tools = True

    def __init__(self, *replies):
        self.replies = list(replies)
        self.sent = []

    def invoke_with_tools(self, messages, tools):
        self.sent.append(list(messages))
        return self.replies.pop(0) if len(self.replies) > 1 else self.replies[0]


class EvaluateTestCase(unittest.TestCase):
    def test_reads_the_arithmetic_models_write(self):
        self.assertAlmostEqual(evaluate("(177,866 − 135,987) ÷ 135,987 × 100"), 30.7963, places=4)
        self.assertEqual(evaluate("-546 / ((38363 + 32963) / 2)"), -546 / 35663)
        self.assertEqual(evaluate("\u2011546 / 2"), -273.0)

    def test_refuses_anything_that_is_not_plain_arithmetic(self):
        self.assertIsNone(evaluate("__import__('os').system('ls')"))
        self.assertIsNone(evaluate("2 ** 1000"))
        self.assertIsNone(evaluate("1 / 0"))
        self.assertIsNone(evaluate("revenue / 2"))


class AnswerWithCalculatorTestCase(unittest.TestCase):
    def test_sends_each_exact_result_back_and_returns_the_calculations(self):
        model = ToolModel(asks("6098 / 17606 * 100", "5802 / 15785 * 100"), FINAL)

        response, calculations = answer_with_calculator(model, "question")

        self.assertIs(response, FINAL)
        self.assertEqual([c.expression for c in calculations], ["6098 / 17606 * 100", "5802 / 15785 * 100"])
        results = [m.content for m in model.sent[1][2:]]
        self.assertEqual(results, ["34.63591957", "36.75641432"])

    def test_an_invalid_expression_gets_an_error_and_is_not_recorded(self):
        model = ToolModel(asks("revenue / 2"), FINAL)

        _, calculations = answer_with_calculator(model, "question")

        self.assertEqual(calculations, [])
        self.assertTrue(model.sent[1][-1].content.startswith("error"))

    def test_stops_after_the_round_limit(self):
        model = ToolModel(asks("1 + 1"))

        answer_with_calculator(model, "question")

        self.assertEqual(len(model.sent), MAX_ROUNDS)

    def test_a_model_without_tool_support_is_called_once_with_the_prompt(self):
        plain = SimpleNamespace(invoke=lambda prompt: FINAL)

        self.assertEqual(answer_with_calculator(plain, "question"), (FINAL, []))


if __name__ == "__main__":
    unittest.main()
