"""
tests/test_integration/helpers.py
=================================
Helper predicates and fixtures for live integration testing.
"""

import socket

import httpx


def is_ollama_reachable(timeout: float = 1.0) -> bool:
    """Checks if Ollama daemon is reachable on localhost:11434."""
    try:
        with socket.create_connection(("127.0.0.1", 11434), timeout=timeout):
            return True
    except Exception:
        return False


def get_available_ollama_models() -> set[str]:
    """Returns set of model names available in local Ollama daemon."""
    if not is_ollama_reachable():
        return set()
    try:
        resp = httpx.get("http://127.0.0.1:11434/api/tags", timeout=3.0)
        if resp.status_code == 200:
            data = resp.json()
            models = {m.get("name", "") for m in data.get("models", [])}
            # Also add unversioned base names
            unversioned = {m.split(":")[0] for m in models if ":" in m}
            return models | unversioned
    except Exception:
        pass
    return set()
