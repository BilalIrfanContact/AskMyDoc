"""Pick the passages a question needs from a wide embedding shortlist.

Embedding search is good at "roughly relevant" but poor at ordering: in filings, the table holding a
figure often ranks below paragraphs that only mention the metric, and a question needing two statements
rarely gets both near the top. The adapter embeds the question, takes the top `RERANK_POOL` chunks, and
asks a small model which of them are needed, most useful first. The model decides how many to keep, up
to the caller's limit, so a ratio question can get two statements and a lookup just one.

`pick_evidence` returns positions in the shortlist; an unusable reply returns an empty list and the
caller falls back to embedding order.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Sequence

from .rag_pipeline import GenerationAdapter, _coerce_response_text


RERANK_POOL = 30
EXCERPT_CHARS = 400

RERANK_PROMPT = """You are selecting evidence from one document to answer a question.
Below are candidate passages, each with an id, a short description and its opening text.
Pick the passages needed to answer the question, most useful first. If the answer needs several figures \
or facts (for example from two different statements or years), make sure every one of them is covered. \
Prefer primary financial statements and specific tables over summaries that only mention a metric. \
Return at most {limit} ids, as a comma-separated list, and nothing else.

Question: {question}

Candidates:
{candidates}"""


@dataclass(frozen=True)
class Candidate:
    label: str
    text: str


def pick_evidence(
    question: str,
    candidates: Sequence[Candidate],
    limit: int,
    generator: GenerationAdapter,
) -> list[int]:
    """Return up to `limit` distinct candidate positions the model picked, in its order."""
    if not candidates or limit < 1:
        return []
    listing = "\n\n".join(
        f"[{index}] {candidate.label}\nOpening: {' '.join(candidate.text[:EXCERPT_CHARS].split())}"
        for index, candidate in enumerate(candidates)
    )
    try:
        reply = _coerce_response_text(
            generator.invoke(RERANK_PROMPT.format(limit=limit, question=question, candidates=listing))
        )
    except Exception:
        return []
    picked: list[int] = []
    for match in re.findall(r"\d+", reply):
        position = int(match)
        if position < len(candidates) and position not in picked:
            picked.append(position)
        if len(picked) == limit:
            break
    return picked
