"""Label chunks at indexing time so the evidence reranker can tell what each chunk is.

A chunk holding a financial table is mostly numbers, so its embedding says little about what the table
is ("Consolidated Balance Sheets … 38,363 32,963 …" sits far from "What was AES's return on assets?").
Before embedding, a small model writes a one-line title for the whole document and a short label for
each chunk naming its kind of content, periods and main line items or topics. The label and title are
kept as metadata for the evidence reranker. Voyage embeds only the original chunk text because adding
labels reduced retrieval coverage in the working-set experiment. `embedding_text` preserves the old
labelled format for comparisons; the stored chunk text is unchanged.

Labelling never fails indexing: a chunk whose label can't be generated gets an empty label.
"""

from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from typing import Callable, Sequence


Generate = Callable[[str], str]

LABEL_WORKERS = 8

TITLE_PROMPT = """Below is the start of a document. In one line, say what the document is: the company or \
author, the form or report type, and the period it covers (for example: "Acme Corp, Form 10-K annual report, \
fiscal year ended December 31, 2022"). Output only that line.

{text}"""

LABEL_PROMPT = """You are indexing a passage from a document so that search can find it.
Write 2-4 plain sentences describing the passage: what kind of content it is (for example a specific \
financial statement, a note, a schedule, a risk discussion, management commentary), which periods it covers, \
and the main line items, metrics or topics it contains. Name the key line items explicitly. Do not copy \
numbers. Output only the description.

Text just before the passage (context only):
{previous}

Passage:
{text}"""


@dataclass(frozen=True)
class DocumentLabels:
    title: str
    labels: list[str]


def embedding_text(title: str, label: str, chunk: str) -> str:
    """The text embedded for a chunk: document title, chunk label, then the chunk itself."""
    header = "\n".join(part for part in (title, label) if part)
    return f"{header}\n\n{chunk}" if header else chunk


def _safe(generate: Generate, prompt: str) -> str:
    try:
        return " ".join((generate(prompt) or "").split())
    except Exception:
        return ""


def title_document(chunks: Sequence[str], generate: Generate | None = None) -> str:
    """One line naming the document, from its opening chunks (one model call)."""
    if not chunks:
        return ""
    return _safe(generate or _default_generate(), TITLE_PROMPT.format(text="\n\n".join(chunks[:2])[:6000]))


def label_document(chunks: Sequence[str], generate: Generate | None = None) -> DocumentLabels:
    """Title the document from its opening chunks and label every chunk (in parallel)."""
    generate = generate or _default_generate()
    safe = lambda prompt: _safe(generate, prompt)

    title = title_document(chunks, generate)
    prompts = [
        LABEL_PROMPT.format(previous=chunks[index - 1][-400:] if index else "", text=chunk)
        for index, chunk in enumerate(chunks)
    ]
    with ThreadPoolExecutor(LABEL_WORKERS) as pool:
        labels = list(pool.map(safe, prompts))
    return DocumentLabels(title=title, labels=labels)


def _default_generate() -> Generate:
    from .ai_providers import chat_adapter
    from .rag_pipeline import _coerce_response_text

    labeller = chat_adapter("label")
    return lambda prompt: _coerce_response_text(labeller.invoke(prompt))
