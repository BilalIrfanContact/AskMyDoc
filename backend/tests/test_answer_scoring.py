import unittest

from backend.scripts.answer_scoring import number_matches, score_answer


ANSWERED = {"answer_status": "answered"}
FALLBACK = {"answer_status": "insufficient_context", "answer": "I couldn't find enough information in the document to answer that question."}


def run(answer):
    return {**ANSWERED, "answer": answer}


def grader(**overrides):
    reply = {"facts_complete": True, "no_contradiction": True, "right_subject": True, "verdict": "not_applicable", "reason": "ok"}
    reply.update(overrides)
    prompts = []

    def grade(prompt):
        prompts.append(prompt)
        return reply

    grade.prompts = prompts
    return grade


class NumberMatchTestCase(unittest.TestCase):
    def test_tolerance_is_half_the_last_shown_decimal(self):
        self.assertTrue(number_matches("93.86", "DPO is 93.857 days."))
        self.assertFalse(number_matches("93.86", "DPO is 93.83 days."))
        self.assertTrue(number_matches("30.8%", "Revenue grew 30.8%."))
        self.assertFalse(number_matches("30.8%", "Revenue grew 30.9%."))

    def test_units_and_formatting_are_normalised(self):
        self.assertTrue(number_matches("$8.74 billion", "Net PP&E was $8,738 million."))
        self.assertTrue(number_matches("$9,068 million", "EBITDA less capex was 9068.00."))
        self.assertTrue(number_matches("$1,577 million", "Capex was $1.577 billion."))
        self.assertFalse(number_matches("$8.74 billion", "Net PP&E was $8.70 billion."))

    def test_percent_and_plain_ratios_do_not_mix(self):
        self.assertFalse(number_matches("0.761", "The ratio is 76.1%."))
        self.assertTrue(number_matches("2.1 percentage points", "a drop of 2.12 percentage points"))

    def test_brackets_mean_negative_and_explicit_signs_must_match(self):
        self.assertTrue(number_matches("-0.6%", "Boeing reports an effective tax rate of (0.6)%."))
        self.assertTrue(number_matches("-3.0 percentage points", "The rate declined 3.0 percentage points."))
        self.assertFalse(number_matches("-0.6%", "The effective tax rate was -0.8%."))
        self.assertFalse(number_matches("14.8%", "The rate was -14.8%."))


class ScoreAnswerTestCase(unittest.TestCase):
    def test_abstain_cases_pass_only_on_the_fallback(self):
        case = {"expected": "abstain"}
        self.assertTrue(score_answer(case, FALLBACK, None)["passed"])
        self.assertFalse(score_answer(case, run("Amazon had 100 million Prime members."), None)["passed"])

    def test_zero_or_not_found_rule(self):
        case = {"expected": "answer", "answer_format": "numeric", "scoring": "zero_or_not_found"}
        self.assertTrue(score_answer(case, FALLBACK, None)["passed"])
        self.assertTrue(score_answer(case, run("0 — no restructuring line appears in the FY2022 statement."), None)["passed"])
        self.assertFalse(score_answer(case, run("Restructuring costs were $19 million."), None)["passed"])
        self.assertFalse(score_answer(case, run("The FY2022 statement discusses restructuring costs."), None)["passed"])

    def test_declining_an_answerable_question_fails(self):
        case = {"expected": "answer", "answer_format": "numeric", "key_values": ["93.86"]}
        self.assertEqual(score_answer(case, FALLBACK, None)["method"], "declined")

    def test_numeric_cases_use_code_only_and_accept_any_listed_method(self):
        case = {"expected": "answer", "answer_format": "numeric", "acceptable_answers": ["9.5", "12.1"]}
        must_not_grade = grader()
        self.assertTrue(score_answer(case, run("About 12.1 times."), must_not_grade)["passed"])
        self.assertFalse(score_answer(case, run("About 10 times."), must_not_grade)["passed"])
        self.assertEqual(must_not_grade.prompts, [])

    def test_yes_no_needs_matching_verdict_and_key_numbers(self):
        case = {
            "expected": "answer",
            "answer_format": "yes_no",
            "question": "Did Microsoft increase its debt?",
            "expected_answer": "No. Microsoft decreased its debt by $2.5bn.",
            "key_values": ["$2.5 billion"],
        }
        self.assertTrue(score_answer(case, run("Debt fell by $2.5 billion."), grader(verdict="no"))["passed"])
        wrong_verdict = score_answer(case, run("Debt rose by $2.5 billion."), grader(verdict="yes"))
        self.assertFalse(wrong_verdict["passed"])
        self.assertIn("verdict yes (expected no)", wrong_verdict["reason"])
        self.assertFalse(score_answer(case, run("Debt fell by $4 billion."), grader(verdict="no"))["passed"])
        self.assertFalse(score_answer(case, run("It depends on how debt is defined."), grader(verdict="none"))["passed"])

    def test_prose_fails_when_any_checklist_item_fails_and_passes_the_grader_note(self):
        case = {
            "expected": "answer",
            "answer_format": "prose",
            "question": "What drove AMD's lower operating income?",
            "expected_answer": "Amortization of Xilinx intangibles, higher R&D, and inventory charges.",
            "grader_note": "Either total or clearly labelled partial counts are fine.",
        }
        grade = grader()
        self.assertTrue(score_answer(case, run("Amortization, R&D and inventory charges."), grade)["passed"])
        self.assertIn("Grading note: Either total", grade.prompts[0])
        self.assertFalse(score_answer(case, run("Amortization only."), grader(facts_complete=False))["passed"])

    def test_an_unusable_grader_reply_fails_the_answer(self):
        case = {"expected": "answer", "answer_format": "prose", "expected_answer": "Data Center"}

        def broken(prompt):
            raise ValueError("not json")

        result = score_answer(case, run("Data Center"), broken)
        self.assertFalse(result["passed"])
        self.assertIn("grader reply unusable", result["reason"])


if __name__ == "__main__":
    unittest.main()
