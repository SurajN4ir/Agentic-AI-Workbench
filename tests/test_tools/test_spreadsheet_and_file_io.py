"""
tests/test_tools/test_spreadsheet_and_file_io.py
================================================
Unit tests for pure-Python spreadsheet analysis and scoped file_io tools.
"""

import csv

import pytest
from app.tools.file_io import execute_file_io
from app.tools.interface import ToolStatus, validate_workspace_path
from app.tools.registry import get_tool_registry
from app.tools.spreadsheet import execute_spreadsheet


@pytest.fixture
def test_csv_file(tmp_path: pytest.TempPathFactory) -> tuple[str, str]:
    session_id = "test_sheet_session"
    # Ensure workspace directory exists
    p = validate_workspace_path("sensor_data.csv", session_id, create_parents=True)
    rows = [
        {"sensor_id": "s1", "temperature": 22.5, "pressure": 101.3},
        {"sensor_id": "s2", "temperature": 24.0, "pressure": 102.1},
        {"sensor_id": "s1", "temperature": 23.0, "pressure": 101.5},
        {"sensor_id": "s2", "temperature": 25.5, "pressure": 102.4},
        {"sensor_id": "s3", "temperature": 21.0, "pressure": 100.8},
    ]
    with p.open("w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=["sensor_id", "temperature", "pressure"])
        writer.writeheader()
        writer.writerows(rows)
    return "sensor_data.csv", session_id


class TestSpreadsheetTool:
    def test_read_csv(self, test_csv_file: tuple[str, str]) -> None:
        file_path, session_id = test_csv_file
        res = execute_spreadsheet(file_path=file_path, operation="read", params={"limit": 3}, session_id=session_id)
        assert res.status == ToolStatus.SUCCESS
        assert res.data is not None
        assert len(res.data) == 3
        assert res.total_rows == 5
        assert "temperature" in res.columns

    def test_filter_csv(self, test_csv_file: tuple[str, str]) -> None:
        file_path, session_id = test_csv_file
        res = execute_spreadsheet(
            file_path=file_path,
            operation="filter",
            params={"column": "sensor_id", "value": "s1", "operator": "=="},
            session_id=session_id,
        )
        assert res.status == ToolStatus.SUCCESS
        assert res.data is not None
        assert len(res.data) == 2
        assert all(row["sensor_id"] == "s1" for row in res.data)

    def test_aggregate_csv(self, test_csv_file: tuple[str, str]) -> None:
        file_path, session_id = test_csv_file
        res = execute_spreadsheet(
            file_path=file_path,
            operation="aggregate",
            params={"column": "temperature", "function": "mean"},
            session_id=session_id,
        )
        assert res.status == ToolStatus.SUCCESS
        assert res.data is not None
        assert "mean_temperature" in res.data[0]
        assert res.data[0]["mean_temperature"] == pytest.approx(23.2, 0.1)

    def test_compute_column(self, test_csv_file: tuple[str, str]) -> None:
        file_path, session_id = test_csv_file
        res = execute_spreadsheet(
            file_path=file_path,
            operation="compute",
            params={"target_column": "temp_offset", "formula": "temperature + 10.0"},
            session_id=session_id,
        )
        assert res.status == ToolStatus.SUCCESS
        assert res.data is not None
        assert "temp_offset" in res.data[0]
        assert res.data[0]["temp_offset"] == pytest.approx(32.5, 0.1)

    def test_reject_untrusted_compute_formula(self, test_csv_file: tuple[str, str]) -> None:
        file_path, session_id = test_csv_file
        res = execute_spreadsheet(
            file_path=file_path,
            operation="compute",
            params={"target_column": "hack", "formula": "__import__('os').system('ls')"},
            session_id=session_id,
        )
        assert res.status == ToolStatus.ERROR
        assert (
            "security check failed" in str(res.error).lower()
            or "dangerous" in str(res.error).lower()
            or "syntax" in str(res.error).lower()
        )


class TestFileIOTool:
    def test_write_and_read_file(self) -> None:
        session_id = "test_io_session"
        res_write = execute_file_io(
            operation="write",
            path="config/test_config.yaml",
            content="key: value\nmode: strict",
            session_id=session_id,
        )
        assert res_write.status == ToolStatus.SUCCESS
        assert "Successfully wrote" in str(res_write.summary)

        res_read = execute_file_io(
            operation="read",
            path="config/test_config.yaml",
            session_id=session_id,
        )
        assert res_read.status == ToolStatus.SUCCESS
        assert "key: value" in str(res_read.content)

    def test_list_files(self) -> None:
        session_id = "test_io_session_list"
        execute_file_io(operation="write", path="a.txt", content="hello", session_id=session_id)
        execute_file_io(operation="write", path="sub/b.txt", content="world", session_id=session_id)

        res_list = execute_file_io(operation="list", session_id=session_id)
        assert res_list.status == ToolStatus.SUCCESS
        assert any("a.txt" in f for f in res_list.files)
        assert any("b.txt" in f for f in res_list.files)

    def test_reject_path_traversal(self) -> None:
        session_id = "test_io_session"
        res = execute_file_io(
            operation="read",
            path="../../etc/passwd",
            session_id=session_id,
        )
        assert res.status == ToolStatus.ERROR
        assert "traversal" in str(res.error).lower() or "validation failed" in str(res.error).lower()


class TestRegistryIntegration:
    def test_tools_registered(self) -> None:
        registry = get_tool_registry()
        assert registry.get_tool("spreadsheet") is not None
        assert registry.get_tool("file_io") is not None
