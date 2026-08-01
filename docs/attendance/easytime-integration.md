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
| 3, connector (done) | `connectors/easytime/` | one-shot sync, CoreOps client, cursor, run lock, packaging - section 9 |
| 3, backend | `backend/app/modules/biometric/session_engine.py` | pure calculator: no FastAPI, no SQLAlchemy |
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

## 9. Connector synchronization (Phase 3, delivered)

Phase 3 is entirely **connector** work. The Phase 2 backend contract above was
sufficient as written and needed no change to support it - no new endpoint, no
new migration, no new backend setting.

The connector's job, stated in full: **move raw punch events from EasyTime Pro
on the administrator PC to the CoreOps ingestion endpoint, and know how far it
has got.** It does not interpret them.

### 9a. Architecture

```
EasyTime Pro (admin PC, 10.2.2)
      | JWT, /iclock/api/transactions/, naive local wall-clock text
      v
client.py            authenticate, paginate, retry, RawTransaction
      v
mapper.py            attach +05:30, keep the vendor state verbatim, strip PII,
                     sort deterministically, chunk, derive the batch key
      v
coreops_client.py    POST + X-CoreOps-Connector-Token, classify the status,
                     parse and VALIDATE the counters
      v
state.py             advance the cursor - only after every batch is confirmed
```

`sync.py` is the CLI; `sync_service.py` is the orchestration; `runlock.py`
enforces one run at a time; `logging_setup.py` and `redaction.py` make the logs
safe to email.

| File | Purpose |
|---|---|
| `sync.py` | one-shot CLI: modes, console summary, exit codes |
| `sync_service.py` | window planning, fetch, normalize, batch, send, commit |
| `coreops_client.py` | the only thing that talks to CoreOps |
| `mapper.py` | `RawTransaction` -> `NormalizedPunch`, ordering, batch key |
| `state.py` | SQLite cursor, counters, last error, reconciliation stamp |
| `runlock.py` | OS-level single-instance lock |
| `logging_setup.py` | dated structured logs with redaction on every handler |
| `redaction.py` | the regex pass that runs over everything logged |
| `exit_codes.py` | the numeric contract with Task Scheduler |

### 9b. Commands

```powershell
python sync.py --once                                    # incremental
python sync.py --reconcile                               # last N days
python sync.py --reconcile-days 7                        # explicit span
python sync.py --from-date 2026-07-29 --to-date 2026-07-30   # backfill
python sync.py --status                                  # local health, offline
python sync.py --check-config                            # validate .env, offline
```

Or through the wrapper, which is what the scheduled task calls:

```powershell
.\run_sync.ps1 -Mode Incremental
.\run_sync.ps1 -Mode Reconcile -ReconcileDays 7
.\run_sync.ps1 -Mode Backfill -FromDate 2026-07-29 -ToDate 2026-07-30
.\run_sync.ps1 -Mode Status
```

**One shot, never a daemon.** Each invocation covers one window and exits. A
long-lived Python process on an office PC is a thing that silently dies in March
and is noticed in June.

### 9c. What one run does

1. Load and validate the configuration (fail closed on anything missing).
2. Open the local state database.
3. Acquire the run lock. A second invocation exits 3 immediately.
4. Read the cursor and plan the window (9d).
5. Authenticate to EasyTime, then fetch every page in the window.
6. Normalize every record; count - never silently drop - the ones that fail.
7. Sort deterministically, split into batches of `SYNC_BATCH_SIZE`, derive a
   batch key per chunk.
8. POST each batch in order, accumulating the backend's counters.
9. **Only after every batch succeeds**, advance the cursor.
10. Release the lock, print the summary, exit with a meaningful code.

### 9d. Fetch windows

| Mode | Window |
|---|---|
| incremental, with a cursor | `cursor - SYNC_LOOKBACK_MINUTES` .. now |
| incremental, first run | `now - SYNC_FIRST_RUN_LOOKBACK_HOURS` .. now |
| reconcile | the last N **calendar** days from local midnight .. now |
| backfill | `--from-date 00:00:00` .. `--to-date 23:59:59` |

Worked example of the overlap:

```
last successful source_to = 2026-07-30 14:00
next incremental from     = 2026-07-30 13:45     (15-minute overlap)
```

The overlap is the point. EasyTime accepts a punch that a device uploads long
after it happened, so a window starting exactly where the last one ended would
step over anything that landed in between. Re-fetching fifteen minutes costs
duplicates, and duplicates are free.

Guards, all of which exist because the alternative is an unbounded request
against a live office PC:

- **No unbounded first run.** With no cursor, the window is
  `SYNC_FIRST_RUN_LOOKBACK_HOURS` (default 24), never "all of history".
- **Clamping.** A cursor far in the past is clamped to `SYNC_MAX_RANGE_DAYS`
  (default 31). The run covers the oldest 31 days, moves the cursor there, and
  later runs continue catching up in bounded steps.
- **Backfill needs both dates**, and refuses a range over the limit without
  `--force`.
- **A cursor in the future** (clock moved backwards, state hand-edited)
  re-fetches only the overlap window rather than extending into the future.

### 9e. Deterministic batch keys

```
et1-<sha256 hex>   over, NUL-separated, in this order:
    version tag | connector_id | provider | source_from | source_to
                | batch_number | each external transaction id, in batch order
```

68 characters, inside the backend's 128-char column. Properties, all of which
the sync loop depends on:

- **Retry stability.** Re-sending the same batch produces the same key, so
  CoreOps updates the existing `biometric_sync_batches` row rather than opening
  a second one for work that already has a record.
- **Chunk distinctness.** `batch_number` and the id list both change between
  chunks.
- **No secrets** are inputs, so the key is safe to print, log and store.
- **No clock, no randomness.** A key derived from `time.time()` would differ on
  every retry - precisely the property that must not exist.

Ordering is fixed before chunking (punch time, then transaction id, numerically
for numeric ids), which is what makes a replay reproduce the same chunks.

### 9f. Four layers of idempotency

They are not redundant; each covers what the one below cannot.

| Layer | Mechanism | What it absorbs |
|---|---|---|
| connector overlap | re-fetch `SYNC_LOOKBACK_MINUTES` | punches that arrived mid-run |
| batch key | deterministic SHA-256 | a retry reusing one sync-batch row |
| backend batch resolution | `ON CONFLICT` on `(provider, connector_id, batch_key)` | two requests racing on the same key |
| **punch uniqueness** | `UNIQUE (provider, external_transaction_id)` | **everything else** |

The last row is the one that actually guarantees correctness. The other three
are about tidiness and operational identity: **a lost, wrong or duplicated batch
key can never cause a duplicate punch.** That is what makes replay safe, and
replay is what makes every other design decision here affordable.

### 9g. Batch sizing and partial failure

`SYNC_BATCH_SIZE` (default 500) is validated at load time against the backend's
1000-punch ceiling, so an oversized value is refused on this PC rather than as a
422 on every POST at 03:00 on a Sunday.

If batch 1 of 3 succeeds and batch 2 fails:

- the cursor does **not** move;
- the run fails with the batch's exit code;
- the next run re-fetches the whole window and re-sends batch 1 as well.

Batch 1's punches come back as `duplicates` and nothing is stored twice. The
alternative - advancing past a window that was only partly ingested - loses
punches permanently and silently. Duplicates are free; missing punches are not.

### 9h. Local state

```
C:\ProgramData\CoreOps\EasyTimeConnector\data\state.db      (SQLite)
```

Configurable with `SYNC_STATE_PATH`; a development checkout uses
`connectors/easytime/data/state.db`.

One row per `connector_id`, holding `last_successful_sync_time`,
`last_successful_source_to`, `last_batch_key`, `last_coreops_batch_id`, the five
`last_records_*` counters, `last_success_at`, `last_reconciliation_at`,
`last_error_code` and `last_error_at`. A `schema_meta` table carries
`schema_version`; a file written by a **newer** connector is refused rather than
downgraded.

SQLite rather than a JSON file because the cursor update must be atomic against
a process that can be killed at any instant. A JSON write is
read-modify-write and can leave a truncated file; SQLite gives a real
transaction, in the standard library, with no extra dependency on the admin PC.

**No secret is ever stored here** - not the EasyTime password, not the JWT, not
the connector token. Timestamps, counters and a batch id, and nothing else.

Crash behaviour:

| Process dies... | Result |
|---|---|
| between fetch and upload | nothing written; next run re-fetches the window |
| after upload, before the cursor update | next run replays a stored window; Postgres reports duplicates |
| mid-`record_success` | one transaction: the row is entirely the old run's or entirely the new one's |
| holding the run lock | the kernel releases the lock; the next run takes it |

A **failed** run writes `last_error_code`/`last_error_at` only. It never
disturbs the cursor or the last-success fields, so a failure can never be
mistaken for progress.

### 9i. Retry policy

| Failure | Behaviour |
|---|---|
| transport timeout, connection refused | bounded retry with jittered backoff |
| `429`, `500`, `502`, `503`, `504` | bounded retry with jittered backoff |
| `409` | bounded retry - the backend's sync-batch race is transient |
| `401`, `403` | **stop.** The same token will be rejected forever |
| `404` | **stop.** Wrong URL, or the backend has ingestion disabled |
| `422` | **stop.** A contract bug; the sanitized response is kept as evidence |
| any other 4xx | **stop** |
| a 2xx whose body is not a valid batch result | **stop** |

Backoff is roughly immediate, 2s, 5s, 10s with +/-25% jitter, capped by
`COREOPS_RETRIES` (default 4 attempts). Bounded on purpose: a connector that
runs every five minutes gains nothing from a backoff longer than its own
schedule - the next run simply picks the window up again.

A 200 with an unparseable body, a missing counter, or counters that do not
satisfy `inserted + duplicates + invalid == received` is treated as a
**failure**. Accepting it would advance the cursor over punches that may never
have been stored.

### 9j. Reconciliation - the late-punch net

```powershell
python sync.py --reconcile          # SYNC_RECONCILIATION_DAYS, default 7
python sync.py --reconcile-days 7
```

The live probe proved that some punches reach EasyTime **the following
morning**, after the incremental run for that evening has finished and moved on.
Nothing in the incremental cursor can recover them, because the cursor is
already past that time. The reconciliation pass re-sends the last N calendar
days through the same endpoint and lets
`UNIQUE (provider, external_transaction_id)` sort out what is new.

It re-sends; it never deletes, and never alters a stored punch's timestamps -
the connector has no code path that could. It stamps `last_reconciliation_at`
and deliberately does **not** move the incremental cursor: its window ends at
`now` but starts days in the past, and letting a backward-looking pass write the
forward cursor is how a rewind happens.

Safe to run repeatedly. A second identical pass reports every punch as a
duplicate and stores nothing.

### 9k. Backfill

```powershell
python sync.py --from-date 2026-07-29 --to-date 2026-07-30
```

Both dates required - there is deliberately no default and no "since the
beginning". An unbounded backfill against a live EasyTime install is the one
command here that can take an office PC down, and it must never be reachable by
forgetting an argument. Ranges over `SYNC_MAX_RANGE_DAYS` need `--force`. The
console announces the range before the run starts. It uses the same endpoint,
the same batch keys and the same idempotency, and does **not** move the
incremental cursor.

### 9l. Logging

```
C:\ProgramData\CoreOps\EasyTimeConnector\logs\sync-YYYYMMDD.log
```

Configurable with `SYNC_LOG_DIR`. One file per **day**, not per run: 288 runs a
day for a year would be 105,000 files. Every line carries the run id.

One structured summary line per run, in the same `key=value` shape the backend's
ingestion logger uses:

```
sync.run mode=incremental connector_id=admin-pc-01
  source_from=... source_to=... pages=2 fetched=41 normalized=41
  rejected_locally=0 batches_planned=1 batches_sent=1
  received=41 inserted=38 duplicates=3 unmapped=0 invalid=0
  duration_s=1.84 status=success exit=0
```

**Never logged:** the EasyTime password, the EasyTime JWT or refresh token, the
CoreOps connector token, any Authorization header, face data, fingerprint
templates or photos. Two independent layers enforce it - the code never passes
them to a logger, and `redaction.sanitize_text` runs over every formatted record
(including tracebacks) on its way to every handler. `run_sync.ps1` applies a
third regex pass to the console output it captures.

A log directory that cannot be created is a warning, not a failure. Losing the
ability to write a log must never cost punches.

### 9m. Exit codes

| Code | Meaning | Who acts |
|---|---|---|
| 0 | success | nobody |
| 2 | invalid configuration | whoever edits `.env` on this PC |
| 3 | another run is active | nobody - expected under a 5-minute schedule |
| 4 | EasyTime authentication failure | the EasyTime integration account owner |
| 5 | EasyTime transport/API failure | whoever owns EasyTime Pro on this PC |
| 6 | CoreOps authentication failure | whoever holds the connector token |
| 7 | CoreOps payload rejection | whoever maintains the connector (a contract bug) |
| 8 | CoreOps transport/server failure | whoever operates the CoreOps VPS |
| 9 | local state failure | whoever administers this PC's ProgramData |

1 is left unused on purpose: it is what Python returns for an unhandled
traceback, so `exit 1` always reads as "the connector failed in a way it did not
anticipate".

### 9n. Configuration

Added to `connectors/easytime/.env` (git-ignored; `.env.example` documents every
key and holds no value for any secret):

```env
COREOPS_API_URL=https://coreops.cdccmms.com/api/v1
COREOPS_CONNECTOR_TOKEN=            # must match EASYTIME_CONNECTOR_TOKEN on the VPS
COREOPS_TIMEOUT_SECONDS=30
COREOPS_RETRIES=4
CONNECTOR_ID=admin-pc-01
SYNC_INTERVAL_SECONDS=300           # documentation for the scheduled task
SYNC_LOOKBACK_MINUTES=15
SYNC_RECONCILIATION_DAYS=7
SYNC_FIRST_RUN_LOOKBACK_HOURS=24
SYNC_MAX_RANGE_DAYS=31
SYNC_BATCH_SIZE=500
# SYNC_STATE_PATH= / SYNC_LOG_DIR= / SYNC_LOCK_PATH=   blank = ProgramData
```

Every value is validated at load time and the connector **fails closed**: a
missing URL or token stops the run before a single punch is fetched, rather than
producing a batch with nowhere to go.

### 9o. Run locking

One run at a time, enforced by an OS-level exclusive lock on a file
(`msvcrt.locking` on Windows, `fcntl.flock` elsewhere), defaulting to
`...\data\sync.lock`.

Task Scheduler's "do not start a new instance" is **not** enough on its own: it
does not cover a manual `run_sync.ps1` typed while the scheduled run is
in flight, it does not cover a second task someone adds later, and it is a
checkbox that can be unticked. Both layers are used.

A PID file was rejected deliberately. The usual liveness probe,
`os.kill(pid, 0)`, does not send a signal on Windows - it calls
`TerminateProcess`, so the "check" would kill whatever process now owns that
PID. An OS lock is also strictly better: **the kernel releases it when the
holder dies**, so a crashed run leaves a lock file that is not locked and the
next run takes it immediately. There is no stale-lock recovery logic because
there is no stale-lock state.

### 9p. Windows Task Scheduler - documented, NOT activated

Phase 3 ships these definitions for review. `install_connector.ps1` creates them
only when `-CreateScheduledTask` is passed explicitly, and that switch is
**off**. A connector that starts syncing because someone ran an installer is a
connector nobody decided to switch on.

**Task 1 - incremental sync**

| Setting | Value |
|---|---|
| Action | `powershell.exe -NoProfile -ExecutionPolicy Bypass -File "<path>\run_sync.ps1" -Mode Incremental` |
| Trigger | once, repeat every **5 minutes**, indefinitely |
| Run whether the user is logged on or not | yes |
| If the task is already running | **do not start a new instance** |
| Run as soon as possible after a missed start | yes |
| Restart on failure | every 5 minutes, up to 3 times |
| Stop if it runs longer than | 30 minutes |
| Do not stop on batteries / start on batteries | yes |

**Task 2 - daily reconciliation**

| Setting | Value |
|---|---|
| Action | `... -File "<path>\run_sync.ps1" -Mode Reconcile` |
| Trigger | daily at **02:30** |
| Other settings | as above |

Before activating either: run `-Mode CheckConfig`, then `-Mode Status`, then at
least one manual `-Mode Incremental`, and confirm rows appear in
`biometric_punches` via `GET /api/v1/biometric/sync-batches`.

The account that runs the tasks must be able to write
`C:\ProgramData\CoreOps\EasyTimeConnector\{data,logs}` - `install_connector.ps1`
tests exactly that and reports it.

### 9q. Packaging and installation

```powershell
.\package_connector.ps1     # builds dist\CoreOps-EasyTime-Connector.zip
```

Whitelist-based, not exclusion-based: if a file is not named in the script it
does not reach the archive, so a secret cannot be let through by a pattern that
did not anticipate it. The build **fails** if `.env.example` carries a non-empty
password, token or secret, and the finished ZIP is re-opened and verified entry
by entry.

Never shipped: `.env`, `.venv\`, `logs\`, `data\`, `probe-output\`, `dist\`,
`tests\`, `*.db`, `*.lock`, `*.log`, `__pycache__\`, `.pytest_cache\`, any git
metadata.

On the admin PC:

```powershell
.\install_connector.ps1              # creates the ProgramData layout
.\setup_probe.ps1                    # creates .venv, installs requirements
copy .env.example .env ; notepad .env   # type the credentials yourself
.\run_sync.ps1 -Mode CheckConfig
.\run_sync.ps1 -Mode Status
.\run_sync.ps1 -Mode Incremental
```

No installer writes a credential, on purpose.

### 9r. Health

```powershell
python sync.py --status        # or  .\run_sync.ps1 -Mode Status
```

Prints the last successful sync, the last source range, the last CoreOps batch
id, the last inserted/duplicate/unmapped counts, the last error code and time,
and the last reconciliation - from the local state file, with **no network
call**. That is deliberate: "is the connector alive?" has to be answerable when
the reason it is not alive is that the network is down.

No token, no password, no frontend. A Phase 5 health surface in the CoreOps UI
is a later decision.

### 9s. Security summary

- Secrets live only in `connectors/easytime/.env`, on the admin PC, git-ignored.
  Nothing is written there by any script.
- The connector token travels **only** in `X-CoreOps-Connector-Token`. Never a
  URL, never a query string, never `Authorization`.
- Redaction runs on every log handler, over the fully formatted record including
  tracebacks; `run_sync.ps1` adds a third pass over captured console output.
- Response bodies are sanitized before they reach a log line or an exception
  message, so a server that echoes a secret back does not get it written down.
- Names, photos, and face/fingerprint/vein/iris templates are stripped from
  `raw_payload` before it leaves the PC; the backend strips them again.
- The state database holds timestamps, counters and a batch id - no credential.
- Packaging is whitelist-based and verified after the fact.

### 9t. Troubleshooting

| Symptom | Exit | Look at |
|---|---|---|
| "Choose exactly one mode" | 2 | pass one of `--once` / `--reconcile` / dates / `--status` |
| "COREOPS_CONNECTOR_TOKEN is required" | 2 | `.env`; also check for a UTF-8 BOM |
| `[SKIP] Another connector run holds ...` | 3 | normal; the previous run is slow or hung. `-Mode Status` |
| EasyTime rejected the credentials | 4 | the integration account; try `probe.py --check-config` |
| Could not reach EasyTime | 5 | is EasyTime Pro running? `probe.py --discover` |
| CoreOps rejected the connector token | 6 | `COREOPS_CONNECTOR_TOKEN` vs `EASYTIME_CONNECTOR_TOKEN` on the VPS |
| CoreOps refused the batch (422) | 7 | the sanitized excerpt in the output; a contract bug - report it |
| CoreOps returned 404 | 8 | `COREOPS_API_URL`, **or** `EASYTIME_INGESTION_ENABLED=false` on the VPS |
| state database could not be opened | 9 | permissions on `...\data\`; move a corrupt `state.db` aside |
| punches stored with `employee_id = NULL` | 0 | expected until mappings exist: `POST /api/v1/biometric/mappings` |

A first setting in `.env` that seems to be ignored is almost always a UTF-8 BOM;
`run_sync.ps1` warns when it sees one.

### 9u. Phase 3 limitations

```
Raw automatic synchronization only.
No IN/OUT interpretation.
No session calculation.
No employee frontend.
No official attendance update.
```

In full:

- **IN/OUT is unresolved.** Every live punch was state `"0"` with a null display
  label. The connector sends `raw_punch_state: "0"` and
  `punch_state_display: null` verbatim and infers nothing. Interpretation stays
  blocked on the administrator sign-off in `punch-state-mapping.md`.
- **No sessions, no pairing, no first-IN/last-OUT**, and every intermediate
  punch is transmitted.
- **No working hours,** breaks, outside duration, overtime, late arrival or
  early departure.
- **No employee frontend.** No page, no component, no `NEXT_PUBLIC_*` flag.
- **No official attendance write-back.** `attendance_records` is neither read
  nor written; verified in the end-to-end run.
- **Not deployed to production**, and the scheduled tasks are **not activated**.
- **Untested against a live EasyTime install.** The end-to-end run used
  recorded punch payloads through the real connector into the real local
  backend. The EasyTime side has been exercised only by Phase 1's probe.
- Whether EasyTime employee codes match CoreOps codes remains open (O-6). Until
  mappings exist, punches store with `employee_id = NULL` - stored, not dropped.
