import unittest

from backend.services.keyword_search import bm25_rank, keyword_tokens, reciprocal_rank_fusion


class KeywordSearchTestCase(unittest.TestCase):
    def test_tokens_drop_filler_words_and_thousands_separators(self):
        self.assertEqual(keyword_tokens("What was the total of 25,309?"), ["total", "25309"])

    def test_bm25_ranks_the_table_with_the_exact_line_item_first(self):
        documents = [
            "Management discussed profitability and margins across the programs in detail.",
            "Accounts payable 25,309 34,616 Accrued expenses 13,739 18,170",
            "Inventories 11,461 16,047",
        ]

        self.assertEqual(bm25_rank("What were accounts payable?", documents), [1])

    def test_rank_fusion_rewards_items_ranked_well_in_either_list(self):
        merged = reciprocal_rank_fusion([["a", "b", "c"], ["c", "d"]])

        self.assertEqual(merged[0], "c")
        self.assertEqual(set(merged), {"a", "b", "c", "d"})


if __name__ == "__main__":
    unittest.main()
