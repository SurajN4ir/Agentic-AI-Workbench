"""
app/identity/dependencies.py — FastAPI security dependencies.

Provides:
  - get_current_user: validates Bearer token from Authorization header ONLY
    (no query-param JWT — see audit finding S-9)
  - require_role: enforces a minimum role on an endpoint
"""

import logging
import uuid
from collections.abc import Callable
from typing import Annotated, Any

from fastapi import Depends, HTTPException, Request, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.identity.models import User
from app.identity.service import decode_token

logger = logging.getLogger("sovereign.identity")

# HTTPBearer will reject requests without an Authorization: Bearer <token> header.
# auto_error=True means it raises 403 if the header is missing.
_bearer = HTTPBearer(auto_error=True)


async def get_current_user(
    request: Request,
    credentials: Annotated[HTTPAuthorizationCredentials, Depends(_bearer)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> User:
    """
    Validate a Bearer access token and return the authenticated User.

    Rejects:
    - Missing or malformed Authorization header (403 from HTTPBearer)
    - Invalid or expired JWT signature (401)
    - Token passed via query parameter (never checked here — security fix)
    - Deactivated accounts (401)
    """
    token = credentials.credentials
    payload = decode_token(token)

    if payload is None or payload.get("type") != "access":
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or expired token.",
            headers={"WWW-Authenticate": "Bearer"},
        )

    user_id_str: str = payload.get("sub", "")
    try:
        user_uuid = uuid.UUID(user_id_str)
    except (ValueError, TypeError):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid user identifier in token.",
            headers={"WWW-Authenticate": "Bearer"},
        )

    result = await db.execute(select(User).where(User.id == user_uuid))
    user = result.scalar_one_or_none()

    if user is None or not user.is_active:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="User not found or account deactivated.",
            headers={"WWW-Authenticate": "Bearer"},
        )

    return user


async def get_current_user_optional(
    request: Request,
    db: Annotated[AsyncSession, Depends(get_db)],
) -> User | None:
    """
    Like get_current_user but returns None for unauthenticated requests.
    Only use on genuinely public endpoints where the response is the same
    regardless of authentication state.
    """
    auth = request.headers.get("Authorization", "")
    if not auth.startswith("Bearer "):
        return None
    token = auth.removeprefix("Bearer ").strip()
    payload = decode_token(token)
    if payload is None or payload.get("type") != "access":
        return None
    user_id_str = payload.get("sub", "")
    try:
        user_uuid = uuid.UUID(user_id_str)
    except (ValueError, TypeError):
        return None
    result = await db.execute(select(User).where(User.id == user_uuid))
    return result.scalar_one_or_none()


def require_role(*allowed_roles: str) -> Callable[..., Any]:
    """
    Dependency factory that enforces role-based access.

    Usage:
        @router.delete("/admin/users/{uid}", dependencies=[Depends(require_role("admin"))])
    """

    async def _check(
        current_user: Annotated[User, Depends(get_current_user)],
    ) -> User:
        if current_user.role not in allowed_roles:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"Requires role: {', '.join(allowed_roles)}.",
            )
        return current_user

    return _check
