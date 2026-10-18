"""
app/tools/spreadsheet.py — Lightweight, Pure Python Tabular Data Analysis Tool
=============================================================================
Adapted from sovereign-agent reference architecture (SIH PS 26117).
Provides fast, deterministic read, filter, aggregate, and formula computations
on CSV and Excel (.xlsx) datasets using built-in csv and openpyxl.
Zero pandas dependency required; ultra-fast load time and memory efficiency.
"""

from __future__ import annotations

import csv
import operator
import re
from collections.abc import Callable
from pathlib import Path
from typing import Any, Literal

import openpyxl
from pydantic import Field

from app.tools.interface import ToolInput, ToolResult, ToolStatus, validate_workspace_path


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


ALLOWED_OPERATIONS = {"read", "filter", "aggregate", "compute"}
ALLOWED_FILTER_OPERATORS = {"==", "!=", ">", "<", ">=", "<=", "contains"}
ALLOWED_AGG_FUNCTIONS = {"sum", "mean", "count", "min", "max"}


def _load_table(file_path: Path) -> tuple[list[str], list[dict[str, Any]]]:
    """Loads CSV or XLSX into a list of column names and row dictionaries."""
    suffix = file_path.suffix.lower()
    if suffix in [".csv", ".tsv", ".txt"]:
        sep = "\t" if suffix == ".tsv" else ","
        with file_path.open("r", encoding="utf-8", errors="replace", newline="") as f:
            reader = csv.DictReader(f, delimiter=sep)
            columns = reader.fieldnames or []
            rows: list[dict[str, Any]] = []
            for r in reader:
                # Type convert numeric values
                converted: dict[str, Any] = {}
                for k, v in r.items():
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
            return list(columns), rows

    elif suffix in [".xlsx", ".xls"]:
        wb = openpyxl.load_workbook(file_path, data_only=True)
        sheet = wb.active
        if sheet is None:
            return [], []
        raw_rows = list(sheet.iter_rows(values_only=True))
        if not raw_rows:
            return [], []
        columns = [str(c or f"col_{i}") for i, c in enumerate(raw_rows[0])]
        rows = []
        for r in raw_rows[1:]:
            row_dict: dict[str, Any] = {}
            for i, col in enumerate(columns):
                val = r[i] if i < len(r) else None
                row_dict[col] = val
            rows.append(row_dict)
        return columns, rows

    raise ValueError(f"Unsupported file format '{suffix}'. Expected .xlsx, .xls, .csv, or .tsv")


def _save_table(file_path: Path, columns: list[str], rows: list[dict[str, Any]]) -> None:
    """Saves rows back to CSV or XLSX."""
    suffix = file_path.suffix.lower()
    if suffix in [".csv", ".tsv", ".txt"]:
        sep = "\t" if suffix == ".tsv" else ","
        with file_path.open("w", encoding="utf-8", newline="") as f:
            writer = csv.DictWriter(f, fieldnames=columns, delimiter=sep)
            writer.writeheader()
            writer.writerows(rows)
    elif suffix in [".xlsx", ".xls"]:
        wb = openpyxl.Workbook()
        ws = wb.active
        if ws is not None:
            ws.append(columns)
            for r in rows:
                ws.append([r.get(c) for c in columns])
            wb.save(file_path)


def execute_spreadsheet(
    file_path: str,
    operation: str = "read",
    params: dict[str, Any] | None = None,
    session_id: str = "default",
) -> SpreadsheetResult:
    """Analyze, filter, aggregate, or compute columns on a workspace tabular dataset."""
    op = operation.lower().strip()
    if op not in ALLOWED_OPERATIONS:
        return SpreadsheetResult(
            status=ToolStatus.ERROR,
            error=f"Unsupported spreadsheet operation '{operation}'. Allowed: {sorted(ALLOWED_OPERATIONS)}",
        )

    params = params or {}

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
        limit = int(params.get("limit", 50))
        sub_rows = rows[:limit]
        summary = (
            f"Successfully read {len(sub_rows)} rows of {total_rows} total rows "
            f"across {len(columns)} columns: {columns}."
        )
        return SpreadsheetResult(
            status=ToolStatus.SUCCESS,
            data=sub_rows,
            summary=summary,
            columns=columns,
            total_rows=total_rows,
        )

    elif op == "filter":
        col = params.get("column")
        val = params.get("value")
        raw_op = params.get("operator", "==")

        if not col or col not in columns:
            return SpreadsheetResult(
                status=ToolStatus.ERROR,
                error=f"Filter column '{col}' not found. Available columns: {columns}",
            )

        if raw_op not in ALLOWED_FILTER_OPERATORS:
            return SpreadsheetResult(
                status=ToolStatus.ERROR,
                error=f"Unsupported filter operator '{raw_op}'. Allowed: {sorted(ALLOWED_FILTER_OPERATORS)}",
            )

        # Build comparison predicate
        filtered: list[dict[str, Any]] = []
        for r in rows:
            cell = r.get(col)
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

        limit = int(params.get("limit", 100))
        sub = filtered[:limit]
        summary = (
            f"Filter on '{col} {raw_op} {val}' matched {len(filtered)} rows. "
            f"Returning first {len(sub)} rows."
        )
        return SpreadsheetResult(
            status=ToolStatus.SUCCESS,
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

        # Validate formula expression: strictly allows simple binary math e.g. "colA + colB" or "colA * 1.05"
        pattern = r"^([a-zA-Z_]\w*)\s*([\+\-\*\/])\s*([a-zA-Z_]\w*|\d+(?:\.\d+)?)$"
        match = re.match(pattern, formula)
        if not match:
            return SpreadsheetResult(
                status=ToolStatus.ERROR,
                error=f"Formula '{formula}' contains invalid characters or unsupported syntax. Expected: 'colA + colB' or 'colA * 1.5'.",
            )

        left_token, op_token, right_token = match.groups()
        if left_token not in columns:
            return SpreadsheetResult(status=ToolStatus.ERROR, error=f"Column '{left_token}' not found.")

        is_right_numeric = False
        try:
            right_num = float(right_token)
            is_right_numeric = True
        except ValueError:
            if right_token not in columns:
                return SpreadsheetResult(status=ToolStatus.ERROR, error=f"Column '{right_token}' not found.")

        ops: dict[str, Callable[[float, float], float]] = {
            "+": operator.add,
            "-": operator.sub,
            "*": operator.mul,
            "/": operator.truediv,
        }
        math_fn = ops[op_token]

        for r in rows:
            l_val = r.get(left_token)
            r_val = right_num if is_right_numeric else r.get(right_token)
            if l_val is not None and r_val is not None:
                try:
                    res_val = math_fn(float(l_val), float(r_val))
                    r[new_col] = round(res_val, 4)
                except (ValueError, TypeError, ZeroDivisionError):
                    r[new_col] = None
            else:
                r[new_col] = None

        if new_col not in columns:
            columns.append(new_col)

        # Save back to disk
        try:
            _save_table(validated_path, columns, rows)
        except Exception as e:
            return SpreadsheetResult(status=ToolStatus.ERROR, error=f"Failed saving updated file: {e}")

        summary = f"Successfully computed column '{new_col}' = '{formula}' and updated '{validated_path.name}'."
        return SpreadsheetResult(
            status=ToolStatus.SUCCESS,
            data=rows[:50],
            summary=summary,
            columns=columns,
            total_rows=total_rows,
        )

    return SpreadsheetResult(status=ToolStatus.ERROR, error="Unexpected operation error")
