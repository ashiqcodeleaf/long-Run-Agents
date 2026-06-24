from __future__ import annotations

import math
import unittest

from calculator_app import calculate, divide, evaluate_expression, format_result


class CalculatorAppTests(unittest.TestCase):
    def test_basic_operations(self) -> None:
        self.assertEqual(calculate(2, "+", 3), 5)
        self.assertEqual(calculate(7, "-", 4), 3)
        self.assertEqual(calculate(6, "*", 5), 30)
        self.assertEqual(calculate(8, "/", 2), 4)
        self.assertEqual(calculate(10, "%", 3), 1)
        self.assertEqual(calculate(2, "^", 3), 8)

    def test_expression_evaluation(self) -> None:
        self.assertEqual(evaluate_expression("2 + 3 * 4"), 14.0)
        self.assertEqual(evaluate_expression("sqrt(16)"), 4.0)
        self.assertAlmostEqual(evaluate_expression("sin(pi / 2)"), 1.0)
        self.assertAlmostEqual(evaluate_expression("log(e)"), 1.0)

    def test_formatting_and_errors(self) -> None:
        self.assertEqual(format_result(4.0), "4")
        self.assertEqual(format_result(4.25), "4.25")
        with self.assertRaises(ValueError):
            calculate(1, "?", 2)
        with self.assertRaises(ZeroDivisionError):
            divide(1, 0)
        with self.assertRaises(ValueError):
            evaluate_expression("__import__('os').system('echo nope')")


if __name__ == "__main__":
    unittest.main()