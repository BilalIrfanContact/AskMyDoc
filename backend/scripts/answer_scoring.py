"""Score AskMyDoc answers against the filings eval's verified answer key.

The rules are written down in `evals/financial-filings/scoring-rules.md`:

1. Numbers pass when they round to the expected value (tolerance is half of the expected value's last
   shown decimal place). Units, commas and currency signs are normalised only for the comparison.
2. Yes/no answers need the right verdict and passing support.
3. Prose is checked by a grader model that fills in a fixed checklist; code makes the pass/fail call.
4. `"scoring": "zero_or_not_found"` cases pass on "0", a "not shown" statement, or the app's fallback.

"Not in the document" cases pass only when the app returns its insufficient-context fallback.

`score_answer` takes the case, one evaluator run and a `grade_fn`, so tests can pass a fake grader.
"""

from __future__ import annotations

import json
import os
import re
from dataclasses import dataclass
from typing import Any, Callable


GRADER_PROMPT = """You are grading an answer from a document Q&A app against a verified expected answer.

Question: {question}
Expected answer: {expected_answer}
App's answer: {app_answer}
{note_line}
Judge only whether the app's answer says the same thing as the expected answer.
Do not use outside knowledge. Do not judge whether numbers are correct; numbers are checked separately.

Check each item:
1. facts_complete: every key fact in the expected answer appears in the app's answer.
   All listed facts are required, not only the main one. Extra correct detail is fine.
2. no_contradiction: nothing in the app's answer contradicts the expected answer.
3. right_subject: the answer is about the same company and period as the question.
4. verdict: if the question asks yes or no, which verdict does the app's answer commit to?
   Use "yes" or "no" based on meaning, even if the words "yes" or "no" do not appear.
   Use "none" if it hedges (for example "it depends", "probably", "possibly") or gives no verdict.
   Use "not_applicable" if the question is not a yes/no question.

Return only JSON:
{{"facts_complete": true|false, "no_contradiction": true|false, "right_subject": true|false,
 "verdict": "yes"|"no"|"none"|"not_applicable", "reason": "<one sentence>"}}"""

DEFAULT_GRADER_MODEL = "gpt-5.4-nano"
GradeFn = Callable[[str], dict[str, Any]]

_SCALES = {"thousand": 1e3, "million": 1e6, "mn": 1e6, "m": 1e6, "billion": 1e9, "bn": 1e9, "b": 1e9}
_NUMBER = re.compile(
    r"(?P<open>\()?\s*(?P<minus>[-−–])?\s*\$?\s*(?P<num>\d[\d,]*(?:\.\d+)?)\s*(?P<close>\))?"
    r"\s*(?P<unit>%|percent(?:age points?)?|pp\b|points?\b|thousand\b|million\b|billion\b|mn\b|bn\b|m\b|b\b)?",
    re.IGNORECASE,
)


@dataclass(frozen=True)
class Quantity:
    """A number read from text: its value in base units, whether it is a percentage, and its sign."""

    value: float
    percent: bool
    scale: float
    signed: bool
    decimals: int

    @property
    def scaled(self) -> bool:
        return self.scale != 1.0


def read_quantities(text: str) -> list[Quantity]:
    """Read every number in `text`, handling $, commas, brackets as negatives, % and scale words."""
    quantities = []
    for match in _NUMBER.finditer(text or ""):
        raw = match.group("num").replace(",", "")
        value = float(raw)
        decimals = len(raw.split(".")[1]) if "." in raw else 0
        unit = (match.group("unit") or "").lower()
        negative = bool(match.group("minus")) or bool(match.group("open") and match.group("close"))
        percent = unit.startswith(("%", "percent", "pp", "point"))
        scale = _SCALES.get(unit, 1.0)
        quantities.append(
            Quantity(
                value=-value * scale if negative else value * scale,
                percent=percent,
                scale=scale,
                signed=negative,
                decimals=decimals,
            )
        )
    return quantities


def number_matches(expected: str, answer: str) -> bool:
    """True when some number in `answer` rounds to the single number in `expected`.

    An answer number with no scale word or % is read in the expected number's unit ("9,068" matches
    "$9,068 million"). An unsigned answer number matches a negative expected value, because the sign is
    often given in words ("declined 3.0 points"); an explicitly signed one must match the sign.
    """
    wanted = read_quantities(expected)
    if len(wanted) != 1:
        raise ValueError(f"expected value must contain exactly one number: {expected!r}")
    target = wanted[0]
    tolerance = 0.5 * 10 ** -target.decimals * target.scale + 1e-9

    for found in read_quantities(answer):
        if found.percent != target.percent and (found.percent or found.scaled):
            continue
        value = found.value if found.scaled else found.value * target.scale
        if found.signed:
            if abs(value - target.value) <= tolerance:
                return True
        elif abs(abs(value) - abs(target.value)) <= tolerance:
            return True
    return False


def _expected_verdict(expected_answer: str) -> str | None:
    first = re.match(r"\s*(yes|no)\b", expected_answer or "", re.IGNORECASE)
    return first.group(1).lower() if first else None


def _is_fallback(run: dict[str, Any]) -> bool:
    return run.get("answer_status") == "insufficient_context"


def _result(passed: bool, method: str, reason: str, **checks: Any) -> dict[str, Any]:
    return {"passed": passed, "method": method, "reason": reason, "checks": checks}


def score_answer(case: dict[str, Any], run: dict[str, Any], grade_fn: GradeFn | None) -> dict[str, Any]:
    """Score one completed evaluator run for one case."""
    answer = run.get("answer") or ""

    if case.get("expected") == "abstain":
        if _is_fallback(run):
            return _result(True, "abstain", "declined, as expected")
        return _result(False, "abstain", "answered a question the filing does not answer")

    if case.get("scoring") == "zero_or_not_found":
        if _is_fallback(run):
            return _result(True, "zero_or_not_found", "reported the item is not shown")
        amounts = [q for q in read_quantities(answer) if q.value != 0 and not _looks_like_year(q)]
        if amounts:
            return _result(False, "zero_or_not_found", "gave an amount for an item that is not shown")
        return _result(True, "zero_or_not_found", "answered 0 or not shown")

    if _is_fallback(run):
        return _result(False, "declined", "declined to answer a question the filing answers")

    number_checks = {}
    if case.get("acceptable_answers"):
        options = case["acceptable_answers"]
        number_checks = {"any_of": {value: number_matches(value, answer) for value in options}}
        numbers_pass = any(number_checks["any_of"].values())
    else:
        number_checks = {value: number_matches(value, answer) for value in case.get("key_values", [])}
        numbers_pass = all(number_checks.values())

    answer_format = case.get("answer_format")
    if answer_format == "numeric":
        missing = _missing_numbers(number_checks)
        reason = "number matches" if numbers_pass else f"expected {missing}"
        return _result(numbers_pass, "numbers", reason, numbers=number_checks)

    if grade_fn is None:
        return _result(False, "unscored", "no grader available", numbers=number_checks)

    grade = grade_answer(case, answer, grade_fn)
    checklist_pass = grade["facts_complete"] and grade["no_contradiction"] and grade["right_subject"]
    passed = checklist_pass and numbers_pass
    failures = [name for name in ("facts_complete", "no_contradiction", "right_subject") if not grade[name]]

    if answer_format == "yes_no":
        expected_verdict = _expected_verdict(case.get("expected_answer", ""))
        verdict_pass = grade["verdict"] == expected_verdict
        passed = passed and verdict_pass
        if not verdict_pass:
            failures.insert(0, f"verdict {grade['verdict']} (expected {expected_verdict})")

    if not numbers_pass:
        failures.append(f"numbers: expected {_missing_numbers(number_checks)}")
    reason = "all checks pass" if passed else "; ".join(failures) + f" | grader: {grade['reason']}"
    return _result(passed, "grader", reason, numbers=number_checks, grader=grade)


def _looks_like_year(quantity: Quantity) -> bool:
    return not quantity.percent and not quantity.scaled and quantity.decimals == 0 and 1990 <= quantity.value <= 2035


def _missing_numbers(number_checks: dict[str, Any]) -> list[str]:
    checks = number_checks.get("any_of", number_checks)
    return [value for value, ok in checks.items() if not ok]


def grade_answer(case: dict[str, Any], answer: str, grade_fn: GradeFn) -> dict[str, Any]:
    """Ask the grader to fill in the checklist; a malformed reply counts as failing every check."""
    note = case.get("grader_note")
    prompt = GRADER_PROMPT.format(
        question=case.get("question", ""),
        expected_answer=case.get("expected_answer", ""),
        app_answer=answer,
        note_line=f"Grading note: {note}\n" if note else "",
    )
    try:
        reply = grade_fn(prompt)
        grade = {
            "facts_complete": reply["facts_complete"] is True,
            "no_contradiction": reply["no_contradiction"] is True,
            "right_subject": reply["right_subject"] is True,
            "verdict": str(reply.get("verdict", "none")).lower(),
            "reason": str(reply.get("reason", "")),
        }
    except Exception as exc:
        grade = {
            "facts_complete": False,
            "no_contradiction": False,
            "right_subject": False,
            "verdict": "none",
            "reason": f"grader reply unusable: {type(exc).__name__}",
        }
    return grade


def grader_model() -> str:
    return os.getenv("OPENAI_GRADER_MODEL", DEFAULT_GRADER_MODEL)


def openai_grade_fn() -> GradeFn:
    """Grade with an OpenAI chat model, set by `OPENAI_GRADER_MODEL` (default gpt-5.4-nano)."""
    from langchain_openai import ChatOpenAI

    model = ChatOpenAI(model=grader_model(), temperature=0)

    def grade(prompt: str) -> dict[str, Any]:
        content = model.invoke(prompt).content
        text = content if isinstance(content, str) else "".join(
            part if isinstance(part, str) else part.get("text", "") for part in content
        )
        return json.loads(text.strip().removeprefix("```json").removesuffix("```").strip())

    return grade
