"""Biometric endpoints.

Two routers with deliberately different authentication:

  router        POST /integrations/easytime/punches/batch
                Machine-to-machine. Authenticated by the office connector's
                shared secret in X-CoreOps-Connector-Token - never a user JWT.

  admin_router  /biometric/mappings, /biometric/sync-batches
                Ordinary project_manager endpoints for operations: create the
                external-code -> employee mappings, and read what each
                ingestion attempt did. Backend only; Phase 2 ships no frontend.

There is no endpoint here that reads, writes or derives attendance. Punches go
in; nothing comes out that any existing module consumes.
"""
import uuid

from fastapi import APIRouter, Depends, Query, status
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.deps import require_role
from app.modules.biometric import service
from app.modules.biometric.constants import BATCH_STATUSES, PROVIDER_EASYTIME
from app.modules.biometric.dependencies import ConnectorIdentity, require_connector
from app.modules.biometric.schemas import (
    EmployeeMappingCreate,
    EmployeeMappingOut,
    EmployeeMappingPage,
    PunchBatchIn,
    PunchBatchResult,
    SyncBatchOut,
    SyncBatchPage,
)
from app.modules.users.models import User
from app.shared.errors import AppError

router = APIRouter(prefix="/integrations/easytime", tags=["biometric-ingestion"])
admin_router = APIRouter(prefix="/biometric", tags=["biometric"])

require_manager = require_role("project_manager")


@router.post(
    "/punches/batch",
    response_model=PunchBatchResult,
    status_code=status.HTTP_200_OK,
)
def ingest_punch_batch(
    payload: PunchBatchIn,
    _connector: ConnectorIdentity = Depends(require_connector),
    db: Session = Depends(get_db),
) -> PunchBatchResult:
    """Ingest one batch of raw punches. Idempotent.

    200 (not 201) because a retry of an identical payload is a normal, expected
    outcome that creates nothing: the connector re-fetches an overlap window
    every run and relies on this endpoint absorbing what it has already sent.
    """
    if payload.provider != PROVIDER_EASYTIME:
        # The provider is in the path as well as the body; disagreement means a
        # misconfigured connector, not a batch worth storing.
        raise AppError(
            "validation_error",
            f"This endpoint accepts provider '{PROVIDER_EASYTIME}' only.",
            422,
        )
    return service.ingest_batch(db, payload=payload)


@admin_router.get("/mappings", response_model=EmployeeMappingPage)
def list_employee_mappings(
    provider: str | None = Query(default=None),
    is_active: bool | None = Query(default=None),
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
    _: User = Depends(require_manager),
    db: Session = Depends(get_db),
) -> EmployeeMappingPage:
    items, total = service.list_mappings(
        db, provider=provider, is_active=is_active, limit=limit, offset=offset
    )
    return EmployeeMappingPage(items=items, total=total, limit=limit, offset=offset)


@admin_router.post(
    "/mappings", response_model=EmployeeMappingOut, status_code=status.HTTP_201_CREATED
)
def create_employee_mapping(
    body: EmployeeMappingCreate,
    current: User = Depends(require_manager),
    db: Session = Depends(get_db),
) -> EmployeeMappingOut:
    row = service.create_mapping(
        db,
        actor=current,
        provider=body.provider,
        external_employee_code=body.external_employee_code,
        employee_id=body.employee_id,
    )
    return EmployeeMappingOut.model_validate(row)


@admin_router.delete("/mappings/{mapping_id}", response_model=EmployeeMappingOut)
def deactivate_employee_mapping(
    mapping_id: uuid.UUID,
    current: User = Depends(require_manager),
    db: Session = Depends(get_db),
) -> EmployeeMappingOut:
    row = service.deactivate_mapping(db, actor=current, mapping_id=mapping_id)
    return EmployeeMappingOut.model_validate(row)


@admin_router.get("/sync-batches", response_model=SyncBatchPage)
def list_sync_batches(
    provider: str | None = Query(default=None),
    batch_status: str | None = Query(default=None, alias="status"),
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
    _: User = Depends(require_manager),
    db: Session = Depends(get_db),
) -> SyncBatchPage:
    if batch_status is not None and batch_status not in BATCH_STATUSES:
        raise AppError(
            "validation_error",
            f"status must be one of {sorted(BATCH_STATUSES)}.",
            422,
        )
    items, total = service.list_sync_batches(
        db, provider=provider, status=batch_status, limit=limit, offset=offset
    )
    return SyncBatchPage(
        items=[SyncBatchOut.model_validate(b) for b in items],
        total=total,
        limit=limit,
        offset=offset,
    )
