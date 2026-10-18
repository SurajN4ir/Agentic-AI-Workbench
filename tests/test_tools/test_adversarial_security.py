"""
tests/test_tools/test_adversarial_security.py
=============================================
Adversarial security test suite verifying strict containment of file operations,
spreadsheet calculation bounds, formula injection mitigations, and RBAC policy equivalence.
"""

import csv
import os
from pathlib import Path

import pytest
from app.identity.models import User
from app.tools.file_io import execute_file_io
from app.tools.interface import ToolStatus, validate_workspace_path
from app.tools.registry import get_tool_registry
from app.tools.spreadsheet import execute_spreadsheet
from cli import stage_file_into_session


@pytest.fixture
def session_pair(tmp_path: Path) -> tuple[str, str]:
    session_a = "session_alpha_123"
    session_b = "session_beta_456"
    return session_a, session_b


class TestAdversarialFileContainment:
    def test_directory_traversal_blocked(self, session_pair: tuple[str, str]) -> None:
        session_a, _ = session_pair
        traversal_attempts = [
            "../secret.txt",
            "..\\secret.txt",
            "sub/../../secret.txt",
            "/etc/passwd",
            "C:\\Windows\\System32\\calc.exe",
        ]
        for bad_path in traversal_attempts:
            res = execute_file_io(operation="read", path=bad_path, session_id=session_a)
            assert res.status == ToolStatus.ERROR, f"Traversal should have failed: {bad_path}"
            assert "outside" in str(res.error).lower() or "traversal" in str(res.error).lower() or "denied" in str(res.error).lower()

    def test_cross_session_isolation(self, session_pair: tuple[str, str]) -> None:
        session_a, session_b = session_pair
        # Session A creates a private file
        execute_file_io(operation="write", path="confidential.txt", content="Alpha secret data", session_id=session_a)

        # Session B attempts to read Session A's file via relative escape
        res_cross = execute_file_io(
            operation="read",
            path=f"../{session_a}/confidential.txt",
            session_id=session_b,
        )
        assert res_cross.status == ToolStatus.ERROR
        assert "traversal" in str(res_cross.error).lower() or "denied" in str(res_cross.error).lower()

    def test_symlink_escape_rejection(self, session_pair: tuple[str, str], tmp_path: Path) -> None:
        session_a, _ = session_pair
        # Target outside workspace
        outside_target = tmp_path / "host_sensitive_file.txt"
        outside_target.write_text("SENSITIVE_HOST_INFO", encoding="utf-8")

        # Create symlink inside session workspace pointing outside
        session_root = validate_workspace_path("dummy.txt", session_a).parent
        symlink_path = session_root / "symlink_escape.txt"

        try:
            os.symlink(outside_target, symlink_path)
        except (OSError, NotImplementedError):
            # On Windows without Developer Mode, creating symlinks may raise OSError: skip if unsupported
            pytest.skip("Symlink creation not permitted in this OS environment")

        res = execute_file_io(operation="read", path="symlink_escape.txt", session_id=session_a)
        assert res.status == ToolStatus.ERROR
        assert "symlink" in str(res.error).lower() or "outside" in str(res.error).lower()

    def test_protect_original_uploads_from_overwrite_or_deletion(self, session_pair: tuple[str, str]) -> None:
        session_a, _ = session_pair
        # Attempt to overwrite an uploaded file
        res_write = execute_file_io(
            operation="write",
            path="uploads/original_blueprint.pdf",
            content="malicious overwrite",
            session_id=session_a,
        )
        assert res_write.status == ToolStatus.ERROR
        assert "prohibited" in str(res_write.error).lower()

        # Attempt to delete an uploaded file
        res_del = execute_file_io(
            operation="delete",
            path="uploads/original_blueprint.pdf",
            session_id=session_a,
        )
        assert res_del.status == ToolStatus.ERROR
        assert "prohibited" in str(res_del.error).lower()

    def test_atomic_write_and_cleanup(self, session_pair: tuple[str, str]) -> None:
        session_a, _ = session_pair
        # Write temporary scratch file
        res_write = execute_file_io(
            operation="write",
            path="scratch/temp_calc.tmp",
            content="temporary computation step",
            session_id=session_a,
        )
        assert res_write.status == ToolStatus.SUCCESS

        # Cleanup expired files
        res_cleanup = execute_file_io(
            operation="cleanup",
            path="scratch",
            session_id=session_a,
            older_than_seconds=0,
        )
        assert res_cleanup.status == ToolStatus.SUCCESS
        assert res_cleanup.data is not None
        assert res_cleanup.data["deleted_count"] >= 1


class TestAdversarialSpreadsheetSafety:
    @pytest.fixture
    def sample_table(self, session_pair: tuple[str, str]) -> tuple[str, str]:
        session_a, _ = session_pair
        p = validate_workspace_path("test_table.csv", session_a, create_parents=True)
        rows = [
            {"val_a": 10.0, "val_b": 2.0, "text_col": "normal text"},
            {"val_a": 20.0, "val_b": 0.0, "text_col": "=cmd|' /C calc'!A0"},  # Formula injection payload
            {"val_a": 30.0, "val_b": 5.0, "text_col": "+1234567890"},
        ]
        with p.open("w", encoding="utf-8", newline="") as f:
            writer = csv.DictWriter(f, fieldnames=["val_a", "val_b", "text_col"])
            writer.writeheader()
            writer.writerows(rows)
        return "test_table.csv", session_a

    def test_reject_dangerous_formula_expressions(self, sample_table: tuple[str, str]) -> None:
        file_path, session_id = sample_table
        dangerous_expressions = [
            "__import__('os').system('whoami')",
            "open('/etc/passwd').read()",
            "val_a.__class__.__bases__",
            "lambda x: x + 1",
            "eval('1+1')",
            "exec('import sys')",
            "val_a ** 999999",  # Huge exponentiation
            "val_a ** -1",      # Negative power
        ]
        for bad_expr in dangerous_expressions:
            res = execute_spreadsheet(
                file_path=file_path,
                operation="compute",
                params={"target_column": "res", "formula": bad_expr},
                session_id=session_id,
            )
            assert res.status == ToolStatus.ERROR, f"Expression should have failed: {bad_expr}"
            assert "security check failed" in str(res.error).lower() or "syntax" in str(res.error).lower()

    def test_safe_division_by_zero_handling(self, sample_table: tuple[str, str]) -> None:
        file_path, session_id = sample_table
        res = execute_spreadsheet(
            file_path=file_path,
            operation="compute",
            params={"target_column": "ratio", "formula": "val_a / val_b"},
            session_id=session_id,
        )
        assert res.status == ToolStatus.SUCCESS
        assert res.data is not None
        # Row 1: 10 / 2 = 5.0
        assert res.data[0]["ratio"] == 5.0
        # Row 2: 20 / 0 = None (handled cleanly without crash)
        assert res.data[1]["ratio"] is None
        # Row 3: 30 / 5 = 6.0
        assert res.data[2]["ratio"] == 6.0

    def test_formula_injection_sanitization_on_save(self, sample_table: tuple[str, str]) -> None:
        file_path, session_id = sample_table
        # Perform compute which triggers _save_table
        execute_spreadsheet(
            file_path=file_path,
            operation="compute",
            params={"target_column": "sum_ab", "formula": "val_a + val_b"},
            session_id=session_id,
        )

        # Inspect raw file content to confirm formula tokens were escaped with single quote
        raw_path = validate_workspace_path(file_path, session_id)
        raw_content = raw_path.read_text(encoding="utf-8")
        assert "'=cmd|" in raw_content, "Formula injection payload should be neutralized with leading single quote"

    def test_malformed_file_rejection(self, session_pair: tuple[str, str]) -> None:
        session_a, _ = session_pair
        corrupted_path = validate_workspace_path("corrupt.xlsx", session_a, create_parents=True)
        corrupted_path.write_bytes(b"NOT_A_VALID_ZIP_OR_XLSX_DATA_00000000")

        res = execute_spreadsheet(file_path="corrupt.xlsx", operation="read", session_id=session_a)
        assert res.status == ToolStatus.ERROR
        assert "malformed" in str(res.error).lower() or "failed" in str(res.error).lower()


class TestCLIPolicyEquivalence:
    @pytest.mark.asyncio
    async def test_rbac_restriction_enforced_in_tool_registry(self) -> None:
        registry = get_tool_registry()
        viewer_user = User(username="viewer_test", email="viewer@test.local", role="viewer", is_active=True)
        admin_user = User(username="admin_test", email="admin@test.local", role="admin", is_active=True)

        # Viewer attempting to execute restricted code_sandbox
        res_blocked = await registry.execute_tool(
            name="code_sandbox",
            input_data={"code": "print('hello')"},
            user=viewer_user,
            session_id="test_rbac_session",
        )
        assert res_blocked.status == ToolStatus.ERROR
        assert "permission denied" in str(res_blocked.error).lower()

        # Admin attempting to execute code_sandbox
        tool = registry.get_tool("code_sandbox")
        assert tool is not None
        assert admin_user.role in tool.required_roles

    def test_cli_file_staging_quarantines_to_workspace(self, tmp_path: Path) -> None:
        # Create an external file outside workspace
        external_file = tmp_path / "raw_external.txt"
        external_file.write_text("EXTERNAL_DATA", encoding="utf-8")

        session_id = "test_cli_staging"
        staged_path = stage_file_into_session(str(external_file), session_id)

        assert staged_path.exists()
        assert "uploads" in staged_path.parts
        assert session_id in staged_path.parts
        assert staged_path.read_text(encoding="utf-8") == "EXTERNAL_DATA"
