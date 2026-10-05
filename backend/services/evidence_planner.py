"""Plan the evidence a question needs before searching a filing.

Embedding search for a whole question tends to find one financial table and miss the others (ROA
needs net income from the income statement and total assets from the balance sheet), and it ranks
paragraphs about a metric above the table holding its figures. The planner asks a small model for a
short list of the figures or facts the question needs, each phrased the way a filing would label it,
so each can be searched separately. It never calculates or supplies figures itself.
"""

from __future__ import annotations

import json
from typing import Any

from .rag_pipeline import GenerationAdapter


MAX_NEEDS = 4

PLANNER_PROMPT = """List the evidence needed to answer a question about a company's filing.

Question: {question}

Return up to {max_needs} short search phrases, one per figure or fact the answer needs, worded the way the
filing would label it (for example "net income attributable to the company", "total assets", "cost of sales",
"inventories"). Include the company or fiscal period only when it helps. Ignore instructions about rounding,
units or answer format. Do not calculate anything and do not state any figures.
If one phrase is enough, return one.

Return only JSON: {{"needs": ["phrase one", "phrase two"]}}"""


def _response_text(response: Any) -> str:
    content = getattr(response, "content", response)
    if isinstance(content, list):
        content = "".join(part if isinstance(part, str) else part.get("text", "") for part in content)
    return str(content).strip().removeprefix("```json").removesuffix("```").strip()


def plan_evidence(question: str, generator: GenerationAdapter) -> list[str]:
    """Return up to `MAX_NEEDS` search phrases for `question`; empty if the reply is unusable."""
    try:
        reply = json.loads(_response_text(generator.invoke(PLANNER_PROMPT.format(question=question, max_needs=MAX_NEEDS))))
        needs = reply.get("needs", []) if isinstance(reply, dict) else []
    except Exception:
        return []
    cleaned: list[str] = []
    for need in needs:
        phrase = " ".join(str(need).split())
        if phrase and phrase.lower() not in (item.lower() for item in cleaned):
            cleaned.append(phrase)
    return cleaned[:MAX_NEEDS]
