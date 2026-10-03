import unittest

from backend.services.answer_grounding import find_grounding_failure


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


if __name__ == "__main__":
    unittest.main()
