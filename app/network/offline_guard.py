"""
app/network/offline_guard.py — Strict Offline Mode Enforcement
==============================================================
When STRICT_OFFLINE=true, this module:
  1. Installs a urllib opener that blocks all external HTTP/HTTPS calls at the
     Python application level.
  2. Emits an audit event (and raises) on any blocked attempt.
  3. Provides an allowlist for localhost/loopback connections (Postgres, Ollama).

Limitations (documented):
  - This is an application-level guard. It does not prevent OS-level TCP connections
    made by subprocesses or native extensions.
  - For true network isolation, combine with Docker network=none or OS-level firewall
    rules (iptables/netfilter on Linux, Windows Firewall on Windows).
  - Test with test_offline_guard.py to verify behavior.
"""

import logging
import socket
import urllib.request
from ipaddress import ip_address, ip_network
from typing import Any

logger = logging.getLogger("sovereign.network")

# Networks that are always allowed (loopback, link-local)
_ALLOWED_NETWORKS = [
    ip_network("127.0.0.0/8"),
    ip_network("::1/128"),
    ip_network("169.254.0.0/16"),
]


def _is_allowed_host(host: str) -> bool:
    """Return True if the host resolves to a loopback or allowed address."""
    if host in ("localhost", "127.0.0.1", "::1"):
        return True
    try:
        addr = ip_address(host)
        return any(addr in net for net in _ALLOWED_NETWORKS)
    except ValueError:
        # hostname — attempt resolution
        try:
            infos = socket.getaddrinfo(host, None)
            for info in infos:
                addr = ip_address(info[4][0])
                if any(addr in net for net in _ALLOWED_NETWORKS):
                    return True
        except socket.gaierror:
            pass
    return False


class _BlockingHandler(urllib.request.BaseHandler):
    """urllib handler that blocks external connections in strict-offline mode."""

    def http_open(self, req: Any) -> Any:
        self._check(req)
        return urllib.request.HTTPHandler().http_open(req)

    def https_open(self, req: Any) -> Any:
        self._check(req)
        return urllib.request.HTTPSHandler().https_open(req)

    def _check(self, req: Any) -> None:
        host = req.host.split(":")[0]
        if not _is_allowed_host(host):
            logger.error("STRICT_OFFLINE violation: blocked outbound request to %s", req.full_url)
            raise OfflineViolationError(
                f"Strict offline mode is active. External connection to '{req.full_url}' is blocked."
            )


class OfflineViolationError(RuntimeError):
    """Raised when strict-offline mode blocks an outbound network request."""

    pass


_guard_installed = False


def install_offline_guard() -> None:
    """
    Install the application-level offline guard.
    Call once at startup when STRICT_OFFLINE=true.
    """
    global _guard_installed
    if _guard_installed:
        return
    opener = urllib.request.build_opener(_BlockingHandler())
    urllib.request.install_opener(opener)
    _guard_installed = True
    logger.warning(
        "Strict offline guard installed. All outbound HTTP/HTTPS requests to "
        "non-loopback addresses will be blocked at the application level. "
        "Note: OS-level firewall rules are required for full network isolation."
    )
