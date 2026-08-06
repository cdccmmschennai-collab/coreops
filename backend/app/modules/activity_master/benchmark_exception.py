"""Structured benchmark exceptions — a recorded, validated reason why a numeric
benchmark row is evaluated as achieved despite an actual below its target.

Phase 1 defines exactly one code:

  NO_FURTHER_AVAILABLE_WORK -> the employee completed every TAG that was
      actually available for the activity, but fewer were available than the
      configured target. Target 100, actual 40, exception set: the row is
      evaluated at 100% with 0 pending, while 40 remains the real, stored,
      exported actual. The real count is NEVER overwritten with the target.

Two rules make this safe to extend and impossible to fake:

1. STRUCTURED ONLY. The exception lives in its own column
   (work_report_tasks.benchmark_exception_code), never in the free-text remark.
   An employee typing "no further tags were available" into their remark changes
   nothing — no calculation here reads remark text.

2. EFFECTIVE != REAL. `effective_actual` exists purely to feed percentages and
   pending; it is never persisted and never displayed as the actual. Every
   caller keeps writing the real count into the ACTUAL COMPLETED cell.

Widening past TAGS later is a one-line change to EXCEPTION_ELIGIBLE_COUNT_FIELDS
(plus the frontend's mirror of it): nothing below hard-codes "tags" anywhere
else, and the exported system remark is looked up per unit in
EXPORT_EXCEPTION_REMARK_BY_UNIT.
"""
from decimal import Decimal

from .models import (
    COUNT_FIELD_TAGS,
    DAILY_QUANTITY_BENCHMARK_TYPES,
)

# The one Phase 1 code. VARCHAR + CHECK rather than a native Postgres enum,
# following the benchmark_type / access_type precedent in models.py.
BENCHMARK_EXCEPTION_NO_FURTHER_AVAILABLE_WORK = "NO_FURTHER_AVAILABLE_WORK"
VALID_BENCHMARK_EXCEPTION_CODES = frozenset(
    {BENCHMARK_EXCEPTION_NO_FURTHER_AVAILABLE_WORK}
)

# Which benchmark modes may carry an exception: the pure per-day numeric modes
# only (NUMERIC, NUMERIC_DAILY). Task modes — including TASK_WITH_QUANTITY —
# are excluded by construction, and are not part of the benchmark Excel at all.
EXCEPTION_ELIGIBLE_BENCHMARK_TYPES = frozenset(DAILY_QUANTITY_BENCHMARK_TYPES)

# Phase 1 supports TAGS only. Add COUNT_FIELD_DOCS / _BOM / _SPARES / _PAGES /
# _RECORDS here (and the matching remark below) to widen it — no other backend
# change is required.
EXCEPTION_ELIGIBLE_COUNT_FIELDS = frozenset({COUNT_FIELD_TAGS})

# System-generated remark prepended to the EXPORTED remark of an exception row.
# Export-only: the employee's stored remark is never modified.
EXPORT_EXCEPTION_REMARK_BY_UNIT = {
    COUNT_FIELD_TAGS: "[NO FURTHER TAGS WERE AVAILABLE FOR THIS ACTIVITY]",
}


def _to_decimal(value) -> Decimal | None:
    """Best-effort Decimal, or None for anything that is not a real number
    (None, "", a status string, a bool)."""
    if value is None or isinstance(value, bool):
        return None
    if isinstance(value, Decimal):
        return value
    try:
        return Decimal(str(value))
    except Exception:
        return None


def is_eligible_row(benchmark_type: str | None, count_field: str | None) -> bool:
    """Static eligibility: does this sub-activity's benchmark configuration allow
    an exception at all? Independent of the numbers entered, so it can be checked
    the moment a row is saved (draft included), before any target is frozen."""
    return (
        benchmark_type in EXCEPTION_ELIGIBLE_BENCHMARK_TYPES
        and count_field in EXCEPTION_ELIGIBLE_COUNT_FIELDS
    )


def is_valid_exception(
    code: str | None,
    *,
    benchmark_type: str | None,
    count_field: str | None,
    target,
    actual,
) -> bool:
    """The full server-side verdict, evaluated against frozen numbers.

    Valid only when ALL of:
      - `code` is a known exception code;
      - the benchmark mode is a pure numeric one (never a task mode);
      - the counted unit is exception-eligible (Phase 1: TAGS);
      - a positive target exists;
      - an actual is present (0 counts as present — "none were available");
      - the actual is strictly BELOW the target.

    Anything else is False, which callers turn into a cleared column: an
    exception that no longer describes reality quietly stops applying rather
    than freezing a stale 100%.
    """
    if code not in VALID_BENCHMARK_EXCEPTION_CODES:
        return False
    if not is_eligible_row(benchmark_type, count_field):
        return False
    target_d = _to_decimal(target)
    actual_d = _to_decimal(actual)
    if target_d is None or target_d <= 0:
        return False
    if actual_d is None:
        return False
    return actual_d < target_d


def effective_actual(target, actual, *, has_exception: bool):
    """The CALCULATION-ONLY actual: the target on a valid exception row, the
    real actual otherwise.

    Never persisted, never written into ACTUAL COMPLETED — it exists so a row
    whose available work ran out evaluates at 100% (and 0 pending) while the
    sheet still reports the real count. Callers must have established
    `has_exception` through `is_valid_exception` first.
    """
    if not has_exception:
        return actual
    target_d = _to_decimal(target)
    return actual if target_d is None else target_d


def export_exception_remark(count_field: str | None) -> str | None:
    """The system remark for an exception row's exported REMARKS cell, or None
    for a unit that carries no remark wording (cannot happen for an exception
    that passed validation)."""
    return EXPORT_EXCEPTION_REMARK_BY_UNIT.get(count_field or "")
