"""
tests/test_sandbox/test_docker_sandbox.py
=========================================
Unit tests for the isolated DockerSandbox execution engine.
Verifies security containment parameters, fail-closed behavior, and timeout enforcement.
"""

from unittest.mock import MagicMock

from app.sandbox.docker_sandbox import DockerSandbox


class TestDockerSandbox:
    def test_fail_closed_when_docker_unavailable(self) -> None:
        """When Docker daemon is unreachable, execution must fail-closed.
        Arbitrary host execution via subprocess is strictly forbidden."""

        class FakeFailingClient:
            def ping(self) -> None:
                raise ConnectionError("Docker is not running")

        sandbox = DockerSandbox(docker_client=None)
        # Force _get_docker_client to return None
        sandbox._get_docker_client = lambda: None  # type: ignore[method-assign]

        res = sandbox.execute("print('malicious code')", session_id="test_session")
        assert res.success is False
        assert res.exit_code == -1
        assert "Docker daemon is unavailable" in res.stderr
        assert "host operating system is strictly prohibited" in res.stderr
        assert res.isolated is True

    def test_container_security_parameters_enforced(self) -> None:
        """Verifies container is created with strict security constraints."""
        mock_container = MagicMock()
        mock_container.wait.return_value = {"StatusCode": 0}
        mock_container.logs.side_effect = lambda stdout=False, stderr=False: (b"42\n" if stdout else b"")

        mock_containers = MagicMock()
        mock_containers.run.return_value = mock_container

        mock_client = MagicMock()
        mock_client.ping.return_value = True
        mock_client.containers = mock_containers

        sandbox = DockerSandbox(
            image="python:3.11-slim",
            mem_limit="512m",
            timeout_s=10,
            docker_client=mock_client,
        )

        res = sandbox.execute("print(40 + 2)", session_id="secure_session")

        assert res.success is True
        assert res.stdout == "42\n"
        assert res.exit_code == 0

        # Verify exact security arguments passed to containers.run
        mock_containers.run.assert_called_once()
        kwargs = mock_containers.run.call_args.kwargs

        assert kwargs["network_mode"] == "none"  # Complete air-gap
        assert kwargs["cap_drop"] == ["ALL"]  # Dropped capabilities
        assert kwargs["security_opt"] == ["no-new-privileges:true"]  # No new privileges
        assert kwargs["mem_limit"] == "512m"  # Memory cap
        assert kwargs["pids_limit"] == 50  # Fork bomb protection
        assert kwargs["nano_cpus"] == 2_000_000_000  # CPU cap

        # Verify cleanup
        mock_container.remove.assert_called_once_with(force=True)

    def test_timeout_kills_container(self) -> None:
        """When container times out, kill and force remove must be executed."""
        mock_container = MagicMock()
        mock_container.wait.side_effect = TimeoutError("Read timed out")

        mock_containers = MagicMock()
        mock_containers.run.return_value = mock_container

        mock_client = MagicMock()
        mock_client.ping.return_value = True
        mock_client.containers = mock_containers

        sandbox = DockerSandbox(timeout_s=2, docker_client=mock_client)
        res = sandbox.execute("while True: pass", session_id="timeout_session")

        assert res.success is False
        assert "timed out after" in res.stderr
        mock_container.kill.assert_called_once()
        mock_container.remove.assert_called_once_with(force=True)

    def test_invalid_session_id_aborts_before_container_creation(self) -> None:
        """Invalid session ID stops execution before touching Docker."""
        mock_client = MagicMock()
        sandbox = DockerSandbox(docker_client=mock_client)

        res = sandbox.execute("print(1)", session_id="bad/session/escape")
        assert res.success is False
        assert "Workspace boundary error" in res.stderr
        mock_client.containers.run.assert_not_called()
