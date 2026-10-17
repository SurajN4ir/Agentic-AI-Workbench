"""
app/tools/math_eval.py
======================
Safe, symbolic mathematics and formula evaluation using SymPy.
Never uses python eval() or exec().
Provides step-by-step mathematical reasoning and LaTeX rendering.
"""

from typing import Literal

import sympy as sp
from pydantic import Field

from app.tools.interface import ToolInput, ToolResult, ToolStatus

MathMode = Literal["evaluate", "solve", "simplify", "differentiate", "integrate"]


class MathEvalInput(ToolInput):
    """Input parameters for mathematical formula evaluation."""

    expression: str = Field(..., description="Mathematical expression (e.g., '2*x + 5', 'sin(x)**2 + cos(x)**2')")
    variables: dict[str, float] = Field(default_factory=dict, description="Variable substitutions, e.g. {'x': 3.5}")
    mode: MathMode = Field(default="evaluate", description="Evaluation mode")
    operation: str | None = Field(default=None, description="Alias for mode")


class MathEvalResult(ToolResult):
    result_text: str | None = None
    steps: list[str] = Field(default_factory=list)
    latex: str | None = None


def evaluate_math(input_data: MathEvalInput) -> MathEvalResult:
    """Executes symbolic math calculation safely without code evaluation."""
    expr_str = input_data.expression.strip()
    if not expr_str:
        return MathEvalResult(
            status=ToolStatus.ERROR,
            error="Expression cannot be empty.",
        )

    steps: list[str] = []

    # Bind variables as symbols
    symbol_names = set(input_data.variables.keys()).union({"x", "y", "z", "t", "a", "b", "c", "n"})
    sympy_symbols = {s: sp.Symbol(s) for s in symbol_names}

    try:
        if "=" in expr_str and not expr_str.startswith("Eq("):
            parts = expr_str.split("=", 1)
            lhs = sp.sympify(parts[0].strip(), locals=sympy_symbols, evaluate=False)
            rhs = sp.sympify(parts[1].strip(), locals=sympy_symbols, evaluate=False)
            parsed_expr = sp.Eq(lhs, rhs)
        else:
            parsed_expr = sp.sympify(expr_str, locals=sympy_symbols, evaluate=False)
        steps.append(f"Parsed Expression: {parsed_expr}")
    except Exception as e:
        return MathEvalResult(
            status=ToolStatus.ERROR,
            error=f"Failed to parse mathematical expression '{expr_str}': {e}",
            steps=steps,
        )

    final_result_obj = None
    raw_mode = input_data.operation or input_data.mode
    mode = raw_mode.lower().strip()
    if mode == "eval":
        mode = "evaluate"
    elif mode == "diff":
        mode = "differentiate"


    try:
        if mode == "evaluate":
            if input_data.variables:
                steps.append(f"Substitutions: {input_data.variables}")
                subs_map = {sp.Symbol(k): v for k, v in input_data.variables.items()}
                substituted = parsed_expr.subs(subs_map)
                final_result_obj = substituted.evalf()
                steps.append(f"Evaluated Result: {final_result_obj}")
            else:
                final_result_obj = parsed_expr.evalf()
                steps.append(f"Evaluated Result: {final_result_obj}")

        elif mode == "simplify":
            steps.append("Applying algebraic simplification...")
            final_result_obj = sp.simplify(parsed_expr)
            steps.append(f"Simplified Expression: {final_result_obj}")

        elif mode == "differentiate":
            diff_var = sp.Symbol("x")
            for var_name in input_data.variables:
                diff_var = sp.Symbol(var_name)
                break
            steps.append(f"Computing derivative d/d{diff_var}")
            final_result_obj = sp.diff(parsed_expr, diff_var)
            steps.append(f"Derivative: {final_result_obj}")

        elif mode == "integrate":
            int_var = sp.Symbol("x")
            for var_name in input_data.variables:
                int_var = sp.Symbol(var_name)
                break
            steps.append(f"Computing indefinite integral with respect to {int_var}")
            final_result_obj = sp.integrate(parsed_expr, int_var)
            steps.append(f"Antiderivative: {final_result_obj} + C")

        elif mode == "solve":
            solve_var = sp.Symbol("x")
            for var_name in input_data.variables:
                solve_var = sp.Symbol(var_name)
                break
            steps.append(f"Solving equation for variable '{solve_var}'")
            is_relational = isinstance(parsed_expr, sp.Eq | sp.Ne | sp.Gt | sp.Lt | sp.Ge | sp.Le)
            equation = parsed_expr if is_relational else sp.Eq(parsed_expr, 0)
            final_result_obj = sp.solve(equation, solve_var)
            steps.append(f"Solutions: {final_result_obj}")

        else:
            return MathEvalResult(
                status=ToolStatus.ERROR,
                error=f"Unsupported mode '{mode}'.",
                steps=steps,
            )

        latex_str = sp.latex(final_result_obj) if final_result_obj is not None else sp.latex(parsed_expr)
        result_str = str(final_result_obj)

        return MathEvalResult(
            status=ToolStatus.SUCCESS,
            output=result_str,
            data={"result": result_str, "latex": latex_str},
            result_text=result_str,
            steps=steps,
            latex=latex_str,
        )


    except Exception as exc:
        return MathEvalResult(
            status=ToolStatus.ERROR,
            error=f"Computation error during '{mode}': {exc}",
            steps=steps,
        )
