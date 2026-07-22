"""Centralized activity-access domain rules (migration 0061).

ONE place owns the question "may this employee use this activity?" and the
PM-only mutations (grant / revoke / change access type). Routers and the report
write-path call into here; the rule is never re-implemented elsewhere.

The central rule for STARTING new activity work:

    activity.is_active
    AND (
        activity.access_type == COMMON
        OR an active employee_activity_access row exists for (activity, employee)
    )

Access is at the top-level Activity; sub-activities inherit their parent's
access, so every check resolves a sub-activity to its parent activity first.
All lookups are set-based / EXISTS-driven (never one query per activity) and hit
the employee_activity_access indexes.
"""
import uuid
from datetime import datetime, timezone

from sqlalchemy import and_, exists, func, select
from sqlalchemy.orm import Session, aliased

from app.core.config import settings
from app.modules.activity_master.access_models import EmployeeActivityAccess
from app.modules.activity_master.models import (
    ACCESS_TYPE_COMMON,
    ACCESS_TYPE_RESTRICTED,
    LEVEL_ACTIVITY,
    LEVEL_SUB_ACTIVITY,
    ActivityMaster,
)
from app.modules.audit.constants import AuditAction, EntityType
from app.modules.audit.service import record_audit
from app.modules.employees.models import Employee, EmployeeStatus
from app.modules.users.models import User
from app.shared.errors import AppError


def _now() -> datetime:
    return datetime.now(timezone.utc)


# ── read helpers (shared predicate) ─────────────────────────────────────────

def has_active_access_clause(activity_id_col, employee_id: uuid.UUID):
    """A correlated EXISTS clause: an active grant on `activity_id_col` for
    `employee_id`. Used to filter report-dropdown queries in-DB (no N+1)."""
    return exists(
        select(EmployeeActivityAccess.id).where(
            EmployeeActivityAccess.activity_id == activity_id_col,
            EmployeeActivityAccess.employee_id == employee_id,
            EmployeeActivityAccess.is_active.is_(True),
        )
    )


def usable_activity_clause(activity_alias, employee_id: uuid.UUID | None):
    """Boolean clause for "employee may use this (top-level) activity": COMMON,
    or RESTRICTED with an active grant. `activity_alias` is the ActivityMaster
    row (or alias) of the top-level Activity. A None employee (a user with no
    employee profile) sees only COMMON activities."""
    if employee_id is None:
        return activity_alias.access_type == ACCESS_TYPE_COMMON
    return (activity_alias.access_type == ACCESS_TYPE_COMMON) | has_active_access_clause(
        activity_alias.id, employee_id
    )


def employee_can_use_activity(
    db: Session, *, employee_id: uuid.UUID | None, activity_id: uuid.UUID
) -> bool:
    """Whether `employee_id` may use the top-level Activity `activity_id`
    (ignores is_active — callers validate activity state separately)."""
    row = db.get(ActivityMaster, activity_id)
    if row is None:
        return False
    if row.access_type == ACCESS_TYPE_COMMON:
        return True
    if employee_id is None:
        return False
    return db.execute(
        select(EmployeeActivityAccess.id).where(
            EmployeeActivityAccess.activity_id == activity_id,
            EmployeeActivityAccess.employee_id == employee_id,
            EmployeeActivityAccess.is_active.is_(True),
        )
    ).first() is not None


# ── write-path bulk enforcement ─────────────────────────────────────────────

def _governing_access(
    db: Session, sub_activity_ids: set[uuid.UUID]
) -> dict[uuid.UUID, tuple[uuid.UUID, str, str]]:
    """Map each sub_activity_id -> (parent_activity_id, parent_access_type,
    parent_activity_name), in ONE query. Sub-activities inherit the parent's
    access, so the parent Activity row governs."""
    if not sub_activity_ids:
        return {}
    Parent = aliased(ActivityMaster)
    rows = db.execute(
        select(
            ActivityMaster.id,
            ActivityMaster.parent_id,
            Parent.access_type,
            Parent.name,
        )
        .join(Parent, ActivityMaster.parent_id == Parent.id)
        .where(ActivityMaster.id.in_(sub_activity_ids))
    ).all()
    return {sub_id: (parent_id, access, name) for sub_id, parent_id, access, name in rows}


def validate_report_activity_access(
    db: Session, *, employee_id: uuid.UUID, tasks
) -> None:
    """Reject any task row that selects a RESTRICTED activity the employee is not
    authorized for. Bulk: two queries total regardless of row count (Phase 4/12).

    Continuation exception (approved design, Phase 8): a row that CONTINUES an
    existing work item the employee already owns for the same sub-activity is
    allowed even after access is revoked — the work item was necessarily started
    while access was valid, and continuing it is not "starting new work". Whether
    it can actually be continued (still open, no later entry) is enforced by the
    work_items layer; here we only relax the access gate. This exception applies
    only while task continuation is enabled — otherwise every row is new work.
    """
    sub_ids = {
        task.sub_activity_id
        for task in tasks
        if getattr(task, "sub_activity_id", None) is not None
    }
    if not sub_ids:
        return
    governing = _governing_access(db, sub_ids)

    restricted_parent_ids = {
        parent_id
        for (parent_id, access, _name) in governing.values()
        if access == ACCESS_TYPE_RESTRICTED
    }
    granted: set[uuid.UUID] = set()
    if restricted_parent_ids:
        granted = set(
            db.execute(
                select(EmployeeActivityAccess.activity_id).where(
                    EmployeeActivityAccess.employee_id == employee_id,
                    EmployeeActivityAccess.activity_id.in_(restricted_parent_ids),
                    EmployeeActivityAccess.is_active.is_(True),
                )
            ).scalars()
        )

    for task in tasks:
        sub_id = getattr(task, "sub_activity_id", None)
        if sub_id is None or sub_id not in governing:
            continue
        parent_id, access, activity_name = governing[sub_id]
        if access != ACCESS_TYPE_RESTRICTED or parent_id in granted:
            continue
        if _is_continuation_of_owned_item(db, employee_id=employee_id, task=task):
            continue
        raise AppError(
            "forbidden",
            f'You do not have access to use "{activity_name}". '
            "Contact your PM if this activity is required.",
            403,
        )


def _is_continuation_of_owned_item(db: Session, *, employee_id: uuid.UUID, task) -> bool:
    """True when `task` continues an existing work item this employee owns for
    the same sub-activity (the Phase 8 continuation exception). Only relevant
    while task continuation is enabled."""
    if not settings.TASK_CONTINUATION_ENABLED:
        return False
    work_item_id = getattr(task, "work_item_id", None)
    if work_item_id is None:
        return False
    # Local import avoids a module-load cycle (work_reports imports this module).
    from app.modules.work_reports.models import WorkItem

    item = db.get(WorkItem, work_item_id)
    return (
        item is not None
        and item.employee_id == employee_id
        and item.sub_activity_id == getattr(task, "sub_activity_id", None)
    )


# ── PM-only mutations ───────────────────────────────────────────────────────

def _fetch_activity(db: Session, activity_id: uuid.UUID) -> ActivityMaster:
    row = db.get(ActivityMaster, activity_id)
    if row is None:
        raise AppError("not_found", "Activity not found.", 404)
    if row.level != LEVEL_ACTIVITY:
        raise AppError(
            "validation_error",
            "Access is managed on the top-level Activity, not a sub-activity.",
            422,
        )
    return row


def _assert_activity_mutable(activity: ActivityMaster) -> None:
    if not activity.is_active:
        raise AppError(
            "validation_error",
            "This activity is inactive; reactivate it before changing access.",
            422,
        )


def _validate_active_employees(
    db: Session, employee_ids: list[uuid.UUID]
) -> list[Employee]:
    """All ids must resolve to distinct, active (not soft-deleted) employees, or
    the whole operation is rejected before any write (atomic pre-validation)."""
    unique = list(dict.fromkeys(employee_ids))
    if not unique:
        raise AppError("validation_error", "Select at least one employee.", 422)
    rows = db.execute(
        select(Employee).where(
            Employee.id.in_(unique),
            Employee.deleted_at.is_(None),
            Employee.status == EmployeeStatus.active,
        )
    ).scalars().all()
    found = {e.id for e in rows}
    missing = [str(eid) for eid in unique if eid not in found]
    if missing:
        raise AppError(
            "validation_error",
            "One or more selected employees are invalid or inactive.",
            422,
            {"invalid_employee_ids": missing},
        )
    return rows


def _grant_many(
    db: Session, *, activity_id: uuid.UUID, employee_ids: list[uuid.UUID], actor: User
) -> dict[str, int]:
    """Grant/reactivate access for each employee on `activity_id`. Idempotent:
    an already-active pair is left as-is; a revoked pair is reactivated; a new
    pair is inserted. Returns per-outcome counts. Emits one audit row per newly
    granted/reactivated employee. Joins the caller's transaction (no commit)."""
    unique = list(dict.fromkeys(employee_ids))
    existing = {
        row.employee_id: row
        for row in db.execute(
            select(EmployeeActivityAccess).where(
                EmployeeActivityAccess.activity_id == activity_id,
                EmployeeActivityAccess.employee_id.in_(unique),
            )
        ).scalars()
    }
    now = _now()
    granted = reactivated = already_active = 0
    for emp_id in unique:
        row = existing.get(emp_id)
        if row is None:
            db.add(
                EmployeeActivityAccess(
                    activity_id=activity_id,
                    employee_id=emp_id,
                    is_active=True,
                    granted_by_id=actor.id,
                    granted_at=now,
                )
            )
            granted += 1
            _audit_access(db, actor, AuditAction.ACTIVITY_ACCESS_GRANTED, activity_id, emp_id)
        elif row.is_active:
            already_active += 1
        else:
            # Reactivate the soft-revoked row in place (never a duplicate).
            row.is_active = True
            row.granted_by_id = actor.id
            row.granted_at = now
            row.revoked_by_id = None
            row.revoked_at = None
            db.add(row)
            reactivated += 1
            _audit_access(db, actor, AuditAction.ACTIVITY_ACCESS_GRANTED, activity_id, emp_id)
    db.flush()
    return {"granted": granted, "reactivated": reactivated, "already_active": already_active}


def _revoke_all_active(
    db: Session, *, activity_id: uuid.UUID, actor: User
) -> int:
    """Soft-revoke every currently-active grant on `activity_id`. Returns the
    count revoked. One audit row per employee. Joins the caller's transaction."""
    rows = db.execute(
        select(EmployeeActivityAccess).where(
            EmployeeActivityAccess.activity_id == activity_id,
            EmployeeActivityAccess.is_active.is_(True),
        )
    ).scalars().all()
    now = _now()
    for row in rows:
        row.is_active = False
        row.revoked_by_id = actor.id
        row.revoked_at = now
        db.add(row)
        _audit_access(db, actor, AuditAction.ACTIVITY_ACCESS_REVOKED, activity_id, row.employee_id)
    db.flush()
    return len(rows)


def _active_count(db: Session, activity_id: uuid.UUID) -> int:
    return db.execute(
        select(func.count())
        .select_from(EmployeeActivityAccess)
        .where(
            EmployeeActivityAccess.activity_id == activity_id,
            EmployeeActivityAccess.is_active.is_(True),
        )
    ).scalar_one()


def _audit_access(
    db: Session,
    actor: User,
    action: str,
    activity_id: uuid.UUID,
    employee_id: uuid.UUID | None = None,
    extra: dict | None = None,
) -> None:
    details: dict = {}
    if employee_id is not None:
        details["employee_id"] = str(employee_id)
    if extra:
        details.update(extra)
    record_audit(
        db,
        action=action,
        actor=actor,
        entity_type=EntityType.ACTIVITY,
        entity_id=activity_id,
        details=details,
    )


def change_activity_access_type(
    db: Session,
    *,
    actor: User,
    activity_id: uuid.UUID,
    new_type: str,
    employee_ids: list[uuid.UUID],
) -> dict:
    """Atomically switch an Activity between COMMON and RESTRICTED.

    COMMON -> RESTRICTED: requires >= 1 valid active employee; validates ALL of
    them before any write, then flips the type and grants them in one
    transaction (never leaves the activity restricted with zero employees).

    RESTRICTED -> COMMON: flips the type and soft-revokes every current grant,
    preserving history, in one transaction.

    Idempotent where practical: setting the type it already has is a no-op flip
    that still applies the requested grants (for RESTRICTED)."""
    activity = _fetch_activity(db, activity_id)
    _assert_activity_mutable(activity)
    previous = activity.access_type

    if new_type == ACCESS_TYPE_RESTRICTED:
        _validate_active_employees(db, employee_ids)
        activity.access_type = ACCESS_TYPE_RESTRICTED
        db.add(activity)
        counts = _grant_many(
            db, activity_id=activity_id, employee_ids=employee_ids, actor=actor
        )
    elif new_type == ACCESS_TYPE_COMMON:
        activity.access_type = ACCESS_TYPE_COMMON
        db.add(activity)
        _revoke_all_active(db, activity_id=activity_id, actor=actor)
        counts = {"granted": 0, "reactivated": 0, "already_active": 0}
    else:
        raise AppError("validation_error", "Unknown access type.", 422)

    if previous != new_type:
        _audit_access(
            db,
            actor,
            AuditAction.ACTIVITY_ACCESS_TYPE_CHANGED,
            activity_id,
            extra={"previous": previous, "new": new_type},
        )
    db.commit()
    return {
        "activity_id": activity_id,
        "access_type": activity.access_type,
        **counts,
        "authorized_count": _active_count(db, activity_id),
    }


def grant_activity_access(
    db: Session, *, actor: User, activity_id: uuid.UUID, employee_ids: list[uuid.UUID]
) -> dict:
    """Bulk grant on an already-RESTRICTED activity. Validates all employees
    first, then grants/reactivates in one transaction."""
    activity = _fetch_activity(db, activity_id)
    _assert_activity_mutable(activity)
    if activity.access_type != ACCESS_TYPE_RESTRICTED:
        raise AppError(
            "validation_error",
            "Access can only be granted on a Restricted activity. Switch it to "
            "Restricted first.",
            422,
        )
    _validate_active_employees(db, employee_ids)
    counts = _grant_many(
        db, activity_id=activity_id, employee_ids=employee_ids, actor=actor
    )
    db.commit()
    return {
        "activity_id": activity_id,
        "access_type": activity.access_type,
        **counts,
        "authorized_count": _active_count(db, activity_id),
    }


def revoke_activity_access(
    db: Session, *, actor: User, activity_id: uuid.UUID, employee_id: uuid.UUID
) -> dict:
    """Soft-revoke one employee's active access. Idempotent: revoking an already
    -revoked (or never-granted) pair is a clean no-op, not an error."""
    activity = _fetch_activity(db, activity_id)
    _assert_activity_mutable(activity)
    row = db.execute(
        select(EmployeeActivityAccess).where(
            EmployeeActivityAccess.activity_id == activity_id,
            EmployeeActivityAccess.employee_id == employee_id,
        )
    ).scalar_one_or_none()
    if row is None or not row.is_active:
        return {
            "activity_id": activity_id,
            "access_type": activity.access_type,
            "revoked": False,
            "authorized_count": _active_count(db, activity_id),
        }
    row.is_active = False
    row.revoked_by_id = actor.id
    row.revoked_at = _now()
    db.add(row)
    _audit_access(db, actor, AuditAction.ACTIVITY_ACCESS_REVOKED, activity_id, employee_id)
    db.commit()
    return {
        "activity_id": activity_id,
        "access_type": activity.access_type,
        "revoked": True,
        "authorized_count": _active_count(db, activity_id),
    }


def list_activity_access(
    db: Session, *, activity_id: uuid.UUID, limit: int, offset: int
) -> dict:
    """Read the access config: the activity's access_type, active grant count,
    and a paginated page of active assignments (employee + granter identity)."""
    activity = _fetch_activity(db, activity_id)
    total = _active_count(db, activity_id)

    Granter = aliased(Employee)
    rows = db.execute(
        select(
            Employee.id,
            Employee.employee_code,
            Employee.first_name,
            Employee.last_name,
            EmployeeActivityAccess.granted_at,
            Granter.first_name.label("granter_first"),
            Granter.last_name.label("granter_last"),
            User.email.label("granter_email"),
        )
        .join(Employee, EmployeeActivityAccess.employee_id == Employee.id)
        .outerjoin(User, EmployeeActivityAccess.granted_by_id == User.id)
        .outerjoin(Granter, Granter.user_id == User.id)
        .where(
            EmployeeActivityAccess.activity_id == activity_id,
            EmployeeActivityAccess.is_active.is_(True),
        )
        .order_by(Employee.first_name, Employee.last_name)
        .limit(limit)
        .offset(offset)
    ).all()

    items = []
    for r in rows:
        if r.granter_first:
            granted_by = f"{r.granter_first} {r.granter_last}".strip()
        else:
            granted_by = r.granter_email
        items.append(
            {
                "employee_id": r.id,
                "employee_code": r.employee_code,
                "employee_name": f"{r.first_name} {r.last_name}".strip(),
                "granted_by": granted_by,
                "granted_at": r.granted_at,
            }
        )
    return {
        "activity_id": activity_id,
        "access_type": activity.access_type,
        "authorized_count": total,
        "items": items,
        "total": total,
        "limit": limit,
        "offset": offset,
    }
