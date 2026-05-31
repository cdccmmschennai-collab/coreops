"""Health endpoints.

- GET /health        liveness (matches openapi-v1.yaml: {"status": "ok"})
- GET /health/ready  readiness probe checking DB + Redis connectivity (ops)

The readiness probe is an operational addition for Docker/monitoring; the
liveness contract is exactly as specified in openapi-v1.yaml.
"""
from fastapi import APIRouter, Depends
from sqlalchemy import text
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.redis import get_redis

router = APIRouter(tags=["system"])


@router.get("/health")
def health() -> dict:
    return {"status": "ok"}


@router.get("/health/ready")
def ready(db: Session = Depends(get_db)) -> dict:
    checks: dict[str, str] = {}

    try:
        db.execute(text("SELECT 1"))
        checks["db"] = "ok"
    except Exception:  # noqa: BLE001 - readiness must not raise
        checks["db"] = "error"

    try:
        get_redis().ping()
        checks["redis"] = "ok"
    except Exception:  # noqa: BLE001
        checks["redis"] = "error"

    status = "ok" if all(v == "ok" for v in checks.values()) else "degraded"
    return {"status": status, "checks": checks}
