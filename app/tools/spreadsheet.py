"""
app/tools/spreadsheet.py — Safe, High-Performance Tabular Data Analysis Tool
=============================================================================
Attribution: Adapted from sathwik-anumandla/sovereign-agent (SIH PS 26117).
Hardened for enterprise production with AST-based formula computation,
resource exhaustion bounds (zip bombs, row/column limits), and CSV/Excel formula
injection sanitization.

Guarantees:
1. Zero pandas dependency — pure Python with csv & openpyxl read-only streaming.
2. Expression Safety: AST whitelist; zero eval(), exec(), or arbitrary attribute access.
3. Bounded exponentiation (power <= 4) and safe division-by-zero handling.
4. Resource limits: max 25 MB file size, 50,000 rows, 200 columns.
5. Formula injection mitigation: cell strings starting with =, +, -, @ are sanitized on export.
6. Graceful handling of corrupted/malformed workbooks.
"""

from __future__ import annotations

import ast
import csv
import math
import operator
from pathlib import Path
from typing import Any, Literal

import openpyxl
from pydantic import Field

from app.tools.interface import ToolInput, ToolResult, ToolStatus, validate_workspace_path

# Resource & Security Limits
MAX_SPREADSHEET_BYTES = 25 * 1024 * 1024  # 25 MB
MAX_ROWS = 50_000
MAX_COLUMNS = 200
MAX_POWER_EXPONENT = 4

ALLOWED_OPERATIONS = {"read", "filter", "aggregate", "compute"}
ALLOWED_FILTER_OPERATORS = {"==", "!=", ">", "<", ">=", "<=", "contains"}
ALLOWED_AGG_FUNCTIONS = {"sum", "mean", "count", "min", "max"}


class SpreadsheetInput(ToolInput):
    """Input payload for tabular spreadsheet analysis."""

    file_path: str = Field(description="Relative path to CSV or Excel file in the workspace.")
    operation: Literal["read", "filter", "aggregate", "compute"] = Field(
        default="read",
        description="Tabular operation: 'read' (sample rows), 'filter' (row filtering), 'aggregate' (groupby/stat), 'compute' (new column formula).",
    )
    params: dict[str, Any] = Field(
        default_factory=dict,
        description="Operation parameters (e.g. limit, column, value, operator, group_by, function, target_column, formula).",
    )
    session_id: str = Field(default="default", description="Active workspace session identifier.")


class SpreadsheetResult(ToolResult):
    """Structured output for spreadsheet analysis."""

    data: list[dict[str, Any]] | None = None
    summary: str | None = None
    columns: list[str] | None = None
    total_rows: int | None = None


def _sanitize_cell_for_export(val: Any) -> Any:
    """Mitigate CSV/Excel Formula Injection (DDE attacks).

    Prepends single quote if string starts with formula tokens (=, +, -, @, \\t, \\r).
    """
    if isinstance(val, str) and val:
        if val[0] in ("=", "+", "-", "@", "\t", "\r"):
            return f"'{val}"
    return val


def _load_table(file_path: Path) -> tuple[list[str], list[dict[str, Any]]]:
    """Loads CSV or XLSX into a list of column names and row dictionaries with strict bounds."""
    # Check file size limit
    file_size = file_path.stat().st_size
    if file_size > MAX_SPREADSHEET_BYTES:
        raise ValueError(
            f"Spreadsheet file size ({file_size} bytes) exceeds maximum limit of {MAX_SPREADSHEET_BYTES} bytes."
        )

    suffix = file_path.suffix.lower()

    if suffix in [".csv", ".tsv", ".txt"]:
        sep = "\t" if suffix == ".tsv" else ","
        try:
            with file_path.open("r", encoding="utf-8", errors="replace", newline="") as f:
                reader = csv.DictReader(f, delimiter=sep)
                raw_cols = reader.fieldnames or []
                if len(raw_cols) > MAX_COLUMNS:
                    raise ValueError(
                        f"Spreadsheet column count ({len(raw_cols)}) exceeds maximum allowed ({MAX_COLUMNS})."
                    )

                columns = list(raw_cols)
                rows: list[dict[str, Any]] = []

                for row_idx, r in enumerate(reader, start=1):
                    if row_idx > MAX_ROWS:
                        break  # bounded ingestion

                    converted: dict[str, Any] = {}
                    for k, v in r.items():
                        if k is None:
                            continue
                        if v is None or v == "":
                            converted[k] = None
                        else:
                            try:
                                if "." in v:
                                    converted[k] = float(v)
                                else:
                                    converted[k] = int(v)
                            except ValueError:
                                converted[k] = v
                    rows.append(converted)

                return columns, rows
        except csv.Error as e:
            raise ValueError(f"Malformed CSV file '{file_path.name}': {e}") from e

    elif suffix in [".xlsx", ".xls"]:
        try:
            # Use read_only=True to prevent zip bomb decompressed memory inflation
            wb = openpyxl.load_workbook(file_path, data_only=True, read_only=True)
            sheet = wb.active
            if sheet is None:
                return [], []

            raw_rows_iter = sheet.iter_rows(values_only=True)
            try:
                first_row = next(raw_rows_iter)
            except StopIteration:
                return [], []

            if not first_row:
                return [], []

            if len(first_row) > MAX_COLUMNS:
                raise ValueError(
                    f"Workbook column count ({len(first_row)}) exceeds maximum allowed ({MAX_COLUMNS})."
                )

            columns = [str(c or f"col_{i}") for i, c in enumerate(first_row)]
            rows = []

            for row_idx, r in enumerate(raw_rows_iter, start=1):
                if row_idx > MAX_ROWS:
                    break
                row_dict: dict[str, Any] = {}
                for i, col in enumerate(columns):
                    val = r[i] if i < len(r) else None
                    row_dict[col] = val
                rows.append(row_dict)

            wb.close()
            return columns, rows
        except Exception as e:
            raise ValueError(f"Malformed or unreadable Excel workbook '{file_path.name}': {e}") from e

    raise ValueError(f"Unsupported file format '{suffix}'. Expected .xlsx, .xls, .csv, or .tsv")


def _save_table(file_path: Path, columns: list[str], rows: list[dict[str, Any]]) -> None:
    """Saves rows back to CSV or XLSX with formula injection sanitization."""
    suffix = file_path.suffix.lower()
    if suffix in [".csv", ".tsv", ".txt"]:
        sep = "\t" if suffix == ".tsv" else ","
        with file_path.open("w", encoding="utf-8", newline="") as f:
            writer = csv.DictWriter(f, fieldnames=columns, delimiter=sep)
            writer.writeheader()
            for r in rows:
                sanitized_row = {c: _sanitize_cell_for_export(r.get(c)) for c in columns}
                writer.writerow(sanitized_row)
    elif suffix in [".xlsx", ".xls"]:
        wb = openpyxl.Workbook()
        ws = wb.active
        if ws is not None:
            ws.append([_sanitize_cell_for_export(c) for c in columns])
            for r in rows:
                ws.append([_sanitize_cell_for_export(r.get(c)) for c in columns])
            wb.save(file_path)


class SafeFormulaEvaluator(ast.NodeVisitor):
    """Validates and evaluates arithmetic formulas strictly using an AST whitelist."""

    ALLOWED_OPERATORS = {
        ast.Add: operator.add,
        ast.Sub: operator.sub,
        ast.Mult: operator.mul,
        ast.Div: operator.truediv,
        ast.Pow: operator.pow,
    }

    def __init__(self, allowed_names: set[str]) -> None:
        self.allowed_names = allowed_names

    def validate_ast(self, node: ast.AST) -> None:
        """Walks AST and raises ValueError if any unapproved node type is encountered."""
        for sub_node in ast.walk(node):
            if isinstance(sub_node, ast.Expression | ast.Load):
                continue
            elif isinstance(sub_node, ast.BinOp):
                if type(sub_node.op) not in self.ALLOWED_OPERATORS:
                    raise ValueError(f"Unsupported operator: {type(sub_node.op).__name__}")
                # Exponentiation safety limit: power must be small constant integer
                if isinstance(sub_node.op, ast.Pow):
                    if not isinstance(sub_node.right, ast.Constant) or not isinstance(sub_node.right.value, int):
                        raise ValueError("Exponentiation requires a constant integer exponent.")
                    if sub_node.right.value < 0 or sub_node.right.value > MAX_POWER_EXPONENT:
                        raise ValueError(f"Exponent must be between 0 and {MAX_POWER_EXPONENT}.")
            elif isinstance(sub_node, ast.UnaryOp):
                if not isinstance(sub_node.op, ast.UAdd | ast.USub):
                    raise ValueError(f"Unsupported unary operator: {type(sub_node.op).__name__}")
            elif isinstance(sub_node, ast.Constant):
                if not isinstance(sub_node.value, int | float):
                    raise ValueError(f"Only numeric constants are allowed, found: {sub_node.value}")
            elif isinstance(sub_node, ast.Name):
                if sub_node.id not in self.allowed_names:
                    raise ValueError(f"Unknown or disallowed column name in formula: '{sub_node.id}'")
            elif isinstance(sub_node, ast.Add | ast.Sub | ast.Mult | ast.Div | ast.Pow | ast.UAdd | ast.USub):
                continue
            else:
                raise ValueError(f"Dangerous or unsupported expression element: {type(sub_node).__name__}")

    def eval_node(self, node: ast.AST, context: dict[str, Any]) -> float:
        """Evaluates AST node given a row context dictionary."""
        if isinstance(node, ast.Constant):
            return float(node.value)
        elif isinstance(node, ast.Name):
            val = context.get(node.id)
            if val is None:
                raise ValueError(f"Column '{node.id}' has empty value.")
            return float(val)
        elif isinstance(node, ast.UnaryOp):
            operand = self.eval_node(node.operand, context)
            return -operand if isinstance(node.op, ast.USub) else operand
        elif isinstance(node, ast.BinOp):
            left = self.eval_node(node.left, context)
            right = self.eval_node(node.right, context)
            op_fn = self.ALLOWED_OPERATORS[type(node.op)]
            if type(node.op) is ast.Div and right == 0:
                raise ZeroDivisionError("Division by zero in formula computation.")
            res = float(op_fn(left, right))
            if math.isnan(res) or math.isinf(res):
                raise ValueError("Calculation resulted in NaN or Infinity.")
            return res
        raise ValueError(f"Cannot evaluate node: {type(node).__name__}")


def execute_spreadsheet(
    file_path: str,
    operation: str = "read",
    params: dict[str, Any] | None = None,
    session_id: str = "default",
) -> SpreadsheetResult:
    """Analyze, filter, aggregate, or compute columns on a workspace tabular dataset."""
    op = operation.lower().strip()
    params = dict(params or {})

    # Map intuitive operation aliases to standard spreadsheet operations
    if op in ("max", "min", "mean", "avg", "average", "sum", "count", "std"):
        if "function" not in params:
            params["function"] = op if op not in ("avg", "average") else "mean"
        op = "aggregate"
    elif op in ("preview", "view", "inspect", "show"):
        op = "read"

    if op not in ALLOWED_OPERATIONS:
        return SpreadsheetResult(
            status=ToolStatus.ERROR,
            error=f"Unsupported spreadsheet operation '{operation}'. Allowed: {sorted(ALLOWED_OPERATIONS)}",
        )

    try:
        validated_path = validate_workspace_path(file_path, session_id, create_parents=False)
    except Exception as err:
        return SpreadsheetResult(status=ToolStatus.ERROR, error=f"Path validation failed: {err}")

    if not validated_path.exists() or not validated_path.is_file():
        return SpreadsheetResult(
            status=ToolStatus.ERROR,
            error=f"Spreadsheet file '{file_path}' not found in workspace for session '{session_id}'.",
        )

    try:
        columns, rows = _load_table(validated_path)
    except Exception as e:
        return SpreadsheetResult(
            status=ToolStatus.ERROR,
            error=f"Failed loading spreadsheet '{validated_path.name}': {e}",
        )

    total_rows = len(rows)

    if op == "read":
        limit = min(int(params.get("limit", 50)), 500)
        sub_rows = rows[:limit]
        summary = (
            f"Successfully read {len(sub_rows)} rows of {total_rows} total rows "
            f"across {len(columns)} columns: {columns}."
        )

        # Build clean markdown table representation for LLM context
        lines = [summary]
        if sub_rows:
            header_line = " | ".join(str(c) for c in columns)
            sep_line = " | ".join("---" for _ in columns)
            lines.extend([f"| {header_line} |", f"| {sep_line} |"])
            for r in sub_rows:
                row_str = " | ".join(str(r.get(c, "")) for c in columns)
                lines.append(f"| {row_str} |")

        # Compute quick summary stats for numeric columns
        stat_summaries = []
        for col in columns:
            col_floats = []
            for r in rows:
                v = r.get(col)
                if v is not None:
                    try:
                        col_floats.append(float(v))
                    except (ValueError, TypeError):
                        pass
            if len(col_floats) == total_rows and total_rows > 0:
                min_v = min(col_floats)
                max_v = max(col_floats)
                mean_v = sum(col_floats) / len(col_floats)
                stat_summaries.append(f"{col}: min={min_v}, max={max_v}, mean={round(mean_v, 4)}, count={len(col_floats)}")
        if stat_summaries:
            lines.append("\nSummary Statistics:\n" + "\n".join(f"- {s}" for s in stat_summaries))

        output_text = "\n".join(lines)
        return SpreadsheetResult(
            status=ToolStatus.SUCCESS,
            output=output_text,
            data=sub_rows,
            summary=summary,
            columns=columns,
            total_rows=total_rows,
        )

    elif op == "filter":
        filter_col = str(params.get("column") or "")
        val = params.get("value")
        raw_op = params.get("operator", "==")

        if not filter_col or filter_col not in columns:
            return SpreadsheetResult(
                status=ToolStatus.ERROR,
                error=f"Filter column '{filter_col}' not found. Available columns: {columns}",
            )

        if raw_op not in ALLOWED_FILTER_OPERATORS:
            return SpreadsheetResult(
                status=ToolStatus.ERROR,
                error=f"Unsupported filter operator '{raw_op}'. Allowed: {sorted(ALLOWED_FILTER_OPERATORS)}",
            )

        filtered: list[dict[str, Any]] = []
        for r in rows:
            cell = r.get(filter_col)
            if cell is None or val is None:
                continue
            matched = False
            try:
                if raw_op == "==":
                    matched = str(cell).lower() == str(val).lower() or cell == val
                elif raw_op == "!=":
                    matched = str(cell).lower() != str(val).lower() and cell != val
                elif raw_op in (">", "<", ">=", "<="):
                    c_num = float(str(cell))
                    v_num = float(str(val))
                    if raw_op == ">":
                        matched = c_num > v_num
                    elif raw_op == "<":
                        matched = c_num < v_num
                    elif raw_op == ">=":
                        matched = c_num >= v_num
                    elif raw_op == "<=":
                        matched = c_num <= v_num
                elif raw_op == "contains":
                    matched = str(val).lower() in str(cell).lower()
            except (ValueError, TypeError):
                matched = False
            if matched:
                filtered.append(r)

        limit = min(int(params.get("limit", 100)), 1000)
        sub = filtered[:limit]
        summary = (
            f"Filter on '{filter_col} {raw_op} {val}' matched {len(filtered)} rows. "
            f"Returning first {len(sub)} rows."
        )
        return SpreadsheetResult(
            status=ToolStatus.SUCCESS,
            output=summary,
            data=sub,
            summary=summary,
            columns=columns,
            total_rows=len(filtered),
        )

    elif op == "aggregate":
        group_by = params.get("group_by")
        agg_col = params.get("column")
        agg_func = str(params.get("function", "sum")).lower()

        if agg_func not in ALLOWED_AGG_FUNCTIONS:
            return SpreadsheetResult(
                status=ToolStatus.ERROR,
                error=f"Unsupported aggregation function '{agg_func}'. Allowed: {sorted(ALLOWED_AGG_FUNCTIONS)}",
            )

        if not agg_col or agg_col not in columns:
            return SpreadsheetResult(
                status=ToolStatus.ERROR,
                error=f"Aggregation column '{agg_col}' not found. Available columns: {columns}",
            )

        def _calc_stat(values: list[float], func: str) -> float:
            if not values:
                return 0.0
            if func == "count":
                return float(len(values))
            if func == "sum":
                return sum(values)
            if func == "mean":
                return sum(values) / len(values)
            if func == "min":
                return min(values)
            if func == "max":
                return max(values)
            return 0.0

        if group_by:
            if group_by not in columns:
                return SpreadsheetResult(
                    status=ToolStatus.ERROR,
                    error=f"Group by column '{group_by}' not found. Available columns: {columns}",
                )
            groups: dict[Any, list[float]] = {}
            for r in rows:
                g_val = r.get(group_by)
                c_val = r.get(agg_col)
                if c_val is not None:
                    try:
                        groups.setdefault(g_val, []).append(float(c_val))
                    except (ValueError, TypeError):
                        pass

            agg_rows = []
            for g_val, num_vals in groups.items():
                stat_val = _calc_stat(num_vals, agg_func)
                agg_rows.append({group_by: g_val, f"{agg_func}_{agg_col}": round(stat_val, 4)})

            summary = f"Aggregated '{agg_col}' ({agg_func}) grouped by '{group_by}' ({len(agg_rows)} groups)."
            return SpreadsheetResult(
                status=ToolStatus.SUCCESS,
                output=summary,
                data=agg_rows,
                summary=summary,
                columns=[group_by, f"{agg_func}_{agg_col}"],
                total_rows=len(agg_rows),
            )
        else:
            nums: list[float] = []
            for r in rows:
                val = r.get(agg_col)
                if val is not None:
                    try:
                        nums.append(float(val))
                    except (ValueError, TypeError):
                        pass
            total = _calc_stat(nums, agg_func)
            data = [{f"{agg_func}_{agg_col}": round(total, 4)}]
            summary = f"Overall aggregation '{agg_func}' for column '{agg_col}' = {total}."
            return SpreadsheetResult(
                status=ToolStatus.SUCCESS,
                output=summary,
                data=data,
                summary=summary,
                columns=[f"{agg_func}_{agg_col}"],
                total_rows=total_rows,
            )

    elif op == "compute":
        new_col = params.get("target_column")
        formula = str(params.get("formula", "")).strip()

        if not new_col or not formula:
            return SpreadsheetResult(
                status=ToolStatus.ERROR,
                error="Parameters 'target_column' and 'formula' are required for operation 'compute'",
            )

        # Parse formula into AST
        try:
            expr_ast = ast.parse(formula, mode="eval")
        except SyntaxError as e:
            return SpreadsheetResult(
                status=ToolStatus.ERROR,
                error=f"Syntax error in formula '{formula}': {e}",
            )

        evaluator = SafeFormulaEvaluator(allowed_names=set(columns))
        try:
            evaluator.validate_ast(expr_ast)
        except ValueError as val_err:
            return SpreadsheetResult(
                status=ToolStatus.ERROR,
                error=f"Formula security check failed: {val_err}",
            )

        # Compute row by row using AST evaluator
        calc_errors = 0
        for r in rows:
            try:
                calc_val = evaluator.eval_node(expr_ast.body, r)
                r[new_col] = round(calc_val, 4)
            except ZeroDivisionError:
                r[new_col] = None
                calc_errors += 1
            except Exception:
                r[new_col] = None
                calc_errors += 1

        if new_col not in columns:
            columns.append(new_col)

        # Save back to disk safely
        try:
            _save_table(validated_path, columns, rows)
        except Exception as e:
            return SpreadsheetResult(status=ToolStatus.ERROR, error=f"Failed saving updated file: {e}")

        summary = (
            f"Successfully computed column '{new_col}' = '{formula}' on {total_rows} rows "
            f"({calc_errors} nulls/division-by-zero)."
        )
        return SpreadsheetResult(
            status=ToolStatus.SUCCESS,
            data=rows[:50],
            summary=summary,
            columns=columns,
            total_rows=total_rows,
        )

    return SpreadsheetResult(status=ToolStatus.ERROR, error="Unexpected operation error")
