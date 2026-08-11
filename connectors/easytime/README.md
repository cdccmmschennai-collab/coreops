# CoreOps EasyTime Connector

Runs on the **administrator PC that has EasyTime Pro installed** - never on the
CoreOps VPS. On the VPS, `localhost` is the VPS itself, so nothing there can
reach EasyTime. This connector is the only component that talks to EasyTime; it
sends normalized punches to CoreOps over HTTPS.

```
Biometric devices -> EasyTime Pro (admin PC) -> THIS CONNECTOR -> CoreOps API -> Postgres -> UI
```

**Status: Phase 3 - raw automatic synchronization.**

```
Raw automatic synchronization only.
No IN/OUT interpretation.
No session calculation.
No employee frontend.
No official attendance update.
```

The connector moves raw punch events and records how far it has got. It does not
interpret them. Every live punch the Phase 1 probe saw had state `"0"` with a
null display label, so IN/OUT is genuinely unknown, and guessing would produce
attendance that looks plausible and is wrong. See
`docs/attendance/punch-state-mapping.md`.

## Windows layout

One layout, three roots, and nothing that depends on where you happen to be
standing when you type a command.

| | Path |
|---|---|
| Application | `C:\Program Files\CoreOps\EasyTimeConnector\` |
| Virtual environment | `C:\Program Files\CoreOps\EasyTimeConnector\.venv\` |
| Python | `C:\Program Files\CoreOps\EasyTimeConnector\.venv\Scripts\python.exe` |
| Configuration | `C:\ProgramData\CoreOps\EasyTimeConnector\config\connector.env` |
| Configuration example | `C:\ProgramData\CoreOps\EasyTimeConnector\config\connector.env.example` |
| State + lock | `C:\ProgramData\CoreOps\EasyTimeConnector\data\state.db`, `sync.lock` |
| Logs | `C:\ProgramData\CoreOps\EasyTimeConnector\logs\` |
| Phase 1 probe (separate) | `C:\CoreOps-EasyTime-Probe\` |

ProgramData for everything mutable: the account that runs the connector has to
be able to write its cursor, and Program Files is read-only for exactly that
reason.

The probe is a **separate installation** with its own `.env` and its own
lifecycle. `install_connector.ps1` refuses to install into or under it, never
removes it, and never reads it.

### Which configuration file is in force

`config.resolve_env_path` answers this in one fixed order. None of these rules
looks at the current working directory:

1. `run_sync.ps1 -EnvFile <path>` / an explicit `env_path` argument
2. `%COREOPS_CONNECTOR_ENV_FILE%`
3. `<application folder>\.env` - a source checkout, and the probe folder
4. `C:\ProgramData\CoreOps\EasyTimeConnector\config\connector.env` - installed

An installed connector lands on rule 4, because the install whitelist contains
no `.env`. A source checkout and `C:\CoreOps-EasyTime-Probe` both land on rule
3, which is why the Phase 1 workflow is unchanged. `run_sync.ps1` exports the
path it resolved as `COREOPS_CONNECTOR_ENV_FILE`, so the wrapper and `sync.py`
can never disagree.

`run_sync.ps1 -DataRoot` likewise exports `COREOPS_CONNECTOR_DATA_ROOT`, which
moves the config, data and log roots together. It sets the *default* root only -
`SYNC_STATE_PATH`, `SYNC_LOG_DIR` and `SYNC_LOCK_PATH` in the configuration file
are the administrator's explicit choice and still win.

`-Mode CheckConfig` and `-Mode Status` both print the file in use and the rule
that chose it.

## Install (Windows)

Requires Python 3.11+. Run every step from an **elevated** PowerShell prompt -
Program Files and ProgramData are not writable without it, and the installer
stops with a clear message rather than installing half of itself.

**1. Install the application.** From the folder the ZIP was extracted into:

```powershell
.\install_connector.ps1
```

That copies a whitelist of application files into
`C:\Program Files\CoreOps\EasyTimeConnector\`, creates `config\`, `data\` and
`logs\` under `C:\ProgramData\CoreOps\EasyTimeConnector\`, installs
`connector.env.example`, and prints every final path. It writes no credential,
creates no scheduled task, and leaves an existing `connector.env`, `state.db` or
log file exactly as it found them - so it is safe to re-run for an upgrade.

**2. Create the virtual environment.** From the installed folder:

```powershell
cd 'C:\Program Files\CoreOps\EasyTimeConnector'
.\setup_connector.ps1
```

**3. Create the configuration.** Copy the example and type the credentials in
yourself - no script writes one:

```powershell
copy "C:\ProgramData\CoreOps\EasyTimeConnector\config\connector.env.example" "C:\ProgramData\CoreOps\EasyTimeConnector\config\connector.env"
notepad "C:\ProgramData\CoreOps\EasyTimeConnector\config\connector.env"
```

Fill in `EASYTIME_BASE_URL`, `EASYTIME_USERNAME`, `EASYTIME_PASSWORD`,
`COREOPS_API_URL`, `COREOPS_CONNECTOR_TOKEN` and `CONNECTOR_ID`. Save as
**UTF-8 without BOM** (Notepad's default) or ANSI. A BOM makes the first setting
in the file silently unreadable; `run_sync.ps1` warns if it sees one.

If PowerShell blocks a script, run it as
`powershell -ExecutionPolicy Bypass -File .\<script>.ps1`.

`setup_probe.ps1` is still shipped and still works; it is the Phase 1 entry
point. `setup_connector.ps1` is the production one.

### First test on the admin PC

In this order, from `C:\Program Files\CoreOps\EasyTimeConnector`. Nothing here
switches on a schedule.

```powershell
.\run_sync.ps1 -Mode CheckConfig
.\run_sync.ps1 -Mode Backfill -FromDate 2026-08-03 -ToDate 2026-08-03
.\run_sync.ps1 -Mode Backfill -FromDate 2026-08-03 -ToDate 2026-08-03
.\run_sync.ps1 -Mode Incremental
.\run_sync.ps1 -Mode Reconcile
```

The second backfill is the point: it must report the same punches as
**duplicates** and insert nothing. If it inserts rows again, stop - idempotency
is broken and nothing should be scheduled.

### Uninstall / rollback

There is no uninstaller, on purpose - the layout is two directories.

```powershell
# 1. confirm no scheduled task exists (Phase 3 never creates one)
Get-ScheduledTask -TaskName 'CoreOps EasyTime *' -ErrorAction SilentlyContinue

# 2. remove the application only. Config, cursor and logs survive.
Remove-Item -LiteralPath 'C:\Program Files\CoreOps\EasyTimeConnector' -Recurse -Force

# 3. ONLY if you mean to lose the configuration, the cursor and the logs:
# Remove-Item -LiteralPath 'C:\ProgramData\CoreOps\EasyTimeConnector' -Recurse -Force
```

To roll back to a previous build, re-run `install_connector.ps1` from that
build's extracted package. It overwrites the application files and touches
nothing under ProgramData. `C:\CoreOps-EasyTime-Probe` is not involved in any of
this.

## Run

`run_sync.ps1` resolves everything from its own location - never from the
caller's working directory - so it behaves identically from Program Files, from
another prompt, and from Task Scheduler later. It calls
`.venv\Scripts\python.exe`, mirrors output to a timestamped wrapper log under
`C:\ProgramData\CoreOps\EasyTimeConnector\logs\` after a redaction pass, and
**returns the connector's own exit code**.

```powershell
.\run_sync.ps1 -Mode CheckConfig                              # validate config, no network
.\run_sync.ps1 -Mode Status                                   # local health, no network
.\run_sync.ps1 -Mode Incremental                              # the scheduled run
.\run_sync.ps1 -Mode Reconcile                                # recover late uploads
.\run_sync.ps1 -Mode Reconcile -ReconcileDays 7               # an explicit span
.\run_sync.ps1 -Mode Backfill -FromDate 2026-07-29 -ToDate 2026-07-30
.\run_sync.ps1 -Mode Backfill -FromDate 2026-06-01 -ToDate 2026-07-30 -Force
.\run_sync.ps1 -Mode Incremental -EnvFile 'D:\configs\other.env'
.\run_sync.ps1 -Mode Status -Verbose
```

Those are the complete parameters: `-Mode` (mandatory,
`Incremental|Reconcile|Backfill|Status|CheckConfig`), `-ReconcileDays` (1-90),
`-FromDate`, `-ToDate` (`YYYY-MM-DD`), `-Force`, `-EnvFile`, `-DataRoot`,
`-Verbose`.

There is deliberately no `-Username`, `-Password` or `-Token` parameter:
credentials live only in the configuration file, which the script never reads or
prints. `-EnvFile` is a **path**, not a credential.

`CheckConfig` parses the configuration and prints a redacted view. It makes **no
network call** and does not test connectivity to EasyTime or to CoreOps -
`Incremental` is the first mode that touches the network.

The underlying CLI, if you prefer to call it directly:

```powershell
.\.venv\Scripts\python.exe sync.py --check-config
.\.venv\Scripts\python.exe sync.py --status
.\.venv\Scripts\python.exe sync.py --once
.\.venv\Scripts\python.exe sync.py --reconcile
.\.venv\Scripts\python.exe sync.py --reconcile-days 7
.\.venv\Scripts\python.exe sync.py --from-date 2026-07-29 --to-date 2026-07-30
```

**One shot, never a daemon.** Each invocation covers one window and exits. Task
Scheduler provides the schedule; a long-lived Python process on an office PC is
a thing that silently dies in March and is noticed in June.

## What one run does

1. Load and validate the configuration - fail closed on anything missing.
2. Open the local state database.
3. Acquire the run lock. A second invocation exits 3 immediately.
4. Read the cursor and plan the window.
5. Authenticate to EasyTime, fetch every page in the window.
6. Normalize; count - never silently drop - anything that fails.
7. Sort deterministically, chunk to `SYNC_BATCH_SIZE`, derive a batch key each.
8. POST each batch in order, accumulating the backend's counters.
9. **Only after every batch succeeds**, advance the cursor.
10. Release the lock, print the summary, exit with a meaningful code.

### Fetch windows

| Mode | Window |
|---|---|
| incremental, with a cursor | `cursor - SYNC_LOOKBACK_MINUTES` .. now |
| incremental, first run | `now - SYNC_FIRST_RUN_LOOKBACK_HOURS` .. now |
| reconcile | the last N **calendar** days from local midnight .. now |
| backfill | `--from-date 00:00:00` .. `--to-date 23:59:59` |

```
last successful source_to = 2026-07-30 14:00
next incremental from     = 2026-07-30 13:45     (15-minute overlap)
```

The overlap is the point: EasyTime accepts a punch a device uploads long after
it happened, so a window starting exactly where the last one ended would step
over anything that arrived in between. Re-fetching fifteen minutes costs
duplicates, and duplicates are free.

The first run is bounded (24 hours by default), never "all of history". A cursor
far in the past is clamped to `SYNC_MAX_RANGE_DAYS` and caught up over several
runs rather than in one enormous request.

### Reconciliation

```powershell
.\run_sync.ps1 -Mode Reconcile
```

The live probe proved some punches reach EasyTime **the following morning**,
after the incremental run for that evening has already finished and moved on.
Nothing in the cursor can recover them. This pass re-sends the last seven days
through the same endpoint and lets the database's unique constraint sort out
what is new. It re-sends; it never deletes and never alters a stored punch. Safe
to rerun - a second pass reports every punch as a duplicate.

It does not move the incremental cursor.

### Backfill

```powershell
.\run_sync.ps1 -Mode Backfill -FromDate 2026-07-29 -ToDate 2026-07-30
```

Both dates required, no default, and no "since the beginning". Ranges over
`SYNC_MAX_RANGE_DAYS` need `-Force`. It does not move the incremental cursor.

## Idempotency

Four layers; each covers what the one below cannot.

| Layer | Mechanism |
|---|---|
| connector overlap | re-fetch `SYNC_LOOKBACK_MINUTES` every run |
| batch key | deterministic SHA-256 over the window and the ids |
| backend batch resolution | `ON CONFLICT` on `(provider, connector_id, batch_key)` |
| **punch uniqueness** | **`UNIQUE (provider, external_transaction_id)`** |

The last row is what actually guarantees correctness. A lost, wrong or
duplicated batch key can never cause a duplicate punch - which is what makes
replay after a failure safe, and replay is what every other decision here rests
on.

**Partial failure.** If batch 1 of 3 succeeds and batch 2 fails, the cursor does
not move and the next run re-sends all three. Batch 1 comes back as duplicates
and nothing is stored twice. Advancing past a partly-ingested window would lose
punches permanently and silently.

### Batch keys

`et1-<sha256 hex>` over, NUL-separated: version tag, connector id, provider,
source range start and end, batch number, and each external transaction id in
batch order. No secrets, no clock, no randomness - so the same batch always
produces the same key, and different chunks always produce different ones.

## State

```
C:\ProgramData\CoreOps\EasyTimeConnector\data\state.db
```

SQLite, one row per `CONNECTOR_ID`: the cursor, the last batch key and CoreOps
batch id, the five record counters, the last success, the last reconciliation
and the last error. `SYNC_STATE_PATH` overrides the location.

SQLite rather than JSON because the cursor update must be atomic against a
process that can be killed at any instant. A JSON write is read-modify-write and
can leave a truncated file.

**No secret is stored here.** Not the EasyTime password, not the JWT, not the
CoreOps token.

A failed run writes only `last_error_code` and `last_error_at` - never the
cursor, never the last-success fields. A failure can not be mistaken for
progress.

## Retries and exit codes

| Failure | Behaviour |
|---|---|
| timeout, connection refused, `429`, `5xx`, `409` | bounded retry, jittered backoff |
| `401`, `403`, `404`, `422`, other 4xx | **stop** - a human has to change something |
| 2xx whose body is not a valid batch result | **stop** - never counted as success |

Backoff: immediate, ~2s, ~5s, ~10s with +/-25% jitter, capped by
`COREOPS_RETRIES`.

| Code | Meaning | Who acts |
|---|---|---|
| 0 | success | nobody |
| 2 | invalid configuration | whoever edits `.env` here |
| 3 | another run is active | nobody - expected under a 5-minute schedule |
| 4 | EasyTime authentication failure | the integration account owner |
| 5 | EasyTime transport/API failure | whoever owns EasyTime Pro on this PC |
| 6 | CoreOps authentication failure | whoever holds the connector token |
| 7 | CoreOps payload rejection | whoever maintains the connector |
| 8 | CoreOps transport/server failure | whoever operates the CoreOps VPS |
| 9 | local state failure | whoever administers this PC's ProgramData |

`1` is left unused, so `exit 1` always reads as "failed in a way it did not
anticipate".

## Locking

One run at a time, via an OS-level exclusive lock on `...\data\sync.lock`. Task
Scheduler's "do not start a new instance" is used as well, but is not enough on
its own - it does not cover a manual run typed while the scheduled one is in
flight.

A PID file was rejected on purpose: `os.kill(pid, 0)`, the usual liveness probe,
calls `TerminateProcess` on Windows and would kill whatever now owns that PID.
An OS lock is also released by the kernel when the holder dies, so a crashed run
leaves nothing to recover from.

## Logs

```
C:\ProgramData\CoreOps\EasyTimeConnector\logs\sync-YYYYMMDD.log
```

One file per day (288 runs a day for a year would be 105,000 files), every line
carrying the run id, one structured summary line per run:

```
sync.run mode=incremental connector_id=admin-pc-01 source_from=... source_to=...
  pages=2 fetched=41 normalized=41 rejected_locally=0 batches_planned=1
  batches_sent=1 received=41 inserted=38 duplicates=3 unmapped=0 invalid=0
  duration_s=1.84 status=success exit=0
```

`run_sync.ps1` also keeps a per-run wrapper log under `.\logs\`, which captures
anything that reached the console including a traceback.

## Privacy and secrets

CoreOps only ever ingests: employee code, transaction id, punch timestamp,
punch state, device, verification method, upload time.

**Never logged, never stored, never transmitted:** EasyTime password, EasyTime
JWT and refresh token, CoreOps connector token, Authorization headers, names,
photos, face/fingerprint/vein/iris templates.

Three independent layers hold that line: the code never passes a secret to a
logger; `redaction.sanitize_text` runs over every formatted log record (including
tracebacks) on every handler; and `run_sync.ps1` applies a third regex pass to
captured console output. No installer or setup script ever reads, prints or
writes the configuration file's contents, and the "configuration file not found"
error carries only paths. `tests/test_coreops_client.py::TestSecrets`,
`test_state.py::TestSecrets`, `test_cli.py::TestLogging` and
`test_config.py::TestPhase3Secrets` assert it.

The connector token travels only in `X-CoreOps-Connector-Token` - never a URL,
never a query string, never `Authorization`.

## Scheduled tasks - documented, NOT activated

`install_connector.ps1` registers them only with an explicit
`-CreateScheduledTask`, and Phase 3 does not pass it.

| | Incremental | Reconciliation |
|---|---|---|
| Command | `run_sync.ps1 -Mode Incremental` | `run_sync.ps1 -Mode Reconcile` |
| Trigger | every 5 minutes, indefinitely | daily at 02:30 |
| Run whether logged on or not | yes | yes |
| If already running | do not start a new instance | do not start a new instance |
| Missed start | run as soon as possible | run as soon as possible |
| Restart on failure | every 5 min, up to 3 times | same |
| Stop if longer than | 30 minutes | 30 minutes |

Before switching them on: `-Mode CheckConfig`, then `-Mode Status`, then at
least one manual `-Mode Incremental`, then confirm rows via
`GET /api/v1/biometric/sync-batches`.

## Packaging

Built in the repository, not on the admin PC:

```powershell
.\package_connector.ps1     # dist\CoreOps-EasyTime-Connector.zip
```

Whitelist-based: if a file is not named in the script it does not reach the
archive. The build fails if `.env.example` carries a non-empty password, token
or secret, and the finished ZIP is re-opened and verified entry by entry - every
expected file present, no unexpected file, no forbidden pattern.

To verify a ZIP you were handed, without installing it:

```powershell
Get-FileHash -Algorithm SHA256 .\dist\CoreOps-EasyTime-Connector.zip
Add-Type -AssemblyName System.IO.Compression.FileSystem
[System.IO.Compression.ZipFile]::OpenRead((Resolve-Path .\dist\CoreOps-EasyTime-Connector.zip).Path).Entries |
    Select-Object FullName, Length
```

Never shipped: `.env`, `connector.env`, `.venv\`, `logs\`, `data\`,
`probe-output\`, `dist\`, `tests\`, `*.db`, `*.lock`, `*.log`, `__pycache__\`,
`.pytest_cache\`, git metadata.

`package_probe.ps1` is still there and still builds the Phase 1 probe-only
package; `package_connector.ps1` supersedes it for Phase 3 deployments and ships
the probe as well, because the probe remains the right first thing to run on a
new site.

## The probe (Phase 1)

`probe.py` is read-only and unchanged. It is still how you answer "which
endpoints does this installed version expose?" before pinning them in the
configuration file.

Its own installation lives in `C:\CoreOps-EasyTime-Probe` with its own `.env`
next to `probe.py`, and rule 3 of the resolution order is what keeps it that way
after the connector is installed. `install_connector.ps1` refuses that directory
as a destination and never touches it.

```powershell
.\run_probe.ps1 -Mode CheckConfig
.\run_probe.ps1 -Mode Discover
.\run_probe.ps1 -Mode Transactions -Date 2026-07-28 -SaveReport
```

Pin the working paths (`EASYTIME_AUTH_PATH`, `EASYTIME_TRANSACTIONS_PATH`) so
the sync loop never guesses at runtime.

## Tests

Fully offline (`httpx.MockTransport` on both sides); no EasyTime install and no
CoreOps server needed.

```powershell
.venv\Scripts\python -m pytest tests -q
```

`tests/test_windows_layout.py` reads the PowerShell scripts as text and pins the
installation contract: the application is copied into Program Files, the mutable
roots are ProgramData, the probe directory is never a destination, nothing
deletes a config file or a state database, scheduled-task registration stays
opt-in, and the package whitelist ships every file the installer needs. It is
static verification, not a substitute for a real install.

`tests/test_contract.py` validates the connector's request body against the
**real** backend Pydantic schemas. It skips in this virtualenv, which
deliberately has three packages in it and no Pydantic. Run it from the backend
environment to get that coverage:

```powershell
..\..\backend\.venv\Scripts\python -m pytest tests -q
```

A skip there is a gap in verification, never a pass.

## Files

| File | Purpose |
|---|---|
| `config.py` | `.env` -> config objects; candidate endpoint lists; redaction |
| `exceptions.py` | one error class per failure mode, mapped to one exit code |
| `schemas.py` | `RawTransaction` (as returned) and `NormalizedPunch` (the wire contract) |
| `client.py` | EasyTime: auth, refresh, GET transactions, pagination, retries |
| `probe.py` | the read-only Phase 1 CLI |
| `mapper.py` | normalize, sort, chunk, derive the batch key |
| `coreops_client.py` | the only thing that talks to CoreOps |
| `state.py` | SQLite cursor, counters, crash-safe commit |
| `runlock.py` | OS-level single-instance lock |
| `logging_setup.py` | dated structured logs, redaction on every handler |
| `redaction.py` | the regex pass behind every log line |
| `exit_codes.py` | the numeric contract with Task Scheduler |
| `sync_service.py` | window planning, fetch, normalize, batch, send, commit |
| `sync.py` | the one-shot CLI |
| `tests/` | offline unit tests, the backend contract test, the Windows-layout checks |
| `setup_probe.ps1` | Phase 1: creates `.venv` for the standalone probe (never global) |
| `setup_connector.ps1` | production setup: creates `.venv` in the installed folder, pinned requirements only |
| `install_connector.ps1` | copies the application to Program Files, creates the ProgramData layout; writes no credentials |
| `run_probe.ps1` | runs the probe, sanitized log, propagates the exit code |
| `run_sync.ps1` | runs one sync, sanitized log, propagates the exit code |
| `package_probe.ps1` | builds the Phase 1 probe ZIP (repo side) |
| `package_connector.ps1` | builds the Phase 3 connector ZIP (repo side) |

The `package_*.ps1` scripts stay in the repository - they *build* the admin
package, so they are not themselves shipped inside a ZIP.

## Not in this phase

- **IN/OUT interpretation.** Blocked on administrator sign-off in
  `docs/attendance/punch-state-mapping.md`.
- **Sessions, pairing, first-IN/last-OUT.** Every intermediate punch is sent;
  nothing is paired.
- **Working hours,** breaks, overtime, late arrival, early departure.
- **Employee frontend.** No page, no component, no `NEXT_PUBLIC_*` flag.
- **Official attendance write-back.** `attendance_records` is neither read nor
  written.
- **Production deployment,** and the scheduled tasks are not activated.

## Related docs

- `docs/attendance/easytime-integration.md` - architecture, the Phase 2 contract,
  and section 9 for everything above in more detail
- `docs/attendance/punch-state-mapping.md` - **still unresolved**
- `docs/attendance/attendance-policy-open-decisions.md` - management sign-off list
