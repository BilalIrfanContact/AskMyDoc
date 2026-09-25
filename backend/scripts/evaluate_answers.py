"""Run eval cases end to end and compare answers across QA context limits.

For each case and each limit, this calls the real answer pipeline and records the answer,
whether it fell back (and why), whether the gold chunks reached the answer model, context
size, and latency. Correctness is left to a human: compare `answer` with `expected_answer`.

    .venv/bin/python -m backend.scripts.evaluate_answers \
        --cases evals/pdfqa-benchmark/retrieval-cases.local.json --limits 4 8
"""

from __future__ import annotations

import argparse
import json
import logging
import sys
import time
from pathlib import Path
from typing import Any, Callable, Sequence

from dotenv import load_dotenv

from backend.bootstrap import initialize_backend_environment
from backend.scripts.evaluate_retrieval import _load_cases
from backend.services import rag_pipeline
from backend.services.rag_pipeline import AnswerDecision


DEFAULT_LIMITS = (4, 8)
AnswerFn = Callable[[str, str, int], AnswerDecision]


class _TelemetryCapture(logging.Handler):
    """Collects the pipeline's `answer_policy_decision` events for the current run."""

    def __init__(self) -> None:
        super().__init__(level=logging.INFO)
        self.events: list[dict[str, Any]] = []

    def emit(self, record: logging.LogRecord) -> None:
        try:
            event = json.loads(record.getMessage())
        except (TypeError, ValueError):
            return
        if isinstance(event, dict) and event.get("event") == "answer_policy_decision":
            self.events.append(event)


def evaluate_cases(
    cases: Sequence[dict[str, Any]],
    answer_fn: AnswerFn,
    limits: Sequence[int] = DEFAULT_LIMITS,
) -> dict[str, Any]:
    """Answer every case once per limit and report outcomes side by side."""
    normalized_limits = sorted(set(limits))
    if not normalized_limits or any(limit < 1 for limit in normalized_limits):
        raise ValueError("limits must contain positive integers")

    capture = _TelemetryCapture()
    pipeline_logger = rag_pipeline.logger
    previous_level = pipeline_logger.level
    pipeline_logger.addHandler(capture)
    pipeline_logger.setLevel(logging.INFO)
    try:
        case_results = [
            _evaluate_case(index, case, answer_fn, normalized_limits, capture)
            for index, case in enumerate(cases, start=1)
        ]
    finally:
        pipeline_logger.removeHandler(capture)
        pipeline_logger.setLevel(previous_level)

    summary = {}
    for limit in normalized_limits:
        runs = [
            case["results"][f"limit_{limit}"]
            for case in case_results
            if f"limit_{limit}" in case.get("results", {})
        ]
        completed = [run for run in runs if run["status"] == "completed"]
        summary[f"limit_{limit}"] = {
            "run_count": len(runs),
            "answered_count": sum(run["answer_status"] == "answered" for run in completed),
            "all_gold_in_context_count": sum(run["all_gold_in_context"] for run in completed),
            "fallback_reasons": sorted(
                run["fallback_reason_code"] for run in completed if run["fallback_reason_code"]
            ),
            "mean_context_char_count": _mean(run["context_char_count"] for run in completed),
            "mean_latency_seconds": _mean(run["latency_seconds"] for run in completed),
        }

    return {
        "limits": normalized_limits,
        "case_count": len(case_results),
        "summary": summary,
        "cases": case_results,
    }


def _evaluate_case(
    index: int,
    case: dict[str, Any],
    answer_fn: AnswerFn,
    limits: Sequence[int],
    capture: _TelemetryCapture,
) -> dict[str, Any]:
    case_id = str(case.get("case_id") or f"case-{index}")
    document_id = str(case.get("document_id") or "")
    question = str(case.get("question") or "").strip()
    gold_chunk_ids = [str(chunk_id) for chunk_id in case.get("gold_chunk_ids", [])]
    if not document_id or not question or not gold_chunk_ids:
        return {
            "case_id": case_id,
            "status": "invalid",
            "error": "document_id, question, and gold_chunk_ids are required",
        }

    results = {}
    for limit in limits:
        capture.events.clear()
        started = time.perf_counter()
        try:
            decision = answer_fn(document_id, question, limit)
        except Exception as exc:
            results[f"limit_{limit}"] = {"status": "failed", "error": type(exc).__name__}
            continue
        latency = time.perf_counter() - started
        event = capture.events[-1] if capture.events else {}
        if not event:
            results[f"limit_{limit}"] = {"status": "failed", "error": "TelemetryMissing"}
            continue
        retrieved = event.get("retrieved_chunk_ids", [])
        model_called = event.get("answer_model_called", False)
        in_context = retrieved if model_called else []
        results[f"limit_{limit}"] = {
            "status": "completed",
            "intent": decision.intent,
            "retrieval_mode": decision.retrieval_mode,
            "answer_status": decision.answer_status,
            "fallback_reason_code": event.get("fallback_reason_code"),
            "answer": decision.answer,
            "retrieved_chunk_ids": retrieved,
            "answer_model_called": model_called,
            "context_chunk_ids": in_context,
            "gold_chunk_ids_in_context": [chunk_id for chunk_id in gold_chunk_ids if chunk_id in in_context],
            "all_gold_in_context": bool(gold_chunk_ids) and all(chunk_id in in_context for chunk_id in gold_chunk_ids),
            "context_char_count": event.get("retrieved_context_char_count") if model_called else 0,
            "latency_seconds": round(latency, 2),
        }

    completed_count = sum(result["status"] == "completed" for result in results.values())
    status = "completed" if completed_count == len(limits) else (
        "partial" if completed_count else "failed"
    )
    return {
        "case_id": case_id,
        "status": status,
        "document_id": document_id,
        "question": question,
        "expected_answer": case.get("expected_answer"),
        "gold_chunk_ids": gold_chunk_ids,
        "results": results,
    }


def _mean(values) -> float | None:
    numbers = [value for value in values if isinstance(value, (int, float))]
    return round(sum(numbers) / len(numbers), 2) if numbers else None


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Compare end-to-end answers across QA context limits."
    )
    parser.add_argument("--cases", required=True, help="JSON file containing eval cases.")
    parser.add_argument(
        "--limits",
        nargs="+",
        type=int,
        default=list(DEFAULT_LIMITS),
        help="QA context limits to compare (default: 4 8).",
    )
    parser.add_argument("--output", help="Write the JSON report to this path instead of stdout.")
    args = parser.parse_args(argv)

    load_dotenv(Path(__file__).resolve().parents[1] / ".env")
    initialize_backend_environment()

    try:
        report = evaluate_cases(
            _load_cases(args.cases),
            answer_fn=lambda document_id, question, limit: rag_pipeline.answer_question(
                document_id, question, qa_limit=limit
            ),
            limits=args.limits,
        )
    except (OSError, ValueError, json.JSONDecodeError) as exc:
        print(f"Evaluation failed: {exc}", file=sys.stderr)
        return 1

    rendered = json.dumps(report, indent=2, ensure_ascii=False)
    if args.output:
        Path(args.output).write_text(rendered + "\n", encoding="utf-8")
        print(f"Wrote answer evaluation to {args.output}")
    else:
        print(rendered)
    return 0 if report["case_count"] and all(
        case["status"] == "completed" for case in report["cases"]
    ) else 1


if __name__ == "__main__":
    sys.exit(main())
