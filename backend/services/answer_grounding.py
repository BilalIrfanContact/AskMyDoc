"""Decide whether a drafted answer is backed by the excerpts the model was shown.

The failure that matters in a filings app is an invented figure, so grounding checks numbers:

1. Every number in the answer must appear in the excerpts or in the question, compared by value:
   "$1,577 million" matches "1,577", "$8.74 billion" matches "8,738" (in millions) rounded, and
   "(0.6)%" matches "0.6". Signs aren't compared; the words around a number carry its direction.
2. A number found in neither is accepted only when the answer shows the arithmetic that produced it,
   for example "(177,866 − 135,987) ÷ 135,987 × 100 = 30.8%": every operand must pass rule 1 or be a
   standard constant (× 100, ÷ 2 for an average, 365 days...), and the arithmetic must come out to the
   result as shown. Wrong arithmetic rejects the answer. Label words inside the working are ignored
   ("Operating profit 11,512 + D&A 2,763 = 14,275"), and a checked result may feed the next step.

Words aren't checked. The model's `found_in_excerpts` flag handles "not in the document", and word
overlap rejected honest paraphrases ("Yes, it retained card members") while passing wrong answers
built from the document's own words. The cost: an invented claim with no number in it isn't caught.
"""

from __future__ import annotations

import ast
import operator
import re
from dataclasses import dataclass
from typing import Iterable

_NUMBER = re.compile(r"\d{1,3}(?:,\d{3})+(?:\.\d+)?|\d+(?:\.\d+)?")
_SCALE = re.compile(r"\s*(?:(?:thousand|million|billion|trillion)s?\b|(?:k|m|mm|bn|b)\b)", re.IGNORECASE)
# A shown calculation: anything up to "=" (or "≈") on one line, then the result, which may be negative. The result
# is matched by lookahead so it can start the next step's working.
_WORKING = re.compile(r"([^=≈\n]+?)\s*[=≈]\s*(?=[-−–]?\$?\(?(\d[\d,]*(?:\.\d+)?))")
# Label words such as "Operating profit" or "D&A"; dropped before the arithmetic is read.
_LABEL = re.compile(r"[A-Za-z][A-Za-z&'’]*")
_OPERATOR_SIGN = re.compile(r"[+\-−–*/×÷]")
_OPERATORS = {"−": "-", "–": "-", "×": "*", "÷": "/"}
# Constants a calculation may use without the filing printing them: percentages, averages, periods, units.
_CONSTANTS = {2.0, 4.0, 12.0, 100.0, 360.0, 365.0, 1000.0}
_BINARY = {ast.Add: operator.add, ast.Sub: operator.sub, ast.Mult: operator.mul, ast.Div: operator.truediv}


@dataclass(frozen=True)
class Number:
    text: str
    value: float
    decimals: int
    scaled: bool  # written with a unit like "million" or "bn", so it may be a table figure in other units


def numbers_in(text: str) -> list[Number]:
    found = []
    for match in _NUMBER.finditer(text):
        digits = match.group()
        decimals = len(digits.split(".")[1]) if "." in digits else 0
        scaled = bool(_SCALE.match(text, match.end()))
        found.append(Number(digits, float(digits.replace(",", "")), decimals, scaled))
    return found


def _rounds_to(value: float, number: Number) -> bool:
    return abs(round(value, number.decimals) - number.value) < 10 ** -(number.decimals + 6)


def is_supported(number: Number, sources: Iterable[Number]) -> bool:
    """True when `number` is a source figure, that figure rounded, or the figure in other units."""
    for source in sources:
        if abs(source.value - number.value) < 1e-9:
            return True
        if number.decimals < source.decimals and _rounds_to(source.value, number):
            return True
        if number.scaled and any(_rounds_to(source.value / 1000**step, number) for step in (1, 2, 3)):
            return True
        # Same digits in other units without a unit word: "381.603" for "381,603" (in thousands).
        if number.decimals and any(abs(source.value / 1000**step - number.value) < 1e-9 for step in (1, 2, 3)):
            return True
    return False


def _evaluate(expression: str) -> float | None:
    """Evaluate plain arithmetic (numbers, + - * /, brackets) without `eval`; None if it isn't that."""
    for symbol, replacement in _OPERATORS.items():
        expression = expression.replace(symbol, replacement)
    expression = re.sub(r"(?<=\d),(?=\d{3})", "", expression).replace("$", "").replace("%", "")
    try:
        tree = ast.parse(expression.strip(), mode="eval")
    except SyntaxError:
        return None

    def walk(node: ast.AST) -> float:
        if isinstance(node, ast.Expression):
            return walk(node.body)
        if isinstance(node, ast.Constant) and isinstance(node.value, (int, float)):
            return float(node.value)
        if isinstance(node, ast.UnaryOp) and isinstance(node.op, (ast.USub, ast.UAdd)):
            return -walk(node.operand) if isinstance(node.op, ast.USub) else walk(node.operand)
        if isinstance(node, ast.BinOp) and type(node.op) in _BINARY:
            return _BINARY[type(node.op)](walk(node.left), walk(node.right))
        raise ValueError("not plain arithmetic")

    try:
        return walk(tree)
    except (ValueError, ZeroDivisionError):
        return None


def _shown_arithmetic(text: str) -> tuple[str, float] | None:
    """The longest tail of `text` that is a calculation (two or more numbers and an operator), with its value.

    Trying each starting point drops a leading year or label, as in "In 2017 (177,866 − 135,987) ÷ …".
    """
    text = _LABEL.sub(" ", text)
    starts = [
        i for i, char in enumerate(text)
        if char == "(" or ((char.isdigit() or char in "-−–") and (i == 0 or text[i - 1] in " ($"))
    ]
    for start in starts:
        expression = text[start:]
        if len(numbers_in(expression)) < 2 or not _OPERATOR_SIGN.search(expression):
            continue
        value = _evaluate(expression)
        if value is not None:
            return expression, value
    return None


def _failure(reason: str, numbers: list[str]) -> dict[str, object]:
    return {"reason": reason, "segment_index": None, "unsupported_numbers": numbers, "unsupported_terms": []}


def find_grounding_failure(answer: str, excerpts: Iterable[str], question: str = "") -> dict[str, object] | None:
    """Return why `answer` isn't backed by the excerpts (or the question), or None if it is.

    The failure lists the offending numbers, so logs show why without recording the answer text.
    """
    excerpts = [excerpt for excerpt in excerpts if excerpt]
    if not excerpts:
        return _failure("no_evidence", [])
    sources = [number for text in [*excerpts, question] for number in numbers_in(text)]

    derived: list[Number] = []
    for match in _WORKING.finditer(answer):
        shown = _shown_arithmetic(match.group(1))
        if shown is None:
            continue  # Not a calculation; its result must then be supported like any other number.
        expression, computed = shown
        operands = numbers_in(expression)
        result = numbers_in(match.group(2))[0]
        as_percent = re.match(r"\s*(?:%|percent)", answer[match.end(2):]) is not None
        if not (_rounds_to(abs(computed), result) or (as_percent and _rounds_to(abs(computed) * 100, result))):
            return _failure("calculation_incorrect", [result.text])
        missing = [o.text for o in operands if o.value not in _CONSTANTS and not is_supported(o, [*sources, *derived])]
        if missing:
            return _failure("unsupported_numbers", missing)
        derived += [result, *operands]  # The checked sum vouches for its own constants and result.

    unsupported = {number.text for number in numbers_in(answer) if not is_supported(number, [*sources, *derived])}
    return _failure("unsupported_numbers", sorted(unsupported)) if unsupported else None
