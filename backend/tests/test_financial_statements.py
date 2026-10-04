import unittest
from types import SimpleNamespace
from unittest.mock import Mock

from backend.services.financial_statements import statement_chunk_positions
from backend.services.rag_adapters import ChromaRetrievalAdapter
from backend.services.rag_pipeline import AnswerCitation, RetrievedContext


def table(title, rows=30):
    return f"Table of Contents\n{title}\n(in millions)\n" + "\n".join(f"Line item {i} 1,{i:03d} 2,{i:03d}" for i in range(rows))


class StatementChunkPositionsTestCase(unittest.TestCase):
    def test_finds_each_statement_and_the_chunk_it_runs_into(self):
        chunks = [
            "Table of Contents\nConsolidated Statements of Operations ... 52\nConsolidated Balance Sheets ... 54",
            table("Consolidated Statements of Operations"),
            "continued rows 1,234 5,678",
            table("Consolidated Balance Sheets"),
            table("Consolidated Statements of Cash Flows"),
            "Notes to the statements",
        ]
        self.assertEqual(statement_chunk_positions(chunks), [1, 2, 3, 4, 5])

    def test_a_consolidated_title_beats_a_note_sub_heading_with_more_figures(self):
        chunks = [table("Consolidated Balance Sheet", rows=26), table("Note 14 — Supplemental\nBalance Sheet", rows=40)]
        self.assertEqual(statement_chunk_positions(chunks)[0], 0)

    def test_bare_titles_count_when_there_is_no_consolidated_one(self):
        self.assertEqual(statement_chunk_positions(["intro", table("INCOME STATEMENTS")]), [1])

    def test_prose_that_names_a_statement_is_not_one(self):
        self.assertEqual(statement_chunk_positions(["Consolidated Balance Sheets show total assets of $1,000."]), [])


class RetrievalWithStatementsTestCase(unittest.TestCase):
    def test_statements_follow_the_search_results_without_repeating_them(self):
        texts = ["intro", table("Consolidated Balance Sheets"), "Notes"]
        vectordb = Mock()
        vectordb._collection.get.return_value = {
            "ids": [f"doc:chunk:{i}" for i in range(3)],
            "documents": texts,
            "metadatas": [{"chunk_id": f"doc:chunk:{i}", "chunk_index": i} for i in range(3)],
        }
        adapter = ChromaRetrievalAdapter(vectordb, statements=True)
        searched = RetrievedContext(text="Notes", citations=[AnswerCitation("doc:chunk:2", "Notes")], retrieved_document_count=1)
        adapter._semantic_context = lambda question, limit: searched

        context = adapter.retrieve("semantic", "What were total assets?", 15)

        self.assertEqual([c.chunk_id for c in context.citations], ["doc:chunk:2", "doc:chunk:1"])
        self.assertEqual(context.retrieved_document_count, 2)


if __name__ == "__main__":
    unittest.main()
