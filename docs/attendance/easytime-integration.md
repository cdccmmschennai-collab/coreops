# EasyTime Pro Biometric Integration

**Status:** Phase 1 (probe) delivered, not yet run against the live system.
**Branch:** `biometric-probe`
**Applies to:** CoreOps backend, `connectors/easytime`, frontend attendance surfaces.

Nothing in this document is live yet. No production table, endpoint, flag or
attendance behaviour has changed. Existing day-based attendance
(`attendance_records`) continues to work exactly as before and will keep doing so
until a pilot is signed off (Phase 10).

---

## 1. Why a connector, and not a direct call

EasyTime Pro runs on an administrator's Windows PC and is reached at
`http://localhost:<port>` **on that PC**. Two consequences drive the whole design:

- The CoreOps VPS cannot reach it. On the VPS, `localhost` is the VPS.
- The browser must not reach it either - that would put EasyTime credentials in
  `NEXT_PUBLIC_*` variables, i.e. in every user's browser.

So an office-side connector owns the EasyTime connection and pushes normalized
punches to CoreOps over HTTPS:

```
Biometric devices
    -> EasyTime Pro (admin PC, localhost)
        -> CoreOps EasyTime connector (admin PC)   [connectors/easytime]
            -> HTTPS + connector token
                -> CoreOps API (VPS)               [Phase 2]
                    -> PostgreSQL
                        -> CoreOps frontend
```

Credential split, enforced by where the files live:

| Secret | Lives on | Never on |
|---|---|---|
| EasyTime username / password | admin PC, `connectors/easytime/.env` | the VPS, git, the browser |
| Connector shared token | both sides (`COREOPS_CONNECTOR_TOKEN` / `EASYTIME_CONNECTOR_TOKEN`) | git, the browser |
| Anything EasyTime-related | - | any `NEXT_PUBLIC_*` variable |

---

## 2. Where the code goes

Confirmed against the real repository layout (one folder per domain module under
`backend/app/modules/`, each with `models.py` / `schemas.py` / `service.py` /
`router.py`; routers registered in `app/main.py`; migrations numbered
`NNNN_slug.py`; tests flat in `backend/tests/`).

| Phase | Path | Contains |
|---|---|---|
| 1 (done) | `connectors/easytime/` | probe, client, schemas, config, offline tests |
| 2 | `backend/app/integrations/easytime/` | vendor mapper + ingestion DTOs (no business rules) |
| 2 | `backend/app/modules/biometric/` | raw punches, sync batches, ingestion endpoint |
| 3 | `backend/app/modules/biometric/session_engine.py` | pure calculator: no FastAPI, no SQLAlchemy |
| 4 | `backend/app/modules/biometric/` | sessions, day summaries, exceptions, recalc task |
| 6 | `backend/app/modules/permissions/` | permission requests + monthly ledger |
| 7 | `backend/app/modules/attendance_corrections/` | regularization + official duty |
| 8 | `backend/app/modules/attendance/reconciliation.py` | combines biometric + leave + permission |
| 9 | `backend/app/modules/reports_export/` | monthly attendance workbook (PM only) |

Rationale for a separate `biometric` module rather than growing
`modules/attendance/`: today's `attendance` module is a small day-status CRUD
(one row per employee-day, PM-managed). Biometric punches are a different
lifecycle (immutable event log, batch ingestion, recalculation) and must not
destabilise it while the two run side by side in shadow mode. They meet in one
place only - the reconciliation service in Phase 8.

---

## 3. Data flow, phase by phase

```
Phase 2   punches land in biometric_punches. Nothing else changes.
Phase 3   pure session engine, unit-tested, wired to nothing.
Phase 4   sessions + day summaries computed in SHADOW. attendance_records untouched.
Phase 5   read-only UI behind BIOMETRIC_UI_ENABLED.
Phase 6   permission workflow (Head approves, PM fallback).
Phase 7   regularization + official duty, as separate workflows.
Phase 8   reconciliation writes the final daily summary.
Phase 9   PM-only monthly Excel export.
Phase 10  pilot -> parallel run against the manual workbook -> rollout.
```

`BIOMETRIC_ATTENDANCE_APPLY_ENABLED` stays `false` until the parallel run in
Phase 10 matches the manual workbook.

---

## 4. Authentication against EasyTime - unconfirmed

The installed version is unknown, so the connector treats the API surface as a
hypothesis to be tested, not a fact:

- Auth candidates: `/api/jwt-api-token-auth/`, `/jwt-api-token-auth/`,
  `/api/api-token-auth/`, `/api-token-auth/`
- Refresh candidate: `/api/jwt-api-token-refresh/`
- Transactions candidates: `/iclock/api/transactions/`, `/api/transactions/`,
  `/att/api/transactionReport/`
- Authorization header prefix: `JWT`, `Token`, or bare - all three supported

`probe.py --discover` reports which of these exist. The confirmed paths are then
pinned in `.env`, so the sync loop never probes at runtime.

Use a dedicated integration account with the minimum permissions needed to read
transactions.

---

## 5. Environment variables

### Admin PC - `connectors/easytime/.env` (git-ignored)

See `connectors/easytime/.env.example` for the annotated list. Summary:
`EASYTIME_BASE_URL`, `EASYTIME_USERNAME`, `EASYTIME_PASSWORD`,
`EASYTIME_AUTH_MODE`, `EASYTIME_AUTH_HEADER_SCHEME`, `EASYTIME_AUTH_PATH`,
`EASYTIME_REFRESH_PATH`, `EASYTIME_TRANSACTIONS_PATH`, `EASYTIME_VERIFY_SSL`,
`EASYTIME_TIMEOUT_SECONDS`, `EASYTIME_RETRIES`, `EASYTIME_PAGE_SIZE`,
`COREOPS_API_URL`, `COREOPS_CONNECTOR_TOKEN`, `SYNC_INTERVAL_SECONDS`,
`SYNC_LOOKBACK_MINUTES`, `SYNC_RECONCILIATION_DAYS`, `TIMEZONE`.

### CoreOps backend - Phase 2, not added yet

To be appended to `backend/.env.example` and `app/core/config.py` when Phase 2
lands (all default-off, matching the existing `TASK_CONTINUATION_ENABLED` /
`REPORT_DAY_PARTS_ENABLED` precedent):

```
EASYTIME_INGESTION_ENABLED=false
EASYTIME_CONNECTOR_TOKEN=
BIOMETRIC_UI_ENABLED=false
BIOMETRIC_ATTENDANCE_APPLY_ENABLED=false
PERMISSION_WORKFLOW_ENABLED=false
BIOMETRIC_SYNC_STALE_MINUTES=15
ATTENDANCE_TIMEZONE=Asia/Kolkata
```

The EasyTime username/password are deliberately absent: the VPS never talks to
EasyTime.

### Frontend - Phase 5, not added yet

`NEXT_PUBLIC_BIOMETRIC_UI_ENABLED=false` only. Never any EasyTime credential.

---

## 6. Ingestion contract (Phase 2 preview)

```
POST /api/v1/integrations/easytime/punches/batch
Authorization: Bearer <connector token>      # NOT a user JWT
```

One punch on the wire (`NormalizedPunch` in `connectors/easytime/schemas.py`):

```json
{
  "provider": "easytime",
  "external_transaction_id": "10432",
  "employee_code": "EMP069",
  "punch_time": "2026-07-28T09:30:00+05:30",
  "punch_state": "0",
  "verify_type": "1",
  "terminal_serial_number": "CDC-DEV-01",
  "terminal_alias": "Main Gate",
  "source": "1",
  "upload_time": "2026-07-28T09:30:04+05:30",
  "raw_payload": {}
}
```

`punch_state` stays the **vendor code**. IN/OUT is resolved server-side from the
reviewed mapping table, so a wrong mapping is fixed by editing one table and
recalculating - never by editing raw punches.

Idempotency is `UNIQUE(provider, external_transaction_id)` in the database, not
an in-memory cursor. The connector re-fetches an overlap window every run and
relies on that constraint.

---

## 7. Timezone

EasyTime returns naive local timestamps (`2026-07-28 09:30:00`). The connector
does not invent a zone: it preserves the raw string, and the offset comes from
`TIMEZONE` (`Asia/Kolkata`) at normalization time. CoreOps stores
`TIMESTAMP WITH TIME ZONE`, matching every existing table.

**Unverified until the probe runs:** that the API string equals what the EasyTime
UI displays for the same punch. If they differ, a device clock or a server-side
conversion is involved and ingestion must not be enabled until that is explained.

---

## 8. What Phase 1 explicitly does not decide

- The meaning of any punch-state code - see `punch-state-mapping.md`.
- Any attendance policy number - see `attendance-policy-open-decisions.md`.
- Whether EasyTime employee codes match CoreOps `employees.employee_code`.
  CoreOps enforces uniqueness on that column
  (`employees_code_uq`, partial on `deleted_at IS NULL`), so the mapping is a
  clean lookup **if** the codes match exactly. Any that do not become an
  `UNMAPPED_EMPLOYEE` exception; their punches are still stored, never dropped.
