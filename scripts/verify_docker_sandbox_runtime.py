"""Run bounded real Docker checks for the code sandbox using synthetic inputs.

This is a manual acceptance helper, not part of the default test suite. It uses
the configured local Python image, a fresh workspace below eval/, and a
loopback-only nonexistent registry for the missing-image failure case.
"""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

EVIDENCE_DIR = ROOT / "eval" / "post-audit-2026-10-26"
WORKSPACE = EVIDENCE_DIR / "docker-sandbox-workspace"
OUTPUT = EVIDENCE_DIR / "docker_sandbox_runtime.json"
IMAGE = "python:3.11-slim"


class TrackedContainer:
    def __init__(self, container: Any, observer: ObservedClient) -> None:
        self._container = container
        self._observer = observer

    def wait(self, *args: Any, **kwargs: Any) -> Any:
        self._observer.inspect_before_wait(self._container.id)
        return self._container.wait(*args, **kwargs)

    def __getattr__(self, name: str) -> Any:
        return getattr(self._container, name)


class ObservedContainers:
    def __init__(self, client: Any, observer: ObservedClient) -> None:
        self._containers = client.containers
        self._observer = observer

    def run(self, *args: Any, **kwargs: Any) -> TrackedContainer:
        container = self._containers.run(*args, **kwargs)
        self._observer.container_id = container.id
        return TrackedContainer(container, self._observer)


class ObservedClient:
    """Proxy the real SDK client to snapshot HostConfig before the short job exits."""

    def __init__(self, client: Any) -> None:
        self._client = client
        self.container_id: str | None = None
        self.host_config: dict[str, Any] | None = None
        self.mounts: list[dict[str, Any]] | None = None
        self.user: str | None = None

    @property
    def containers(self) -> ObservedContainers:
        return ObservedContainers(self._client, self)

    def inspect_before_wait(self, container_id: str) -> None:
        inspected = self._client.api.inspect_container(container_id)
        self.host_config = inspected["HostConfig"]
        self.mounts = inspected.get("Mounts", [])
        self.user = inspected.get("Config", {}).get("User")

    def __getattr__(self, name: str) -> Any:
        return getattr(self._client, name)


def check(condition: bool, detail: str) -> dict[str, Any]:
    return {"passed": bool(condition), "detail": detail}


def main() -> int:
    import docker
    from app.config import get_settings
    from app.sandbox.docker_sandbox import DockerSandbox
    from docker.errors import NotFound

    os.environ.setdefault("POSTGRES_PASSWORD", "synthetic-docker-verification-only")
    os.environ.setdefault("JWT_SECRET_KEY", "synthetic-docker-verification-key-000000000000")
    os.environ["WORKSPACE_DIR"] = str(WORKSPACE)
    get_settings.cache_clear()
    WORKSPACE.mkdir(parents=True, exist_ok=True)
    session = f"runtime-verification-{os.getpid()}"
    session_dir = WORKSPACE / session
    session_dir.mkdir(parents=True, exist_ok=True)

    client = docker.from_env(timeout=8)
    client.ping()
    server = client.version()
    image_present = any(
        IMAGE in tag for image in client.images.list() for tag in image.tags
    )

    result: dict[str, Any] = {
        "date": "2026-10-26",
        "server": {
            "version": server.get("Version"),
            "os": server.get("Os"),
            "architecture": server.get("Arch"),
            "image_preexisting": image_present,
        },
        "checks": {},
        "notes": [
            "Synthetic code and a fresh eval/ workspace only; no user documents were read.",
            "The Docker image used was present before the test; no image was pulled.",
            "Network probe used the literal public IP 1.1.1.1 with a short timeout.",
            "The missing-image registry address is loopback-only (127.0.0.1:1).",
        ],
    }

    observer = ObservedClient(client)
    sandbox = DockerSandbox(image=IMAGE, docker_client=observer)
    allowed = sandbox.execute(
        "from pathlib import Path; Path('/workspace/allowed.txt').write_text('synthetic-ok'); print('ALLOWED_OK')",
        session_id=session,
        timeout_s=10,
    )
    resource = observer.host_config or {}
    mount_sources = [Path(m["Source"]).resolve() for m in observer.mounts or [] if m.get("Destination") == "/workspace"]
    checks = result["checks"]
    checks["allowed_execution"] = check(
        allowed.success and allowed.stdout.strip() == "ALLOWED_OK" and (session_dir / "allowed.txt").read_text() == "synthetic-ok",
        f"success={allowed.success}; exit={allowed.exit_code}; stdout={allowed.stdout.strip()!r}; stderr={allowed.stderr[:500]!r}; synthetic workspace output verified",
    )
    checks["mount_boundary"] = check(
        len(mount_sources) == 1 and mount_sources[0] == session_dir.resolve() and resource.get("Binds"),
        f"only /workspace bind source={str(mount_sources[0]) if mount_sources else None}; no other host bind recorded",
    )
    checks["resource_limits"] = check(
        resource.get("Memory") == 512 * 1024 * 1024
        and resource.get("NanoCpus") == 2_000_000_000
        and resource.get("PidsLimit") == 50,
        f"Memory={resource.get('Memory')}; NanoCpus={resource.get('NanoCpus')}; PidsLimit={resource.get('PidsLimit')}",
    )
    checks["isolation_flags"] = check(
        resource.get("NetworkMode") == "none"
        and resource.get("CapDrop") == ["ALL"]
        and "no-new-privileges:true" in (resource.get("SecurityOpt") or [])
        and observer.user == "1000:1000",
        f"NetworkMode={resource.get('NetworkMode')}; CapDrop={resource.get('CapDrop')}; SecurityOpt={resource.get('SecurityOpt')}; User={observer.user}",
    )
    try:
        client.api.inspect_container(observer.container_id)
        removed = False
    except NotFound:
        removed = True
    checks["cleanup"] = check(removed, f"container {observer.container_id} absent after execute() returned")

    denied = sandbox.execute(
        "import os, socket\n"
        "try:\n os.setuid(0); print('PRIVILEGE_ESCALATION_ALLOWED')\n"
        "except OSError as e: print('PRIVILEGE_ESCALATION_BLOCKED', type(e).__name__)\n"
        "try:\n socket.create_connection(('1.1.1.1', 443), timeout=1); print('NETWORK_ALLOWED')\n"
        "except OSError as e: print('NETWORK_BLOCKED', type(e).__name__)\n"
        "try:\n open('/etc/shadow').read(1); print('SHADOW_READ_ALLOWED')\n"
        "except OSError as e: print('SHADOW_READ_BLOCKED', type(e).__name__)\n",
        session_id=session,
        timeout_s=5,
    )
    checks["denied_operations"] = check(
        denied.success
        and "PRIVILEGE_ESCALATION_BLOCKED" in denied.stdout
        and "NETWORK_BLOCKED" in denied.stdout
        and "SHADOW_READ_BLOCKED" in denied.stdout
        and "NETWORK_ALLOWED" not in denied.stdout,
        f"exit={denied.exit_code}; output={denied.stdout.strip()!r}",
    )

    host_probe = ROOT / "eval" / "docker-container-host-boundary-probe.txt"
    if host_probe.exists():
        raise RuntimeError(f"Refusing to overwrite pre-existing probe path: {host_probe}")
    boundary = sandbox.execute(
        "from pathlib import Path; Path('/tmp/docker-container-host-boundary-probe.txt').write_text('container-only'); print('CONTAINER_PATH_WRITTEN')",
        session_id=session,
        timeout_s=5,
    )
    checks["host_filesystem_boundary"] = check(
        boundary.success and "CONTAINER_PATH_WRITTEN" in boundary.stdout and not host_probe.exists(),
        f"container local filesystem write succeeded; corresponding host probe absent at {host_probe}",
    )

    timeout = sandbox.execute("while True: pass", session_id=session, timeout_s=2)
    checks["timeout"] = check(
        not timeout.success and "timed out after 2 seconds" in timeout.stderr,
        f"success={timeout.success}; stderr={timeout.stderr!r}; elapsed_ms={timeout.execution_time_ms}",
    )
    timeout_container_id = observer.container_id
    try:
        client.api.inspect_container(timeout_container_id)
        timeout_removed = False
    except NotFound:
        timeout_removed = True
    checks["timeout_cleanup"] = check(
        timeout_removed,
        f"timed-out container {timeout_container_id} absent after execute() returned",
    )

    invalid_session = sandbox.execute("print('must-not-run')", session_id="../escape", timeout_s=2)
    checks["invalid_workspace_boundary"] = check(
        not invalid_session.success and "Workspace boundary error" in invalid_session.stderr,
        f"success={invalid_session.success}; stderr={invalid_session.stderr!r}",
    )

    missing = DockerSandbox(image="127.0.0.1:1/synthetic/no-such-image:never", docker_client=client)
    missing_result = missing.execute("print('must-not-run')", session_id=session, timeout_s=2)
    checks["missing_image_failure"] = check(
        not missing_result.success
        and missing_result.exit_code == -1
        and "Container error" in missing_result.stderr
        and "127.0.0.1:1" in missing_result.stderr
        and "failed to resolve reference" in missing_result.stderr,
        f"success={missing_result.success}; exit={missing_result.exit_code}; error={missing_result.stderr[:500]!r}",
    )

    # Exercise the actual SDK ping failure path without stopping/reconfiguring Docker Desktop.
    original_from_env = docker.from_env
    try:
        docker.from_env = lambda **kwargs: docker.DockerClient(base_url="tcp://127.0.0.1:1", timeout=1)  # type: ignore[assignment]
        unavailable = DockerSandbox()
        daemon_failure = unavailable.execute("print('must-not-run')", session_id=session, timeout_s=2)
    finally:
        docker.from_env = original_from_env  # type: ignore[assignment]
    checks["daemon_ping_failure_fail_closed"] = check(
        not daemon_failure.success
        and "Docker daemon is unavailable" in daemon_failure.stderr
        and any("fail-closed" in step for step in daemon_failure.steps),
        f"success={daemon_failure.success}; exit={daemon_failure.exit_code}; steps={daemon_failure.steps}",
    )

    result["checks"] = checks
    result["summary"] = {
        "passed": sum(1 for item in checks.values() if item["passed"]),
        "total": len(checks),
        "failed": [name for name, item in checks.items() if not item["passed"]],
    }
    result["commands"] = [
        "docker context ls",
        "docker version",
        "docker info --format '{{.ServerVersion}} {{.OperatingSystem}} {{.OSType}} {{.Architecture}}'",
        "docker image ls --format '{{.Repository}}:{{.Tag}} {{.ID}}'",
        ".venv\\Scripts\\python.exe scripts\\verify_docker_sandbox_runtime.py",
    ]
    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT.write_text(json.dumps(result, indent=2), encoding="utf-8")
    print(json.dumps(result, indent=2))
    client.close()
    return 0 if result["summary"]["passed"] == result["summary"]["total"] else 1


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except Exception as exc:
        print(f"Docker runtime verification blocked: {type(exc).__name__}: {exc}")
        raise
