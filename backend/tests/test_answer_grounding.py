import unittest

from backend.services.answer_grounding import find_grounding_failure
from backend.services.calculator import Calculation


BALANCE_SHEET = "Year Ended December 31, 2017 2016. Total net sales 177,866 135,987 (in millions). Accounts payable 34,616 25,309. Tax rate (0.6)%"


class AnswerGroundingTestCase(unittest.TestCase):
    def assert_grounded(self, answer, excerpt=BALANCE_SHEET, question=""):
        self.assertIsNone(find_grounding_failure(answer, [excerpt], question))

    def assert_rejected(self, answer, reason, excerpt=BALANCE_SHEET, question=""):
        failure = find_grounding_failure(answer, [excerpt], question)
        self.assertIsNotNone(failure)
        self.assertEqual(failure["reason"], reason)

    def test_numbers_match_by_value_across_formats_units_and_rounding(self):
        self.assert_grounded("Net sales were $177,866 million.")
        self.assert_grounded("Net sales were $177.9 billion.")
        self.assert_grounded("The tax rate was -0.6%.")

    def test_a_table_figure_restated_in_larger_units_matches_digit_for_digit(self):
        self.assert_grounded("Operating cash flow was 381.603.", excerpt="Net cash provided 381,603 (in thousands)")
        self.assert_rejected("Operating cash flow was 381.7.", "unsupported_numbers", excerpt="Net cash provided 381,603")

    def test_an_invented_number_is_rejected(self):
        self.assert_rejected("Accounts payable was $36,000 million.", "unsupported_numbers")

    def test_numbers_from_the_question_are_allowed(self):
        self.assert_grounded("Using 365 days, see the working.", question="DPO is 365 times payables over COGS.")

    def test_a_yes_no_answer_without_shared_words_is_not_blocked(self):
        self.assert_grounded("Yes. The company retained its card members.", excerpt="Card Members in force grew.")

    def test_a_calculated_number_passes_when_its_working_is_shown_and_correct(self):
        self.assert_grounded("Net sales grew 30.8% in 2017: (177,866 − 135,987) ÷ 135,987 × 100 = 30.8%.")
        self.assert_grounded("In 2017 (177,866 − 135,987) ÷ 135,987 = 30.8%.")

    def test_a_negative_result_counts_as_shown_working(self):
        self.assert_grounded("Payables fell: 25,309 − 34,616 = −9,307 million.")
        self.assert_rejected("Payables fell: 25,309 − 34,616 = −9,400 million.", "calculation_incorrect")

    def test_working_may_start_with_a_negative_number(self):
        self.assert_grounded("Return: -546 ÷ ((38,363 + 32,963) ÷ 2) = -0.02", excerpt="Net loss (546). Assets 38,363 32,963")

    def test_a_checked_result_can_feed_the_next_step_with_labels_in_between(self):
        self.assert_grounded("Sales plus payables = Net sales 177,866 + Accounts payable 34,616 = 212,482. "
                             "Share = 177,866 ÷ 212,482 × 100 = 83.7%.")

    def test_working_with_notes_and_narrow_spaces_is_read(self):
        self.assert_grounded("Sum = Net sales $177,866\u202fmillion (from the income statement) + Accounts payable & other "
                             "$34,616\u202fmillion = $212,482\u202fmillion.")

    def test_wrong_arithmetic_is_rejected(self):
        self.assert_rejected("Growth: (177,866 − 135,987) ÷ 135,987 × 100 = 31.5%.", "calculation_incorrect")

    def test_an_average_can_use_standard_constants(self):
        self.assert_grounded("Average payables: (34,616 + 25,309) ÷ 2 = 29,962.5 million.")

    def test_working_with_an_invented_operand_is_rejected(self):
        self.assert_rejected("Growth: (190,000 − 135,987) ÷ 135,987 × 100 = 39.7%.", "unsupported_numbers")

    def test_a_calculated_number_without_working_is_rejected(self):
        self.assert_rejected("Net sales grew 30.8% in 2017.", "unsupported_numbers")

    def test_no_evidence_is_a_failure(self):
        self.assertEqual(find_grounding_failure("Anything.", [], "")["reason"], "no_evidence")

    def test_calculator_results_back_bare_and_rounded_numbers(self):
        margins = "Operating income 6,098 5,802. Total revenue 17,606 15,785."
        calculations = [
            Calculation("6098 / 17606 * 100", 34.6359),
            Calculation("5802 / 15785 * 100", 36.7564),
            Calculation("36.7564 - 34.6359", 2.1205),
        ]
        self.assertIsNone(find_grounding_failure("The margin fell to 34.6%.", [margins], "", calculations))
        # Subtracting the rounded margins gives 2.2, but the calculator worked from the exact ones.
        answer = "Margins were 36.8% and 34.6%: 36.8% − 34.6% = 2.1 percentage points."
        self.assertIsNone(find_grounding_failure(answer, [margins], "", calculations))

    def test_working_that_ends_in_a_calculator_result_may_use_constants(self):
        # The model asked for 6098/17606 and wrote the × 100 itself (seen in the first calculator run).
        answer = "Giving (6,098 ÷ 17,606) × 100 = 34.6%."
        calculations = [Calculation("6098/17606", 0.346359)]
        self.assertIsNone(find_grounding_failure(answer, ["Operating income 6,098. Revenue 17,606."], "", calculations))

    def test_a_chain_that_restates_the_same_value_vouches_for_its_figures(self):
        excerpt = "Accounts payable 25,309 34,616. Cost of sales 111,934. Inventories 16,047 11,461."
        answer = "DPO = 365 × ((25,309 + 34,616) / 2) / (111,934 + (16,047 − 11,461)) = 365 × 29,962.5 / 116,520 = 93.86 days."
        self.assertIsNone(find_grounding_failure(answer, [excerpt], "DPO is 365 times average payables."))
        wrong = answer.replace("= 93.86", "= 95.10")
        self.assertEqual(find_grounding_failure(wrong, [excerpt], "DPO is 365 times average payables.")["reason"], "calculation_incorrect")

    def test_a_chain_may_carry_units_between_its_steps(self):
        excerpt = "Cash and cash equivalents 689. Trade receivables 1,875. Total current liabilities 4,476."
        answer = "( $689 million + $1,875 million ) ÷ $4,476 million = $2,564 million ÷ $4,476 million = 0.5728 (≈0.57)."
        self.assertIsNone(find_grounding_failure(answer, [excerpt]))

    def test_a_calculation_from_an_invented_input_vouches_for_nothing(self):
        calculations = [Calculation("190000 / 135987 * 100", 139.72)]
        failure = find_grounding_failure("Sales were 139.7% of the prior year.", [BALANCE_SHEET], "", calculations)
        self.assertEqual(failure["reason"], "unsupported_numbers")


if __name__ == "__main__":
    unittest.main()
