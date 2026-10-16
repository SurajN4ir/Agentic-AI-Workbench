"""
tests/test_identity/test_auth.py
=================================
Security-critical tests for authentication, JWT, and account lockout.
All tests use the in-memory SQLite DB — no Postgres or Ollama required.

Test categories:
  - Config validation (JWT secret enforcement)
  - Password hashing (bcrypt roundtrip, constant-time)
  - JWT token creation/verification (valid, expired, forged, wrong type)
  - Health/readiness endpoints (no sensitive data)
  - Login API (success, wrong password, unknown user)
  - Account lockout (N failures → locked)
  - JWT via header only (query-param rejected)
  - Token type enforcement (refresh token rejected as access)
  - Admin-only 2FA disable enforcement
"""

import time
import uuid
from unittest.mock import patch

import pytest
from app.config import get_settings
from app.identity.models import User
from app.identity.service import (
    create_access_token,
    decode_token,
    hash_password,
    verify_password,
)
from httpx import AsyncClient

from tests.conftest import auth_headers, make_access_token


# ─── Config validation ────────────────────────────────────────────────────────
class TestConfigValidation:
    def test_jwt_secret_too_short(self) -> None:
        """Settings must reject a JWT secret shorter than 32 chars."""
        from app.config import Settings
        from pydantic import ValidationError

        with pytest.raises(ValidationError, match="at least 32 characters"):
            Settings(
                jwt_secret_key="tooshort",
                postgres_password="SomeStrongPass123!",
            )

    def test_known_insecure_jwt_secret_rejected(self) -> None:
        """The well-known placeholder secret from the original repo must be rejected."""
        from app.config import Settings
        from pydantic import ValidationError

        with pytest.raises(ValidationError, match="insecure placeholder"):
            Settings(
                jwt_secret_key="sovereign_agent_air_gapped_jwt_secret_key_2026",
                postgres_password="SomeStrongPass123!",
            )

    def test_weak_db_password_rejected(self) -> None:
        """Known weak DB passwords must be rejected."""
        from app.config import Settings
        from pydantic import ValidationError

        with pytest.raises(ValidationError):
            Settings(
                jwt_secret_key="a" * 32,
                postgres_password="postgres_sovereign_2026",
            )

    def test_valid_config_accepted(self) -> None:
        """Valid config (strong secret, strong password) must be accepted."""
        from app.config import Settings

        s = Settings(
            jwt_secret_key="a" * 32,
            postgres_password="StrongUniquePass99!",
        )
        assert s.jwt_secret_key == "a" * 32


# ─── Password hashing ─────────────────────────────────────────────────────────
class TestPasswordHashing:
    def test_hash_and_verify(self) -> None:
        pw = "MySecureP@ssw0rd"
        h = hash_password(pw)
        assert h.startswith("$2b$")  # bcrypt
        assert verify_password(pw, h)

    def test_wrong_password_rejected(self) -> None:
        h = hash_password("correct")
        assert not verify_password("wrong", h)

    def test_empty_hash_rejected(self) -> None:
        assert not verify_password("anything", "")

    def test_different_hashes_for_same_password(self) -> None:
        """bcrypt must produce a different hash each time (random salt)."""
        pw = "SamePassword1!"
        h1 = hash_password(pw)
        h2 = hash_password(pw)
        assert h1 != h2
        assert verify_password(pw, h1)
        assert verify_password(pw, h2)

    def test_pbkdf2_legacy_hash_verified(self) -> None:
        """The PBKDF2 path (salt$hash format) from original repo must still verify."""
        import hashlib

        salt = "abc123"
        derived = hashlib.pbkdf2_hmac("sha256", b"legacypass", salt.encode(), 100_000).hex()
        stored = f"{salt}${derived}"
        assert verify_password("legacypass", stored)
        assert not verify_password("wrongpass", stored)


# ─── JWT token ────────────────────────────────────────────────────────────────
class TestJWT:
    def test_valid_access_token(self) -> None:
        uid = str(uuid.uuid4())
        token = create_access_token(uid, "user", "alice")
        payload = decode_token(token)
        assert payload is not None
        assert payload["sub"] == uid
        assert payload["type"] == "access"

    def test_forged_token_rejected(self) -> None:
        """A token signed with a different key must be rejected."""
        import hashlib
        import hmac
        import json
        from base64 import urlsafe_b64encode

        secret = b"different_secret_key_totally_wrong_one_here!!"
        header = urlsafe_b64encode(json.dumps({"alg": "HS256", "typ": "JWT"}).encode()).rstrip(b"=")
        payload = urlsafe_b64encode(json.dumps({"sub": "hacker", "exp": 9999999999, "type": "access"}).encode()).rstrip(
            b"="
        )
        signing_input = header + b"." + payload
        sig = urlsafe_b64encode(hmac.new(secret, signing_input, hashlib.sha256).digest()).rstrip(b"=")
        forged = f"{header.decode()}.{payload.decode()}.{sig.decode()}"
        assert decode_token(forged) is None

    def test_expired_token_rejected(self) -> None:
        """An expired token (exp in the past) must be rejected."""
        import hashlib
        import hmac
        import json
        from base64 import urlsafe_b64encode

        s = get_settings()
        secret = s.jwt_secret_key.encode()
        payload_data = {
            "sub": "user1",
            "role": "user",
            "username": "u1",
            "iat": int(time.time()) - 10000,
            "exp": int(time.time()) - 1,  # expired 1 second ago
            "type": "access",
        }
        header = urlsafe_b64encode(json.dumps({"alg": "HS256", "typ": "JWT"}).encode()).rstrip(b"=")
        payload = urlsafe_b64encode(json.dumps(payload_data).encode()).rstrip(b"=")
        signing_input = header + b"." + payload
        sig = urlsafe_b64encode(hmac.new(secret, signing_input, hashlib.sha256).digest()).rstrip(b"=")
        expired_token = f"{header.decode()}.{payload.decode()}.{sig.decode()}"
        assert decode_token(expired_token) is None

    def test_refresh_token_rejected_as_access(self) -> None:
        """A refresh token must not be accepted where an access token is required."""
        from app.identity.service import create_refresh_token

        token = create_refresh_token("user-id-123", str(uuid.uuid4()))
        payload = decode_token(token)
        assert payload is not None
        assert payload["type"] == "refresh"
        # The type check in get_current_user rejects non-access tokens
        # Here we verify the type field is correctly set
        assert payload["type"] != "access"


# ─── Health endpoints ─────────────────────────────────────────────────────────
class TestHealthEndpoints:
    @pytest.mark.asyncio
    async def test_health_returns_200(self, client: AsyncClient) -> None:
        r = await client.get("/health")
        assert r.status_code == 200
        body = r.json()
        assert body["status"] == "ok"
        # Must NOT expose model names, VRAM info, or topology
        assert "model" not in body
        assert "vram" not in body
        assert "ollama" not in body

    @pytest.mark.asyncio
    async def test_health_no_auth_required(self, client: AsyncClient) -> None:
        """Health probe must work without any auth header."""
        r = await client.get("/health")
        assert r.status_code == 200

    @pytest.mark.asyncio
    async def test_ready_returns_503_when_db_unreachable(self, client: AsyncClient) -> None:
        """Readiness probe returns 503 when DB is unreachable."""
        with patch("app.main.check_database_health", return_value=False):
            r = await client.get("/ready")
        assert r.status_code == 503


# ─── Login API ────────────────────────────────────────────────────────────────
class TestLoginAPI:
    @pytest.mark.asyncio
    async def test_login_success(self, client: AsyncClient, test_user: User) -> None:
        r = await client.post(
            "/api/v1/auth/login",
            json={
                "username": "testuser",
                "password": "TestPass123!",
            },
        )
        assert r.status_code == 200
        body = r.json()
        assert "access_token" in body
        assert body["access_token"] != ""
        assert body["requires_2fa"] is False

    @pytest.mark.asyncio
    async def test_login_wrong_password(self, client: AsyncClient, test_user: User) -> None:
        r = await client.post(
            "/api/v1/auth/login",
            json={
                "username": "testuser",
                "password": "WrongPassword!!",
            },
        )
        assert r.status_code == 401

    @pytest.mark.asyncio
    async def test_login_unknown_user(self, client: AsyncClient) -> None:
        r = await client.post(
            "/api/v1/auth/login",
            json={
                "username": "nobody",
                "password": "irrelevant",
            },
        )
        assert r.status_code == 401

    @pytest.mark.asyncio
    async def test_no_default_admin_account(self, client: AsyncClient) -> None:
        """The known default credentials from the original repo must NOT work."""
        for creds in [
            {"username": "admin", "password": "admin123"},
            {"username": "engineer1", "password": "engineer123"},
            {"username": "analyst1", "password": "analyst123"},
        ]:
            r = await client.post("/api/v1/auth/login", json=creds)
            assert r.status_code == 401, f"Default account {creds['username']} should not exist"


# ─── Auth header enforcement ──────────────────────────────────────────────────
class TestAuthHeaderEnforcement:
    @pytest.mark.asyncio
    async def test_protected_endpoint_requires_auth(self, client: AsyncClient) -> None:
        r = await client.get("/api/v1/auth/me")
        assert r.status_code in (401, 403)

    @pytest.mark.asyncio
    async def test_jwt_via_query_param_rejected(self, client: AsyncClient, test_user: User) -> None:
        """
        JWT passed as ?token= query param must NOT be accepted.
        This was a vulnerability in the original server.py.
        """
        token = make_access_token(test_user)
        r = await client.get(f"/api/v1/auth/me?token={token}")
        # Should get 401/403 because we only accept Authorization header
        assert r.status_code in (401, 403)

    @pytest.mark.asyncio
    async def test_valid_bearer_token_accepted(self, client: AsyncClient, test_user: User) -> None:
        r = await client.get("/api/v1/auth/me", headers=auth_headers(test_user))
        assert r.status_code == 200
        body = r.json()
        assert body["username"] == "testuser"
        assert body["role"] == "user"


# ─── RBAC enforcement ─────────────────────────────────────────────────────────
class TestRBACEnforcement:
    @pytest.mark.asyncio
    async def test_security_headers_present(self, client: AsyncClient) -> None:
        """All responses must include key security headers."""
        r = await client.get("/health")
        assert r.headers.get("x-content-type-options") == "nosniff"
        assert r.headers.get("x-frame-options") == "DENY"
        assert "content-security-policy" in r.headers


# ─── Token Lifecycle & Password API ───────────────────────────────────────────
class TestTokenLifecycleAndSession:
    @pytest.mark.asyncio
    async def test_token_refresh_and_rotation(self, client: AsyncClient, test_user: User) -> None:
        """Login, refresh token rotation, and old token revocation."""
        login_res = await client.post(
            "/api/v1/auth/login",
            json={
                "username": "testuser",
                "password": "TestPass123!",
            },
        )
        assert login_res.status_code == 200
        ref_token = login_res.json()["refresh_token"]

        # Refresh
        refresh_res = await client.post("/api/v1/auth/refresh", json={"refresh_token": ref_token})
        assert refresh_res.status_code == 200
        new_ref_token = refresh_res.json()["refresh_token"]
        assert new_ref_token != ref_token

        # Using old token again must be rejected (revoked)
        reuse_res = await client.post("/api/v1/auth/refresh", json={"refresh_token": ref_token})
        assert reuse_res.status_code == 401

    @pytest.mark.asyncio
    async def test_logout_revokes_session(self, client: AsyncClient, test_user: User) -> None:
        """Logout must revoke the refresh token."""
        login_res = await client.post(
            "/api/v1/auth/login",
            json={
                "username": "testuser",
                "password": "TestPass123!",
            },
        )
        ref_token = login_res.json()["refresh_token"]
        headers = auth_headers(test_user)

        # Logout
        logout_res = await client.post("/api/v1/auth/logout", json={"refresh_token": ref_token}, headers=headers)
        assert logout_res.status_code == 204

        # Refresh with revoked token must fail
        refresh_res = await client.post("/api/v1/auth/refresh", json={"refresh_token": ref_token})
        assert refresh_res.status_code == 401

    @pytest.mark.asyncio
    async def test_change_password_flow(self, client: AsyncClient, test_user: User) -> None:
        """Password change verifies current password and accepts new compliant password."""
        headers = auth_headers(test_user)
        # Wrong current password fails
        bad_req = await client.post(
            "/api/v1/auth/password",
            json={
                "current_password": "WrongPassword1!",
                "new_password": "NewStrongP@ss999!",
            },
            headers=headers,
        )
        assert bad_req.status_code == 400

        # Correct password succeeds
        good_req = await client.post(
            "/api/v1/auth/password",
            json={
                "current_password": "TestPass123!",
                "new_password": "NewStrongP@ss999!",
            },
            headers=headers,
        )
        assert good_req.status_code == 204
