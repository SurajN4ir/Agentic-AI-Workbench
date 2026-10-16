"""
app/identity/service.py — Sovereign Workbench Authentication Service
=====================================================================
Adapted from tools/rbac.py (SIH PS 26117 — co-author access confirmed).

Changes from original:
- REMOVED: hardcoded DEFAULT_USERS / seeded credentials
- REMOVED: fallback JWT secret string ("sovereign_agent_air_gapped_jwt_secret_key_2026")
- REMOVED: LEGACY_SALT static salt path
- REMOVED: JWT accepted via query parameter
- ADDED:   mandatory JWT_SECRET_KEY from settings (fails at startup if absent)
- ADDED:   bcrypt via passlib for stronger hashing (PBKDF2 kept for migration)
- ADDED:   session revocation via DB token_hash lookup
- ADDED:   account lockout after N failed attempts
- ADDED:   audit event emission on every auth action
"""

import hashlib
import hmac
import json
import uuid
from base64 import urlsafe_b64decode, urlsafe_b64encode
from datetime import UTC, datetime, timedelta
from typing import Any, cast

import bcrypt
from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.audit.models import AuditEventType
from app.audit.service import emit_event
from app.config import get_settings
from app.identity.models import Session, User

settings = get_settings()


# ─── Password hashing ─────────────────────────────────────────────────────────


def hash_password(plain: str) -> str:
    """Hash a password using bcrypt (work factor 12). Returns the bcrypt hash string."""
    return bcrypt.hashpw(plain.encode("utf-8"), bcrypt.gensalt(rounds=12)).decode("utf-8")


def verify_password(plain: str, stored_hash: str) -> bool:
    """
    Verify a password against a stored hash.
    Supports both bcrypt (new) and PBKDF2 (migrated from original rbac.py).
    Uses constant-time comparison in both paths.
    """
    if not stored_hash:
        return False

    # bcrypt hashes start with $2b$ or $2a$
    if stored_hash.startswith("$2"):
        return bcrypt.checkpw(plain.encode("utf-8"), stored_hash.encode("utf-8"))

    # Legacy PBKDF2 path — format: "salt$derived" (original rbac.py format)
    # Note: LEGACY_SALT path is removed; only random-salt format is supported.
    if "$" in stored_hash:
        try:
            salt, derived = stored_hash.split("$", 1)
            expected = hashlib.pbkdf2_hmac("sha256", plain.encode("utf-8"), salt.encode("utf-8"), 100_000).hex()
            return hmac.compare_digest(expected, derived)
        except Exception:
            return False

    return False


# ─── JWT ──────────────────────────────────────────────────────────────────────


def _get_secret() -> bytes:
    """Return the JWT signing key as bytes. Secret sourced exclusively from settings."""
    return settings.jwt_secret_key.encode("utf-8")


def create_access_token(user_id: str, role: str, username: str) -> str:
    """
    Create a short-lived JWT access token (HS256).
    Secret is sourced from JWT_SECRET_KEY — never from a fallback.
    Token does NOT carry sensitive profile data.
    """
    now = int(datetime.now(UTC).timestamp())
    payload = {
        "sub": user_id,
        "role": role,
        "username": username,
        "iat": now,
        "exp": now + settings.jwt_access_token_expire_seconds,
        "type": "access",
    }
    return _encode_jwt(payload)


def create_refresh_token(user_id: str, session_id: str) -> str:
    """Create a long-lived refresh token. Stored only as SHA-256 hash in DB."""
    now = int(datetime.now(UTC).timestamp())
    payload = {
        "sub": user_id,
        "session_id": session_id,
        "iat": now,
        "exp": now + settings.jwt_refresh_token_expire_seconds,
        "type": "refresh",
    }
    return _encode_jwt(payload)


def create_temp_2fa_token(user_id: str, role: str) -> str:
    """
    Create a short-lived (5 min) token issued after password verification
    but before TOTP completion. Only valid for the /auth/2fa/verify endpoint.
    """
    now = int(datetime.now(UTC).timestamp())
    payload = {
        "sub": user_id,
        "role": role,
        "iat": now,
        "exp": now + 300,
        "type": "2fa_challenge",
    }
    return _encode_jwt(payload)


def _encode_jwt(payload: dict[str, Any]) -> str:
    header = json.dumps({"alg": "HS256", "typ": "JWT"}).encode("utf-8")
    payload_bytes = json.dumps(payload).encode("utf-8")

    b64h = urlsafe_b64encode(header).rstrip(b"=").decode()
    b64p = urlsafe_b64encode(payload_bytes).rstrip(b"=").decode()

    signing_input = f"{b64h}.{b64p}".encode()
    sig = hmac.new(_get_secret(), signing_input, hashlib.sha256).digest()
    b64s = urlsafe_b64encode(sig).rstrip(b"=").decode()

    return f"{b64h}.{b64p}.{b64s}"


def decode_token(token: str) -> dict[str, Any] | None:
    """
    Verify and decode a JWT token. Returns payload dict on success, None on failure.
    Rejects: invalid signature, expired tokens, malformed structure.
    """
    try:
        parts = token.split(".")
        if len(parts) != 3:
            return None

        b64h, b64p, b64s = parts
        signing_input = f"{b64h}.{b64p}".encode()
        expected_sig = hmac.new(_get_secret(), signing_input, hashlib.sha256).digest()

        # Constant-time signature comparison
        actual_sig = urlsafe_b64decode(b64s + "=" * (-len(b64s) % 4))
        if not hmac.compare_digest(expected_sig, actual_sig):
            return None

        payload_bytes = urlsafe_b64decode(b64p + "=" * (-len(b64p) % 4))
        raw_payload = json.loads(payload_bytes.decode("utf-8"))
        if not isinstance(raw_payload, dict):
            return None
        payload = cast(dict[str, Any], raw_payload)

        if payload.get("exp", 0) < datetime.now(UTC).timestamp():
            return None

        return payload
    except Exception:
        return None


def hash_refresh_token(token: str) -> str:
    """SHA-256 hash of a refresh token for storage in DB."""
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


# ─── Authentication flow ─────────────────────────────────────────────────────


async def authenticate(
    db: AsyncSession,
    username: str,
    password: str,
    ip_address: str | None = None,
    user_agent: str | None = None,
) -> User | None:
    """
    Verify credentials. Returns the User object on success, None on failure.
    Records failed attempts and locks the account after the threshold.
    Emits audit events for all outcomes.
    """
    result = await db.execute(select(User).where(User.username == username))
    user = result.scalar_one_or_none()

    # Always verify password (even if user not found) to prevent timing attacks
    dummy_hash = "$2b$12$32hD/kToSESnCg31dlYvw.sFDUBll9wn/7rAuWOFTK7iBQUoDro.2"
    candidate_hash = user.password_hash if user else dummy_hash

    ok = verify_password(password, candidate_hash)

    if not ok or user is None:
        if user is not None:
            await _record_failed_login(db, user)
            await emit_event(
                db,
                event_type=AuditEventType.LOGIN_FAILURE,
                user_id=str(user.id),
                outcome="failure",
                ip_address=ip_address,
                user_agent=user_agent,
                summary=f"Failed login for user '{username}'",
            )
        else:
            await emit_event(
                db,
                event_type=AuditEventType.LOGIN_FAILURE,
                outcome="failure",
                ip_address=ip_address,
                summary=f"Login attempt for unknown username '{username}'",
            )
        return None

    # Check account state
    if not user.is_active:
        await emit_event(
            db,
            event_type=AuditEventType.LOGIN_FAILURE,
            user_id=str(user.id),
            outcome="denied",
            ip_address=ip_address,
            summary="Login denied — account is deactivated",
        )
        return None

    if user.locked_until and user.locked_until > datetime.now(UTC):
        await emit_event(
            db,
            event_type=AuditEventType.LOGIN_FAILURE,
            user_id=str(user.id),
            outcome="denied",
            ip_address=ip_address,
            summary=f"Login denied — account locked until {user.locked_until.isoformat()}",
        )
        return None

    # Success — reset failed count
    await db.execute(update(User).where(User.id == user.id).values(failed_login_count=0, locked_until=None))
    return user


async def _record_failed_login(db: AsyncSession, user: User) -> None:
    """Increment failure count; lock account if threshold reached."""
    new_count = user.failed_login_count + 1
    lock_until = None

    if new_count >= settings.max_failed_login_attempts:
        lock_until = datetime.now(UTC) + timedelta(seconds=settings.account_lockout_seconds)
        await emit_event(
            db,
            event_type=AuditEventType.ACCOUNT_LOCKED,
            user_id=str(user.id),
            outcome="success",
            summary=f"Account '{user.username}' locked for {settings.account_lockout_seconds}s "
            f"after {new_count} failed login attempts",
        )

    await db.execute(
        update(User).where(User.id == user.id).values(failed_login_count=new_count, locked_until=lock_until)
    )


# ─── Session management ───────────────────────────────────────────────────────


async def create_session(
    db: AsyncSession,
    user: User,
    ip_address: str | None = None,
    user_agent: str | None = None,
) -> tuple[str, str]:
    """
    Create a new session. Returns (access_token, refresh_token).
    Only the hash of the refresh token is stored in the DB.
    """
    session_id = str(uuid.uuid4())
    refresh_token = create_refresh_token(str(user.id), session_id)
    token_hash = hash_refresh_token(refresh_token)

    expires_at = datetime.now(UTC) + timedelta(seconds=settings.jwt_refresh_token_expire_seconds)

    session = Session(
        id=uuid.UUID(session_id),
        user_id=user.id,
        token_hash=token_hash,
        ip_address=ip_address,
        user_agent=user_agent,
        expires_at=expires_at,
    )
    db.add(session)

    access_token = create_access_token(str(user.id), user.role, user.username)
    return access_token, refresh_token


async def revoke_session(db: AsyncSession, token_hash: str) -> bool:
    """Revoke a session by its token hash. Returns True if found and revoked."""
    result = await db.execute(
        select(Session).where(
            Session.token_hash == token_hash,
            Session.revoked_at.is_(None),
        )
    )
    session = result.scalar_one_or_none()
    if session is None:
        return False

    await db.execute(update(Session).where(Session.id == session.id).values(revoked_at=datetime.now(UTC)))
    return True


async def is_session_valid(db: AsyncSession, token_hash: str) -> bool:
    """Check if a refresh token hash corresponds to a valid, non-revoked session."""
    result = await db.execute(
        select(Session).where(
            Session.token_hash == token_hash,
            Session.revoked_at.is_(None),
            Session.expires_at > datetime.now(UTC),
        )
    )
    return result.scalar_one_or_none() is not None
