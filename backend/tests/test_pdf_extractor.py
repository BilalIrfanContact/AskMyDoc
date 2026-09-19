import unittest

from backend.services.pdf_extractor import (
    _TableContext,
    _extract_page_text,
    _extract_page_text_with_context,
    _serialize_table,
)


class FakeTable:
    def __init__(self, rows, bbox=(0.0, 100.0, 100.0, 200.0)):
        self._rows = rows
        self.bbox = bbox

    def extract(self):
        return self._rows


class FakePage:
    def __init__(self, words, tables, height=1000.0):
        self._words = words
        self._tables = tables
        self.height = height

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

    def test_structured_value_table_repeats_merged_labels(self):
        rows = [
            ["Value", "Mass", "Description"],
            ["$1", "8.10 g", "Susan B. Anthony"],
            [None, "8.10 g", "Apollo 11 mission insignia"],
        ]

        serialized = _serialize_table(rows)

        self.assertIsNotNone(serialized)
        self.assertIn("$1 | 8.10 g | Apollo 11 mission insignia", serialized)

    def test_continuation_page_reuses_table_header_and_last_label(self):
        page = FakePage(
            words=[
                {"text": "8.10", "x0": 0, "x1": 20, "top": 20, "bottom": 28},
                {"text": "g", "x0": 25, "x1": 30, "top": 20, "bottom": 28},
                {"text": "Susan", "x0": 35, "x1": 60, "top": 20, "bottom": 28},
            ],
            tables=[
                FakeTable(
                    [
                        [None, "8.10 g", "Susan B. Anthony"],
                        ["$1", "8.10 g", "Sacagawea"],
                        [None, "8.10 g", "Native American Themes"],
                    ],
                    bbox=(0.0, 400.0, 100.0, 430.0),
                )
            ],
        )
        previous_context = _TableContext(
            ("Value", "Mass", "Description"),
            "$1",
            (0.0, 700.0, 100.0, 730.0),
        )

        text, context = _extract_page_text_with_context(page, previous_context)

        self.assertIn("Value | Mass | Description", text)
        self.assertIn("$1 | 8.10 g | Susan B. Anthony", text)
        self.assertIn("$1 | 8.10 g | Native American Themes", text)
        self.assertEqual(context.first_column_value, "$1")

    def test_continuation_table_can_start_below_page_furniture(self):
        table = FakeTable(
            [
                [None, "8.10 g", "Susan B. Anthony"],
                [None, "8.10 g", "Sacagawea"],
                [None, "8.10 g", "Native American Themes"],
            ],
            bbox=(10.0, 500.0, 110.0, 530.0),
        )
        previous_context = _TableContext(
            ("Value", "Mass", "Description"),
            "$1",
            (10.0, 700.0, 110.0, 730.0),
        )

        text, _context = _extract_page_text_with_context(
            FakePage([], [table]),
            previous_context,
        )

        self.assertIn("Value | Mass | Description", text)
        self.assertIn("$1 | 8.10 g | Susan B. Anthony", text)

    def test_data_rows_are_not_detected_as_headers_by_substring(self):
        rows = [
            ["Massachusetts", "10 years", "evaluation"],
            ["Boston", "5 years", "review"],
            ["Salem", "3 years", "draft"],
        ]

        self.assertIsNone(_serialize_table(rows))

    def test_unrelated_table_does_not_inherit_context(self):
        previous_table = FakeTable(
            [
                ["Value", "Mass", "Description"],
                ["$1", "8.10 g", "Susan B. Anthony"],
                [None, "8.10 g", "Sacagawea"],
            ],
            bbox=(0.0, 100.0, 200.0, 200.0),
        )
        unrelated_table = FakeTable(
            [
                ["Boston", "5 years", "review"],
                ["Salem", "3 years", "draft"],
                ["Austin", "2 years", "final"],
            ],
            bbox=(0.0, 300.0, 200.0, 400.0),
        )

        text, context = _extract_page_text_with_context(
            FakePage([], [previous_table, unrelated_table]),
        )

        self.assertIn("Value | Mass | Description", text)
        self.assertNotIn("Boston |", text)
        self.assertEqual(context.first_column_value, "$1")

    def test_unrelated_top_table_does_not_inherit_context_across_pages(self):
        unrelated_table = FakeTable(
            [
                ["Boston", "5 years", "review"],
                ["Salem", "3 years", "draft"],
                ["Austin", "2 years", "final"],
            ],
            bbox=(0.0, 300.0, 200.0, 400.0),
        )

        text, context = _extract_page_text_with_context(
            FakePage([], [unrelated_table]),
            _TableContext(("Value", "Mass", "Description"), "$1"),
        )

        self.assertEqual(text, "")
        self.assertIsNone(context)

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
