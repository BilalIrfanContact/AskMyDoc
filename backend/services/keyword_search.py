"""Keyword ranking (BM25) and rank fusion for hybrid retrieval.

Meaning-based (embedding) search ranks chat-like paragraphs above tables of line items, because a
table has few sentences to match. BM25 rewards exact terms shared with the question, such as
"accounts payable" or "total assets", so combining the two rankings surfaces table chunks that
embedding search alone ranks too low.
"""

from __future__ import annotations

import math
import re
from collections import Counter
from typing import Sequence


_TOKEN = re.compile(r"[a-z]+|\d[\d,]*(?:\.\d+)?")
_STOPWORDS = {
    "a", "an", "and", "are", "as", "at", "be", "by", "did", "do", "does", "for", "from", "has", "have",
    "how", "in", "is", "it", "its", "of", "on", "or", "the", "their", "to", "was", "were", "what",
    "which", "who", "with",
}


def keyword_tokens(text: str) -> list[str]:
    """Lowercase words and numbers (thousands separators dropped), without common filler words."""
    return [
        token.replace(",", "")
        for token in _TOKEN.findall(text.lower())
        if token not in _STOPWORDS
    ]


def bm25_rank(query: str, documents: Sequence[str], k1: float = 1.5, b: float = 0.75) -> list[int]:
    """Return document indexes ordered by BM25 score for `query`, best first; zero scores are left out."""
    tokenized = [keyword_tokens(document) for document in documents]
    if not tokenized:
        return []
    average_length = sum(len(tokens) for tokens in tokenized) / len(tokenized) or 1.0
    document_frequency = Counter(token for tokens in tokenized for token in set(tokens))
    total = len(tokenized)

    scores = []
    for index, tokens in enumerate(tokenized):
        counts = Counter(tokens)
        score = 0.0
        for term in set(keyword_tokens(query)):
            frequency = counts.get(term, 0)
            if not frequency:
                continue
            idf = math.log(1 + (total - document_frequency[term] + 0.5) / (document_frequency[term] + 0.5))
            score += idf * frequency * (k1 + 1) / (frequency + k1 * (1 - b + b * len(tokens) / average_length))
        if score > 0:
            scores.append((score, index))
    return [index for _, index in sorted(scores, key=lambda item: (-item[0], item[1]))]


def reciprocal_rank_fusion(rankings: Sequence[Sequence[str]], k: int = 60) -> list[str]:
    """Merge ranked ID lists: each list adds 1 / (k + rank) to an ID, so items ranked well anywhere rise."""
    scores: dict[str, float] = {}
    for ranking in rankings:
        for rank, item in enumerate(ranking, start=1):
            scores[item] = scores.get(item, 0.0) + 1.0 / (k + rank)
    return sorted(scores, key=lambda item: -scores[item])
