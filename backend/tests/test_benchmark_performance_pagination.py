"""Employee-performance list: filter -> sort -> total -> paginate ORDER.

Regression guard for the bug where the status filter ran client-side AFTER the
page was sliced: the roster was paginated first, then only the current page's
rows were filtered, so "Needs Review" could show 1 row while the footer still
read "of 27" and Next stayed active. The fix moved the status filter into
get_employees_performance so it runs BEFORE sort/pagination and `total` is the
filtered count.

These tests drive the service directly with a synthetic daily ledger (patched
in) so each employee's pending is controlled exactly — pending > 0 => the
"Needs Review" bucket the Status badge shows, pending 0 => "On Track".
"""
import uuid
from datetime import date
from decimal import Decimal

import pytest

from app.modules.benchmarks import service
from app.modules.users.models import UserRole

PAGE_SIZE = 7  # mirrors the frontend PerformanceTable PAGE_SIZE


def _ledger_row(emp_id, *, target, actual, sub_id=None, on=date(2026, 1, 2)):
    """One get_daily_benchmark_ledger()-shaped row. Only the keys the rollup and
    reconciliation read are required (employee_id, sub_activity_id, date, target,
    actual); pending is derived the same way the real ledger derives it."""
    tgt, act = Decimal(str(target)), Decimal(str(actual))
    return {
        "employee_id": emp_id,
        "sub_activity_id": sub_id or uuid.uuid4(),
        "date": on,
        "target": tgt,
        "actual": act,
        "pending": max(Decimal("0"), tgt - act),
    }


@pytest.fixture()
def roster(make_user, make_employee):
    """Create employees (report-authoring role) from (code, name) specs and
    return them in creation order."""

    def _make(specs):
        emps = []
        for code, name in specs:
            u = make_user(f"{code.lower()}@x.com", role=UserRole.employee)
            emps.append(
                make_employee(
                    employee_code=code, user_id=u.id, first_name=name, last_name="X"
                )
            )
        return emps

    return _make


@pytest.fixture()
def patch_ledger(monkeypatch):
    """Patch the daily ledger the performance list reads so pending is fully
    controlled. `rows` is a flat list of _ledger_row() dicts."""

    def _apply(rows):
        monkeypatch.setattr(
            service, "get_daily_benchmark_ledger", lambda *a, **k: list(rows)
        )

    return _apply


def _codes(res):
    return [r["employee_code"] for r in res["items"]]


# --- test 1: 20 filtered matches out of a larger roster paginate 7, 7, 6 -----

def test_twenty_matches_paginate_seven_seven_six(db, roster, patch_ledger):
    # 24-employee roster: 20 with a shortfall (Needs Review), 4 met exactly
    # (On Track). The 4 On Track employees must NOT dilute the Needs Review
    # pages the way per-page filtering did.
    review = roster([(f"NR{i:02d}", f"Review {i:02d}") for i in range(20)])
    ontrack = roster([(f"OK{i:02d}", f"Okay {i:02d}") for i in range(4)])
    ledger = [_ledger_row(e.id, target=100, actual=50) for e in review]  # pending 50
    ledger += [_ledger_row(e.id, target=100, actual=100) for e in ontrack]  # pending 0
    patch_ledger(ledger)

    def page(n):
        return service.get_employees_performance(
            db, page=n, page_size=PAGE_SIZE, status="needs_review"
        )

    p1, p2, p3 = page(1), page(2), page(3)

    # total is the FILTERED count (20), not the 24-employee roster.
    assert p1["total"] == p2["total"] == p3["total"] == 20
    # Rows compact into full pages, remainder last: 7, 7, 6 (not 6, 7, 7).
    assert [len(p1["items"]), len(p2["items"]), len(p3["items"])] == [7, 7, 6]
    # Every returned row is genuinely a Needs Review employee, across all pages.
    seen = _codes(p1) + _codes(p2) + _codes(p3)
    assert len(seen) == 20 and set(seen) == {f"NR{i:02d}" for i in range(20)}
    # No On Track employee leaks into the filtered result.
    assert not any(c.startswith("OK") for c in seen)


# --- test 2: a single match reports total 1, not the roster total -----------

def test_single_match_reports_total_one(db, roster, patch_ledger):
    emps = roster([(f"E{i:02d}", f"Emp {i:02d}") for i in range(12)])
    # Exactly one employee has pending work; the rest are On Track.
    ledger = [_ledger_row(emps[0].id, target=100, actual=30)]
    ledger += [_ledger_row(e.id, target=100, actual=100) for e in emps[1:]]
    patch_ledger(ledger)

    res = service.get_employees_performance(
        db, page=1, page_size=PAGE_SIZE, status="needs_review"
    )
    # The footer total is 1 (this is what makes "Showing 1-1 of 1" correct),
    # NOT the 12-employee roster total.
    assert res["total"] == 1
    assert len(res["items"]) == 1
    assert res["items"][0]["employee_code"] == "E00"


# --- test 3: a filtered total that fits one page needs no second page -------

def test_filtered_total_fits_single_page(db, roster, patch_ledger):
    # 15 employees, exactly 7 on track -> On Track filter yields one full page.
    emps = roster([(f"E{i:02d}", f"Emp {i:02d}") for i in range(15)])
    on_track, needs = emps[:7], emps[7:]
    ledger = [_ledger_row(e.id, target=100, actual=100) for e in on_track]  # pending 0
    ledger += [_ledger_row(e.id, target=100, actual=10) for e in needs]  # pending 90
    patch_ledger(ledger)

    res = service.get_employees_performance(
        db, page=1, page_size=PAGE_SIZE, status="on_track"
    )
    # total == PAGE_SIZE: the frontend renders the pager only when total >
    # PAGE_SIZE, so Next is hidden and the whole result is on page 1.
    assert res["total"] == 7
    assert len(res["items"]) == 7
    assert res["total"] <= PAGE_SIZE


# --- test 5: search AND status are both applied before pagination -----------

def test_search_and_status_combined_before_pagination(db, roster, patch_ledger):
    # Two families of names. Search narrows to the ALPHA family, status narrows
    # to Needs Review; only the intersection may survive, and total reflects it.
    alpha = roster([(f"ALPHA{i:02d}", f"Alpha {i:02d}") for i in range(10)])
    beta = roster([(f"BETA{i:02d}", f"Beta {i:02d}") for i in range(10)])
    # 6 ALPHA need review, 4 ALPHA on track; every BETA needs review (must be
    # excluded by the search even though they match the status).
    ledger = [_ledger_row(e.id, target=100, actual=40) for e in alpha[:6]]
    ledger += [_ledger_row(e.id, target=100, actual=100) for e in alpha[6:]]
    ledger += [_ledger_row(e.id, target=100, actual=40) for e in beta]
    patch_ledger(ledger)

    res = service.get_employees_performance(
        db, page=1, page_size=PAGE_SIZE, search="alpha", status="needs_review"
    )
    # Intersection = 6 (ALPHA AND Needs Review); BETA rows are filtered out by
    # search, On Track ALPHA rows by status — all before the page slice.
    assert res["total"] == 6
    assert {c[:5] for c in _codes(res)} == {"ALPHA"}
    assert len(res["items"]) == 6


# --- test 6: sort runs over the whole filtered set, not one page ------------

def test_sort_applied_to_full_filtered_set_before_slice(db, roster, patch_ledger):
    # 10 Needs Review employees with distinct pending values. Sorted by pending
    # desc, page 1 must hold the globally-largest pending values, proving the
    # sort ran across the full filtered set before the page was sliced.
    emps = roster([(f"E{i:02d}", f"Emp {i:02d}") for i in range(10)])
    # pending = 10, 20, ... 100 (actual = 100 - pending against target 100).
    pendings = {e.employee_code: (i + 1) * 10 for i, e in enumerate(emps)}
    ledger = [
        _ledger_row(e.id, target=100, actual=100 - pendings[e.employee_code])
        for e in emps
    ]
    patch_ledger(ledger)

    p1 = service.get_employees_performance(
        db, page=1, page_size=PAGE_SIZE, status="needs_review",
        sort="pending", order="desc",
    )
    p2 = service.get_employees_performance(
        db, page=2, page_size=PAGE_SIZE, status="needs_review",
        sort="pending", order="desc",
    )
    assert p1["total"] == 10
    ordered = [Decimal(str(r["pending"])) for r in p1["items"] + p2["items"]]
    # Strictly descending across the page boundary (100, 90, ... 10).
    assert ordered == sorted(ordered, reverse=True)
    assert ordered[0] == Decimal("100")  # global max leads page 1
    assert ordered[-1] == Decimal("10")  # global min trails page 2
    # Page 1 holds the seven largest; the smallest three fall to page 2.
    assert [Decimal(str(r["pending"])) for r in p1["items"]] == [
        Decimal(str(v)) for v in (100, 90, 80, 70, 60, 50, 40)
    ]
