"""
app/sandbox/docker_sandbox.py
=============================
Isolated container sandbox for executing untrusted Python scripts safely.
Enforces strict security boundaries:
  - network_mode="none": the sandbox container receives no network attachment
  - cap_drop=["ALL"]: drops all Linux capabilities
  - security_opt=["no-new-privileges:true"]: prevents privilege escalation
  - mem_limit="512m" and pids_limit=50: prevents memory exhaustion and fork bombs
  - user="1000:1000": non-root execution
  - Fail-closed: Never executes untrusted code on host system when Docker is unavailable
"""

import logging
import time
from typing import Any

import docker
from pydantic import BaseModel, Field

from app.config import get_settings
from app.tools.interface import validate_workspace_path

logger = logging.getLogger("sovereign.sandbox")

DOCKER_INSTALLED = True


class SandboxExecutionResult(BaseModel):
    success: bool
    stdout: str = ""
    stderr: str = ""
    exit_code: int | None = None
    execution_time_ms: float = 0.0
    generated_files: list[str] = Field(default_factory=list)
    steps: list[str] = Field(default_factory=list)
    isolated: bool = True


class DockerSandbox:
    """Manages secure, containerized execution of untrusted code."""

    def __init__(
        self,
        image: str | None = None,
        mem_limit: str | None = None,
        timeout_s: int | None = None,
        docker_client: Any | None = None,
    ) -> None:
        settings = get_settings()
        self.image = image or settings.sandbox_image
        self.mem_limit = mem_limit or settings.sandbox_mem_limit
        self.default_timeout_s = timeout_s or settings.sandbox_timeout_seconds
        self._client = docker_client

    def _get_docker_client(self) -> Any:
        """Retrieves or initializes Docker client, returning None if daemon unavailable."""
        if self._client is not None:
            return self._client

        if not DOCKER_INSTALLED or docker is None:
            return None

        try:
            client = docker.from_env()
            client.ping()
            return client
        except Exception as e:
            logger.warning("Docker daemon check failed: %s", e)
            return None

    def execute(
        self,
        code: str,
        session_id: str,
        timeout_s: int | None = None,
    ) -> SandboxExecutionResult:
        """Executes Python code inside an isolated, air-gapped Docker container.

        Enforces strict fail-closed security: If Docker is unavailable, refuses
        to execute rather than falling back to dangerous host execution.
        """
        start_time = time.perf_counter()
        effective_timeout = timeout_s or self.default_timeout_s
        steps: list[str] = [
            f"Isolation engine: Docker container ({self.image})",
            f"Timeout limit: {effective_timeout}s",
            f"Memory limit: {self.mem_limit}",
            "Container network: Disabled (network_mode=none)",
        ]

        # 1. Enforce workspace boundary
        try:
            session_workspace = validate_workspace_path(".", session_id, create_parents=True)
        except Exception as err:
            return SandboxExecutionResult(
                success=False,
                stderr=f"Workspace boundary error: {err}",
                exit_code=-1,
                execution_time_ms=(time.perf_counter() - start_time) * 1000,
                steps=steps + [f"Boundary check: Failed ({err})"],
                isolated=True,
            )

        # Record initial files for generated files diffing
        initial_files = {f.name for f in session_workspace.iterdir()} if session_workspace.exists() else set()

        # 2. Check Docker availability (Fail-Closed)
        client = self._get_docker_client()
        if client is None:
            duration_ms = (time.perf_counter() - start_time) * 1000
            error_msg = (
                "Security Policy Violation: Docker daemon is unavailable. "
                "Running untrusted code directly on the host operating system is strictly prohibited "
                "to protect sovereign system integrity."
            )
            logger.error("Sandbox execution blocked: Docker daemon is unreachable.")
            return SandboxExecutionResult(
                success=False,
                stdout="",
                stderr=error_msg,
                exit_code=-1,
                execution_time_ms=duration_ms,
                steps=steps + ["Daemon status: Unreachable", "Action: Execution blocked (fail-closed)"],
                isolated=True,
            )

        container = None
        stdout = ""
        stderr = ""
        exit_code = -1

        try:
            # 3. Launch isolated container
            container = client.containers.run(
                image=self.image,
                command=["python", "-c", code],
                volumes={str(session_workspace.resolve()): {"bind": "/workspace", "mode": "rw"}},
                working_dir="/workspace",
                network_mode="none",  # Disable networking for this sandbox container
                mem_limit=self.mem_limit,
                nano_cpus=2_000_000_000,  # Max 2 CPUs
                pids_limit=50,  # Prevent fork bombs
                cap_drop=["ALL"],  # Drop all Linux capabilities
                security_opt=["no-new-privileges:true"],
                user="1000:1000",  # Do not run untrusted code as the image's default root user
                detach=True,
            )

            # Wait for execution with timeout
            result = container.wait(timeout=effective_timeout)
            exit_code = int(result.get("StatusCode", 0))

            raw_stdout = container.logs(stdout=True, stderr=False)
            raw_stderr = container.logs(stdout=False, stderr=True)

            stdout = raw_stdout.decode("utf-8", errors="replace") if isinstance(raw_stdout, bytes) else str(raw_stdout)
            stderr = raw_stderr.decode("utf-8", errors="replace") if isinstance(raw_stderr, bytes) else str(raw_stderr)

            steps.append(f"Execution completed with exit code {exit_code}")

        except Exception as exc:
            exc_str = str(exc)
            if "Read timed out" in exc_str or "timed out" in exc_str.lower():
                stderr = f"Execution timed out after {effective_timeout} seconds."
                steps.append(f"Execution timed out after {effective_timeout}s; killed.")
            else:
                stderr = f"Container error: {exc}"
                steps.append(f"Container runtime error: {exc}")

            if container is not None:
                try:
                    container.kill()
                except Exception as kill_err:
                    logger.debug("Container kill error: %s", kill_err)

        finally:
            if container is not None:
                try:
                    container.remove(force=True)
                except Exception as remove_err:
                    logger.warning("Failed to remove container: %s", remove_err)

        # 4. Compute generated files
        current_files = {f.name for f in session_workspace.iterdir()} if session_workspace.exists() else set()
        new_files = sorted(current_files - initial_files)

        duration_ms = (time.perf_counter() - start_time) * 1000
        success = exit_code == 0

        return SandboxExecutionResult(
            success=success,
            stdout=stdout,
            stderr=stderr,
            exit_code=exit_code,
            execution_time_ms=round(duration_ms, 2),
            generated_files=new_files,
            steps=steps,
            isolated=True,
        )
