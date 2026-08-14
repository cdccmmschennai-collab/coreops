"""Biometric endpoints.

Two routers with deliberately different authentication:

  router        POST /integrations/easytime/punches/batch
                Machine-to-machine. Authenticated by the office connector's
                shared secret in X-CoreOps-Connector-Token - never a user JWT.

  admin_router  /biometric/mappings, /biometric/external-codes,
                /biometric/sync-batches
                Ordinary project_manager endpoints for operations: review the
                external codes the devices actually reported, create the
                external-code -> employee mappings, and read what each
                ingestion attempt did.

No endpoint here writes attendance. `GET /biometric/daily-summary` (Phase 6, with
Phase 7's duration and classification layered on) is read-only observation: the
first and last punch of an attendance day, how long that spans, and whether the
day is objectively settled - which the calendar shows beside the official record.

Nothing here pairs punches into multiple sessions, infers a device IN/OUT state,
or touches `attendance_records`. The classification never concludes half_day,
permission, leave or absent: biometric evidence carries no cause. See
`classification.py`.
"""
import uuid
from datetime import date, datetime
from zoneinfo import ZoneInfo

from fastapi import APIRouter, Depends, Query, status
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.database import get_db
from app.core.deps import get_current_user, require_role
from app.modules.biometric import service
from app.modules.biometric.constants import (
    BATCH_STATUSES,
    CLASSIFICATIONS,
    CODE_STATUS_MAPPED,
    CODE_STATUS_UNMAPPED,
    PROVIDER_EASYTIME,
    SUPPORTED_PROVIDERS,
)
from app.modules.biometric.dependencies import ConnectorIdentity, require_connector
from app.modules.biometric.schemas import (
    BulkMappingCreate,
    BulkMappingResult,
    DailyReviewPage,
    DailySummaryOut,
    DailySummaryPage,
    EmployeeMappingCreate,
    EmployeeMappingOut,
    EmployeeMappingPage,
    ExternalCodeOut,
    ExternalCodePage,
    PunchBatchIn,
    PunchBatchResult,
    SummarySchedule,
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


@admin_router.get("/external-codes", response_model=ExternalCodePage)
def list_external_codes(
    provider: str = Query(default=PROVIDER_EASYTIME),
    code_status: str | None = Query(default=None, alias="status"),
    q: str | None = Query(default=None, max_length=100),
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
    _: User = Depends(require_manager),
    db: Session = Depends(get_db),
) -> ExternalCodePage:
    """Every DISTINCT external employee code seen in the raw punch log, with
    its punch count, seen-window and current mapping.

    Read-only, and it proposes nothing: no mapping is created here, no employee
    is suggested, and nothing about a stored punch changes.
    """
    normalized_provider = provider.strip().lower()
    if normalized_provider not in SUPPORTED_PROVIDERS:
        raise AppError(
            "validation_error",
            f"provider must be one of {sorted(SUPPORTED_PROVIDERS)}.",
            422,
        )
    if code_status is not None and code_status not in (
        CODE_STATUS_MAPPED,
        CODE_STATUS_UNMAPPED,
    ):
        raise AppError(
            "validation_error",
            f"status must be '{CODE_STATUS_MAPPED}' or '{CODE_STATUS_UNMAPPED}'.",
            422,
        )

    items, total, summary = service.list_external_codes(
        db,
        provider=normalized_provider,
        status=code_status,
        q=q,
        limit=limit,
        offset=offset,
    )
    return ExternalCodePage(
        items=[ExternalCodeOut.model_validate(i) for i in items],
        total=total,
        limit=limit,
        offset=offset,
        **summary,
    )


@admin_router.get("/daily-summary", response_model=DailySummaryPage)
def list_daily_summary(
    provider: str = Query(default=PROVIDER_EASYTIME),
    employee_id: uuid.UUID | None = Query(default=None),
    date_from: date = Query(alias="from"),
    date_to: date = Query(alias="to"),
    current: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> DailySummaryPage:
    """First IN / last OUT per mapped employee per attendance day (Asia/Kolkata),
    with the worked duration and a conservative classification.

    NOT an attendance record and NOT a device-reported IN/OUT. EasyTime supplies
    no punch direction in this deployment, so the boundaries are the earliest and
    latest punch of the day after re-scan collapsing (`summary.py`), and the
    classification only ever says `present` / `incomplete` / `needs_review` /
    `no_record` - never half_day, permission, leave or absent
    (`classification.py`). Nothing is written and `attendance_records` remains the
    official source.

    Unlike the rest of this router this is NOT project_manager-only: an employee
    must be able to see their own calendar. Scoping mirrors the attendance module
    exactly - a PM sees everyone, anyone else only themselves.
    """
    normalized_provider = provider.strip().lower()
    if normalized_provider not in SUPPORTED_PROVIDERS:
        raise AppError(
            "validation_error",
            f"provider must be one of {sorted(SUPPORTED_PROVIDERS)}.",
            422,
        )

    items, schedule = service.list_daily_summary(
        db,
        actor=current,
        provider=normalized_provider,
        employee_id=employee_id,
        date_from=date_from,
        date_to=date_to,
    )
    return DailySummaryPage(
        items=[DailySummaryOut.model_validate(i) for i in items],
        total=len(items),
        provider=normalized_provider,
        date_from=date_from,
        date_to=date_to,
        schedule=SummarySchedule.model_validate(schedule) if schedule else None,
    )


@admin_router.get("/daily-review", response_model=DailyReviewPage)
def list_daily_review(
    review_date: date = Query(alias="date"),
    provider: str = Query(default=PROVIDER_EASYTIME),
    classification: str | None = Query(default=None),
    _: User = Depends(require_manager),
    db: Session = Depends(get_db),
) -> DailyReviewPage:
    """One attendance day across every in-scope employee, for PM review.

    project_manager ONLY - unlike `/daily-summary`, which an employee may call
    for their own calendar. This one returns the whole roster, so it carries the
    same authority as the rest of this admin router.

    Read-only and non-committal: it reports what the biometric evidence supports
    and which days a human still has to settle. Nothing is approved, finalized or
    written; `attendance_records` is untouched. An employee with no punches is
    reported as `no_record`, NEVER as absent - the cause could be approved leave,
    a permission, official duty or a missed punch, and none of those are knowable
    from a punch stream (Phase 9 supplies them).
    """
    normalized_provider = provider.strip().lower()
    if normalized_provider not in SUPPORTED_PROVIDERS:
        raise AppError(
            "validation_error",
            f"provider must be one of {sorted(SUPPORTED_PROVIDERS)}.",
            422,
        )
    if classification is not None and classification not in CLASSIFICATIONS:
        raise AppError(
            "validation_error",
            f"classification must be one of {sorted(CLASSIFICATIONS)}.",
            422,
        )
    # A future date has no evidence and never will yet: every row would read
    # "No record", which looks like a company-wide absence rather than a date
    # that has not happened. "Today" is judged in the attendance timezone, not
    # the server's.
    today_local = datetime.now(ZoneInfo(settings.ATTENDANCE_TIMEZONE)).date()
    if review_date > today_local:
        raise AppError("validation_error", "Date must not be in the future.", 422)

    result = service.list_daily_review(
        db,
        provider=normalized_provider,
        on_date=review_date,
        classification=classification,
    )
    return DailyReviewPage.model_validate(result)


@admin_router.post("/mappings/bulk", response_model=BulkMappingResult)
def create_employee_mappings_bulk(
    body: BulkMappingCreate,
    current: User = Depends(require_manager),
    db: Session = Depends(get_db),
) -> BulkMappingResult:
    """Apply a reviewed list of mappings in one go (initial setup).

    200, not 201: the outcome is per item - some are created, some are already
    correct, some are skipped - so there is no single resource to point at.
    Every pair must be supplied explicitly by the caller.
    """
    result = service.create_mappings_bulk(
        db,
        actor=current,
        provider=body.provider,
        items=body.items,
        allow_remap=body.allow_remap,
    )
    return BulkMappingResult.model_validate(result)


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
