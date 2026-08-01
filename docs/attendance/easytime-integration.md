# EasyTime Pro Biometric Integration

**Status:** Phase 1 (probe) run against the live system. Phase 2 (ingestion)
implemented, migration **not applied to production**, feature **off by default**.
**Branch:** `feature/punch-ingestion`
**Applies to:** CoreOps backend, `connectors/easytime`, frontend attendance surfaces.

No production table, endpoint, flag or attendance behaviour has changed.
Existing day-based attendance (`attendance_records`) continues to work exactly
as before and will keep doing so until a pilot is signed off (Phase 10).

**Confirmed by the live probe (EasyTime Pro 10.2.2):** JWT auth at
`/api/jwt-api-token-auth/` with the `JWT` header scheme, raw transactions at
`/iclock/api/transactions/`, pagination works, external transaction ids are
present and stable, employee filtering works, intermediate punches are returned,
and some punches are uploaded the following day. **Every observed punch had
`punch_state_raw = "0"` and `punch_state_display = null`, so IN/OUT is
unresolved** - see `punch-state-mapping.md`.

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
| 2 (done) | `backend/app/modules/biometric/` | raw punches, sync batches, mappings, ingestion endpoint |
| 3 | `backend/app/modules/biometric/session_engine.py` | pure calculator: no FastAPI, no SQLAlchemy |
| 4 | `backend/app/modules/biometric/` | sessions, day summaries, exceptions, recalc task |
| 6 | `backend/app/modules/permissions/` | permission requests + monthly ledger |
| 7 | `backend/app/modules/attendance_corrections/` | regularization + official duty |
| 8 | `backend/app/modules/attendance/reconciliation.py` | combines biometric + leave + permission |
| 9 | `backend/app/modules/reports_export/` | monthly attendance workbook (PM only) |

Phase 2 landed as a single module (`models.py` / `schemas.py` / `service.py` /
`router.py` / `dependencies.py` / `constants.py`), matching the repository's
existing 5-file module shape. There is deliberately **no `repository.py`**: no
module in this codebase has one - queries live in `service.py` via
`db.execute(select(...))`, and the service is the repository layer. The planned
`backend/app/integrations/easytime/` package was **not** created either: the
backend receives an already-normalized payload, so there is no vendor mapping
left to do server-side. EasyTime HTTP access stays entirely in
`connectors/easytime/`.

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

### CoreOps backend - added in Phase 2

Now present in `app/core/config.py` and `backend/.env.example` (all default-off,
matching the existing `TASK_CONTINUATION_ENABLED` / `REPORT_DAY_PARTS_ENABLED`
precedent):

```
EASYTIME_INGESTION_ENABLED=false
EASYTIME_CONNECTOR_TOKEN=
ATTENDANCE_TIMEZONE=Asia/Kolkata
BIOMETRIC_EXACT_CODE_MATCH_ENABLED=true
```

Still **not** added - they belong to later phases and nothing reads them yet:
`BIOMETRIC_UI_ENABLED`, `BIOMETRIC_ATTENDANCE_APPLY_ENABLED`,
`PERMISSION_WORKFLOW_ENABLED`, `BIOMETRIC_SYNC_STALE_MINUTES`.

The EasyTime username/password are deliberately absent: the VPS never talks to
EasyTime.

### Frontend - Phase 5, not added yet

`NEXT_PUBLIC_BIOMETRIC_UI_ENABLED=false` only. Never any EasyTime credential.

---

## 6. Ingestion contract (Phase 2, delivered)

### Endpoint

```
POST /api/v1/integrations/easytime/punches/batch
X-CoreOps-Connector-Token: <connector token>
Content-Type: application/json
```

**The header changed from the Phase 1 preview.** It is `X-CoreOps-Connector-Token`,
not `Authorization: Bearer`. A dedicated header cannot be confused with (or fall
back to) a user JWT, and it keeps the connector's machine identity structurally
separate from every human credential path. The token is **never** accepted as a
query parameter - query strings land in access logs, proxy logs, browser history
and `Referer` headers.

### Request

```json
{
  "provider": "easytime",
  "connector_id": "admin-pc-01",
  "batch_key": "2026-07-29T18:00:00+05:30/admin-pc-01",
  "source_from_time": "2026-07-29T00:00:00+05:30",
  "source_to_time": "2026-07-29T23:59:59+05:30",
  "punches": [
    {
      "external_transaction_id": "10432",
      "employee_code": "61",
      "punch_time": "2026-07-29T10:12:10+05:30",
      "raw_punch_state": "0",
      "punch_state_display": null,
      "terminal_alias": "F22/ID",
      "terminal_serial_number": "CDC-DEV-01",
      "verify_type": "1",
      "source": "1",
      "upload_time": "2026-07-29T10:12:14+05:30",
      "raw_payload": {}
    }
  ]
}
```

`punch_state` (the Phase 1 `NormalizedPunch` field name) is accepted as an alias
for `raw_punch_state`, and `verification_type` for `verify_type`, so the existing
connector DTO needs no change. `punch_state` stays the **vendor code**: IN/OUT is
resolved server-side from a reviewed mapping table in a later phase, so a wrong
mapping is fixed by editing one table and recalculating - never by editing raw
punches.

Limits and validation:

| Rule | Behaviour |
|---|---|
| `punches` empty, or more than **1000** | `422`, nothing stored |
| unsupported `provider` | `422` |
| missing required key, or an oversized string | `422` |
| blank transaction id / employee code | that record counted `invalid`, the rest still stored |
| unparseable or out-of-range `punch_time` | that record counted `invalid`, the rest still stored |
| unparseable `upload_time` | punch stored with `upload_time = NULL` |
| `raw_punch_state` null or any value | accepted verbatim, never validated against a vocabulary |

Per-record validation is deliberate: one bad row in a 500-punch page must cost
one record, not a `422` that discards 499 good punches.

### Response

```json
{
  "batch_id": "...",
  "received": 128,
  "inserted": 120,
  "duplicates": 5,
  "unmapped": 3,
  "invalid": 0,
  "status": "completed_with_errors"
}
```

Counting contract, and it is exact:

```
inserted + duplicates + invalid == received
unmapped is a SUBSET of inserted   (newly inserted rows with employee_id IS NULL)
```

`unmapped` is **not** a fourth disjoint bucket. An unmapped punch is stored; it
is simply not attributable to a CoreOps employee yet.

Status is `completed` when everything was valid and mapped,
`completed_with_errors` when anything was invalid or unmapped, `failed` when every
record was rejected or storage itself failed. `200` (not `201`) because a retry
that creates nothing is a normal, expected outcome.

### Administrative endpoints (project_manager, backend only - no frontend)

```
GET    /api/v1/biometric/mappings
POST   /api/v1/biometric/mappings
DELETE /api/v1/biometric/mappings/{id}      (deactivate; never deletes)
GET    /api/v1/biometric/sync-batches       (?provider= &status= &limit= &offset=)
```

---

## 6a. Database (migration `0063_biometric_punch_ingestion`)

Three additive tables. No existing table, column, enum, index or constraint was
altered.

**`biometric_punches`** - the immutable raw event log. Carries `created_at` but
deliberately **no `updated_at` and no `deleted_at`** (mirroring `audit_logs`): a
punch is a fact, never edited, never removed.

| Constraint / index | Why |
|---|---|
| `UNIQUE (provider, external_transaction_id)` | the idempotency anchor |
| `(employee_id, punch_time)` | per-employee timeline, the only read shape later phases need |
| `(external_employee_code, punch_time)` | the same timeline for punches that never mapped |
| `(punch_time)` | date-range sweeps; not served by the composite above, whose leading column is nullable |
| `(upload_time)` | "what arrived late?" - the recalculation driver |
| `(sync_batch_id)` | batch provenance; also keeps `ON DELETE SET NULL` off a sequential scan |

`employee_id` is **nullable** and its FK is `ON DELETE SET NULL`, so purging an
employee can never cascade away attendance evidence.

**`biometric_sync_batches`** - one row per ingestion attempt, with counters,
status and a sanitized error. `UNIQUE (provider, connector_id, batch_key)`.
`status` is `VARCHAR + CHECK`, not a new Postgres enum, following the
`benchmark_type` / `report_mode` / `access_type` precedent.

**`biometric_employee_mappings`** - external code to CoreOps employee. A
**partial** unique index `(provider, external_employee_code) WHERE is_active`
guarantees one external code can point at only one employee at a time, while
superseded rows stay for history.

---

## 6b. Idempotency

Duplicate protection is the database unique index, **not** an application-side
pre-check. Insertion is a single
`INSERT ... ON CONFLICT (provider, external_transaction_id) DO NOTHING RETURNING`
per chunk of 500 rows.

- **Retries.** Re-POSTing an identical payload inserts zero rows and reports
  every punch as a duplicate. The connector re-fetches an overlap window each
  run and relies on exactly this.
- **Concurrency.** Two connectors replaying the same window race on the unique
  index; Postgres serializes them, the loser's rows are skipped rather than
  rolled back, and every genuinely new punch in the same statement still lands.
- **Partial failure.** A plain `INSERT` would abort the whole statement on the
  first collision and take the valid rows with it. A `SELECT`-then-`INSERT`
  pre-check would be a race. `ON CONFLICT DO NOTHING` is the only option that is
  both correct under concurrency and single-round-trip. Its cost: `RETURNING`
  yields only the rows that actually inserted, so duplicates are computed by
  subtraction rather than reported directly.
- **Within one request.** Repeated transaction ids inside a single payload are
  de-duplicated in Python (first occurrence wins) so the counts stay honest; the
  constraint would absorb them regardless.

`batch_key` is **connector-generated**. Only the connector knows whether a POST
is a retry or a genuinely new window that happens to overlap. If it is omitted,
the backend **derives** a deterministic key by hashing
`provider + connector_id + window + sorted external transaction ids`, so an
identical retried payload still resolves the same batch row. Punch-level
idempotency does not depend on the key at all - the key only controls whether a
retry reuses one batch record or opens a second one. A re-POSTed key updates the
existing row in place, so its counters always describe the most recent attempt
and therefore always agree with the response the connector just received.

Transaction boundaries are explicit: the batch row is created and committed
first (so a crash mid-write still leaves an operator-visible record), then the
punches and counters commit together, and only on failure is the batch reopened
and marked `failed`.

---

## 6c. Employee mapping

Resolution order, and nothing else is ever tried:

1. An **active row** in `biometric_employee_mappings` for
   `(provider, external_employee_code)`. Explicit, human-verified, always
   authoritative - it wins even when an exact code match also exists.
2. **Exact, case-sensitive** match on `employees.employee_code` among
   non-deleted employees. Deterministic because that column carries a partial
   unique index (`employees_code_uq WHERE deleted_at IS NULL`), so it resolves to
   at most one employee and can never guess. Disable with
   `BIOMETRIC_EXACT_CODE_MATCH_ENABLED=false`.
3. Otherwise **unmapped**: the punch is stored with `employee_id = NULL`.

**Names are never used for matching, in any form.** In practice step 2 rarely
fires: the live probe returned bare numeric EasyTime codes (`61`) while CoreOps
uses prefixed codes (`EMP225`), which is exactly why the mapping table exists and
why equality is not assumed.

Two queries resolve a whole batch, whatever its size. Mapping changes are
audited; re-pointing a code at a different employee deactivates the previous row
rather than editing it. **Punches already stored are never rewritten** - they are
immutable, and re-attributing historical punches is a later phase's job.

---

## 6d. Security

| Concern | How it is handled |
|---|---|
| Storage | `EASYTIME_CONNECTOR_TOKEN` lives only in the server `.env`; never in git, never in a `NEXT_PUBLIC_*` variable, never in the browser |
| Comparison | `secrets.compare_digest` - constant time, so response timing cannot recover the secret |
| Transport | dedicated `X-CoreOps-Connector-Token` header; query parameters are rejected by construction |
| Disabled by default | `EASYTIME_INGESTION_ENABLED=false` - the route is mounted but answers a bare `404`, so a disabled deployment does not advertise that ingestion exists |
| Fail closed | with `ENV` outside `local`/`test`, `Settings` **refuses to boot** if ingestion is enabled without a token of at least 32 characters; the dependency independently rejects everything when no token is configured |
| Generic failures | one message for "no token" and "wrong token" alike |
| Redaction | the supplied token is never logged, echoed, or written to an audit row - auth-failure audit rows carry only the slug `missing` / `invalid` |
| Payload hygiene | `raw_payload` drops PII keys (names, photo, face/fingerprint/vein/iris templates, contact details), any secret-shaped key, all nested objects and arrays, and any string over 500 characters; key count and total size are capped |
| Error text | `error_message` on a failed batch carries only the exception **class name** - never SQL, bound parameters, or connection strings |

---

## 6e. Audit and observability

Audit is **event-level, never per punch**: a successful batch of 500 punches
writes zero audit rows. One row per punch would drown the log and make it useless
for the security events it exists to record. Recorded actions:

```
biometric.connector.auth_failure
biometric.batch.failed
biometric.batch.unmapped_high     (>= 50% unmapped, minimum 5 records)
biometric.mapping.create
biometric.mapping.change
biometric.mapping.deactivate
```

Every batch emits one structured line on `coreops.biometric.ingestion` carrying
`batch_id`, `connector_id`, `provider`, `received`, `inserted`, `duplicates`,
`unmapped`, `invalid`, `duration_ms` and `status`. Never logged: the connector
token, any EasyTime password/JWT/refresh token, biometric templates, face data or
photos.

---

## 7. Timezone

EasyTime returns naive local timestamps (`2026-07-29 10:12:10`). The connector
attaches the `Asia/Kolkata` offset at normalization time; when it does not, the
backend applies `ATTENDANCE_TIMEZONE` (default `Asia/Kolkata`) to any naive value
it receives. Everything is then converted to UTC and stored as
`TIMESTAMP WITH TIME ZONE`, matching every existing CoreOps table.

A misconfigured `ATTENDANCE_TIMEZONE` raises rather than falling back to UTC:
silently reading naive IST wall-clock values as UTC would shift every punch by
5h30m, which is precisely the kind of quiet, total corruption this integration
exists to avoid.

The **original timestamp text** is preserved in `raw_payload` under the reserved
keys `_punch_time_text` and `_upload_time_text`, so the exact string the device
reported survives normalization and can be compared against the EasyTime UI.

`punch_time` and `upload_time` are never conflated:

- `punch_time` is when the person actually punched - the attendance event.
- `upload_time` is when EasyTime received the record, which the live probe
  confirmed can be the **following morning**.

Because Phase 2 derives nothing at write time, a day is never "closed". Late
punches simply insert later, and any future phase can recalculate that day from
the raw rows. Nothing assumes a day's records are complete at midnight.

---

## 8. Phase 2 limitations - read this before Phase 3

Phase 2 is storage, and only storage.

- **IN/OUT semantics are unresolved.** Every live punch was state `"0"` with a
  null display label. Nothing infers direction, and there is no direction column.
- **No session calculation.** No session start/end, no pairing, no alternating
  logic, no "first punch is IN, last is OUT".
- **No working hours,** overtime, outside duration, late arrival, early
  departure or attendance status.
- **No automatic connector.** Nothing pushes punches yet; the endpoint waits to
  be called.
- **No employee frontend.** No page, no component, no `NEXT_PUBLIC_*` flag.
  Mapping and batch inspection are backend project-manager endpoints only.
- **No official attendance changes.** `attendance_records` is neither read nor
  written by ingestion. The only link is a nullable `employee_id` on a punch.
- **Production migration not applied.** `0063` has been applied to the local and
  test databases only.
- **Unverified:** that the API timestamp string equals what the EasyTime UI
  displays for the same punch. If they differ, a device clock or a server-side
  conversion is involved and ingestion must not be enabled until that is
  explained.
- Whether EasyTime employee codes match CoreOps `employees.employee_code`
  remains open (O-6). The live probe says they generally do **not** - hence the
  explicit mapping table. Unmapped punches are stored with `employee_id = NULL`,
  never dropped.
- Any attendance policy number remains open - see
  `attendance-policy-open-decisions.md`.

---

## 9. Phase 3 handoff - connector-side work

Phase 3 is **connector** work. The backend contract above is stable and needs no
further change to support it.

1. **CoreOps API client** (`connectors/easytime/coreops_client.py`) - POST to
   `/api/v1/integrations/easytime/punches/batch` with the
   `X-CoreOps-Connector-Token` header, mapping `NormalizedPunch` onto the request
   body and parsing the counters back.
2. **One-shot sync command** - fetch a window from EasyTime, normalize, POST,
   report the counters, exit with a meaningful code. Runnable by hand before
   anything is scheduled.
3. **Cursor storage** - a local file or SQLite row holding the last successfully
   ingested `upload_time` / window end. Never the source of truth for
   deduplication; the server's unique constraint is.
4. **Overlap** - re-fetch `SYNC_LOOKBACK_MINUTES` before the cursor every run, so
   a punch that arrived while the previous run was in flight is not skipped.
   Duplicates are expected and free.
5. **Retries** - retry transport errors and 5xx with backoff; treat `422` as a
   payload bug to report, not to retry forever; treat `401`/`404` as
   configuration errors and stop.
6. **Seven-day reconciliation** - a daily pass re-fetching the last
   `SYNC_RECONCILIATION_DAYS` days, which is what actually catches punches
   EasyTime uploaded the following morning.
7. **Packaging** - extend `package_probe.ps1` to ship the sync command with the
   same whitelist and secret checks.
8. **Task Scheduler** - a Windows scheduled task on the administrator PC running
   every `SYNC_INTERVAL_SECONDS`, plus the daily reconciliation pass.
9. **Connector health** - surface last-success time, last error and last counters
   so a silently dead connector is visible rather than assumed healthy.

Phase 3 must **not** begin punch-state interpretation. That is blocked on the
administrator sign-off in `punch-state-mapping.md`.
