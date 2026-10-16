"""
tests/test_identity/test_rbac.py
=================================
Tests for Role-Based Access Control and authorization dependencies.

Verifies:
  - require_role dependency allows users with matching role
  - require_role dependency forbids users without matching role (403)
  - get_current_user_optional returns user when token present, None when absent
  - Password strength validation in ChangePasswordRequest
"""

from collections.abc import AsyncGenerator

import pytest
import pytest_asyncio
from app.database import get_db
from app.identity.dependencies import get_current_user_optional, require_role
from app.identity.models import User
from app.identity.schemas import ChangePasswordRequest
from fastapi import Depends, FastAPI
from httpx import ASGITransport, AsyncClient
from pydantic import ValidationError
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from tests.conftest import auth_headers

# Create a mini test app exercising require_role
_rbac_test_app = FastAPI()


@_rbac_test_app.get("/admin-only", dependencies=[Depends(require_role("admin"))])
async def admin_endpoint() -> dict[str, str]:
    return {"message": "admin granted"}


@_rbac_test_app.get("/user-or-admin", dependencies=[Depends(require_role("admin", "user"))])
async def multi_role_endpoint() -> dict[str, str]:
    return {"message": "access granted"}


@_rbac_test_app.get("/optional-auth")
async def optional_endpoint(user: User | None = Depends(get_current_user_optional)) -> dict[str, str]:
    if user:
        return {"user": user.username}
    return {"user": "anonymous"}


@pytest_asyncio.fixture
async def rbac_client(test_engine) -> AsyncGenerator[AsyncClient, None]:
    """Test client for _rbac_test_app with test_engine DB wired in."""
    session_factory = async_sessionmaker(test_engine, expire_on_commit=False)

    async def override_get_db() -> AsyncGenerator[AsyncSession, None]:
        async with session_factory() as session:
            try:
                yield session
                await session.commit()
            except Exception:
                await session.rollback()
                raise

    _rbac_test_app.dependency_overrides[get_db] = override_get_db
    async with AsyncClient(
        transport=ASGITransport(app=_rbac_test_app),
        base_url="http://test",
    ) as ac:
        yield ac
    _rbac_test_app.dependency_overrides.clear()


class TestRBACDependencies:
    @pytest.mark.asyncio
    async def test_admin_can_access_admin_endpoint(self, rbac_client: AsyncClient, admin_user: User) -> None:
        """Admin user must be allowed on admin endpoints."""
        r = await rbac_client.get("/admin-only", headers=auth_headers(admin_user))
        assert r.status_code == 200
        assert r.json() == {"message": "admin granted"}

    @pytest.mark.asyncio
    async def test_regular_user_forbidden_on_admin_endpoint(self, rbac_client: AsyncClient, test_user: User) -> None:
        """Regular user must receive 403 on admin-only endpoints."""
        r = await rbac_client.get("/admin-only", headers=auth_headers(test_user))
        assert r.status_code == 403
        assert "Requires role: admin" in r.json()["detail"]

    @pytest.mark.asyncio
    async def test_multi_role_access(self, rbac_client: AsyncClient, test_user: User, admin_user: User) -> None:
        """Both user and admin can access endpoints permitting either role."""
        r1 = await rbac_client.get("/user-or-admin", headers=auth_headers(test_user))
        assert r1.status_code == 200

        r2 = await rbac_client.get("/user-or-admin", headers=auth_headers(admin_user))
        assert r2.status_code == 200

    @pytest.mark.asyncio
    async def test_optional_auth_without_token(self, rbac_client: AsyncClient) -> None:
        """Unauthenticated requests to optional endpoint succeed as anonymous."""
        r = await rbac_client.get("/optional-auth")
        assert r.status_code == 200
        assert r.json() == {"user": "anonymous"}

    @pytest.mark.asyncio
    async def test_optional_auth_with_token(self, rbac_client: AsyncClient, test_user: User) -> None:
        """Authenticated requests to optional endpoint return username."""
        r = await rbac_client.get("/optional-auth", headers=auth_headers(test_user))
        assert r.status_code == 200
        assert r.json() == {"user": "testuser"}


class TestPasswordPolicySchema:
    def test_strong_password_accepted(self) -> None:
        req = ChangePasswordRequest(
            current_password="oldPassword123!",
            new_password="NewStrongP@ssw0rd99",
        )
        assert req.new_password == "NewStrongP@ssw0rd99"

    def test_missing_uppercase_rejected(self) -> None:
        with pytest.raises(ValidationError, match="uppercase"):
            ChangePasswordRequest(
                current_password="old",
                new_password="lowercaseonly123!",
            )

    def test_missing_digit_rejected(self) -> None:
        with pytest.raises(ValidationError, match="digit"):
            ChangePasswordRequest(
                current_password="old",
                new_password="NoDigitsHereAtAll!",
            )

    def test_missing_special_char_rejected(self) -> None:
        with pytest.raises(ValidationError, match="special character"):
            ChangePasswordRequest(
                current_password="old",
                new_password="NoSpecialChar9999",
            )
