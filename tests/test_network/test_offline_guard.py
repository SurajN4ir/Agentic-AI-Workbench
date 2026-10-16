"""
tests/test_network/test_offline_guard.py
=========================================
Tests for the strict offline mode guard.

Verifies:
  - External HTTP calls are blocked when the guard is installed
  - Localhost calls are allowed through
  - OfflineViolationError is raised (not silently dropped)
  - The guard itself does not make any external calls during testing
"""

import pytest
from app.network.offline_guard import (
    OfflineViolationError,
    _BlockingHandler,
    _is_allowed_host,
)


class TestAllowedHosts:
    def test_localhost_allowed(self) -> None:
        assert _is_allowed_host("localhost")

    def test_127_0_0_1_allowed(self) -> None:
        assert _is_allowed_host("127.0.0.1")

    def test_loopback_range_allowed(self) -> None:
        assert _is_allowed_host("127.0.0.2")

    def test_external_ip_blocked(self) -> None:
        assert not _is_allowed_host("8.8.8.8")

    def test_external_hostname_blocked(self) -> None:
        # We test the logic without making real DNS calls
        # by checking a non-resolvable domain returns False
        assert not _is_allowed_host("api.openai.invalid")


class TestBlockingHandler:
    def test_blocks_external_http_request(self) -> None:
        """Outbound request to external host raises OfflineViolationError."""

        class FakeRequest:
            host = "api.example.com:443"
            full_url = "https://api.example.com/v1/chat"

        handler = _BlockingHandler()
        with pytest.raises(OfflineViolationError, match="External connection"):
            handler._check(FakeRequest())

    def test_allows_localhost_request(self) -> None:
        """Request to localhost must not raise."""

        class FakeRequest:
            host = "127.0.0.1:11434"
            full_url = "http://127.0.0.1:11434/api/generate"

        handler = _BlockingHandler()
        # Should not raise
        handler._check(FakeRequest())

    def test_allows_postgres_localhost(self) -> None:
        class FakeRequest:
            host = "localhost:5432"
            full_url = "http://localhost:5432/"

        handler = _BlockingHandler()
        handler._check(FakeRequest())
