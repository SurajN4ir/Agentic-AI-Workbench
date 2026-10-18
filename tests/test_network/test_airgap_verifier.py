"""
tests/test_network/test_airgap_verifier.py
==========================================
Integration tests asserting that all 6 air-gap verification checks pass in pytest.
"""

from scripts.verify_airgap import (
    check_codebase_urls,
    check_docker_compose,
    check_sandbox_configuration,
    check_secrets_and_git_hygiene,
    check_serialization_and_math_safety,
    check_socket_egress,
)


def test_egress_interception_check() -> None:
    res = check_socket_egress()
    assert res.passed, res.details


def test_codebase_urls_check() -> None:
    res = check_codebase_urls()
    assert res.passed, res.details


def test_sandbox_configuration_check() -> None:
    res = check_sandbox_configuration()
    assert res.passed, res.details


def test_secrets_and_git_hygiene_check() -> None:
    res = check_secrets_and_git_hygiene()
    assert res.passed, res.details


def test_docker_compose_check() -> None:
    res = check_docker_compose()
    assert res.passed, res.details


def test_serialization_and_math_safety_check() -> None:
    res = check_serialization_and_math_safety()
    assert res.passed, res.details
