"""The answer model's calculator: the model asks, the app does the arithmetic.

The answer model slips on arithmetic (93.91 instead of 93.86 days; a 2.2-point drop from subtracting already
rounded margins when the exact figures give 2.1), so it gets one tool, `calculate`, and is told to use it for
every step. `answer_with_calculator` runs the exchange: the model asks for a calculation, the app evaluates it
and sends back the exact result, and the model carries on until it writes its final reply. The calculations
are returned so grounding can accept their results (see `answer_grounding`).

`evaluate` reads plain arithmetic only (numbers, + - * /, brackets) by walking Python's syntax tree, never
`eval`, so nothing a model sends can run as code.
"""

from __future__ import annotations

import ast
import operator
import re
from dataclasses import dataclass
from typing import Any

# Model calls one answer may take; a single call can ask for several calculations at once.
MAX_ROUNDS = 6

CALCULATE_TOOL = {
    "type": "function",
    "function": {
        "name": "calculate",
        "description": "Evaluate arithmetic exactly. Use it for every calculation instead of working it out yourself.",
        "parameters": {
            "type": "object",
            "properties": {
                "expression": {
                    "type": "string",
                    "description": "Numbers, + - * / and brackets only, e.g. (177866 - 135987) / 135987 * 100",
                }
            },
            "required": ["expression"],
        },
    },
}

_OPERATORS = {"−": "-", "–": "-", "×": "*", "÷": "/"}
_BINARY = {ast.Add: operator.add, ast.Sub: operator.sub, ast.Mult: operator.mul, ast.Div: operator.truediv}


@dataclass(frozen=True)
class Calculation:
    expression: str
    result: float


def evaluate(expression: str) -> float | None:
    """The value of plain arithmetic, or None if `expression` is anything else or divides by zero.

    Accepts the symbols models write (−, ×, ÷), thousands commas, "$" and "%".
    """
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
        if isinstance(node, ast.Constant) and isinstance(node.value, (int, float)) and not isinstance(node.value, bool):
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


def answer_with_calculator(generator: Any, prompt: str) -> tuple[Any, list[Calculation]]:
    """Return the model's final reply to `prompt` and the calculations it asked for on the way.

    Only generators that declare `supports_tools = True` (the metered Groq model) get the tool; any other
    generator is called once with the plain prompt. If the model is still asking for calculations after
    `MAX_ROUNDS` calls, its last reply is returned and the caller finds no valid answer in it.
    """
    if getattr(generator, "supports_tools", False) is not True:
        return generator.invoke(prompt), []

    from langchain_core.messages import HumanMessage, ToolMessage

    messages: list[Any] = [HumanMessage(content=prompt)]
    calculations: list[Calculation] = []
    for _ in range(MAX_ROUNDS):
        response = generator.invoke_with_tools(messages, [CALCULATE_TOOL])
        tool_calls = getattr(response, "tool_calls", None) or []
        if not tool_calls:
            break
        messages.append(response)
        for call in tool_calls:
            expression = str((call.get("args") or {}).get("expression", ""))
            value = evaluate(expression)
            if value is None:
                reply = "error: use only numbers, + - * / and brackets"
            else:
                calculations.append(Calculation(expression, value))
                reply = f"{value:.10g}"
            messages.append(ToolMessage(content=reply, tool_call_id=call["id"]))
    return response, calculations
