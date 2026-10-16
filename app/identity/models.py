"""
app/identity/models.py — Sovereign Workbench Identity Models
=============================================================
SQLAlchemy ORM models for users and sessions.
No hardcoded passwords, no default credentials.
"""

import uuid
from datetime import UTC, datetime

from sqlalchemy import Boolean, DateTime, ForeignKey, Integer, String, Text, Uuid, func
from sqlalchemy.dialects.postgresql import UUID as PG_UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base


class User(Base):
    """
    Registered workbench user.

    Roles:
      admin  — full administrative access; 2FA mandatory
      user   — standard access to their own threads and the shared knowledge base
    """

    __tablename__ = "users"

    id: Mapped[uuid.UUID] = mapped_column(
        Uuid().with_variant(PG_UUID(as_uuid=True), "postgresql"),
        primary_key=True,
        default=uuid.uuid4,
    )
    username: Mapped[str] = mapped_column(String(64), unique=True, nullable=False, index=True)
    name: Mapped[str] = mapped_column(String(128), nullable=False)
    email: Mapped[str | None] = mapped_column(String(256), unique=True, nullable=True)
    role: Mapped[str] = mapped_column(String(32), nullable=False, default="user")
    department: Mapped[str | None] = mapped_column(String(128), nullable=True)
    avatar_color: Mapped[str] = mapped_column(String(32), nullable=False, default="bg-slate-500")

    # ─── Password ─────────────────────────────────────────────
    # Stored as PBKDF2-HMAC-SHA256 with a random 16-byte hex salt: "salt$derived"
    # Never stored in plaintext.
    password_hash: Mapped[str] = mapped_column(String(256), nullable=False)

    # ─── TOTP / 2FA ───────────────────────────────────────────
    totp_secret: Mapped[str | None] = mapped_column(String(128), nullable=True)
    totp_enabled: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    backup_codes: Mapped[str | None] = mapped_column(Text, nullable=True)
    # backup_codes stored as JSON: ["hash1", "hash2", ...] (hashed, one-time use)

    # ─── Account state ────────────────────────────────────────
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    failed_login_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    locked_until: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    must_change_password: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)

    # ─── Timestamps ───────────────────────────────────────────
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now(), onupdate=func.now()
    )

    # ─── Relationships ────────────────────────────────────────
    sessions: Mapped[list["Session"]] = relationship("Session", back_populates="user", cascade="all, delete-orphan")

    def __repr__(self) -> str:
        return f"<User id={self.id} username={self.username!r} role={self.role!r}>"


class Session(Base):
    """
    Active user session (JWT refresh token tracker).
    Allows server-side token revocation.
    """

    __tablename__ = "sessions"

    id: Mapped[uuid.UUID] = mapped_column(
        Uuid().with_variant(PG_UUID(as_uuid=True), "postgresql"),
        primary_key=True,
        default=uuid.uuid4,
    )
    user_id: Mapped[uuid.UUID] = mapped_column(
        Uuid().with_variant(PG_UUID(as_uuid=True), "postgresql"),
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    # SHA-256 hash of the refresh token — never store raw tokens
    token_hash: Mapped[str] = mapped_column(String(64), unique=True, nullable=False, index=True)
    ip_address: Mapped[str | None] = mapped_column(String(45), nullable=True)
    user_agent: Mapped[str | None] = mapped_column(String(512), nullable=True)

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now())
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    user: Mapped["User"] = relationship("User", back_populates="sessions")

    @property
    def is_valid(self) -> bool:
        """Returns True if the session is not revoked and not expired."""
        now = datetime.now(UTC)
        return self.revoked_at is None and self.expires_at > now

    def __repr__(self) -> str:
        return f"<Session id={self.id} user_id={self.user_id} revoked={self.revoked_at is not None}>"
