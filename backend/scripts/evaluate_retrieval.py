"""Measure whether the current semantic retriever finds declared gold chunks."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any, Callable, Sequence

from dotenv import load_dotenv

from backend.bootstrap import initialize_backend_environment
from backend.services.rag_adapters import ChromaRetrievalAdapter
from backend.services.vector_store import get_vector_store


DEFAULT_LIMITS = (4, 8)
RetrieverFactory = Callable[[str], ChromaRetrievalAdapter]


def evaluate_chunk_ids(
    retrieved_chunk_ids: Sequence[str],
    gold_chunk_ids: Sequence[str],
    limit: int,
) -> dict[str, Any]:
    """Return top-k evidence coverage without calling the answer model."""
    retrieved = list(retrieved_chunk_ids[:limit])
    gold = list(dict.fromkeys(gold_chunk_ids))
    found = [chunk_id for chunk_id in gold if chunk_id in retrieved]

    return {
        "limit": limit,
        "retrieved_chunk_ids": retrieved,
        "gold_chunk_ids": gold,
        "gold_chunk_ids_found": found,
        "gold_chunk_recall": len(found) / len(gold) if gold else None,
        "any_gold_chunk_found": bool(found),
        "all_gold_chunks_found": bool(gold) and len(found) == len(gold),
    }


def evaluate_cases(
    cases: Sequence[dict[str, Any]],
    retriever_factory: RetrieverFactory,
    limits: Sequence[int] = DEFAULT_LIMITS,
) -> dict[str, Any]:
    """Run each case against the existing semantic retrieval adapter."""
    normalized_limits = sorted(set(limits))
    if not normalized_limits or any(limit < 1 for limit in normalized_limits):
        raise ValueError("limits must contain positive integers")

    case_results = []
    for index, case in enumerate(cases, start=1):
        case_id = str(case.get("case_id") or f"case-{index}")
        document_id = str(case.get("document_id") or "")
        question = str(case.get("question") or "").strip()
        gold_chunk_ids = [str(chunk_id) for chunk_id in case.get("gold_chunk_ids", [])]

        if not document_id or not question or not gold_chunk_ids:
            case_results.append(
                {
                    "case_id": case_id,
                    "status": "invalid",
                    "error": "document_id, question, and gold_chunk_ids are required",
                }
            )
            continue

        results = {}
        retrieved_document_count = None
        try:
            retriever = retriever_factory(document_id)
        except Exception as exc:
            case_results.append(
                {"case_id": case_id, "status": "failed", "document_id": document_id,
                 "question": question, "error": type(exc).__name__}
            )
            continue
        for limit in normalized_limits:
            try:
                context = retriever.retrieve("semantic", question, limit)
                retrieved_document_count = context.retrieved_document_count
                retrieved_chunk_ids = [citation.chunk_id for citation in context.citations]
                results[f"top_{limit}"] = evaluate_chunk_ids(
                    retrieved_chunk_ids,
                    gold_chunk_ids,
                    limit,
                )
            except Exception as exc:
                results[f"top_{limit}"] = {"status": "failed", "error": type(exc).__name__}
        successful_count = sum("gold_chunk_recall" in result for result in results.values())
        status = "completed" if successful_count == len(normalized_limits) else (
            "partial" if successful_count else "failed"
        )
        case_results.append(
            {"case_id": case_id, "status": status, "document_id": document_id,
             "question": question, "retrieved_document_count": retrieved_document_count,
             "results": results}
        )

    summary = {}
    completed = [case for case in case_results if case["status"] == "completed"]
    for limit in normalized_limits:
        measurements = [
            case["results"][f"top_{limit}"] for case in case_results
            if f"top_{limit}" in case.get("results", {})
            and "gold_chunk_recall" in case["results"][f"top_{limit}"]
        ]
        any_hit_count = sum(measurement["any_gold_chunk_found"] for measurement in measurements)
        complete_hit_count = sum(measurement["all_gold_chunks_found"] for measurement in measurements)
        recalls = [measurement["gold_chunk_recall"] for measurement in measurements]
        summary[f"top_{limit}"] = {
            "case_count": len(measurements),
            "any_gold_chunk_hit_count": any_hit_count,
            "any_gold_chunk_hit_rate": any_hit_count / len(measurements) if measurements else None,
            "all_gold_chunks_hit_count": complete_hit_count,
            "all_gold_chunks_hit_rate": complete_hit_count / len(measurements) if measurements else None,
            "mean_gold_chunk_recall": sum(recalls) / len(recalls) if recalls else None,
        }

    return {
        "limits": normalized_limits,
        "case_count": len(case_results),
        "completed_case_count": len(completed),
        "summary": summary,
        "cases": case_results,
    }


def _load_cases(path: str) -> list[dict[str, Any]]:
    payload = json.loads(Path(path).read_text(encoding="utf-8"))
    cases = payload.get("cases") if isinstance(payload, dict) else payload
    if not isinstance(cases, list) or not all(isinstance(case, dict) for case in cases):
        raise ValueError("case file must contain a list or an object with a 'cases' list")
    return cases


def _write_output(report: dict[str, Any], output: str | None) -> None:
    rendered = json.dumps(report, indent=2, ensure_ascii=False)
    if output:
        Path(output).write_text(rendered + "\n", encoding="utf-8")
        print(f"Wrote retrieval evaluation to {output}")
        return
    print(rendered)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Measure top-k semantic retrieval against declared gold chunk IDs."
    )
    parser.add_argument("--cases", required=True, help="JSON file containing retrieval cases.")
    parser.add_argument(
        "--limits",
        nargs="+",
        type=int,
        default=list(DEFAULT_LIMITS),
        help="Top-k limits to measure (default: 4 8).",
    )
    parser.add_argument("--output", help="Write the JSON report to this path instead of stdout.")
    args = parser.parse_args(argv)

    load_dotenv(Path(__file__).resolve().parents[1] / ".env")
    initialize_backend_environment()

    try:
        report = evaluate_cases(
            _load_cases(args.cases),
            retriever_factory=lambda document_id: ChromaRetrievalAdapter(
                get_vector_store(document_id)
            ),
            limits=args.limits,
        )
    except (OSError, ValueError, json.JSONDecodeError) as exc:
        print(f"Evaluation failed: {exc}", file=sys.stderr)
        return 1

    _write_output(report, args.output)
    return 0 if report["completed_case_count"] == report["case_count"] else 1


if __name__ == "__main__":
    sys.exit(main())
