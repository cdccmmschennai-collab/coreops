# Phase 9A — Records Consolidation Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make Attendance → Records the single PM daily attendance-review workspace: remove the old "Record attendance" (`/attendance/new`) entry points, shrink the four large KPI cards to one compact summary line, relabel the classification vocabulary to Present / Needs review / Punch missing / No punch, add employee search + server-side pagination (15/page) to the Records table, split the table into biometric evidence vs. official status columns, and replace the row popover with navigation to a new (stub) detail route.

**Architecture:** `GET /biometric/daily-review` already computes the whole roster's classification in one pass (three queries, no N+1) inside `service.list_daily_review`. Pagination and employee search are added as an in-memory filter/slice inside that same loop — consistent with how the existing `classification` filter already works (counts are computed before any filter is applied; only `items` is filtered/sliced). No new calculation engine, no SQL-level filtering, no migration. The frontend keeps the same read-only, non-committal review surface; only presentation, filters, and navigation change. The old bulk "Record attendance" sheet (`/attendance/new`, `AttendanceSheet`) is deleted from the UI — its backend endpoints (`GET /attendance/sheet`, `POST /attendance/bulk`) and the `attendance_records` table are untouched.

**Tech Stack:** FastAPI + SQLAlchemy (backend/app/modules/biometric), Next.js App Router + React Query + Tailwind (frontend/src/features/biometric, frontend/src/features/attendance).

**Spec:** Phase 9A instructions provided in-conversation (2026-08-16) — see conversation history for the full text; key excerpts are inlined per task below.

## Global Constraints

- Do not create a migration. Do not modify/delete `biometric_punches`, `attendance_records`, leave records, or audit records.
- Do not touch the calendar's existing visual behaviour, calculation path, or its own `AttendanceDayPopover` usage (`attendance-calendar.tsx`).
- Do not implement leave integration, punch correction, or final attendance reconciliation (Phases 9C/9D/9E).
- User-facing vocabulary in the Records UI must be exactly: **Present, Needs review, Punch missing, No punch**. Never show "Incomplete" or "Complete" anywhere in that UI. Internal backend slugs (`incomplete`, `no_record`) may stay as-is — only labels change.
- Default page size for Records is **15**.
- Do not commit. Do not delete backend APIs merely because a frontend page is removed — verify no other consumer first (already done during investigation; see report at the end of this session).
- Do not start Phase 9B/9C/9D/9E/9F work (leave integration, punch correction, full detail page, KPI reconciliation).

---

## Investigation summary (already done, informs every task below)

- `AttendanceView` (`frontend/src/features/attendance/components/attendance-view.tsx`) renders the header actions (Export / Request Leave / **Record attendance** → `/attendance/new`) and the tab body; `tab === "history"` renders `AttendanceRecords` (the Records tab, already relabeled from "History" in a prior phase).
- `AttendanceRecords` (`frontend/src/features/attendance/components/attendance-records.tsx`) is the Phase 8 PM daily review: date + classification filter → `useDailyReview` → `GET /biometric/daily-review` (`backend/app/modules/biometric/router.py` → `service.list_daily_review`). It currently renders 4 `Kpi` cards, no search, no pagination, and opens `AttendanceDayPopover` on row click.
- `AttendanceDayPopover` (`frontend/src/features/biometric/components/attendance-day-popover.tsx`) is shared with `AttendanceCalendar` via its own independent `anchor` state — removing Records' usage does not affect the calendar.
- `/attendance/new` (`frontend/src/app/(app)/attendance/new/page.tsx` → `AttendanceSheet`) is the old bulk roster-marking UI. It is linked from two places: `AttendanceView`'s header button and `project-manager-dashboard.tsx`'s "Shortcuts" card (`features/dashboard/project-manager-dashboard.tsx:196`). Its backend endpoints (`GET /attendance/sheet`, `POST /attendance/bulk`) are exercised only by `backend/tests/test_attendance.py` outside the frontend — safe to leave in the backend.
- `RecordDecisionDialog` (writes `attendance_records` via `POST/PATCH /attendance`) is the Phase 8 editing affordance, opened from a pencil button in the Records table. It must be preserved unchanged — this is the "editing functionality consistent with Phase 8" the spec requires.
- `/attendance/[id]` and `/attendance/[id]/edit` (`AttendanceDetail`, `AttendanceEdit`, `AttendanceForm`, `AttendanceHistory`, `AttendanceTable`, `DeleteDialog`, `AttendanceFilters`) are **already dead code** — nothing in the app links to them (the Records tab renders `AttendanceRecords`, not `AttendanceHistory`). They are out of Phase 9A's stated scope (not the "Record attendance" duplication) and keyed by `attendance_records.id`, which most review rows don't have — they cannot serve as the Phase 9B detail page. Left untouched; flagged in the final report as a pre-existing cleanup candidate, not touched by this plan.
- `GET /biometric/daily-review` has no `q`/pagination params today. `service.list_daily_review` (backend/app/modules/biometric/service.py:1259) loops over every in-scope employee once to build `counts` (before any filter) and `items` (after the `classification` filter, via `continue`). This is the exact pattern to extend for search + pagination.
- No existing backend test exercises `list_daily_review` / `/biometric/daily-review` at all (confirmed via repo-wide grep). New tests for this endpoint are new coverage, following the fixture patterns in `backend/tests/test_biometric_mapping_admin.py` (`client`, `pm` fixture via `auth_header(..., role=UserRole.project_manager)`, `db`, `make_employee`).

---

## Task 1: Backend — pagination + employee search on `GET /biometric/daily-review`

**Files:**
- Modify: `backend/app/modules/biometric/service.py:1259` (`list_daily_review`)
- Modify: `backend/app/modules/biometric/router.py:232` (`list_daily_review` endpoint)
- Modify: `backend/app/modules/biometric/schemas.py:427` (`DailyReviewPage`)
- Test: `backend/tests/test_biometric_daily_review.py` (new file)

**Interfaces:**
- Produces: `service.list_daily_review(db, *, provider, on_date, classification, q=None, limit=15, offset=0) -> dict` with new keys `"limit"` and `"offset"` added to the returned dict, and `"items"` now the **paginated** slice while `"total"` is the count after search+classification filtering but before slicing. `"counts"` is unchanged — always the whole day, unaffected by `q`, `classification`, or pagination (same guarantee the endpoint already documents for `classification`).
- Consumes: nothing new from other tasks.

- [x] **Step 1: Add `q`, `limit`, `offset` to `list_daily_review` service function**

In `backend/app/modules/biometric/service.py`, change the signature and the tail of the function (around line 1259–1379):

```python
def list_daily_review(
    db: Session,
    *,
    provider: str,
    on_date: date,
    classification: str | None,
    q: str | None = None,
    limit: int = 15,
    offset: int = 0,
) -> dict:
```

Add the docstring note (append to the existing docstring, do not rewrite it):

```python
    """...(existing docstring unchanged)...

    `q`, `limit` and `offset` filter and paginate `items` ONLY — exactly like
    `classification` already does. `counts` always describes the whole day
    before any of the three are applied, so the compact summary never lies
    about what the current page or search happens to show.
    """
```

Inside the employee loop, the existing filter is:

```python
        if classification is not None and verdict.classification != classification:
            continue
```

Add the search filter immediately after it (still before `items.append(...)`):

```python
        if classification is not None and verdict.classification != classification:
            continue

        if normalized_q:
            name = f"{first_name} {last_name}".strip().lower()
            code = (employee_code or "").lower()
            if normalized_q not in name and normalized_q not in code:
                continue
```

Normalize `q` once before the loop starts (near the top of the function, after `employees = _review_employees(...)`):

```python
    normalized_q = q.strip().lower() if q and q.strip() else None
```

Change the return statement at the end of the function from:

```python
    return {
        "review_date": on_date,
        "provider": provider,
        "items": items,
        "total": len(items),
        "counts": {
            **counts,
            "employees": len(employees),
            "review_required": review_required_count,
        },
    }
```

to:

```python
    return {
        "review_date": on_date,
        "provider": provider,
        "items": items[offset : offset + limit],
        "total": len(items),
        "limit": limit,
        "offset": offset,
        "counts": {
            **counts,
            "employees": len(employees),
            "review_required": review_required_count,
        },
    }
```

- [x] **Step 2: Add `q`, `limit`, `offset` query params to the router endpoint**

In `backend/app/modules/biometric/router.py`, change the `list_daily_review` endpoint signature (around line 232):

```python
@admin_router.get("/daily-review", response_model=DailyReviewPage)
def list_daily_review(
    review_date: date = Query(alias="date"),
    provider: str = Query(default=PROVIDER_EASYTIME),
    classification: str | None = Query(default=None),
    q: str | None = Query(default=None, max_length=100),
    limit: int = Query(default=15, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
    _: User = Depends(require_manager),
    db: Session = Depends(get_db),
) -> DailyReviewPage:
```

Pass the new params through to the service call (around line 274):

```python
    result = service.list_daily_review(
        db,
        provider=normalized_provider,
        on_date=review_date,
        classification=classification,
        q=q,
        limit=limit,
        offset=offset,
    )
    return DailyReviewPage.model_validate(result)
```

- [x] **Step 3: Add `limit`/`offset` to the `DailyReviewPage` schema**

In `backend/app/modules/biometric/schemas.py`, in `DailyReviewPage` (around line 427):

```python
class DailyReviewPage(BaseModel):
    """...(existing docstring unchanged)..."""

    review_date: date
    provider: str
    items: list[DailyReviewRowOut]
    # Rows AFTER filtering AND before pagination; `counts` describes the
    # unfiltered day. Frontend pagination math (`total`/`limit`/`offset`)
    # matches every other paginated list in this API.
    total: int
    limit: int
    offset: int
    counts: DailyReviewCounts
```

- [x] **Step 4: Write the new backend test file**

Create `backend/tests/test_biometric_daily_review.py`:

```python
"""Phase 9A — GET /biometric/daily-review: employee search + pagination.

`counts` must always describe the whole day; `q` and pagination only ever
narrow/slice `items`. Mirrors the fixture style in
test_biometric_mapping_admin.py (client / pm / db / make_employee).
"""
from datetime import datetime, timezone

import pytest

from app.modules.biometric.models import BiometricEmployeeMapping, BiometricPunch
from app.modules.users.models import UserRole

REVIEW = "/api/v1/biometric/daily-review"
DAY = "2026-08-11"


@pytest.fixture()
def pm(auth_header):
    return auth_header("pm-review@x.com", role=UserRole.project_manager)


def _punch_present(db, employee, *, code: str):
    """One employee, two punches on DAY -> classification `present`."""
    db.add(
        BiometricEmployeeMapping(
            provider="easytime",
            external_employee_code=code,
            employee_id=employee.id,
            is_active=True,
        )
    )
    for hh in (9, 17):
        db.add(
            BiometricPunch(
                provider="easytime",
                external_transaction_id=f"txn-{code}-{hh}",
                external_employee_code=code,
                employee_id=None,
                punch_time=datetime(2026, 8, 11, hh - 5, 30, tzinfo=timezone.utc)
                if hh < 24
                else datetime(2026, 8, 11, hh, tzinfo=timezone.utc),
                received_at=datetime.now(timezone.utc),
                raw_punch_state="0",
            )
        )
    db.commit()


def test_pagination_slices_items_but_not_counts(client, pm, db, make_employee):
    for i in range(20):
        emp = make_employee(employee_code=f"E{i:03d}", first_name=f"Emp{i}", last_name="Test")
        _punch_present(db, emp, code=f"E{i:03d}")

    page1 = client.get(REVIEW, params={"date": DAY, "limit": 15, "offset": 0}, headers=pm)
    assert page1.status_code == 200, page1.text
    body1 = page1.json()
    assert len(body1["items"]) == 15
    assert body1["total"] >= 20
    assert body1["limit"] == 15
    assert body1["offset"] == 0
    assert body1["counts"]["present"] >= 20

    page2 = client.get(REVIEW, params={"date": DAY, "limit": 15, "offset": 15}, headers=pm)
    body2 = page2.json()
    assert body2["counts"] == body1["counts"]
    assert {r["employee_id"] for r in body2["items"]}.isdisjoint(
        {r["employee_id"] for r in body1["items"]}
    )


def test_default_limit_is_fifteen(client, pm, db, make_employee):
    for i in range(20):
        emp = make_employee(employee_code=f"F{i:03d}", first_name=f"F{i}", last_name="Test")
        _punch_present(db, emp, code=f"F{i:03d}")

    res = client.get(REVIEW, params={"date": DAY}, headers=pm)
    assert res.status_code == 200, res.text
    assert len(res.json()["items"]) == 15
    assert res.json()["limit"] == 15


def test_search_matches_name_or_code(client, pm, db, make_employee):
    alice = make_employee(employee_code="A100", first_name="Alice", last_name="Zephyr")
    bob = make_employee(employee_code="B200", first_name="Bob", last_name="Yankee")
    _punch_present(db, alice, code="A100")
    _punch_present(db, bob, code="B200")

    by_name = client.get(REVIEW, params={"date": DAY, "q": "alice"}, headers=pm).json()
    assert [r["employee_id"] for r in by_name["items"]] == [str(alice.id)]

    by_code = client.get(REVIEW, params={"date": DAY, "q": "b200"}, headers=pm).json()
    assert [r["employee_id"] for r in by_code["items"]] == [str(bob.id)]


def test_search_does_not_change_counts(client, pm, db, make_employee):
    alice = make_employee(employee_code="A101", first_name="Alice", last_name="Zephyr")
    bob = make_employee(employee_code="B201", first_name="Bob", last_name="Yankee")
    _punch_present(db, alice, code="A101")
    _punch_present(db, bob, code="B201")

    unfiltered = client.get(REVIEW, params={"date": DAY}, headers=pm).json()
    filtered = client.get(REVIEW, params={"date": DAY, "q": "alice"}, headers=pm).json()
    assert filtered["counts"] == unfiltered["counts"]
    assert filtered["total"] == 1


def test_search_and_pagination_are_pm_only(client, auth_header):
    emp_header = auth_header("emp-review@x.com", role=UserRole.employee)
    res = client.get(REVIEW, params={"date": DAY, "q": "x"}, headers=emp_header)
    assert res.status_code == 403
```

- [x] **Step 5: Run the new and existing biometric tests**

Run: `docker exec wms-backend-1 pytest tests/test_biometric_daily_review.py tests/test_biometric_daily_summary.py tests/test_biometric_classification.py tests/test_biometric_mapping_admin.py -v`
Expected: all PASS.

- [x] **Step 6: Run the full backend suite to catch regressions**

Run: `docker exec wms-backend-1 pytest -q`
Expected: PASS (same pre-existing failures as documented in memory `running-tests.md`, no new failures).

---

## Task 2: Frontend — biometric types/api/hooks/keys for search + pagination

**Files:**
- Modify: `frontend/src/features/biometric/types.ts`
- Modify: `frontend/src/features/biometric/api.ts`
- Modify: `frontend/src/features/biometric/hooks.ts`
- Modify: `frontend/src/features/biometric/keys.ts`

**Interfaces:**
- Consumes: nothing (pure plumbing task).
- Produces: `useDailyReview({ date, classification?, q?, limit, offset })` returning `DailyReviewPage` with `limit`/`offset` fields — consumed by Task 4.

- [x] **Step 1: Add `limit`/`offset` to `DailyReviewPage` in `types.ts`**

In `frontend/src/features/biometric/types.ts`, in `DailyReviewPage` (around line 203):

```typescript
export interface DailyReviewPage {
  review_date: string;
  provider: string;
  items: DailyReviewRow[];
  /** Rows after filtering and pagination; `counts` always describes the
   *  unfiltered day. */
  total: number;
  limit: number;
  offset: number;
  counts: DailyReviewCounts;
}
```

- [x] **Step 2: Add `q`, `limit`, `offset` to `listDailyReview` in `api.ts`**

In `frontend/src/features/biometric/api.ts`, replace the `listDailyReview` method (around line 66):

```typescript
  /** One attendance day across every in-scope employee, for PM review.
   *  project_manager-only and strictly read-only: nothing is approved,
   *  finalized or written. Server-side search and pagination — the client
   *  never filters or slices a roster it was not sent. */
  listDailyReview: (params: {
    date: string;
    classification?: string;
    q?: string;
    limit: number;
    offset: number;
    provider?: string;
  }) => {
    const sp = new URLSearchParams({
      provider: params.provider ?? PROVIDER_EASYTIME,
      date: params.date,
      limit: String(params.limit),
      offset: String(params.offset),
    });
    if (params.classification) sp.set("classification", params.classification);
    if (params.q?.trim()) sp.set("q", params.q.trim());
    return api.get<DailyReviewPage>(`${BASE}/daily-review?${sp.toString()}`);
  },
```

- [x] **Step 3: Add `q`, `limit`, `offset` to `useDailyReview` in `hooks.ts`**

In `frontend/src/features/biometric/hooks.ts`, replace `useDailyReview` (around line 71):

```typescript
export function useDailyReview(params: {
  date: string;
  classification?: string;
  q?: string;
  limit: number;
  offset: number;
  enabled?: boolean;
}) {
  return useQuery({
    queryKey: biometricKeys.dailyReview(
      params.date,
      params.classification ?? "all",
      params.q ?? "",
      params.limit,
      params.offset,
    ),
    queryFn: () =>
      biometricApi.listDailyReview({
        date: params.date,
        classification: params.classification,
        q: params.q,
        limit: params.limit,
        offset: params.offset,
      }),
    enabled: params.enabled !== false && !!params.date,
    // Punches arrive when the connector runs, not continuously.
    staleTime: 60 * 1000,
    // Keeps the table from flashing to a skeleton on every keystroke/page turn.
    placeholderData: (prev) => prev,
  });
}
```

- [x] **Step 4: Extend the `dailyReview` key builder in `keys.ts`**

In `frontend/src/features/biometric/keys.ts`, replace the `dailyReview` key (around line 17):

```typescript
  // PM daily review: one date, the whole roster. Keyed by the classification
  // filter, search text and page too, since all three are applied server-side.
  dailyReview: (
    date: string,
    classification: string,
    q: string,
    limit: number,
    offset: number,
  ) => [...biometricKeys.all, "daily-review", date, classification, q, limit, offset] as const,
```

- [x] **Step 5: Typecheck**

Run: `docker exec wms-frontend-1 npm run typecheck`
Expected: fails only on `attendance-records.tsx` (Task 4 not yet updated to pass `limit`/`offset`) — confirms the new required params are wired correctly. If anything else fails, stop and investigate before continuing.

---

## Task 3: Frontend — relabel classification vocabulary

**Files:**
- Modify: `frontend/src/features/biometric/review.ts`

**Interfaces:**
- Produces: `CLASSIFICATION_LABEL` and `REVIEW_FILTERS` with the new user-facing words — consumed by Task 4 (Records table/filter/summary) and already-existing consumers (`RecordDecisionDialog` does not use these; `attendance-day-popover.tsx` uses `day-detail.ts`'s own `statusLine`, not this file — verify no change needed there, see Step 3).

- [x] **Step 1: Relabel `CLASSIFICATION_LABEL`**

In `frontend/src/features/biometric/review.ts` (around line 47):

```typescript
export const CLASSIFICATION_LABEL: Record<BiometricClassification, string> = {
  present: "Present",
  incomplete: "Punch missing",
  needs_review: "Needs review",
  no_record: "No punch",
};
```

- [x] **Step 2: Reorder and relabel `REVIEW_FILTERS`**

In `frontend/src/features/biometric/review.ts` (around line 19). Keep `DEFAULT_REVIEW_FILTER = "needs_review"` unchanged (line ~36) — only the array's labels and display order change, matching the exact order the spec lists (All, Present, Needs review, Punch missing, No punch):

```typescript
export const REVIEW_FILTERS = [
  { value: "all", label: "All" },
  { value: "present", label: "Present" },
  { value: "needs_review", label: "Needs review" },
  { value: "incomplete", label: "Punch missing" },
  { value: "no_record", label: "No punch" },
] as const;
```

- [x] **Step 3: Confirm `day-detail.ts` (calendar popover) is unaffected**

Read `frontend/src/features/biometric/day-detail.ts` and confirm its own label map (used by `AttendanceDayPopover`/calendar) is separate from `review.ts`'s `CLASSIFICATION_LABEL`. Per Global Constraints, the calendar's existing visual behaviour must not change in this phase — if `day-detail.ts` imports `CLASSIFICATION_LABEL` from `review.ts`, leave a calendar-specific label untouched and only change the Records-facing one. (Investigation during Task 3 execution showed `review.ts` has no runtime imports of `day-detail.ts` beyond the `BiometricClassification` type, so this is expected to be a no-op check, not a code change.)

- [x] **Step 4: Typecheck**

Run: `docker exec wms-frontend-1 npm run typecheck`
Expected: same pre-existing failure as Task 2 Step 5 (attendance-records.tsx not yet updated), nothing new.

---

## Task 4: Frontend — rewrite `AttendanceRecords` (compact summary, search, pagination, split columns, no popover)

**Files:**
- Modify: `frontend/src/features/attendance/components/attendance-records.tsx`

**Interfaces:**
- Consumes: `useDailyReview` (Task 2), `CLASSIFICATION_LABEL`/`CLASSIFICATION_VARIANT`/`REVIEW_FILTERS` (Task 3), the stub route from Task 5 (`/attendance/records/[employeeId]`).
- Produces: nothing new consumed elsewhere — this is the leaf UI component `AttendanceView` already renders for `tab === "history"`.

- [x] **Step 1: Replace state — add search + pagination, remove popover selection**

The spec wants the Records page to *feel* like "Daily Attendance Review" while the tab keeps its "Records" label (spec section 3) — add a small section heading to convey this; it is not a tab rename. Add above the controls row, as the very first thing rendered in the JSX (Step 2 shows exactly where):

```tsx
<h2 className="mb-3 text-lg font-semibold">Daily Attendance Review</h2>
```

Replace the component's state block (the `date`/`filter` URL state plus the `selected`/`editing` local state) with:

```typescript
const PAGE_SIZE = 15;

export function AttendanceRecords() {
  const router = useRouter();
  const today = React.useMemo(() => isoInIST(nowInIST()), []);
  const [rawDate, setDate] = useUrlState("date", today);
  const [rawFilter, setFilter] = useUrlState("review", DEFAULT_REVIEW_FILTER);
  const [rawQ, setRawQ] = useUrlState("q", "");
  const [rawOffset, setRawOffset] = useUrlState("offset", "0");

  const date = /^\d{4}-\d{2}-\d{2}$/.test(rawDate) ? rawDate : today;
  const filter = isReviewFilter(rawFilter) ? rawFilter : DEFAULT_REVIEW_FILTER;
  const offset = Math.max(0, Number(rawOffset) || 0);

  // Debounced fetch text, so every keystroke doesn't fire a request — the URL
  // itself still updates immediately (rawQ), matching the mapping tab's pattern.
  const [q, setQ] = React.useState(rawQ);
  React.useEffect(() => {
    const t = setTimeout(() => setQ(rawQ.trim().toLowerCase()), 300);
    return () => clearTimeout(t);
  }, [rawQ]);

  // The row whose official record the PM is setting, or null.
  const [editing, setEditing] = React.useState<DailyReviewRow | null>(null);

  // Any change to what's being viewed starts back at page 1.
  React.useEffect(() => {
    setRawOffset("0");
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [date, filter, q]);

  const query = useDailyReview({
    date,
    classification: filterToClassification(filter),
    q,
    limit: PAGE_SIZE,
    offset,
  });

  const rows = query.data?.items ?? [];
  const counts = query.data?.counts;

  const showRows = !query.isLoading && !query.isError && rows.length > 0;
  const showEmpty = !query.isLoading && !query.isError && rows.length === 0;

  function openDetail(row: DailyReviewRow) {
    router.push(`/attendance/records/${row.employee_id}?date=${date}`);
  }

  return (
    <>
      <h2 className="mb-3 text-lg font-semibold">Daily Attendance Review</h2>
      {/* see Steps 2-5 for the rest of the JSX body */}
    </>
  );
}
```

Remove the old `React.useEffect(() => { setSelected(null); }, [date, filter]);` and the `openRow`/`selected` variables entirely — there is no more popover state.

Add the new imports this needs: `useRouter` from `next/navigation`, and keep the rest as before minus `AttendanceDayPopover`.

- [x] **Step 2: Replace the controls row — Date picker, Employee search, Status filter (in that order)**

Replace the existing controls `<div>` (date input + filter select + date text) with:

```tsx
      <div className="mb-4 flex flex-col gap-2 sm:flex-row sm:items-center">
        <Input
          type="date"
          className="sm:w-44"
          value={date}
          max={today}
          onChange={(e) => e.target.value && setDate(e.target.value)}
          aria-label="Attendance date"
        />
        <Input
          type="search"
          placeholder="Search by name or ID"
          className="sm:w-56"
          value={rawQ}
          onChange={(e) => setRawQ(e.target.value)}
          aria-label="Search employees"
        />
        <Select value={filter} onValueChange={setFilter}>
          <SelectTrigger className="sm:w-44" aria-label="Status filter">
            <SelectValue />
          </SelectTrigger>
          <SelectContent>
            {REVIEW_FILTERS.map((f) => (
              <SelectItem key={f.value} value={f.value}>
                {f.label}
              </SelectItem>
            ))}
          </SelectContent>
        </Select>
      </div>
```

- [x] **Step 3: Replace the 4 `Kpi` cards with one compact summary line**

Replace the `{counts && <KpiGrid>...</KpiGrid>}` block with:

```tsx
      {counts && (
        <div className="mb-4 rounded-lg border border-border bg-card px-4 py-3">
          <p className="text-sm font-semibold">{formatReviewDate(date)}</p>
          <p className="mt-1 text-sm text-muted-foreground">
            <span className="font-medium text-foreground tabular">{counts.present}</span>{" "}
            {CLASSIFICATION_LABEL.present}
            <span className="mx-1.5">·</span>
            <span className="font-medium text-foreground tabular">{counts.needs_review}</span>{" "}
            {CLASSIFICATION_LABEL.needs_review}
            <span className="mx-1.5">·</span>
            <span className="font-medium text-foreground tabular">{counts.incomplete}</span>{" "}
            {CLASSIFICATION_LABEL.incomplete}
            <span className="mx-1.5">·</span>
            <span className="font-medium text-foreground tabular">{counts.no_record}</span>{" "}
            {CLASSIFICATION_LABEL.no_record}
          </p>
        </div>
      )}
```

Remove the now-unused `Kpi`/`KpiGrid` import and the old inline `formatReviewDate(date)` `<p>` next to the controls (it now lives in this summary block).

- [x] **Step 4: Split the table into Biometric evidence vs. official Status, add Action column, route on row click**

Replace the `<TableHeader>` row:

```tsx
            <TableRow>
              <TableHead>Employee</TableHead>
              <TableHead className="w-24">First IN</TableHead>
              <TableHead className="w-24">Last OUT</TableHead>
              <TableHead className="w-24">Worked</TableHead>
              <TableHead className="w-32">Biometric</TableHead>
              <TableHead className="w-32">Status</TableHead>
              <TableHead>Reason</TableHead>
              <TableHead className="w-16 text-right">Action</TableHead>
            </TableRow>
```

Update `<TableSkeleton cols={7} />` to `cols={8}`.

Replace the row body: the row's `onClick` now calls `openDetail(r)` instead of toggling popover state; the badge cell is split into a Biometric cell (classification, unchanged content) and a separate Status cell (the official `attendance_status`, no click needed since it carries no button); the Action cell holds only the pencil button, `stopPropagation`d:

```tsx
              {rows.map((r) => {
                const reason = primaryReason(r.blocking_reasons);
                return (
                  <TableRow
                    key={r.employee_id}
                    className="cursor-pointer"
                    onClick={() => openDetail(r)}
                  >
                    <TableCell className="font-medium">
                      {r.employee_name || EMPTY}
                      {r.employee_code && (
                        <span className="ml-1.5 text-xs font-normal text-muted-foreground">
                          {r.employee_code}
                        </span>
                      )}
                    </TableCell>
                    <TableCell className="tabular">
                      {r.first_in ? formatISTTime(r.first_in) : EMPTY}
                    </TableCell>
                    <TableCell
                      className={cn("tabular", !r.last_out && "text-muted-foreground")}
                    >
                      {r.last_out ? formatISTTime(r.last_out) : EMPTY}
                    </TableCell>
                    <TableCell className="tabular">
                      {formatWorked(r.worked_minutes)}
                    </TableCell>
                    <TableCell>
                      <Badge variant={CLASSIFICATION_VARIANT[r.classification]} dot>
                        {CLASSIFICATION_LABEL[r.classification]}
                      </Badge>
                    </TableCell>
                    <TableCell>
                      {r.attendance_status ? (
                        <Badge variant="outline">
                          {ATTENDANCE_STATUS_LABEL[
                            r.attendance_status as AttendanceStatus
                          ] ?? r.attendance_status}
                        </Badge>
                      ) : (
                        <span className="text-sm text-muted-foreground">{EMPTY}</span>
                      )}
                    </TableCell>
                    <TableCell className="text-sm text-muted-foreground">
                      {reason ?? EMPTY}
                    </TableCell>
                    <TableCell className="text-right" onClick={(e) => e.stopPropagation()}>
                      <Button
                        variant="ghost"
                        size="icon"
                        className="h-7 w-7"
                        aria-label={`Set attendance for ${r.employee_name ?? "employee"}`}
                        onClick={() => setEditing(r)}
                      >
                        <Pencil className="h-3.5 w-3.5" />
                      </Button>
                    </TableCell>
                  </TableRow>
                );
              })}
```

- [x] **Step 5: Add the pagination footer and remove `AttendanceDayPopover`**

Inside the `<div className="overflow-hidden rounded-lg border border-border bg-card">` wrapper, after the error/empty states and before the closing `</div>`, add:

```tsx
        {showRows && query.data && (
          <Pagination
            total={query.data.total}
            limit={query.data.limit}
            offset={query.data.offset}
            onPageChange={(next) => setRawOffset(String(next))}
          />
        )}
```

Delete the entire `<AttendanceDayPopover ... />` block (previously right after the table wrapper `</div>` and before `<RecordDecisionDialog ...>`) and its `DaySummaryShape` helper type, and remove the now-unused `AttendanceDayPopover` import. Add the `Pagination` import: `import { Pagination } from "@/components/data/pagination";`.

Keep `<RecordDecisionDialog row={editing} date={date} onClose={...} />` exactly as-is (Phase 8 editing must not change).

- [x] **Step 6: Typecheck**

Run: `docker exec wms-frontend-1 npm run typecheck`
Expected: fails only on the still-missing `/attendance/records/[employeeId]` route referenced by `openDetail`'s string literal (not a type error — Next.js typed routes may or may not catch this; if `npm run typecheck` doesn't cover route literals, this step should PASS cleanly). If it fails for any other reason, stop and investigate.

- [x] **Step 7: Manual verification with the dev server**

Run: `docker exec wms-frontend-1 npm run build` (or start the dev server per the repo's `run` skill) and in a browser:
1. Navigate to Attendance → Records.
2. Confirm the 4 large cards are gone and the compact summary line reads `<date>` then `Present N · Needs review N · Punch missing N · No punch N`.
3. Confirm the word "Incomplete" and "Complete" appear nowhere on the page.
4. Type into the search box; confirm the table narrows to matching employees after a short pause.
5. Change the Status filter through all 5 options; confirm the table updates each time.
6. If more than 15 employees exist for the day, confirm Prev/Next pagination works and the summary counts stay constant across pages.
7. Click a row (not the pencil icon); confirm it navigates to `/attendance/records/<employee_id>?date=<date>` (Task 5) rather than opening a popover.
8. Click the pencil icon on a row; confirm `RecordDecisionDialog` still opens and saves exactly as before.
9. Switch to the Calendar tab; confirm it is visually and functionally unchanged, and its own day-popover still opens on a day click.
10. Switch to the Leave and Holidays tabs; confirm both still render normally (no code in this task touches them, but the shared `AttendanceView` shell does still import `AttendanceRecords`, so a broken import would break the whole page).

---

## Task 5: Frontend — minimal Phase 9B stub route

**Files:**
- Create: `frontend/src/app/(app)/attendance/records/[employeeId]/page.tsx`

**Interfaces:**
- Consumes: `employeeId` route param, `date` query param (both supplied by Task 4's `openDetail`).
- Produces: nothing consumed elsewhere in this phase — this is intentionally a dead end until Phase 9B.

- [x] **Step 1: Create the stub page**

```tsx
"use client";

import { Suspense } from "react";
import Link from "next/link";
import { useParams, useSearchParams } from "next/navigation";
import { ArrowLeft } from "lucide-react";

import { RequireCapability } from "@/components/auth/require-capability";
import { EmptyState } from "@/components/feedback/empty-state";
import { PageHeader } from "@/components/shell/page-header";

function AttendanceRecordDetail() {
  const { employeeId } = useParams<{ employeeId: string }>();
  const searchParams = useSearchParams();
  const date = searchParams.get("date");

  return (
    <RequireCapability capability="attendance.manage">
      <Link
        href={date ? `/attendance?tab=history&date=${date}` : "/attendance?tab=history"}
        className="inline-flex items-center gap-1 text-sm text-primary hover:underline"
      >
        <ArrowLeft className="h-3.5 w-3.5" />
        Records
      </Link>
      <PageHeader
        className="mt-2"
        title="Attendance detail"
        subtitle={date ? `Employee ${employeeId} · ${date}` : `Employee ${employeeId}`}
      />
      <EmptyState
        title="Coming in Phase 9B"
        description="The full daily attendance detail view — biometric evidence, official record and edit history side by side — is not built yet. Use the Records table to review and set this day for now."
      />
    </RequireCapability>
  );
}

export default function AttendanceRecordDetailPage() {
  return (
    <Suspense>
      <AttendanceRecordDetail />
    </Suspense>
  );
}
```

- [x] **Step 2: Typecheck**

Run: `docker exec wms-frontend-1 npm run typecheck`
Expected: PASS with zero errors (this resolves the last failure from Task 4 Step 6, if any).

- [x] **Step 3: Manual verification**

With the dev server running, click a Records row and confirm the new page renders: back link to Records, "Attendance detail" header with the employee id and date, and the "Coming in Phase 9B" empty state. Confirm a non-PM account gets the `RequireCapability` "Not allowed" state instead.

---

## Task 6: Frontend — remove the "Record attendance" entry points

**Files:**
- Modify: `frontend/src/features/attendance/components/attendance-view.tsx`
- Modify: `frontend/src/features/dashboard/project-manager-dashboard.tsx`
- Delete: `frontend/src/app/(app)/attendance/new/page.tsx` (and the now-empty `new/` directory)
- Delete: `frontend/src/features/attendance/components/attendance-sheet.tsx`

**Interfaces:**
- Consumes: nothing from other tasks.
- Produces: nothing consumed elsewhere — `AttendanceSheet` has exactly one caller (`new/page.tsx`), confirmed during investigation.

- [x] **Step 1: Remove the header button in `attendance-view.tsx`**

Remove this block from the `actions` JSX (around line 70):

```tsx
      {canManage && (
        <Button asChild>
          <Link href="/attendance/new">
            <Plus className="h-4 w-4" />
            Record attendance
          </Link>
        </Button>
      )}
```

Remove the now-unused `Plus` import from `lucide-react` (keep `Download`, `CalendarOff`). Leave the `Export` button (`toast.info("Export - coming soon")`) exactly as-is — it stays in the same top-right actions area.

- [x] **Step 2: Remove the dashboard shortcut in `project-manager-dashboard.tsx`**

Remove this block from the "Shortcuts" card (around line 195):

```tsx
              <Button asChild className="justify-start" variant="secondary">
                <Link href="/attendance/new">
                  <ClipboardList className="h-4 w-4" /> Record attendance
                </Link>
              </Button>
```

Remove the now-unused `ClipboardList` import if nothing else in the file uses it (grep the file first — `Search` for other `ClipboardList` usages before deleting the import).

- [x] **Step 3: Delete the old route and its component**

Delete `frontend/src/app/(app)/attendance/new/page.tsx` and the resulting empty `frontend/src/app/(app)/attendance/new/` directory.

Delete `frontend/src/features/attendance/components/attendance-sheet.tsx`.

Leave `useAttendanceSheet`, `useBulkSaveAttendance` (`hooks.ts`), `getSheet`, `bulkSave` (`api.ts`), and the `AttendanceSheet`/`AttendanceBulkSaveBody` types (`types.ts`) in place — they wrap real, tested, working backend endpoints (`GET /attendance/sheet`, `POST /attendance/bulk`) that are not being removed this phase. Report them as orphaned-but-preserved rather than deleting, per the "do not blindly delete" instruction.

- [x] **Step 4: Typecheck and build**

Run: `docker exec wms-frontend-1 npm run typecheck`
Expected: PASS.

Run: `docker exec wms-frontend-1 npm run build`
Expected: PASS (confirms no other file imports the deleted `AttendanceSheet` component or `new/page.tsx`).

- [x] **Step 5: Confirm `/attendance/new` is unreachable and run the existing frontend unit tests**

Run: `docker exec wms-frontend-1 npm test` (or the repo's actual unit test script — check `package.json`)
Expected: PASS, including `frontend/src/features/attendance/tabs.test.ts` and the biometric pure-function tests (`day-detail.test.ts`, `mapping-format.test.ts`, `popover-position.test.ts`), none of which should be affected by this task.

Manually confirm in the browser: the Attendance page header no longer shows "Record attendance"; the PM dashboard "Shortcuts" card no longer shows "Record attendance"; navigating directly to `/attendance/new` in the URL bar now 404s (Next.js App Router removes the route once the page file is deleted).

---

## Self-review checklist (run after all tasks land)

- [x] Every Phase 9A instruction section (1–16 from the spec) maps to a task above: header (Task 6), old-UI removal (Task 6), tab label unchanged (no task needed — already "Records"), compact summary (Task 4 Step 3), status vocabulary (Task 3), filters (Task 4 Step 2), table design (Task 4 Steps 4–5), pagination (Tasks 1, 2, 4), employee search (Tasks 1, 2, 4), popover removal + detail route (Tasks 4 Step 5, 5), calendar untouched (verified in Task 4 Step 7.9), KPI cards untouched (not in scope, no task touches `attendance-kpis.tsx`), database safety (no migration in any task), git safety (no task commits).
- [x] No task introduces the words "Incomplete" or "Complete" into any Records-facing JSX or label map.
- [x] `counts` is never filtered by `q`, `classification`, or pagination in the backend (Task 1 Step 1) — verified by `test_search_does_not_change_counts` and `test_pagination_slices_items_but_not_counts`.
