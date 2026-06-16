"""ActivityMaster service — admin CRUD (Activity + Sub-Activity) + benchmark calc.

RBAC for mutations is enforced in the router (require_role("project_manager")),
mirroring activity_types. This module just enforces the data-shape rules that
don't belong in the router: parent/level consistency, NUMERIC requiring a value,
and that benchmark_* fields are never set on a level='activity' row.
"""
import uuid
from datetime import date
from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session, aliased

from app.modules.activity_master.models import (
    LEVEL_ACTIVITY,
    LEVEL_SUB_ACTIVITY,
    ActivityMaster,
)
from app.modules.activity_master.schemas import (
    ActivityCreate,
    ActivityMasterUpdate,
    SubActivityCreate,
)
from app.shared.errors import AppError

_BENCHMARK_FIELDS = (
    "benchmark_type", "benchmark_value", "benchmark_period_days",
    "benchmark_unit_note", "benchmark_remarks", "relevant_count_field",
)


def compute_benchmark(
    benchmark_type: str | None,
    benchmark_value: Decimal | float | None,
    actual_value: int | None,
) -> tuple[Decimal | None, Decimal | None]:
    """Returns (deficit, productivity_pct). NUMERIC only — TASK_BASED and no-
    benchmark rows never get a deficit/productivity calculation, by design.

    `actual_value` is whichever of the work report task's existing
    tags_count/docs_count/bom_count/spares_count the sub-activity's
    relevant_count_field points to — there's no separate "actual count" entry,
    by design (callers must not enter the same production number twice)."""
    if benchmark_type != "NUMERIC" or benchmark_value is None:
        return None, None
    value = Decimal(str(benchmark_value))
    if value == 0:
        return None, None
    actual = Decimal(actual_value or 0)
    deficit = max(Decimal("0"), value - actual)
    productivity_pct = (actual / value) * 100
    return deficit, productivity_pct


def compute_overdue(
    due_date: date | None, is_completed: bool, today: date | None = None,
) -> tuple[bool, int]:
    """Returns (is_overdue, days_overdue) for a TASK_BASED row. Computed
    fresh on every call (never stored) so it's always relative to the
    current date rather than stale from whenever it was last checked.

    A completed task, or one with no due_date at all (no benchmark tracked),
    is never overdue."""
    if is_completed or due_date is None:
        return False, 0
    today = today or date.today()
    if today <= due_date:
        return False, 0
    return True, (today - due_date).days


def _fetch(db: Session, activity_master_id: uuid.UUID) -> ActivityMaster:
    row = db.get(ActivityMaster, activity_master_id)
    if row is None:
        raise AppError("not_found", "Activity not found.", 404)
    return row


def get_activity_master(db: Session, activity_master_id: uuid.UUID) -> ActivityMaster:
    return _fetch(db, activity_master_id)


def list_activities(db: Session, *, active_only: bool = True) -> list[ActivityMaster]:
    stmt = select(ActivityMaster).where(ActivityMaster.level == LEVEL_ACTIVITY)
    if active_only:
        stmt = stmt.where(ActivityMaster.is_active.is_(True))
    stmt = stmt.order_by(ActivityMaster.sort_order, ActivityMaster.name)
    return list(db.execute(stmt).scalars().all())


def list_sub_activities(
    db: Session, activity_id: uuid.UUID, *, active_only: bool = True
) -> list[ActivityMaster]:
    _assert_is_activity(db, activity_id)
    stmt = select(ActivityMaster).where(ActivityMaster.parent_id == activity_id)
    if active_only:
        stmt = stmt.where(ActivityMaster.is_active.is_(True))
    stmt = stmt.order_by(ActivityMaster.sort_order, ActivityMaster.name)
    return list(db.execute(stmt).scalars().all())


def list_all_sub_activities_flat(db: Session, *, active_only: bool = True) -> list[dict]:
    """Every leaf row across every Activity, joined to the parent's name — the
    shape the work-report cascading select ultimately needs."""
    Parent = aliased(ActivityMaster)
    stmt = (
        select(ActivityMaster, Parent.name)
        .join(Parent, ActivityMaster.parent_id == Parent.id)
        .where(ActivityMaster.level == LEVEL_SUB_ACTIVITY)
    )
    if active_only:
        stmt = stmt.where(ActivityMaster.is_active.is_(True), Parent.is_active.is_(True))
    stmt = stmt.order_by(Parent.sort_order, Parent.name, ActivityMaster.sort_order, ActivityMaster.name)
    rows = db.execute(stmt).all()
    return [
        {
            "id": sub.id,
            "activity_id": sub.parent_id,
            "activity_name": parent_name,
            "name": sub.name,
            "benchmark_type": sub.benchmark_type,
            "benchmark_value": sub.benchmark_value,
            "benchmark_period_days": sub.benchmark_period_days,
            "relevant_count_field": sub.relevant_count_field,
            "is_active": sub.is_active,
        }
        for sub, parent_name in rows
    ]


def _assert_is_activity(db: Session, activity_id: uuid.UUID) -> ActivityMaster:
    activity = _fetch(db, activity_id)
    if activity.level != LEVEL_ACTIVITY:
        raise AppError("validation_error", "Not a top-level Activity.", 422)
    return activity


def create_activity(
    db: Session, data: ActivityCreate, *, created_by: uuid.UUID | None = None
) -> ActivityMaster:
    row = ActivityMaster(
        parent_id=None,
        level=LEVEL_ACTIVITY,
        code=data.code,
        name=data.name,
        sort_order=data.sort_order,
        is_active=data.is_active,
        created_by=created_by,
    )
    db.add(row)
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        raise AppError("conflict", "An active activity with this code already exists.", 409)
    db.refresh(row)
    return row


def create_sub_activity(
    db: Session,
    activity_id: uuid.UUID,
    data: SubActivityCreate,
    *,
    created_by: uuid.UUID | None = None,
) -> ActivityMaster:
    _assert_is_activity(db, activity_id)
    row = ActivityMaster(
        parent_id=activity_id,
        level=LEVEL_SUB_ACTIVITY,
        code=data.code,
        name=data.name,
        benchmark_type=data.benchmark_type,
        benchmark_value=data.benchmark_value,
        benchmark_period_days=data.benchmark_period_days,
        benchmark_unit_note=data.benchmark_unit_note,
        benchmark_remarks=data.benchmark_remarks,
        relevant_count_field=data.relevant_count_field,
        sort_order=data.sort_order,
        is_active=data.is_active,
        created_by=created_by,
    )
    db.add(row)
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        raise AppError("conflict", "An active sub-activity with this code already exists.", 409)
    db.refresh(row)
    return row


def update_activity_master(
    db: Session, activity_master_id: uuid.UUID, data: ActivityMasterUpdate
) -> ActivityMaster:
    row = _fetch(db, activity_master_id)
    fields = data.model_dump(exclude_unset=True)

    if row.level == LEVEL_ACTIVITY and any(f in fields for f in _BENCHMARK_FIELDS):
        raise AppError(
            "validation_error", "Benchmarks only apply to sub-activities, not activities.", 422
        )

    new_type = fields.get("benchmark_type", row.benchmark_type)
    new_value = fields.get("benchmark_value", row.benchmark_value)
    new_count_field = fields.get("relevant_count_field", row.relevant_count_field)
    if new_type == "NUMERIC":
        if new_value is None:
            raise AppError("validation_error", "benchmark_value is required when benchmark_type is NUMERIC.", 422)
        if new_count_field is None:
            raise AppError(
                "validation_error",
                "relevant_count_field is required when benchmark_type is NUMERIC "
                "(it's the benchmark's actual-value source).",
                422,
            )

    for key, value in fields.items():
        setattr(row, key, value)
    db.add(row)
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        raise AppError("conflict", "An active activity with this code already exists.", 409)
    db.refresh(row)
    return row


def deactivate_activity_master(db: Session, activity_master_id: uuid.UUID) -> ActivityMaster:
    """Soft-deactivate. Does not cascade to children — an Activity's
    Sub-Activities must be deactivated explicitly, one at a time (Phase 1
    keeps this simple/explicit rather than guessing intent)."""
    row = _fetch(db, activity_master_id)
    row.is_active = False
    db.add(row)
    db.commit()
    db.refresh(row)
    return row
