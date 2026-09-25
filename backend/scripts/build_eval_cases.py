"""Turn proposed filing cases into evaluator cases with document IDs and gold chunk IDs.

Each proposed case names a PDF, quotes its evidence text, and gives the zero-indexed PDF page
of each quote. This script looks up the PDF's `document_id` in the index manifest written by
`index_eval_documents`, finds which stored chunks came from each evidence page, and picks the
fewest of those chunks that together contain the quote's words and numbers. Matching is by
tokens, not exact text, because the quotes come from a different PDF parser.

A case is marked `review` when the page's chunks cover less than `--min-coverage` of a quote,
so a person can check it. Rerun after re-indexing: chunk IDs are recomputed, never hand-kept.

    .venv/bin/python -m backend.scripts.build_eval_cases \
        --proposed evals/financial-filings-corpus/proposed-cases.json \
        --indexed evals/financial-filings-corpus/indexed-documents.local.json \
        --output evals/financial-filings-corpus/cases.local.json
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path
from typing import Any, Callable

from backend.services.pdf_extractor import extract_pdf_pages


DEFAULT_MIN_COVERAGE = 0.9
_TOKEN_PATTERN = re.compile(r"[a-z]{3,}|\d[\d,]*(?:\.\d+)?")

# (pages, [(chunk_id, text)] in chunk order) for one document.
DocumentLoader = Callable[[str, str], tuple[list[str], list[tuple[str, str]]]]


def tokens(text: str) -> set[str]:
    """Words of 3+ letters and numbers without thousands separators ("25,309" -> "25309")."""
    return {token.replace(",", "") for token in _TOKEN_PATTERN.findall(text.lower())}


def chunk_pages(pages: list[str], chunks: list[tuple[str, str]]) -> dict[str, set[int]]:
    """Map each chunk ID to the zero-indexed PDF pages its text came from.

    Rebuilds the ingestion text (non-empty pages joined by blank lines) and finds each chunk
    in it. Chunks that can't be found map to no pages.
    """
    joined_pages = [(index, page) for index, page in enumerate(pages) if page]
    joined = "\n\n".join(page for _, page in joined_pages).strip()
    spans: list[tuple[int, int, int]] = []
    cursor = 0
    for index, page in joined_pages:
        start = joined.find(page, cursor)
        if start < 0:
            continue
        spans.append((index, start, start + len(page)))
        cursor = start + len(page)

    located: dict[str, set[int]] = {}
    cursor = 0
    for chunk_id, text in chunks:
        start = joined.find(text, cursor)
        if start < 0:
            start = joined.find(text)
        if start < 0:
            located[chunk_id] = set()
            continue
        end = start + len(text)
        located[chunk_id] = {index for index, page_start, page_end in spans if page_start < end and page_end > start}
        cursor = start + 1
    return located


def select_chunks(
    evidence: str,
    candidates: list[tuple[str, str]],
    min_coverage: float = DEFAULT_MIN_COVERAGE,
) -> tuple[list[str], float]:
    """Greedily pick the fewest candidate chunks covering the evidence's tokens.

    Returns the chosen chunk IDs and the share of evidence tokens they contain.
    """
    wanted = tokens(evidence)
    if not wanted:
        return [], 0.0
    covered: set[str] = set()
    chosen: list[str] = []
    remaining = [(chunk_id, tokens(text)) for chunk_id, text in candidates]
    while remaining and len(covered) / len(wanted) < min_coverage:
        best_id, best_tokens = max(remaining, key=lambda item: len((item[1] & wanted) - covered))
        gain = (best_tokens & wanted) - covered
        if not gain:
            break
        chosen.append(best_id)
        covered |= gain
        remaining = [item for item in remaining if item[0] != best_id]
    return chosen, round(len(covered) / len(wanted), 3)


def _best_anywhere(evidence: str, chunks: list[tuple[str, str]]) -> tuple[str | None, float]:
    wanted = tokens(evidence)
    if not wanted or not chunks:
        return None, 0.0
    chunk_id, text = max(chunks, key=lambda item: len(tokens(item[1]) & wanted))
    return chunk_id, round(len(tokens(text) & wanted) / len(wanted), 3)


def build_case(
    proposed: dict[str, Any],
    document_id: str,
    pages: list[str],
    chunks: list[tuple[str, str]],
    min_coverage: float = DEFAULT_MIN_COVERAGE,
) -> dict[str, Any]:
    """Return an evaluator case; answerable cases get `gold_chunk_ids` and a `gold_mapping`."""
    case = {
        key: proposed.get(key)
        for key in ("case_id", "question", "expected", "expected_answer", "answer_format", "question_type", "split", "company", "filing", "source")
    }
    case["document_id"] = document_id
    if proposed.get("expected") == "abstain":
        return case

    located = chunk_pages(pages, chunks)
    gold: list[str] = []
    evidence_results = []
    for evidence, page in zip(proposed.get("gold_evidence_text", []), proposed.get("gold_page", [])):
        candidates = [(chunk_id, text) for chunk_id, text in chunks if page in located.get(chunk_id, set())]
        chosen, coverage = select_chunks(evidence, candidates, min_coverage)
        result: dict[str, Any] = {"page": page, "chunk_ids": chosen, "coverage": coverage}
        if coverage < min_coverage:
            result["best_chunk_anywhere"], result["best_coverage_anywhere"] = _best_anywhere(evidence, chunks)
        evidence_results.append(result)
        gold.extend(chunk_id for chunk_id in chosen if chunk_id not in gold)

    matched = bool(evidence_results) and all(result["coverage"] >= min_coverage for result in evidence_results)
    case["gold_chunk_ids"] = gold
    case["gold_mapping"] = {"status": "matched" if matched else "review", "evidence": evidence_results}
    return case


def _load_document(pdf_path: str, document_id: str) -> tuple[list[str], list[tuple[str, str]]]:
    from backend.services.vector_store import get_persisted_collection

    pages = extract_pdf_pages(Path(pdf_path).read_bytes())
    stored = get_persisted_collection(document_id).get(include=["documents", "metadatas"])
    rows = sorted(
        zip(stored["ids"], stored["documents"], stored["metadatas"]),
        key=lambda row: (row[2] or {}).get("chunk_index", 0),
    )
    return pages, [(chunk_id, text) for chunk_id, text, _ in rows]


def build_cases(
    proposed_cases: list[dict[str, Any]],
    indexed_documents: list[dict[str, Any]],
    *,
    load_document: DocumentLoader = _load_document,
    min_coverage: float = DEFAULT_MIN_COVERAGE,
) -> dict[str, Any]:
    by_filename = {Path(entry["path"]).name: entry for entry in indexed_documents}
    cache: dict[str, tuple[list[str], list[tuple[str, str]]]] = {}
    cases: list[dict[str, Any]] = []
    unmatched_documents: list[str] = []

    for proposed in proposed_cases:
        filename = Path(proposed["document_url_or_path"]).name
        entry = by_filename.get(filename)
        if entry is None:
            unmatched_documents.append(f"{proposed['case_id']}: {filename}")
            continue
        document_id = entry["document_id"]
        if proposed.get("expected") == "abstain":
            cases.append(build_case(proposed, document_id, [], [], min_coverage))
            continue
        if document_id not in cache:
            print(f"loading {filename}", file=sys.stderr)
            cache[document_id] = load_document(entry["path"], document_id)
        pages, chunks = cache[document_id]
        cases.append(build_case(proposed, document_id, pages, chunks, min_coverage))

    review = [case["case_id"] for case in cases if case.get("gold_mapping", {}).get("status") == "review"]
    return {
        "min_coverage": min_coverage,
        "case_count": len(cases),
        "review_case_ids": review,
        "unmatched_documents": unmatched_documents,
        "cases": cases,
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Build evaluator cases with gold chunk IDs from proposed filing cases.")
    parser.add_argument("--proposed", required=True, help="JSON list of proposed cases.")
    parser.add_argument("--indexed", required=True, help="Manifest written by index_eval_documents.")
    parser.add_argument("--output", required=True, help="Where to write the evaluator case file.")
    parser.add_argument("--min-coverage", type=float, default=DEFAULT_MIN_COVERAGE)
    args = parser.parse_args(argv)

    try:
        proposed = json.loads(Path(args.proposed).read_text(encoding="utf-8"))
        indexed = json.loads(Path(args.indexed).read_text(encoding="utf-8"))["documents"]
    except (OSError, KeyError, ValueError) as exc:
        print(f"Building cases failed: {exc}", file=sys.stderr)
        return 1

    report = build_cases(proposed, indexed, min_coverage=args.min_coverage)
    Path(args.output).write_text(json.dumps(report, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(
        f"Wrote {report['case_count']} cases to {args.output}; "
        f"{len(report['review_case_ids'])} need review; {len(report['unmatched_documents'])} unmatched",
        file=sys.stderr,
    )
    return 1 if report["unmatched_documents"] else 0


if __name__ == "__main__":
    sys.exit(main())
