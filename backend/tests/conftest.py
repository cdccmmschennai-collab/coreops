"""Pytest fixtures.

Targets a dedicated `wms_test` database so tests never touch dev data. The test
DB URL is derived from DATABASE_URL and set BEFORE importing the app, so app
settings/engine and Alembic all point at the test database. Schema is created by
running the real migrations once; each test gets a clean slate (truncate + redis
flush).
"""
import os

import pytest

# --- redirect to the test database BEFORE importing the app ---------------
_base_url = os.environ.get("DATABASE_URL", "postgresql+psycopg://wms:wms@db:5432/wms")
_server, _db = _base_url.rsplit("/", 1)
_TEST_URL = f"{_server}/wms_test"
os.environ["DATABASE_URL"] = _TEST_URL
os.environ.setdefault("ENV", "local")

from fastapi.testclient import TestClient  # noqa: E402
from sqlalchemy import create_engine, text  # noqa: E402

from app.core.database import SessionLocal  # noqa: E402
from app.core.redis import get_redis  # noqa: E402
from app.core.security import hash_password  # noqa: E402
from app.main import app  # noqa: E402
from app.modules.users.models import User, UserRole  # noqa: E402


@pytest.fixture(scope="session", autouse=True)
def _prepare_database():
    # Create wms_test if absent, then apply migrations.
    admin_engine = create_engine(_base_url, isolation_level="AUTOCOMMIT")
    with admin_engine.connect() as conn:
        exists = conn.execute(
            text("SELECT 1 FROM pg_database WHERE datname = 'wms_test'")
        ).scalar()
        if not exists:
            conn.execute(text("CREATE DATABASE wms_test"))
    admin_engine.dispose()

    from alembic import command
    from alembic.config import Config

    command.upgrade(Config("alembic.ini"), "head")
    yield


@pytest.fixture(autouse=True)
def _clean_state():
    # Clean slate per test: empty users, clear redis (throttle/denylist keys).
    with SessionLocal() as db:
        db.execute(text("TRUNCATE TABLE users RESTART IDENTITY CASCADE"))
        db.commit()
    get_redis().flushdb()
    yield


@pytest.fixture()
def db():
    session = SessionLocal()
    try:
        yield session
    finally:
        session.close()


@pytest.fixture()
def client() -> TestClient:
    return TestClient(app)


# --- helpers ---------------------------------------------------------------
@pytest.fixture()
def make_user(db):
    def _make(email: str, password: str = "password123", role: UserRole = UserRole.employee,
              is_active: bool = True) -> User:
        user = User(
            email=email,
            password_hash=hash_password(password),
            role=role,
            is_active=is_active,
        )
        db.add(user)
        db.commit()
        db.refresh(user)
        return user

    return _make


@pytest.fixture()
def auth_header(client, make_user):
    def _login(email: str = "user@example.com", password: str = "password123",
               role: UserRole = UserRole.employee) -> dict:
        make_user(email, password, role)
        res = client.post("/api/v1/auth/login", json={"email": email, "password": password})
        assert res.status_code == 200, res.text
        return {"Authorization": f"Bearer {res.json()['access_token']}"}

    return _login
