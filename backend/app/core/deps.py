"""Shared FastAPI dependencies.

V0 exposes only the DB session dependency. Authentication dependencies
(`get_current_user`, `require_role`) are added in V1 — Authentication.
"""
from app.core.database import get_db

__all__ = ["get_db"]
