"""Turn proposed filing cases into evaluator cases with document IDs and gold chunk IDs.

Each proposed case names a PDF, quotes its evidence text, and gives the zero-indexed PDF page
of each quote. This script looks up the PDF's `document_id` in the index manifest written by
`index_eval_documents`, finds which stored chunks came from each evidence page, and picks the
fewest of those chunks that together contain the quote's words and numbers. Matching is by
tokens, not exact text, because the quotes come from a different PDF parser.

A case is marked `review` when the page's chunks cover less than `--min-coverage` of a quote,
so a person can check it. After checking, add a `gold_review_note` to the proposed case to mark
it `accepted` on every rerun. Rerun after re-indexing: chunk IDs are recomputed, never hand-kept.

    .venv/bin/python -m backend.scripts.build_eval_cases \
        --proposed evals/financial-filings/cases.json \
        --indexed evals/financial-filings/indexed-documents.local.json \
        --output evals/financial-filings/cases.local.json \
        --recomputes evals/financial-filings/verification/answer-recomputes.json
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
SCORING_FIELDS = ("acceptable_answers", "key_values", "scoring", "grader_note")
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


_STOPWORDS = {
    "the", "and", "for", "from", "with", "that", "this", "was", "were", "are", "its", "their", "has", "have",
    "had", "about", "which", "than", "into", "over", "per", "all", "not", "but", "any", "our", "also",
    "yes", "fiscal", "year", "years", "company", "total", "million", "billion", "percent", "percentage", "points",
}


def answer_anchors(proposed: dict[str, Any], evidence: str, formula: str = "") -> tuple[set[str], set[str]]:
    """Numbers and distinctive words from the expected answer that also appear in this evidence.

    These mark which part of a long evidence quote actually answers the question. `formula` is the
    recomputation of a calculated answer; its input figures are anchors too.
    """
    answer_tokens = tokens(" ".join([str(proposed.get("expected_answer") or ""), *proposed.get("key_values", []), formula]))
    shared = answer_tokens & tokens(evidence)
    numbers = {token for token in shared if token[0].isdigit() and not (len(token) == 4 and token.startswith(("19", "20")))}
    words = {token for token in shared if token[0].isalpha()} - tokens(proposed.get("question") or "") - _STOPWORDS
    return numbers, words


def add_answer_chunks(
    chosen: list[str],
    candidates: list[tuple[str, str]],
    anchors: tuple[set[str], set[str]],
) -> list[str]:
    """Add page chunks holding answer numbers that the chosen chunks miss.

    Coverage can reach its threshold on headings and neighbouring rows before the row with the
    answer is picked, so the answer's own figures are checked separately.
    """
    numbers, _ = anchors
    texts = dict(candidates)
    held = set().union(*(tokens(texts[chunk_id]) for chunk_id in chosen)) & numbers
    added = list(chosen)
    for chunk_id, text in candidates:
        missing = (numbers - held) & tokens(text)
        if chunk_id not in added and missing:
            added.append(chunk_id)
            held |= missing
    return added


def keep_answer_chunks(
    chosen: list[str],
    texts: dict[str, str],
    anchors: tuple[set[str], set[str]],
) -> tuple[list[str], list[str]]:
    """Keep only chunks that hold an anchor: one number, or (with no number anchors) two words.

    Evidence quotes are sometimes a whole page, and covering every word pulls in chunks that don't
    hold the answer. With no anchors, or if nothing would be kept, the selection is left unchanged.
    """
    numbers, words = anchors
    if not numbers and len(words) < 2:
        return chosen, []

    def holds_answer(chunk_id: str) -> bool:
        chunk_tokens = tokens(texts[chunk_id])
        if numbers:
            return bool(numbers & chunk_tokens)
        return len(words & chunk_tokens) >= 2

    kept = [chunk_id for chunk_id in chosen if holds_answer(chunk_id)]
    if not kept:
        return chosen, []
    return kept, [chunk_id for chunk_id in chosen if chunk_id not in kept]


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
    formula: str = "",
) -> dict[str, Any]:
    """Return an evaluator case; answerable cases get `gold_chunk_ids` and a `gold_mapping`.

    Scoring fields are copied when present: `acceptable_answers` (any one option passes, for questions
    with two standard methods; an option may list several values), `key_values` (numbers the answer must contain), `scoring` (a special
    rule) and `grader_note` (extra guidance for the prose grader).
    """
    case = {
        key: proposed.get(key)
        for key in ("case_id", "question", "expected", "expected_answer", "answer_format", "question_type", "split", "company", "filing", "source")
    }
    for key in SCORING_FIELDS:
        if proposed.get(key):
            case[key] = proposed[key]
    case["document_id"] = document_id
    if proposed.get("expected") == "abstain":
        return case

    located = chunk_pages(pages, chunks)
    texts = dict(chunks)
    gold: list[str] = []
    evidence_results = []
    for evidence, page in zip(proposed.get("gold_evidence_text", []), proposed.get("gold_page", [])):
        candidates = [(chunk_id, text) for chunk_id, text in chunks if page in located.get(chunk_id, set())]
        chosen, coverage = select_chunks(evidence, candidates, min_coverage)
        anchors = answer_anchors(proposed, evidence, formula)
        chosen = add_answer_chunks(chosen, candidates, anchors)
        kept, dropped = keep_answer_chunks(chosen, texts, anchors)
        result: dict[str, Any] = {"page": page, "chunk_ids": kept, "coverage": coverage}
        if dropped:
            result["dropped_chunk_ids"] = dropped
        if coverage < min_coverage:
            result["best_chunk_anywhere"], result["best_coverage_anywhere"] = _best_anywhere(evidence, chunks)
        evidence_results.append((result, bool(anchors[0] or anchors[1])))

    # A quote that shares nothing with the answer, in a case whose other quotes do, is a page the
    # source listed but the answer doesn't use. It stays in the mapping record but isn't gold.
    any_anchored = any(anchored for _, anchored in evidence_results)
    for result, anchored in evidence_results:
        if any_anchored and not anchored:
            result["unused_by_answer"] = True
            continue
        gold.extend(chunk_id for chunk_id in result["chunk_ids"] if chunk_id not in gold)
    evidence_results = [result for result, _ in evidence_results]

    matched = bool(evidence_results) and all(result["coverage"] >= min_coverage for result in evidence_results)
    case["gold_chunk_ids"] = gold
    status = "matched" if matched else ("accepted" if proposed.get("gold_review_note") else "review")
    case["gold_mapping"] = {"status": status, "evidence": evidence_results}
    if status == "accepted":
        case["gold_mapping"]["review_note"] = proposed["gold_review_note"]
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
    formulas: dict[str, str] | None = None,
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
        formula = (formulas or {}).get(proposed["case_id"], "")
        cases.append(build_case(proposed, document_id, pages, chunks, min_coverage, formula))

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
    parser.add_argument("--recomputes", help="Answer recompute record; formula inputs mark which chunks hold the answer.")
    args = parser.parse_args(argv)

    try:
        proposed = json.loads(Path(args.proposed).read_text(encoding="utf-8"))
        indexed = json.loads(Path(args.indexed).read_text(encoding="utf-8"))["documents"]
        formulas = {}
        if args.recomputes:
            record = json.loads(Path(args.recomputes).read_text(encoding="utf-8"))
            formulas = {row["case_id"]: row["formula"] for row in record["cases"]}
    except (OSError, KeyError, ValueError) as exc:
        print(f"Building cases failed: {exc}", file=sys.stderr)
        return 1

    report = build_cases(proposed, indexed, min_coverage=args.min_coverage, formulas=formulas)
    Path(args.output).write_text(json.dumps(report, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(
        f"Wrote {report['case_count']} cases to {args.output}; "
        f"{len(report['review_case_ids'])} need review; {len(report['unmatched_documents'])} unmatched",
        file=sys.stderr,
    )
    return 1 if report["unmatched_documents"] else 0


if __name__ == "__main__":
    sys.exit(main())
