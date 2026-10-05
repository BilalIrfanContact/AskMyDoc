import unittest

from backend.scripts.build_eval_cases import build_case, chunk_pages, select_chunks, tokens


PAGES = [
    "Cover page. Annual report pursuant to section 13.",
    "",
    "Accounts payable 25,309 34,616\nInventories 11,461 16,047",
    "Risk factors about competition and suppliers.",
]
CHUNKS = [
    ("doc:chunk:0", "Cover page. Annual report pursuant to section 13."),
    ("doc:chunk:1", "Accounts payable 25,309 34,616"),
    ("doc:chunk:2", "Inventories 11,461 16,047\n\nRisk factors about competition"),
    ("doc:chunk:3", "Risk factors about competition and suppliers."),
]


class BuildEvalCasesTestCase(unittest.TestCase):
    def test_tokens_drop_thousands_separators_and_short_words(self):
        self.assertEqual(tokens("Net sales of $25,309 in FY"), {"net", "sales", "25309"})

    def test_chunk_pages_uses_zero_indexed_pdf_pages_and_spans_page_breaks(self):
        located = chunk_pages(PAGES, CHUNKS)

        self.assertEqual(located["doc:chunk:0"], {0})
        self.assertEqual(located["doc:chunk:1"], {2})
        self.assertEqual(located["doc:chunk:2"], {2, 3})

    def test_select_chunks_picks_the_fewest_chunks_that_cover_the_evidence(self):
        chosen, coverage = select_chunks(
            "Accounts payable 25309 34616 Inventories 11461 16047",
            CHUNKS[1:3],
        )

        self.assertEqual(chosen, ["doc:chunk:1", "doc:chunk:2"])
        self.assertEqual(coverage, 1.0)

    def test_build_case_maps_gold_chunks_from_the_evidence_page(self):
        case = build_case(
            {
                "case_id": "dpo",
                "question": "What is DPO?",
                "expected": "answer",
                "gold_evidence_text": ["Accounts payable $ 25,309 $ 34,616"],
                "gold_page": [2],
                "acceptable_answers": ["93.86", "94.10"],
            },
            "doc",
            PAGES,
            CHUNKS,
        )

        self.assertEqual(case["document_id"], "doc")
        self.assertEqual(case["gold_chunk_ids"], ["doc:chunk:1"])
        self.assertEqual(case["gold_mapping"]["status"], "matched")
        self.assertEqual(case["acceptable_answers"], ["93.86", "94.10"])

    def test_build_case_flags_review_and_points_elsewhere_when_the_page_lacks_the_evidence(self):
        case = build_case(
            {
                "case_id": "wrong-page",
                "question": "What are the risks?",
                "expected": "answer",
                "gold_evidence_text": ["Risk factors about competition and suppliers"],
                "gold_page": [0],
            },
            "doc",
            PAGES,
            CHUNKS,
        )

        evidence = case["gold_mapping"]["evidence"][0]
        self.assertEqual(case["gold_mapping"]["status"], "review")
        self.assertEqual(evidence["best_chunk_anywhere"], "doc:chunk:3")
        self.assertEqual(evidence["best_coverage_anywhere"], 1.0)

    def test_a_review_note_marks_a_weak_match_as_accepted(self):
        case = build_case(
            {
                "case_id": "glued-words",
                "question": "What was accounts payable?",
                "expected": "answer",
                "gold_evidence_text": ["Accountspayable 25,309 34,616"],
                "gold_page": [2],
                "gold_review_note": "Numbers all match; the quote glues words together.",
            },
            "doc",
            PAGES,
            CHUNKS,
        )

        self.assertEqual(case["gold_chunk_ids"], ["doc:chunk:1"])
        self.assertEqual(case["gold_mapping"]["status"], "accepted")
        self.assertEqual(case["gold_mapping"]["review_note"], "Numbers all match; the quote glues words together.")

    def test_chunks_without_the_answer_are_dropped_from_a_whole_page_quote(self):
        case = build_case(
            {
                "case_id": "payables",
                "question": "What were accounts payable?",
                "expected": "answer",
                "expected_answer": "$25,309 million",
                "gold_evidence_text": ["Accounts payable 25,309 34,616 Inventories 11,461 16,047"],
                "gold_page": [2],
            },
            "doc",
            PAGES,
            CHUNKS,
        )

        self.assertEqual(case["gold_chunk_ids"], ["doc:chunk:1"])
        self.assertEqual(case["gold_mapping"]["evidence"][0]["dropped_chunk_ids"], ["doc:chunk:2"])

    def test_the_chunk_with_the_answer_is_gold_even_after_coverage_is_reached_without_it(self):
        case = build_case(
            {
                "case_id": "inventories",
                "question": "What were inventories?",
                "expected": "answer",
                "expected_answer": "$11,461 million",
                "gold_evidence_text": ["Accounts payable 25,309 34,616 Inventories 11,461"],
                "gold_page": [2],
            },
            "doc",
            PAGES,
            CHUNKS,
            min_coverage=0.6,
        )

        self.assertEqual(case["gold_chunk_ids"], ["doc:chunk:2"])

    def test_calculated_answers_without_anchors_keep_every_selected_chunk(self):
        case = build_case(
            {
                "case_id": "dpo",
                "question": "What is DPO?",
                "expected": "answer",
                "expected_answer": "93.86",
                "gold_evidence_text": ["Accounts payable 25,309 34,616 Inventories 11,461 16,047"],
                "gold_page": [2],
            },
            "doc",
            PAGES,
            CHUNKS,
        )

        self.assertEqual(case["gold_chunk_ids"], ["doc:chunk:1", "doc:chunk:2"])

    def test_recompute_inputs_anchor_a_calculated_answer(self):
        case = build_case(
            {
                "case_id": "dpo",
                "question": "What is DPO?",
                "expected": "answer",
                "expected_answer": "93.86",
                "gold_evidence_text": ["Accounts payable 25,309 34,616 Inventories 11,461 16,047"],
                "gold_page": [2],
            },
            "doc",
            PAGES,
            CHUNKS,
            formula="365 * ((25,309 + 34,616) / 2)",
        )

        self.assertEqual(case["gold_chunk_ids"], ["doc:chunk:1"])

    def test_a_quote_sharing_nothing_with_the_answer_is_not_gold(self):
        case = build_case(
            {
                "case_id": "ppe-share",
                "question": "What share of assets was PP&E?",
                "expected": "answer",
                "expected_answer": "25,309 of 34,616",
                "gold_evidence_text": ["Cover page. Annual report pursuant to section 13.", "Accounts payable 25,309 34,616"],
                "gold_page": [0, 2],
            },
            "doc",
            PAGES,
            CHUNKS,
        )

        self.assertEqual(case["gold_chunk_ids"], ["doc:chunk:1"])
        self.assertTrue(case["gold_mapping"]["evidence"][0]["unused_by_answer"])

    def test_abstain_cases_only_get_a_document_id(self):
        case = build_case(
            {"case_id": "absent", "question": "How many Prime members?", "expected": "abstain"},
            "doc",
            [],
            [],
        )

        self.assertEqual(case["document_id"], "doc")
        self.assertNotIn("gold_chunk_ids", case)


if __name__ == "__main__":
    unittest.main()
