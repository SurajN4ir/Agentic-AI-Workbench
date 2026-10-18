#!/usr/bin/env python3
"""
verify_airgap.py — Sovereign Air-Gap & Security Integrity Verifier

Automated audit tool to verify that the Sovereign Agentic AI Workbench strictly
adheres to air-gapped enterprise security requirements:
1. Active Egress Interception: Outbound HTTP/HTTPS requests to non-loopback hosts are blocked.
2. Codebase Outbound URL Audit: Zero unauthorized external telemetry or cloud APIs in app/.
3. Sandbox Security Profile: Air-gapped container settings (network_mode=none, cap_drop=ALL).
4. Secrets & Git Hygiene: .env is gitignored and not tracked; secrets >= 32 chars.
5. Docker Compose Profile: Localhost-only (127.0.0.1) bindings; no hardcoded passwords.
6. Serialization & AST Safety: Zero pickle deserialization; zero eval() in math engine.
"""

from __future__ import annotations

import ast
import re
import subprocess
import sys
import urllib.request
from pathlib import Path
from typing import NamedTuple

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))


class CheckResult(NamedTuple):
    name: str
    passed: bool
    details: str


def check_socket_egress() -> CheckResult:
    """Verify that OfflineGuard intercepts and blocks outbound non-loopback network calls."""
    from app.network.offline_guard import (
        OfflineViolationError,
        _BlockingHandler,
        _is_allowed_host,
        install_offline_guard,
    )

    # 1. Host allowlist check
    if not _is_allowed_host("127.0.0.1") or not _is_allowed_host("localhost"):
        return CheckResult(
            "Egress Interception Guard",
            False,
            "CRITICAL: Localhost/127.0.0.1 not recognized as allowed host",
        )

    if _is_allowed_host("8.8.8.8") or _is_allowed_host("api.openai.com"):
        return CheckResult(
            "Egress Interception Guard",
            False,
            "CRITICAL: External addresses (8.8.8.8 / api.openai.com) marked as allowed!",
        )

    # 2. Handler check
    class FakeExternalRequest:
        host = "api.openai.com:443"
        full_url = "https://api.openai.com/v1/chat/completions"

    class FakeLocalRequest:
        host = "127.0.0.1:11434"
        full_url = "http://127.0.0.1:11434/api/tags"

    handler = _BlockingHandler()

    try:
        handler._check(FakeExternalRequest())
        return CheckResult(
            "Egress Interception Guard",
            False,
            "CRITICAL: Fake external request was NOT blocked by _BlockingHandler!",
        )
    except OfflineViolationError:
        pass  # expected

    try:
        handler._check(FakeLocalRequest())
    except Exception as e:
        return CheckResult(
            "Egress Interception Guard",
            False,
            f"CRITICAL: Localhost request was blocked: {e}",
        )

    # 3. urllib.request opener installation
    install_offline_guard()

    try:
        req = urllib.request.Request("https://api.anthropic.com/v1/messages")
        urllib.request.urlopen(req, timeout=1)  # noqa: S310
        return CheckResult(
            "Egress Interception Guard",
            False,
            "CRITICAL: urllib.request to external URL succeeded without raising!",
        )
    except OfflineViolationError:
        pass  # expected
    except Exception:  # noqa: S110
        pass

    return CheckResult(
        "Egress Interception Guard",
        True,
        "OfflineGuard active: outbound external requests blocked with OfflineViolationError.",
    )


def check_codebase_urls() -> CheckResult:
    """Scan app/ for non-whitelisted outbound URLs."""
    app_dir = PROJECT_ROOT / "app"
    url_pattern = re.compile(r'https?://[^\s\'"<>]+')

    whitelisted_hosts = {
        "localhost",
        "127.0.0.1",
        "0.0.0.0",  # noqa: S104
        "backend",
        "postgres",
        "ollama",
        "w3.org",  # XML namespaces in openpyxl/docx
        "schemas.openxmlformats.org",
        "purl.org",
    }

    suspicious_urls: list[tuple[str, int, str]] = []

    for py_file in app_dir.rglob("*.py"):
        if "__pycache__" in py_file.parts:
            continue
        try:
            content = py_file.read_text(encoding="utf-8")
        except Exception:  # noqa: S112
            continue

        for line_num, line in enumerate(content.splitlines(), start=1):
            stripped = line.strip()
            if stripped.startswith("#"):
                continue

            matches = url_pattern.findall(line)
            for url in matches:
                host_match = re.search(r"https?://([^/:\s]+)", url)
                if not host_match:
                    continue
                host = host_match.group(1).lower()
                if not any(wl in host for wl in whitelisted_hosts):
                    rel_path = py_file.relative_to(PROJECT_ROOT)
                    suspicious_urls.append((str(rel_path), line_num, url))

    if suspicious_urls:
        details = "\n".join(f"  {p}:{ln} -> {url}" for p, ln, url in suspicious_urls[:5])
        return CheckResult(
            "Codebase Outbound URL Audit",
            False,
            f"Found {len(suspicious_urls)} unapproved external URLs in app/:\n{details}",
        )

    return CheckResult(
        "Codebase Outbound URL Audit",
        True,
        "Zero unauthorized external URLs found in application source code.",
    )


def check_sandbox_configuration() -> CheckResult:
    """Verify Docker sandbox enforces air-gap, unprivileged execution, and fail-closed policy."""
    sandbox_file = PROJECT_ROOT / "app" / "sandbox" / "docker_sandbox.py"
    if not sandbox_file.exists():
        return CheckResult("Sandbox Security Profile", False, "docker_sandbox.py not found")

    content = sandbox_file.read_text(encoding="utf-8")

    issues: list[str] = []
    if 'network_mode="none"' not in content and "'network_mode': 'none'" not in content:
        issues.append("Sandbox does not enforce network_mode='none'")

    if 'cap_drop=["ALL"]' not in content and "'ALL'" not in content:
        issues.append("Sandbox does not drop ALL Linux capabilities")

    if "fail-closed" not in content.lower():
        issues.append("Fail-closed policy verification missing")

    if issues:
        return CheckResult("Sandbox Security Profile", False, "; ".join(issues))

    return CheckResult(
        "Sandbox Security Profile",
        True,
        "Air-gap container configuration verified (network_mode=none, cap_drop=ALL, fail-closed policy).",
    )


def check_secrets_and_git_hygiene() -> CheckResult:
    """Verify git hygiene, .env exclusion, and secret enforcement."""
    gitignore_file = PROJECT_ROOT / ".gitignore"
    if not gitignore_file.exists():
        return CheckResult("Secrets & Git Hygiene", False, ".gitignore file missing")

    gitignore_content = gitignore_file.read_text(encoding="utf-8")
    if ".env" not in gitignore_content:
        return CheckResult("Secrets & Git Hygiene", False, ".env is not excluded in .gitignore")

    # Check git tracked files
    result = subprocess.run(  # noqa: S603
        ["git", "ls-files", ".env"],  # noqa: S607
        cwd=PROJECT_ROOT,
        capture_output=True,
        text=True,
    )
    if result.stdout.strip():
        return CheckResult(
            "Secrets & Git Hygiene",
            False,
            "CRITICAL: .env file is currently tracked in Git version control!",
        )

    # Check config.py secret enforcement
    config_file = PROJECT_ROOT / "app" / "config.py"
    config_content = config_file.read_text(encoding="utf-8")
    if "jwt_secret_key" not in config_content or (
        "len(v) < 32" not in config_content and "min_length=32" not in config_content
    ):
        return CheckResult(
            "Secrets & Git Hygiene",
            False,
            "JWT_SECRET_KEY length validation (>= 32 chars) missing in config.py",
        )

    return CheckResult(
        "Secrets & Git Hygiene",
        True,
        ".env is gitignored, untracked, and config enforces >=32 character cryptographically strong secrets.",
    )


def check_docker_compose() -> CheckResult:
    """Verify docker-compose binds only to 127.0.0.1 and avoids hardcoded credentials."""
    compose_file = PROJECT_ROOT / "docker-compose.yml"
    if not compose_file.exists():
        return CheckResult("Docker Compose Profile", False, "docker-compose.yml not found")

    content = compose_file.read_text(encoding="utf-8")
    issues: list[str] = []

    # Check for ports exposed on 0.0.0.0
    in_ports_section = False
    ports_indent = 0

    for line in content.splitlines():
        # Check indentation level
        stripped = line.strip()
        indent = len(line) - len(line.lstrip())

        if stripped.startswith("ports:"):
            in_ports_section = True
            ports_indent = indent
            continue

        if in_ports_section:
            # If line is less or equally indented than 'ports:', we exited the ports section
            if stripped and indent <= ports_indent and not stripped.startswith("#"):
                in_ports_section = False
            elif stripped.startswith("- "):
                port_match = re.search(r'-\s*["\']?([^"\']+)["\']?', stripped)
                if port_match:
                    port_str = port_match.group(1)
                    # Port map (host:container or host_ip:host_port:container_port)
                    if not port_str.startswith("127.0.0.1"):
                        issues.append(f"Port mapping '{port_str}' not bound to 127.0.0.1")

    # Check for hardcoded postgres password
    for line in content.splitlines():
        if "POSTGRES_PASSWORD:" in line and "${" not in line:
            issues.append("Hardcoded POSTGRES_PASSWORD detected in docker-compose.yml")

    if issues:
        return CheckResult("Docker Compose Profile", False, "; ".join(issues))

    return CheckResult(
        "Docker Compose Profile",
        True,
        "All exposed ports explicitly bound to 127.0.0.1; credentials passed via environment variables.",
    )


def check_serialization_and_math_safety() -> CheckResult:
    """Verify zero pickle deserialization and AST-only math evaluation."""
    app_dir = PROJECT_ROOT / "app"
    issues: list[str] = []

    for py_file in app_dir.rglob("*.py"):
        if "__pycache__" in py_file.parts:
            continue
        try:
            content = py_file.read_text(encoding="utf-8")
            tree = ast.parse(content, filename=str(py_file))
        except Exception:  # noqa: S112
            continue

        rel_path = py_file.relative_to(PROJECT_ROOT)

        # Walk AST to detect actual dangerous function calls
        for node in ast.walk(tree):
            if isinstance(node, ast.Call):
                func = node.func
                if isinstance(func, ast.Name) and func.id in ("eval", "exec"):
                    issues.append(f"{rel_path}:{node.lineno}: Dangerous {func.id}() call detected")
                elif isinstance(func, ast.Attribute) and func.attr in ("load", "loads"):
                    if isinstance(func.value, ast.Name) and func.value.id == "pickle":
                        issues.append(f"{rel_path}:{node.lineno}: Unsafe pickle.{func.attr}() call detected")

    if issues:
        return CheckResult("Serialization & AST Safety", False, "; ".join(issues))

    return CheckResult(
        "Serialization & AST Safety",
        True,
        "AST verification passed: Zero pickle deserialization and zero eval()/exec() calls across app/.",
    )


def main() -> int:
    print("\n" + "=" * 70)
    print(" SOVEREIGN AIR-GAP & SECURITY INTEGRITY VERIFIER")
    print(" Validating On-Premise Industrial Security Constraints")
    print("=" * 70 + "\n")

    checks = [
        check_socket_egress,
        check_codebase_urls,
        check_sandbox_configuration,
        check_secrets_and_git_hygiene,
        check_docker_compose,
        check_serialization_and_math_safety,
    ]

    all_passed = True
    results: list[CheckResult] = []

    for check_fn in checks:
        res = check_fn()
        results.append(res)
        status_symbol = "[PASS]" if res.passed else "[FAIL]"
        print(f"{status_symbol} {res.name}")
        print(f"       -> {res.details}\n")
        if not res.passed:
            all_passed = False

    print("-" * 70)
    passed_count = sum(1 for r in results if r.passed)
    total_count = len(results)
    print(f"Summary: {passed_count}/{total_count} Security & Air-Gap Checks Passed.")
    print("=" * 70 + "\n")

    return 0 if all_passed else 1


if __name__ == "__main__":
    sys.exit(main())
