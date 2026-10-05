"""Run eval cases end to end and compare answers across QA context limits.

For each case and each limit, this calls the real answer pipeline and records the answer,
whether it fell back (and why), whether the gold chunks reached the answer model, context
size, and latency. Each answer is also scored against the case's verified answer key using the rules
in `backend/scripts/answer_scoring.py` (a grader model checks prose), unless `--no-score` is given.

Cases default to `"expected": "answer"` and need `gold_chunk_ids`. Cases marked
`"expected": "abstain"` ask something the document does not contain; they need no gold
chunks and count as correct only when the pipeline returns its insufficient-context fallback.

    .venv/bin/python -m backend.scripts.evaluate_answers \
        --cases evals/financial-filings/cases.local.json --split working --limits 4

Re-score a saved report without asking AskMyDoc again (after a provable scoring-rule fix):

    .venv/bin/python -m backend.scripts.evaluate_answers \
        --cases evals/financial-filings/cases.local.json --rescore results.json
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
from backend.scripts.answer_scoring import grader_model, model_grade_fn, score_answer
from backend.scripts.evaluate_retrieval import _load_cases
from backend.services import rag_pipeline
from backend.services.rag_pipeline import AnswerDecision


DEFAULT_LIMITS = (4, 8)
AnswerFn = Callable[[str, str, int], AnswerDecision]
ScoreFn = Callable[[dict[str, Any], dict[str, Any]], dict[str, Any]]


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
    score_fn: ScoreFn | None = None,
) -> dict[str, Any]:
    """Answer every case once per limit and report outcomes side by side.

    With `score_fn`, each completed run also gets a `score` and the summary counts passes.
    """
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

    if score_fn is not None:
        score_results(cases, case_results, score_fn)

    summary = _summarize(case_results, normalized_limits, scored=score_fn is not None)

    return {
        "limits": normalized_limits,
        "case_count": len(case_results),
        "summary": summary,
        "cases": case_results,
    }


def _summarize(case_results: Sequence[dict[str, Any]], limits: Sequence[int], scored: bool) -> dict[str, Any]:
    """Per-limit run counts, fallback reasons and averages, plus pass counts when the runs are scored."""
    summary = {}
    for limit in limits:
        runs = [
            (case["expected"], case["results"][f"limit_{limit}"])
            for case in case_results
            if f"limit_{limit}" in case.get("results", {})
        ]
        completed = [run for _, run in runs if run["status"] == "completed"]
        answerable = [run for expected, run in runs if expected == "answer" and run["status"] == "completed"]
        abstain = [run for expected, run in runs if expected == "abstain" and run["status"] == "completed"]
        summary[f"limit_{limit}"] = {
            "run_count": len(runs),
            "answerable_run_count": len(answerable),
            "answered_count": sum(run["answer_status"] == "answered" for run in answerable),
            "all_gold_in_context_count": sum(run["all_gold_in_context"] for run in answerable),
            "abstain_run_count": len(abstain),
            "abstained_count": sum(run["answer_status"] == "insufficient_context" for run in abstain),
            "fallback_reasons": sorted(
                run["fallback_reason_code"] for run in completed if run["fallback_reason_code"]
            ),
            "mean_context_char_count": _mean(run["context_char_count"] for run in completed),
            "mean_latency_seconds": _mean(run["latency_seconds"] for run in completed),
        }
        if scored:
            summary[f"limit_{limit}"]["scores"] = _score_summary(case_results, limit)
    return summary


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
    expected = case.get("expected", "answer")
    gold_chunk_ids = [str(chunk_id) for chunk_id in case.get("gold_chunk_ids", [])]
    if expected not in ("answer", "abstain"):
        return {"case_id": case_id, "status": "invalid", "error": 'expected must be "answer" or "abstain"'}
    if not document_id or not question or (expected == "answer" and not gold_chunk_ids):
        return {
            "case_id": case_id,
            "status": "invalid",
            "error": "document_id, question, and gold_chunk_ids (for answerable cases) are required",
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
            "grounding_failure": event.get("grounding_failure"),
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
        "expected": expected,
        "expected_answer": case.get("expected_answer"),
        "answer_format": case.get("answer_format"),
        "question_type": case.get("question_type"),
        "split": case.get("split"),
        "gold_chunk_ids": gold_chunk_ids,
        "results": results,
    }


def score_results(
    cases: Sequence[dict[str, Any]],
    case_results: Sequence[dict[str, Any]],
    score_fn: ScoreFn,
) -> None:
    """Add a `score` to every completed run, looking up each case's answer key by case ID."""
    by_id = {str(case.get("case_id")): case for case in cases}
    for result in case_results:
        case = by_id.get(result["case_id"])
        if case is None:
            continue
        for run in result.get("results", {}).values():
            if run.get("status") == "completed":
                run["score"] = score_fn(case, run)


def _score_summary(case_results: Sequence[dict[str, Any]], limit: int) -> dict[str, Any]:
    """Pass counts, kept separate for answerable and abstain cases, then by question type and split."""
    scored = [
        (case, case["results"][f"limit_{limit}"]["score"])
        for case in case_results
        if "score" in case.get("results", {}).get(f"limit_{limit}", {})
    ]

    def tally(pairs) -> dict[str, int]:
        pairs = list(pairs)
        return {"passed": sum(score["passed"] for _, score in pairs), "total": len(pairs)}

    answerable = [(case, score) for case, score in scored if case["expected"] == "answer"]
    groups: dict[str, dict[str, list]] = {"by_question_type": {}, "by_split": {}}
    for case, score in scored:
        key = "abstain" if case["expected"] == "abstain" else (case.get("question_type") or "unknown")
        groups["by_question_type"].setdefault(key, []).append((case, score))
        groups["by_split"].setdefault(case.get("split") or "unknown", []).append((case, score))
    return {
        "answerable": tally(answerable),
        "abstain": tally((case, score) for case, score in scored if case["expected"] == "abstain"),
        "all": tally(scored),
        **{name: {key: tally(pairs) for key, pairs in sorted(group.items())} for name, group in groups.items()},
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
    parser.add_argument("--split", help="Only run cases whose `split` matches (e.g. working).")
    parser.add_argument("--no-score", action="store_true", help="Skip scoring and the grader model.")
    parser.add_argument("--rescore", help="Re-score this saved report instead of asking AskMyDoc again.")
    args = parser.parse_args(argv)

    load_dotenv(Path(__file__).resolve().parents[1] / ".env")
    initialize_backend_environment()

    try:
        cases = _load_cases(args.cases)
        if args.split:
            cases = [case for case in cases if case.get("split") == args.split]
        score_fn = None
        if not args.no_score:
            grade_fn = model_grade_fn()
            score_fn = lambda case, run: score_answer(case, run, grade_fn)
        if args.rescore:
            report = rescore_report(json.loads(Path(args.rescore).read_text(encoding="utf-8")), cases, score_fn)
        else:
            report = evaluate_cases(
                cases,
                answer_fn=lambda document_id, question, limit: rag_pipeline.answer_question(
                    document_id, question, qa_limit=limit
                ),
                limits=args.limits,
                score_fn=score_fn,
            )
        if score_fn is not None:
            report["grader_model"] = grader_model()
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


def rescore_report(
    report: dict[str, Any],
    cases: Sequence[dict[str, Any]],
    score_fn: ScoreFn | None,
) -> dict[str, Any]:
    """Replace every score in a saved report using the current answer key and rules.

    Only the given cases are kept, so a rescore filtered with `--split` never mixes in old scores.
    """
    if score_fn is None:
        raise ValueError("--rescore needs scoring; drop --no-score")
    case_ids = {case["case_id"] for case in cases}
    report["cases"] = [result for result in report["cases"] if result["case_id"] in case_ids]
    report["case_count"] = len(report["cases"])
    score_results(cases, report["cases"], score_fn)
    report["summary"] = _summarize(report["cases"], report["limits"], scored=True)
    return report


if __name__ == "__main__":
    sys.exit(main())
