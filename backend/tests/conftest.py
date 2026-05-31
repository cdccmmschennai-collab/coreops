"""Pytest fixtures. V0 provides an HTTP client over the app; DB-backed
fixtures arrive with the first models in V1."""
import pytest
from fastapi.testclient import TestClient

from app.main import app


@pytest.fixture()
def client() -> TestClient:
    return TestClient(app)
