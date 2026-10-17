"""
tests/test_tools/test_math_eval.py
==================================
Unit tests for the safe symbolic math evaluation tool using SymPy.
"""

from app.tools.interface import ToolStatus
from app.tools.math_eval import MathEvalInput, evaluate_math


class TestMathEvaluation:
    def test_evaluate_basic_numeric(self) -> None:
        inp = MathEvalInput(expression="2 + 3 * 4", mode="evaluate")
        res = evaluate_math(inp)
        assert res.status == ToolStatus.SUCCESS
        assert res.result_text is not None
        assert float(res.result_text) == 14.0

    def test_evaluate_with_variable_substitutions(self) -> None:
        inp = MathEvalInput(
            expression="x**2 + 2*x + 1",
            variables={"x": 3.0},
            mode="evaluate",
        )
        res = evaluate_math(inp)
        assert res.status == ToolStatus.SUCCESS
        assert res.result_text is not None
        assert float(res.result_text) == 16.0

    def test_simplify_trigonometric_identity(self) -> None:
        inp = MathEvalInput(
            expression="sin(x)**2 + cos(x)**2",
            mode="simplify",
        )
        res = evaluate_math(inp)
        assert res.status == ToolStatus.SUCCESS
        assert res.result_text == "1"

    def test_differentiate_polynomial(self) -> None:
        inp = MathEvalInput(
            expression="x**3 + 5*x**2 - 7*x + 12",
            mode="differentiate",
            variables={"x": 0.0},
        )
        res = evaluate_math(inp)
        assert res.status == ToolStatus.SUCCESS
        assert res.result_text is not None
        assert "3*x**2 + 10*x - 7" in res.result_text

    def test_integrate_polynomial(self) -> None:
        inp = MathEvalInput(
            expression="3*x**2 + 2*x",
            mode="integrate",
            variables={"x": 0.0},
        )
        res = evaluate_math(inp)
        assert res.status == ToolStatus.SUCCESS
        assert res.result_text is not None
        assert "x**3 + x**2" in res.result_text

    def test_solve_quadratic_equation(self) -> None:
        inp = MathEvalInput(
            expression="x**2 - 9",
            mode="solve",
            variables={"x": 0.0},
        )
        res = evaluate_math(inp)
        assert res.status == ToolStatus.SUCCESS
        assert res.result_text is not None
        assert "-3" in res.result_text and "3" in res.result_text

    def test_empty_expression_returns_error(self) -> None:
        inp = MathEvalInput(expression="   ", mode="evaluate")
        res = evaluate_math(inp)
        assert res.status == ToolStatus.ERROR
        assert "Expression cannot be empty" in str(res.error)

    def test_invalid_syntax_returns_error(self) -> None:
        inp = MathEvalInput(expression="2 +* 5", mode="evaluate")
        res = evaluate_math(inp)
        assert res.status == ToolStatus.ERROR
        assert "Failed to parse" in str(res.error)

    def test_latex_output_generated(self) -> None:
        inp = MathEvalInput(expression="sqrt(x) + x/2", mode="simplify")
        res = evaluate_math(inp)
        assert res.status == ToolStatus.SUCCESS
        assert res.latex is not None
        assert "\\sqrt{x}" in res.latex
