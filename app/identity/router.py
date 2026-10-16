"""
app/identity/router.py — Authentication API endpoints.

Endpoints:
  POST /auth/login          — password auth; returns tokens or 2FA challenge
  POST /auth/2fa/verify     — complete 2FA; returns full tokens
  POST /auth/refresh        — rotate refresh token
  POST /auth/logout         — revoke current session
  GET  /auth/me             — current user profile
  POST /auth/password       — change own password
  GET  /auth/2fa/setup      — get TOTP provisioning URI + QR code
  POST /auth/2fa/enable     — confirm and enable TOTP
  POST /auth/2fa/disable    — disable TOTP (admin or self)
"""

import base64
import io
import logging
import uuid
from typing import Annotated

import pyotp
import qrcode
from fastapi import APIRouter, Depends, HTTPException, Request, status
from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.audit.models import AuditEventType
from app.audit.service import emit_event
from app.config import get_settings
from app.database import get_db
from app.identity.dependencies import get_current_user
from app.identity.models import User
from app.identity.schemas import (
    ChangePasswordRequest,
    LoginRequest,
    RefreshRequest,
    TokenResponse,
    TOTPSetupResponse,
    TOTPVerifyRequest,
    TwoFactorRequest,
    UserProfile,
)
from app.identity.service import (
    authenticate,
    create_session,
    create_temp_2fa_token,
    decode_token,
    hash_password,
    hash_refresh_token,
    is_session_valid,
    revoke_session,
    verify_password,
)

logger = logging.getLogger("sovereign.auth")
settings = get_settings()
router = APIRouter(prefix="/auth", tags=["auth"])


def _client_ip(request: Request) -> str:
    xff = request.headers.get("X-Forwarded-For")
    if xff:
        return xff.split(",")[0].strip()
    return request.client.host if request.client else "unknown"


# ─── POST /auth/login ─────────────────────────────────────────────────────────
@router.post("/login", response_model=TokenResponse)
async def login(
    body: LoginRequest,
    request: Request,
    db: Annotated[AsyncSession, Depends(get_db)],
) -> TokenResponse:
    """
    Authenticate with username + password.
    If 2FA is enabled, returns requires_2fa=True and a short-lived temp_token.
    Otherwise returns full access + refresh tokens.
    """
    ip = _client_ip(request)
    ua = request.headers.get("User-Agent", "")

    user = await authenticate(db, body.username, body.password, ip_address=ip, user_agent=ua)
    if user is None:
        # authenticate() already emitted LOGIN_FAILURE
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid credentials.")

    if user.totp_enabled:
        temp = create_temp_2fa_token(str(user.id), user.role)
        return TokenResponse(
            access_token="",
            refresh_token="",
            requires_2fa=True,
            temp_token=temp,
        )

    access, refresh = await create_session(db, user, ip_address=ip, user_agent=ua)
    await emit_event(
        db,
        AuditEventType.LOGIN_SUCCESS,
        user_id=str(user.id),
        ip_address=ip,
        user_agent=ua,
        summary=f"User '{user.username}' logged in (no 2FA).",
    )
    return TokenResponse(access_token=access, refresh_token=refresh)


# ─── POST /auth/2fa/verify ────────────────────────────────────────────────────
@router.post("/2fa/verify", response_model=TokenResponse)
async def verify_2fa(
    body: TwoFactorRequest,
    request: Request,
    db: Annotated[AsyncSession, Depends(get_db)],
) -> TokenResponse:
    """Complete the TOTP 2FA challenge after successful password auth."""
    ip = _client_ip(request)
    ua = request.headers.get("User-Agent", "")

    payload = decode_token(body.temp_token)
    if payload is None or payload.get("type") != "2fa_challenge":
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid or expired 2FA token.")

    try:
        user_uuid = uuid.UUID(payload.get("sub", ""))
    except (ValueError, TypeError):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid user identifier.")

    result = await db.execute(select(User).where(User.id == user_uuid))
    user = result.scalar_one_or_none()
    if user is None or not user.totp_enabled or not user.totp_secret:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="2FA not configured for this account.")

    totp = pyotp.TOTP(user.totp_secret)
    if not totp.verify(body.totp_code, valid_window=1):
        await emit_event(
            db,
            AuditEventType.LOGIN_2FA_FAILURE,
            user_id=str(user.id),
            ip_address=ip,
            outcome="failure",
            summary=f"TOTP verification failed for user '{user.username}'.",
        )
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid TOTP code.")

    access, refresh = await create_session(db, user, ip_address=ip, user_agent=ua)
    await emit_event(
        db,
        AuditEventType.LOGIN_2FA_SUCCESS,
        user_id=str(user.id),
        ip_address=ip,
        user_agent=ua,
        summary=f"User '{user.username}' completed 2FA login.",
    )
    return TokenResponse(access_token=access, refresh_token=refresh)


# ─── POST /auth/refresh ───────────────────────────────────────────────────────
@router.post("/refresh", response_model=TokenResponse)
async def refresh_token(
    body: RefreshRequest,
    request: Request,
    db: Annotated[AsyncSession, Depends(get_db)],
) -> TokenResponse:
    """Rotate a refresh token. The old refresh token is revoked immediately."""
    ip = _client_ip(request)
    ua = request.headers.get("User-Agent", "")

    payload = decode_token(body.refresh_token)
    if payload is None or payload.get("type") != "refresh":
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid refresh token.")

    old_hash = hash_refresh_token(body.refresh_token)
    if not await is_session_valid(db, old_hash):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Session expired or revoked.")

    await revoke_session(db, old_hash)

    try:
        user_uuid = uuid.UUID(payload.get("sub", ""))
    except (ValueError, TypeError):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid user identifier.")

    result = await db.execute(select(User).where(User.id == user_uuid))
    user = result.scalar_one_or_none()
    if user is None or not user.is_active:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Account not found or deactivated.")

    access, new_refresh = await create_session(db, user, ip_address=ip, user_agent=ua)
    await emit_event(
        db,
        AuditEventType.TOKEN_REFRESH,
        user_id=str(user.id),
        ip_address=ip,
        summary=f"Token refreshed for '{user.username}'.",
    )
    return TokenResponse(access_token=access, refresh_token=new_refresh)


# ─── POST /auth/logout ────────────────────────────────────────────────────────
@router.post("/logout", status_code=status.HTTP_204_NO_CONTENT)
async def logout(
    body: RefreshRequest,
    request: Request,
    current_user: Annotated[User, Depends(get_current_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> None:
    """Revoke the current session's refresh token."""
    token_hash = hash_refresh_token(body.refresh_token)
    await revoke_session(db, token_hash)
    await emit_event(
        db,
        AuditEventType.LOGOUT,
        user_id=str(current_user.id),
        ip_address=_client_ip(request),
        summary=f"User '{current_user.username}' logged out.",
    )


# ─── GET /auth/me ─────────────────────────────────────────────────────────────
@router.get("/me", response_model=UserProfile)
async def get_me(current_user: Annotated[User, Depends(get_current_user)]) -> User:
    return current_user


# ─── POST /auth/password ──────────────────────────────────────────────────────
@router.post("/password", status_code=status.HTTP_204_NO_CONTENT)
async def change_password(
    body: ChangePasswordRequest,
    request: Request,
    current_user: Annotated[User, Depends(get_current_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> None:
    """Change own password. Requires current password verification."""
    if not verify_password(body.current_password, current_user.password_hash):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Current password is incorrect.")
    new_hash = hash_password(body.new_password)
    await db.execute(
        update(User).where(User.id == current_user.id).values(password_hash=new_hash, must_change_password=False)
    )
    await emit_event(
        db,
        AuditEventType.PASSWORD_CHANGED,
        user_id=str(current_user.id),
        ip_address=_client_ip(request),
        summary=f"Password changed for user '{current_user.username}'.",
    )


# ─── GET /auth/2fa/setup ──────────────────────────────────────────────────────
@router.get("/2fa/setup", response_model=TOTPSetupResponse)
async def totp_setup(
    current_user: Annotated[User, Depends(get_current_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> TOTPSetupResponse:
    """Generate a new TOTP secret and return QR code. Does not enable 2FA yet."""
    secret = pyotp.random_base32()
    totp = pyotp.TOTP(secret)
    uri = totp.provisioning_uri(name=current_user.username, issuer_name="Sovereign Workbench")

    # Generate QR code as base64 PNG
    img = qrcode.make(uri)
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    b64 = base64.b64encode(buf.getvalue()).decode("utf-8")

    # Store the secret (not yet enabled)
    await db.execute(update(User).where(User.id == current_user.id).values(totp_secret=secret))
    return TOTPSetupResponse(
        provisioning_uri=uri,
        qr_code_base64=f"data:image/png;base64,{b64}",
    )


# ─── POST /auth/2fa/enable ────────────────────────────────────────────────────
@router.post("/2fa/enable", status_code=status.HTTP_204_NO_CONTENT)
async def totp_enable(
    body: TOTPVerifyRequest,
    request: Request,
    current_user: Annotated[User, Depends(get_current_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> None:
    """Verify TOTP code against stored secret and enable 2FA."""
    if not current_user.totp_secret:
        raise HTTPException(status_code=400, detail="Call /auth/2fa/setup first.")
    totp = pyotp.TOTP(current_user.totp_secret)
    if not totp.verify(body.totp_code, valid_window=1):
        raise HTTPException(status_code=400, detail="Invalid TOTP code.")
    await db.execute(update(User).where(User.id == current_user.id).values(totp_enabled=True))
    await emit_event(
        db,
        AuditEventType.TOTP_ENROLLED,
        user_id=str(current_user.id),
        ip_address=_client_ip(request),
        summary=f"2FA enabled for '{current_user.username}'.",
    )


# ─── POST /auth/2fa/disable ───────────────────────────────────────────────────
@router.post("/2fa/disable", status_code=status.HTTP_204_NO_CONTENT)
async def totp_disable(
    body: TOTPVerifyRequest,
    request: Request,
    current_user: Annotated[User, Depends(get_current_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> None:
    """Disable 2FA. Requires a valid TOTP code to prevent accidental lockout."""
    if not current_user.totp_enabled or not current_user.totp_secret:
        raise HTTPException(status_code=400, detail="2FA is not currently enabled.")
    # Admin accounts cannot disable 2FA
    if current_user.role == "admin":
        raise HTTPException(status_code=403, detail="2FA cannot be disabled for admin accounts.")
    totp = pyotp.TOTP(current_user.totp_secret)
    if not totp.verify(body.totp_code, valid_window=1):
        raise HTTPException(status_code=400, detail="Invalid TOTP code.")
    await db.execute(update(User).where(User.id == current_user.id).values(totp_enabled=False, totp_secret=None))
    await emit_event(
        db,
        AuditEventType.TOTP_DISABLED,
        user_id=str(current_user.id),
        ip_address=_client_ip(request),
        summary=f"2FA disabled for '{current_user.username}'.",
    )
