import unittest

from backend.services.pdf_extractor import _extract_page_text, _serialize_table


class FakeTable:
    def __init__(self, rows, bbox=(0.0, 100.0, 100.0, 200.0)):
        self._rows = rows
        self.bbox = bbox

    def extract(self):
        return self._rows


class FakePage:
    def __init__(self, words, tables):
        self._words = words
        self._tables = tables

    def extract_words(self, use_text_flow=True):
        return self._words

    def find_tables(self):
        return self._tables


class PdfExtractorTestCase(unittest.TestCase):
    def test_word_reconstruction_preserves_financial_number_tokens(self):
        page = FakePage(
            words=[
                {"text": "Total", "x0": 0, "x1": 20, "top": 0, "bottom": 10},
                {"text": "net", "x0": 25, "x1": 40, "top": 0, "bottom": 10},
                {"text": "sales", "x0": 45, "x1": 70, "top": 0, "bottom": 10},
                {"text": "$", "x0": 80, "x1": 85, "top": 0, "bottom": 10},
                {"text": "170,910", "x0": 90, "x1": 130, "top": 0, "bottom": 10},
            ],
            tables=[],
        )

        self.assertIn("Total net sales $ 170,910", _extract_page_text(page))

    def test_structured_year_table_repeats_merged_year_values(self):
        rows = [
            ["Year", "Title", "Role", "Notes"],
            ["2010", "Amigo", "Gil", ""],
            [None, "At Risk", "Cal Tradd", ""],
            ["2012", "Chronicle", "Andrew Detmer", ""],
            [None, "Jack & Diane", "Chris", ""],
        ]

        serialized = _serialize_table(rows)

        self.assertIsNotNone(serialized)
        self.assertIn("2010 | At Risk | Cal Tradd |", serialized)
        self.assertIn("2012 | Jack & Diane | Chris |", serialized)

    def test_structured_table_replaces_flattened_words(self):
        table = FakeTable(
            [
                ["Year", "Title", "Role"],
                ["2012", "Chronicle", "Andrew Detmer"],
                [None, "Jack & Diane", "Chris"],
            ],
            bbox=(0.0, 10.0, 200.0, 40.0),
        )
        words = [
            {"text": "Filmography", "x0": 0, "x1": 60, "top": 0, "bottom": 8},
            {"text": "2012", "x0": 0, "x1": 20, "top": 20, "bottom": 28},
            {"text": "Chronicle", "x0": 25, "x1": 70, "top": 20, "bottom": 28},
        ]

        text = _extract_page_text(FakePage(words, [table]))

        self.assertEqual(text, "Filmography\nYear | Title | Role\n--- | --- | ---\n2012 | Chronicle | Andrew Detmer\n2012 | Jack & Diane | Chris")


if __name__ == "__main__":
    unittest.main()
