import unittest
from types import SimpleNamespace

from backend.services.evidence_planner import plan_evidence
from backend.services.rag_adapters import select_with_reserved_slots


class FakeGenerator:
    def __init__(self, reply):
        self.reply = reply
        self.prompts = []

    def invoke(self, prompt):
        self.prompts.append(prompt)
        return SimpleNamespace(content=self.reply)


class EvidencePlannerTestCase(unittest.TestCase):
    def test_plan_returns_distinct_needs_capped_at_four(self):
        generator = FakeGenerator('{"needs": ["net income", "Net income", "total assets 2022", "total assets 2021", "a", "b"]}')

        self.assertEqual(plan_evidence("What is ROA?", generator), ["net income", "total assets 2022", "total assets 2021", "a"])
        self.assertIn("Do not calculate anything", generator.prompts[0])

    def test_an_unusable_plan_falls_back_to_no_needs(self):
        self.assertEqual(plan_evidence("What is ROA?", FakeGenerator("not json")), [])


class ReservedSlotsTestCase(unittest.TestCase):
    def test_each_need_gets_a_slot_before_the_question_fills_the_rest(self):
        question = ["prose-1", "prose-2", "prose-3", "prose-4"]
        needs = [["income-statement", "prose-1"], ["balance-sheet", "prose-2"]]

        self.assertEqual(
            select_with_reserved_slots(question, needs, 4),
            ["income-statement", "balance-sheet", "prose-1", "prose-2"],
        )

    def test_without_needs_the_question_ranking_is_kept(self):
        self.assertEqual(select_with_reserved_slots(["a", "b", "c"], [], 2), ["a", "b"])

    def test_needs_sharing_a_best_chunk_take_their_next_best(self):
        self.assertEqual(select_with_reserved_slots(["q"], [["x", "y"], ["x", "z"]], 3), ["x", "z", "q"])


if __name__ == "__main__":
    unittest.main()
