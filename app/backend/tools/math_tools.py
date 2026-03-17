"""Math tool — safe expression evaluation via AST parsing.

Module role:
    Provides a ``calculate`` tool that evaluates arithmetic expressions
    without using ``eval()``.  Parses the expression into a Python AST
    and recursively evaluates only whitelisted node types (constants,
    binary ops, unary ops, function calls from a safe set).

    This eliminates the class-based sandbox escape vectors that
    ``eval(expr, {"__builtins__": {}}, ...)`` is vulnerable to.

Safe functions:
    sqrt, sin, cos, tan, log, log10, ceil, floor, abs, round, min, max

Safe constants:
    pi, e

Dependents:
    Available to agents via scenario.yaml ``tools: [tools.math_tools:calculate]``
"""

import ast
import math
import operator
from typing import Annotated

from agent_framework import tool
from pydantic import Field

# ── Safe operator mapping for binary and unary AST nodes ───────────────────
_OPS = {
    ast.Add: operator.add,
    ast.Sub: operator.sub,
    ast.Mult: operator.mul,
    ast.Div: operator.truediv,
    ast.Pow: operator.pow,
    ast.FloorDiv: operator.floordiv,
    ast.Mod: operator.mod,
    ast.USub: operator.neg,
    ast.UAdd: operator.pos,
}

# ── Whitelisted math functions and constants ────────────────────────────
_FUNCS = {
    "sqrt": math.sqrt, "sin": math.sin, "cos": math.cos, "tan": math.tan,
    "log": math.log, "log10": math.log10, "ceil": math.ceil, "floor": math.floor,
    "abs": abs, "round": round, "min": min, "max": max,
}
_CONSTS = {"pi": math.pi, "e": math.e}


def _safe_eval(node):
    """Recursively evaluate an AST node using only safe operations.

    Parameters:
        node: An ``ast.AST`` node from ``ast.parse(expr, mode="eval")``.

    Returns:
        The numeric result of the expression.

    Raises:
        ValueError: If the node type is unsupported or references an
            unknown variable/function.
    """
    if isinstance(node, ast.Expression):
        return _safe_eval(node.body)
    if isinstance(node, ast.Constant):
        if isinstance(node.value, (int, float)):
            return node.value
        raise ValueError(f"Unsupported constant: {node.value!r}")
    if isinstance(node, ast.Name):
        if node.id in _CONSTS:
            return _CONSTS[node.id]
        raise ValueError(f"Unknown variable: {node.id}")
    if isinstance(node, ast.BinOp):
        op = _OPS.get(type(node.op))
        if not op:
            raise ValueError(f"Unsupported operator: {type(node.op).__name__}")
        return op(_safe_eval(node.left), _safe_eval(node.right))
    if isinstance(node, ast.UnaryOp):
        op = _OPS.get(type(node.op))
        if not op:
            raise ValueError(f"Unsupported unary op: {type(node.op).__name__}")
        return op(_safe_eval(node.operand))
    if isinstance(node, ast.Call):
        if not isinstance(node.func, ast.Name) or node.func.id not in _FUNCS:
            raise ValueError(f"Unknown function: {ast.dump(node.func)}")
        args = [_safe_eval(a) for a in node.args]
        return _FUNCS[node.func.id](*args)
    raise ValueError(f"Unsupported expression: {ast.dump(node)}")


@tool
def calculate(
    expression: Annotated[str, Field(description="A math expression, e.g. '2 + 3 * 4' or 'sqrt(144)'")],
) -> str:
    """Evaluate a mathematical expression safely. Supports arithmetic, sqrt, sin, cos, log, pi, e."""
    try:
        tree = ast.parse(expression, mode="eval")
        result = _safe_eval(tree)
        return str(result)
    except Exception as e:
        return f"Error: {e}"
