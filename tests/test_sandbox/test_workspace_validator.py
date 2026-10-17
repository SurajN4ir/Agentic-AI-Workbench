"""
tests/test_sandbox/test_workspace_validator.py
==============================================
Tests for workspace filesystem containment and path traversal protection.
"""

from pathlib import Path

import pytest
from app.tools.interface import validate_workspace_path


class TestWorkspaceValidator:
    def test_valid_relative_path(self, tmp_path: Path) -> None:
        """Valid relative path resolves strictly inside session directory."""
        target = validate_workspace_path(
            "output.csv",
            session_id="session_123",
            base_override=tmp_path,
        )
        assert target.name == "output.csv"
        assert target.is_relative_to(tmp_path / "session_123")
        assert target.parent.exists()

    def test_valid_nested_subdirectory(self, tmp_path: Path) -> None:
        """Subdirectories inside session workspace are created cleanly."""
        target = validate_workspace_path(
            "reports/2026/summary.json",
            session_id="session_abc",
            base_override=tmp_path,
        )
        assert target.name == "summary.json"
        assert target.is_relative_to(tmp_path / "session_abc")
        assert target.parent.exists()

    def test_directory_traversal_double_dot_rejected(self, tmp_path: Path) -> None:
        """Path traversal with '..' is blocked immediately."""
        with pytest.raises(PermissionError, match="Path traversal"):
            validate_workspace_path(
                "../../secret.env",
                session_id="session_123",
                base_override=tmp_path,
            )

    def test_middle_traversal_rejected(self, tmp_path: Path) -> None:
        """Middle path traversal attempting escape is blocked."""
        with pytest.raises(PermissionError, match="Path traversal"):
            validate_workspace_path(
                "subdir/../../outside.txt",
                session_id="session_123",
                base_override=tmp_path,
            )

    def test_windows_backslash_traversal_rejected(self, tmp_path: Path) -> None:
        """Windows backslash path traversal is blocked."""
        with pytest.raises(PermissionError, match="Path traversal"):
            validate_workspace_path(
                "..\\..\\system32\\cmd.exe",
                session_id="session_123",
                base_override=tmp_path,
            )

    def test_absolute_path_outside_workspace_rejected(self, tmp_path: Path) -> None:
        """Absolute path pointing outside session directory is blocked."""
        outside_path = (tmp_path / "other_dir" / "file.txt").resolve()
        with pytest.raises(PermissionError, match="Security Violation"):
            validate_workspace_path(
                str(outside_path),
                session_id="session_123",
                base_override=tmp_path,
            )

    def test_empty_or_whitespace_session_id_rejected(self, tmp_path: Path) -> None:
        """Empty session_id raises ValueError."""
        with pytest.raises(ValueError, match="session_id is required"):
            validate_workspace_path("test.txt", session_id="", base_override=tmp_path)

        with pytest.raises(ValueError, match="session_id is required"):
            validate_workspace_path("test.txt", session_id="   ", base_override=tmp_path)

    def test_malicious_session_id_characters_rejected(self, tmp_path: Path) -> None:
        """Session ID with invalid characters is rejected."""
        with pytest.raises(ValueError, match="Invalid session_id"):
            validate_workspace_path("test.txt", session_id="session/../escape", base_override=tmp_path)

        with pytest.raises(ValueError, match="Invalid session_id"):
            validate_workspace_path("test.txt", session_id="session$evil", base_override=tmp_path)

    def test_null_byte_in_path_rejected(self, tmp_path: Path) -> None:
        """Null bytes in path string raise ValueError."""
        with pytest.raises(ValueError, match="Null bytes are not allowed"):
            validate_workspace_path("test\0file.txt", session_id="session_123", base_override=tmp_path)
