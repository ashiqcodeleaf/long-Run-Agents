"""Classic-style terminal calculator for LongRun Agent MVP.

This is a dependency-light calculator that renders a keypad in the terminal,
supports expression entry, and provides common scientific functions.

Run directly for an interactive calculator experience.
"""

from __future__ import annotations

import ast
import math
from dataclasses import dataclass
from typing import Any, Callable


Number = float


class CalculatorError(ValueError):
    """Raised when an expression cannot be evaluated safely."""


SAFE_FUNCTIONS: dict[str, Callable[..., Number]] = {
    "abs": abs,
    "round": round,
    "sqrt": math.sqrt,
    "sin": math.sin,
    "cos": math.cos,
    "tan": math.tan,
    "asin": math.asin,
    "acos": math.acos,
    "atan": math.atan,
    "log": math.log,
    "log10": math.log10,
    "exp": math.exp,
    "floor": math.floor,
    "ceil": math.ceil,
}

SAFE_CONSTANTS: dict[str, Number] = {
    "pi": math.pi,
    "e": math.e,
    "tau": math.tau,
}

KEYPAD = (
    ("C", "⌫", "(", ")"),
    ("7", "8", "9", "/"),
    ("4", "5", "6", "*"),
    ("1", "2", "3", "-"),
    ("0", ".", "=", "+"),
)


def add(a: Number, b: Number) -> Number:
    return a + b


def subtract(a: Number, b: Number) -> Number:
    return a - b


def multiply(a: Number, b: Number) -> Number:
    return a * b


def divide(a: Number, b: Number) -> Number:
    if b == 0:
        raise ZeroDivisionError("Cannot divide by zero.")
    return a / b


def percentage(value: Number) -> Number:
    return value / 100


def negate(value: Number) -> Number:
    return -value


@dataclass(frozen=True)
class SupportedExpression:
    text: str


class _SafeEvaluator(ast.NodeVisitor):
    def visit_Expression(self, node: ast.Expression) -> Number:
        return self.visit(node.body)

    def visit_BinOp(self, node: ast.BinOp) -> Number:
        left = self.visit(node.left)
        right = self.visit(node.right)
        if isinstance(node.op, ast.Add):
            return add(left, right)
        if isinstance(node.op, ast.Sub):
            return subtract(left, right)
        if isinstance(node.op, ast.Mult):
            return multiply(left, right)
        if isinstance(node.op, ast.Div):
            return divide(left, right)
        if isinstance(node.op, ast.Mod):
            return left % right
        if isinstance(node.op, ast.Pow):
            return left**right
        raise CalculatorError("Unsupported operator.")

    def visit_UnaryOp(self, node: ast.UnaryOp) -> Number:
        operand = self.visit(node.operand)
        if isinstance(node.op, ast.UAdd):
            return +operand
        if isinstance(node.op, ast.USub):
            return -operand
        raise CalculatorError("Unsupported unary operator.")

    def visit_Call(self, node: ast.Call) -> Number:
        if not isinstance(node.func, ast.Name):
            raise CalculatorError("Only direct function calls are allowed.")
        func = SAFE_FUNCTIONS.get(node.func.id)
        if func is None:
            raise CalculatorError(f"Unsupported function: {node.func.id}")
        args = [self.visit(arg) for arg in node.args]
        if node.keywords:
            raise CalculatorError("Keyword arguments are not supported.")
        return float(func(*args))

    def visit_Name(self, node: ast.Name) -> Number:
        try:
            return SAFE_CONSTANTS[node.id]
        except KeyError as exc:
            raise CalculatorError(f"Unknown name: {node.id}") from exc

    def visit_Constant(self, node: ast.Constant) -> Number:
        if isinstance(node.value, (int, float)):
            return float(node.value)
        raise CalculatorError("Only numeric constants are allowed.")

    def generic_visit(self, node: ast.AST) -> Any:
        raise CalculatorError(f"Unsupported syntax: {type(node).__name__}")


EVALUATOR = _SafeEvaluator()


def calculate(a: Number, operator: str, b: Number) -> Number:
    operators: dict[str, Callable[[Number, Number], Number]] = {
        "+": add,
        "-": subtract,
        "*": multiply,
        "/": divide,
        "%": lambda x, y: x % y,
        "^": lambda x, y: x**y,
    }
    try:
        operation = operators[operator]
    except KeyError as exc:
        raise ValueError(f"Unsupported operator: {operator}") from exc
    return operation(a, b)


def evaluate_expression(expression: str) -> Number:
    normalized = expression.strip()
    if not normalized:
        raise CalculatorError("Empty expression.")
    normalized = normalized.replace("×", "*").replace("÷", "/").replace("^", "**")
    try:
        tree = ast.parse(normalized, mode="eval")
    except SyntaxError as exc:
        raise CalculatorError("Invalid expression.") from exc
    result = EVALUATOR.visit(tree)
    return float(result)


def format_result(value: Number) -> str:
    if value.is_integer():
        return str(int(value))
    return f"{value:.10g}"


def render_ui(display: str) -> None:
    print("\n" + "=" * 34)
    print(" LongRun Calculator")
    print("=" * 34)
    print(f" Display: {display or '0'}")
    print("".join(["=" * 34]))
    for row in KEYPAD:
        print("  " + "  ".join(f"[{key:^2}]" for key in row))
    print("\nCommands: = evaluate | C clear | ⌫ delete | quit exit")
    print("Functions: sqrt(x), sin(x), cos(x), tan(x), log(x), log10(x), abs(x), round(x)")
    print("Constants: pi, e, tau")


def apply_key(expression: str, key: str) -> str:
    if key in {"C", "clear"}:
        return ""
    if key in {"⌫", "back", "backspace"}:
        return expression[:-1]
    if key == "=":
        return expression
    if key == "±":
        return expression + "-"
    if key == "%":
        return expression + "/100"
    return expression + key


def main() -> int:
    expression = ""
    last_result = 0.0

    while True:
        render_ui(expression)
        user_input = input("Key or expression> ").strip()
        if not user_input:
            continue
        lower = user_input.lower()
        if lower in {"quit", "exit", "q"}:
            print("Goodbye.")
            return 0
        if user_input in {"C", "clear"}:
            expression = ""
            continue
        if user_input in {"⌫", "back", "backspace"}:
            expression = expression[:-1]
            continue
        if user_input == "=":
            try:
                last_result = evaluate_expression(expression)
                expression = format_result(last_result)
                print(f"Result: {expression}")
            except CalculatorError as exc:
                print(f"Error: {exc}")
            continue

        if user_input == "ANS":
            expression += format_result(last_result)
            continue

        if len(user_input) == 1 and user_input in set("0123456789.+-*/()%^"):
            expression = apply_key(expression, user_input)
            continue

        try:
            preview = evaluate_expression(user_input)
            expression = format_result(preview)
            last_result = preview
            print(f"Result: {expression}")
        except CalculatorError:
            expression = apply_key(expression, user_input)


if __name__ == "__main__":
    raise SystemExit(main())
