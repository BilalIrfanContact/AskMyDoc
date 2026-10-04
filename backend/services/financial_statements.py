"""Find a filing's three primary financial statements among its chunks.

Many filing questions need a figure from the income statement, balance sheet or cash flow statement, but
the question's wording often doesn't resemble the table, so search misses it (AES's total assets, Boeing's
gross profit). The answer step therefore always adds these statements to the excerpts.

A statement is the chunk that opens with its title on its own line and holds the most figures. A title
with "consolidated" beats a bare one, which skips note sub-headings such as "Balance Sheet" in a
supplemental note while still finding Microsoft's bare "INCOME STATEMENTS". A statement usually runs into
the next chunk, so that chunk is included too.
"""

from __future__ import annotations

import re
from typing import Sequence

STATEMENT_TITLES = (
    re.compile(
        r"^\s*(?:consolidated\s+)?(?:statements?\s+of\s+(?:operations|income|earnings)\b(?!\s+and\s+comprehensive)"
        r"|income\s+statements?\b)",
        re.IGNORECASE | re.MULTILINE,
    ),
    re.compile(r"^\s*(?:consolidated\s+)?(?:balance\s+sheets?|statements?\s+of\s+financial\s+position)\b", re.IGNORECASE | re.MULTILINE),
    re.compile(r"^\s*(?:consolidated\s+)?(?:statements?\s+of\s+cash\s+flows?|cash\s+flows?\s+statements?)\b", re.IGNORECASE | re.MULTILINE),
)
_FIGURE = re.compile(r"\d[\d,]{2,}")
# Fewer figures than this is prose or a table of contents that names the statement, not the statement.
_MIN_FIGURES = 25
# The title must open the chunk: within its first few lines, after any running header.
_TITLE_WINDOW = 400


def statement_chunk_positions(texts: Sequence[str]) -> list[int]:
    """Positions in `texts` (chunks in document order) of the statements and their continuation chunks."""
    positions: set[int] = set()
    for title in STATEMENT_TITLES:
        best: tuple[tuple[bool, int], int] | None = None
        for position, text in enumerate(texts):
            match = title.search(text[:_TITLE_WINDOW])
            figures = len(_FIGURE.findall(text)) if match else 0
            if figures < _MIN_FIGURES:
                continue
            rank = ("consolidated" in match.group().lower(), figures)
            if best is None or rank > best[0]:
                best = (rank, position)
        if best is not None:
            positions.update(p for p in (best[1], best[1] + 1) if p < len(texts))
    return sorted(positions)
