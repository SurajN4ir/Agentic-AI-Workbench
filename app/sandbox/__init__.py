"""
app/sandbox/__init__.py
=======================
Isolated execution environment for running untrusted code safely.
Enforces Docker container boundaries with zero network egress.
"""

from app.sandbox.docker_sandbox import DockerSandbox, SandboxExecutionResult

__all__ = [
    "DockerSandbox",
    "SandboxExecutionResult",
]
