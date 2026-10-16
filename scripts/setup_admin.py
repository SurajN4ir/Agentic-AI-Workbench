"""
scripts/setup_admin.py — Interactive first-run admin account setup.

Run once after Alembic migrations:
    python scripts/setup_admin.py

Creates the first admin account interactively.
NO default accounts are created automatically — this script is the
only way to bootstrap the system with proper credentials.
"""

import asyncio
import getpass
import os
import re
import sys

# Ensure project root is on path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import uuid

from app.config import get_settings
from app.database import AsyncSessionLocal
from app.identity.models import User
from app.identity.service import hash_password
from sqlalchemy import select

PASSWORD_POLICY = re.compile(r"^(?=.*[a-z])(?=.*[A-Z])(?=.*\d)(?=.*[!@#$%^&*()\-_=+\[\]{}|;:,.<>?]).{12,}$")


def prompt_password(label: str) -> str:
    while True:
        pw = getpass.getpass(f"{label}: ")
        if not PASSWORD_POLICY.match(pw):
            print(
                "Password must be ≥12 characters with uppercase, lowercase, digit, "
                "and a special character (!@#$%^&*()-_=+[]{}|;:,.<>?). Try again."
            )
            continue
        confirm = getpass.getpass("Confirm password: ")
        if pw != confirm:
            print("Passwords do not match. Try again.")
            continue
        return pw


async def main() -> None:
    # Validate environment settings on startup
    _ = get_settings()
    print("\n=== Sovereign Workbench — First-Run Admin Setup ===\n")
    print("This script creates the initial admin account.")
    print("Run it once after: alembic upgrade head\n")

    username = input("Admin username (e.g. sysadmin): ").strip()
    if not username or len(username) > 64:
        print("Invalid username.")
        sys.exit(1)

    name = input("Display name (e.g. System Administrator): ").strip()
    if not name:
        name = username

    email = input("Email (optional, press Enter to skip): ").strip() or None
    department = input("Department (optional): ").strip() or None
    password = prompt_password("Password")

    async with AsyncSessionLocal() as db:
        existing = await db.execute(select(User).where(User.username == username))
        if existing.scalar_one_or_none():
            print(f"\nUser '{username}' already exists. Aborting.")
            sys.exit(1)

        user = User(
            id=uuid.uuid4(),
            username=username,
            name=name,
            email=email,
            role="admin",
            department=department,
            avatar_color="bg-blue-600",
            password_hash=hash_password(password),
            totp_enabled=False,
            must_change_password=False,
        )
        db.add(user)
        await db.commit()

    print(f"\n✓ Admin account '{username}' created successfully.")
    print("  Next step: run the application and enable 2FA via /auth/2fa/setup")
    print("  2FA is strongly recommended for admin accounts.\n")


if __name__ == "__main__":
    asyncio.run(main())
