"""Idempotent first-admin bootstrap.

Reads FIRST_ADMIN_EMAIL / FIRST_ADMIN_PASSWORD from the environment and creates
an admin user if that email does not already exist. Safe to re-run.

Usage (inside the backend container or a venv):
    python -m scripts.seed_admin
"""
import os
import sys

from sqlalchemy import select

from app.core.database import SessionLocal
from app.core.security import hash_password
from app.modules.users.models import User, UserRole


def main() -> int:
    email = os.environ.get("FIRST_ADMIN_EMAIL")
    password = os.environ.get("FIRST_ADMIN_PASSWORD")
    if not email or not password:
        print("ERROR: FIRST_ADMIN_EMAIL and FIRST_ADMIN_PASSWORD must be set.")
        return 1

    db = SessionLocal()
    try:
        existing = db.execute(
            select(User).where(User.email == email, User.deleted_at.is_(None))
        ).scalar_one_or_none()
        if existing is not None:
            print(f"Admin already exists: {email} (no change).")
            return 0

        db.add(
            User(
                email=email,
                password_hash=hash_password(password),
                role=UserRole.admin,
            )
        )
        db.commit()
        print(f"Created admin user: {email}")
        return 0
    finally:
        db.close()


if __name__ == "__main__":
    sys.exit(main())
