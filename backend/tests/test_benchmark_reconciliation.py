"""Pure unit tests for the comparison-table backlog reconciliation
(_reconciled_pending_by_employee). Mirrors the frontend reconciliation.ts so
the PM 'Employee performance' table's Pending agrees with the per-employee
detail view. No DB / fixtures needed."""
import uuid
from decimal import Decimal as D

from app.modules.benchmarks.service import (
    _reconcile_effective_pending,
    _reconciled_pending_by_employee,
)


def _row(emp, sub, day, target, actual):
    return {
        "employee_id": emp,
        "sub_activity_id": sub,
        "date": f"2026-06-{day:02d}",
        "target": D(target),
        "actual": D(actual),
    }


def test_later_surplus_clears_earlier_deficit():
    """Santhosh's week: Mon 80/100 (−20) is recovered by Wed 120/100 (+20) in
    the same sub-activity, so reconciled pending is 62, not the raw 82."""
    emp = uuid.uuid4()
    fmtl, mtl, doc = uuid.uuid4(), uuid.uuid4(), uuid.uuid4()
    daily = [
        _row(emp, fmtl, 15, 100, 80),    # -20
        _row(emp, mtl, 16, 160, 100),    # -60
        _row(emp, fmtl, 17, 100, 120),   # +20 -> clears Mon's -20
        _row(emp, doc, 18, 1000, 998),   # -2
        _row(emp, mtl, 19, 100, 100),    # 0
    ]
    assert _reconciled_pending_by_employee(daily)[emp] == D(62)


def test_surplus_does_not_carry_forward_to_future_deficit():
    """An earlier surplus is dropped; it never pays down a *later* deficit."""
    emp = uuid.uuid4()
    sub = uuid.uuid4()
    daily = [
        _row(emp, sub, 15, 100, 120),  # +20 surplus first...
        _row(emp, sub, 16, 100, 80),   # ...does NOT cover this -20
    ]
    assert _reconciled_pending_by_employee(daily)[emp] == D(20)


def test_surplus_isolated_per_sub_activity():
    """A surplus in one sub-activity cannot clear another's deficit."""
    emp = uuid.uuid4()
    a, b = uuid.uuid4(), uuid.uuid4()
    daily = [
        _row(emp, a, 15, 100, 50),    # -50 in A
        _row(emp, b, 16, 100, 200),   # +100 in B (unrelated)
    ]
    assert _reconciled_pending_by_employee(daily)[emp] == D(50)


def test_partial_recovery_leaves_remainder():
    """A +20 day only partially pays down a −50 day: 30 remains."""
    emp = uuid.uuid4()
    sub = uuid.uuid4()
    daily = [
        _row(emp, sub, 15, 100, 50),    # -50
        _row(emp, sub, 16, 100, 120),   # +20 -> 30 remains
    ]
    assert _reconciled_pending_by_employee(daily)[emp] == D(30)


def test_effective_pending_per_row_fully_recovered():
    """Per-row remaining (powers the team backlog): a deficit fully cleared by a
    later surplus reports 0 remaining on both rows, so neither shows as backlog."""
    emp = uuid.uuid4()
    sub = uuid.uuid4()
    daily = [
        _row(emp, sub, 15, 100, 80),    # -20
        _row(emp, sub, 17, 100, 120),   # +20 -> clears Mon
    ]
    eff = _reconcile_effective_pending(daily)
    assert eff[(emp, "2026-06-15", sub)] == D(0)
    assert eff[(emp, "2026-06-17", sub)] == D(0)


def test_effective_pending_per_row_partial_remaining():
    """Partial recovery leaves the reconciled remaining on the earlier row —
    this is the quantity the dashboards surface."""
    emp = uuid.uuid4()
    sub = uuid.uuid4()
    daily = [
        _row(emp, sub, 15, 100, 50),    # -50
        _row(emp, sub, 16, 100, 120),   # +20
    ]
    eff = _reconcile_effective_pending(daily)
    assert eff[(emp, "2026-06-15", sub)] == D(30)   # 50 - 20 still outstanding
    assert eff[(emp, "2026-06-16", sub)] == D(0)
