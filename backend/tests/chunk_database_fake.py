"""In-memory stand-in for the Supabase chunk tables, answering the PostgREST calls `vector_store` makes.

`commit_document_index` and `match_document_chunks` mirror the SQL functions in
`supabase/migrations/202610110001_document_chunks.sql`; `test_document_chunks_database` checks the real SQL.
"""

import math


class FakeChunkDatabase:
    def __init__(self):
        self.tables: dict[str, list[dict]] = {"document_indexes": [], "document_chunks": []}
        self.fail_commit = False
        self.request_count = 0

    def from_(self, table: str) -> "_Query":
        return _Query(self, table)

    def rpc(self, name: str, params: dict) -> "_Result":
        return _Result(getattr(self, name)(**params))

    def commit_document_index(self, p_document_id, p_generation, p_embedding_model, p_embedding_input, p_expected_count):
        chunks = self.tables["document_chunks"]
        stored = sum(1 for row in chunks if row["document_id"] == p_document_id and row["generation"] == p_generation)
        if self.fail_commit or stored != p_expected_count:
            raise RuntimeError(f"stored {stored} of {p_expected_count} chunks")
        self.tables["document_indexes"] = [
            *(row for row in self.tables["document_indexes"] if row["document_id"] != p_document_id),
            {
                "document_id": p_document_id,
                "generation": p_generation,
                "embedding_model": p_embedding_model,
                "embedding_input": p_embedding_input,
                "chunk_count": stored,
            },
        ]
        self.tables["document_chunks"] = [
            row for row in chunks if row["document_id"] != p_document_id or row["generation"] == p_generation
        ]
        return stored

    def match_document_chunks(self, p_document_id, p_generation, p_query, p_count):
        rows = [
            row
            for row in self.tables["document_chunks"]
            if row["document_id"] == p_document_id and row["generation"] == p_generation
        ]
        rows.sort(key=lambda row: (_cosine_distance(row["embedding"], p_query), row["chunk_index"]))
        return [{key: row[key] for key in ("chunk_id", "chunk_index", "content", "metadata")} for row in rows[:p_count]]


def _cosine_distance(left, right) -> float:
    dot = sum(a * b for a, b in zip(left, right))
    return 1 - dot / (math.hypot(*left) * math.hypot(*right))


class _Result:
    def __init__(self, data):
        self.data = data

    def execute(self) -> "_Result":
        return self


class _Query:
    def __init__(self, database: FakeChunkDatabase, table: str):
        self._database = database
        self._table = table
        self._action = "select"
        self._columns: list[str] | None = None
        self._filters = []
        self._order: str | None = None
        self._window: tuple[int, int] | None = None
        self._rows: list[dict] = []

    def select(self, columns: str) -> "_Query":
        self._columns = [column.strip() for column in columns.split(",")]
        return self

    def insert(self, rows: list[dict], returning=None) -> "_Query":
        self._action, self._rows = "insert", rows
        return self

    def delete(self) -> "_Query":
        self._action = "delete"
        return self

    def eq(self, column: str, value) -> "_Query":
        self._filters.append(lambda row: row[column] == value)
        return self

    def in_(self, column: str, values) -> "_Query":
        allowed = set(values)
        self._filters.append(lambda row: row[column] in allowed)
        return self

    def order(self, column: str) -> "_Query":
        self._order = column
        return self

    def range(self, start: int, end: int) -> "_Query":
        self._window = (start, end + 1)
        return self

    def limit(self, count: int) -> "_Query":
        self._window = (0, count)
        return self

    def execute(self) -> _Result:
        self._database.request_count += 1
        table = self._database.tables[self._table]
        if self._action == "insert":
            table.extend(dict(row) for row in self._rows)
            return _Result([])
        matches = [row for row in table if all(keep(row) for keep in self._filters)]
        if self._action == "delete":
            self._database.tables[self._table] = [row for row in table if not any(row is match for match in matches)]
            return _Result([])
        if self._order:
            matches.sort(key=lambda row: row[self._order])
        if self._window:
            matches = matches[self._window[0] : self._window[1]]
        return _Result([{column: row[column] for column in self._columns} for row in matches])
