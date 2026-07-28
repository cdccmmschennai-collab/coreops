"""ENABLE_API_DOCS gates Swagger / ReDoc / openapi.json.

The docs URLs are baked into the FastAPI instance at construction time, so each
test builds a fresh app via `create_app()` with the flag pinned, rather than
reusing the module-level `app.main.app` (whose URLs reflect the developer's
local .env).
"""
import pytest
from fastapi.testclient import TestClient

from app.core.config import Settings, settings
from app.main import create_app

SWAGGER_URL = f"{settings.API_V1_PREFIX}/docs"
REDOC_URL = "/redoc"
OPENAPI_URL = f"{settings.API_V1_PREFIX}/openapi.json"


@pytest.fixture()
def docs_client():
    """Build a TestClient over an app created with ENABLE_API_DOCS pinned."""

    def _make(enabled: bool) -> TestClient:
        previous = settings.ENABLE_API_DOCS
        settings.ENABLE_API_DOCS = enabled
        try:
            return TestClient(create_app())
        finally:
            settings.ENABLE_API_DOCS = previous

    return _make


def test_secure_default_is_false():
    # The field default (not the local .env value) must fail closed.
    assert Settings.model_fields["ENABLE_API_DOCS"].default is False


def test_docs_available_when_enabled(docs_client):
    client = docs_client(True)

    swagger = client.get(SWAGGER_URL)
    assert swagger.status_code == 200
    assert "swagger-ui" in swagger.text.lower()

    redoc = client.get(REDOC_URL)
    assert redoc.status_code == 200
    assert "redoc" in redoc.text.lower()

    schema = client.get(OPENAPI_URL)
    assert schema.status_code == 200
    body = schema.json()
    assert body["info"]["title"] == "Coreops API"
    # Existing endpoint URLs are untouched by the flag.
    assert f"{settings.API_V1_PREFIX}/health" in body["paths"]


def test_docs_redoc_and_openapi_404_when_disabled(docs_client):
    client = docs_client(False)

    assert client.get(SWAGGER_URL).status_code == 404
    assert client.get(REDOC_URL).status_code == 404
    assert client.get(OPENAPI_URL).status_code == 404


@pytest.mark.parametrize("enabled", [True, False])
def test_normal_endpoints_unaffected(docs_client, enabled):
    client = docs_client(enabled)

    res = client.get(f"{settings.API_V1_PREFIX}/health")
    assert res.status_code == 200
    assert res.json() == {"status": "ok"}

    # A real (auth-guarded) route still resolves - 401, not 404, proves the
    # router prefixes are intact in both modes.
    assert client.get(f"{settings.API_V1_PREFIX}/auth/me").status_code == 401
