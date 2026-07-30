# CoreOps EasyTime Connector

Runs on the **administrator PC that has EasyTime Pro installed** - never on the
CoreOps VPS. On the VPS, `localhost` is the VPS itself, so nothing there can
reach EasyTime. This connector is the only component that talks to EasyTime; it
sends normalized punches to CoreOps over HTTPS.

```
Biometric devices -> EasyTime Pro (admin PC) -> THIS CONNECTOR -> CoreOps API -> Postgres -> UI
```

**Phase 1 status: probe only.** `probe.py` reads from EasyTime and prints what it
found. Nothing here writes to EasyTime, writes to CoreOps, or touches production
attendance. The sync loop (`sync.py`, `state_store.py`, `service.py`) arrives in
Phase 2, after the probe output has been reviewed.

## Install (Windows)

```powershell
cd C:\CoreOps\EasyTimeProbe
.\setup_probe.ps1     # creates .\.venv and installs requirements INTO IT ONLY
copy .env.example .env
notepad .env          # fill in URL + integration account
```

`setup_probe.ps1` never installs anything globally and never creates or fills in
`.env` - you type the credentials yourself. If PowerShell blocks the script, run
it as `powershell -ExecutionPolicy Bypass -File .\setup_probe.ps1`.

Save `.env` as **UTF-8 without BOM** (Notepad's default) or ANSI. A BOM makes the
first setting in the file silently unreadable; `run_probe.ps1` warns if it sees one.

The manual equivalent, if you prefer not to use the script:

```powershell
py -3 -m venv .venv
.venv\Scripts\pip install -r requirements.txt
```

Requires Python 3.11+ (the same minor as the CoreOps backend is ideal but not
required - this connector shares no code with it).

## Configure

Everything lives in `.env`, which is git-ignored. Read the real EasyTime port
off the browser address bar on the admin PC.

Use a **dedicated integration account** with read access to transactions, not a
person's administrator login. If the EasyTime licence does not allow a second
account, say so in the Phase 1 report rather than pasting an admin password into
this file.

## Run the probe

Use `run_probe.ps1`. It calls `.venv\Scripts\python.exe`, mirrors the output to a
timestamped file under `.\logs\`, and returns the probe's own exit code.

```powershell
.\run_probe.ps1 -Mode CheckConfig                     # validate .env, no network
.\run_probe.ps1 -Mode Discover                        # which endpoints exist?
.\run_probe.ps1 -Mode Transactions -Date 2026-07-28   # fetch one day
.\run_probe.ps1 -Mode Transactions -Date 2026-07-28 -EmployeeCode EMP069 -ShowCodes
.\run_probe.ps1 -Mode Transactions -Date 2026-07-28 -SaveReport
```

There is deliberately no `-Username` or `-Password` parameter: credentials live
only in `.env`, which the script never reads or prints. Employee codes stay
masked in the log unless you pass `-ShowCodes`.

The underlying CLI, if you want to call it directly:

```powershell
.venv\Scripts\python probe.py --check-config
.venv\Scripts\python probe.py --discover
.venv\Scripts\python probe.py --date 2026-07-28 --emp-code EMP069 --show-codes --save-report
```

Work in that order. `--discover` tells you which auth and transactions paths
this installed version exposes; pin them in `.env` (`EASYTIME_AUTH_PATH`,
`EASYTIME_TRANSACTIONS_PATH`) so the sync loop never guesses at runtime.

Pick a date where at least one employee left the office and came back - the
whole point of section 6 of the output is proving EasyTime returns the
**intermediate** punches, not just first-IN and last-OUT.

### What the probe answers

| # | Question | Where it shows up |
|---|---|---|
| 1 | Is EasyTime reachable? | section 2 / any transport error |
| 2 | Which auth endpoint works? | section 2, 3 |
| 3 | Which transactions endpoint works, does it paginate? | section 4 |
| 4 | Are intermediate punches returned? | section 6 |
| 5 | Which punch-state codes does this site emit? | section 5 |
| 6 | Are timestamps local wall-clock? | section 7 |
| 7 | Do EasyTime codes match CoreOps codes? | section 6 with `--show-codes` |

## Privacy

The probe prints, and `--save-report` writes, **no** names, photos or biometric
templates. Employee codes are masked (`EMP**9`) unless you pass `--show-codes`,
which exists only for the CoreOps code-match check and should stay on the admin
PC. CoreOps only ever ingests: employee code, transaction id, punch timestamp,
punch state, device, verification method, upload time.

Passwords and tokens never reach a log line, an exception message or a report
file - `tests/test_client.py::TestSecrets` and `test_config.py::TestSecrets`
hold that line.

## Tests

Fully offline (`httpx.MockTransport`); no EasyTime install needed.

```powershell
.venv\Scripts\python -m pytest tests -q
```

## Files

| File | Purpose |
|---|---|
| `config.py` | `.env` -> `EasyTimeConfig`; candidate endpoint lists; redaction |
| `client.py` | auth, refresh, GET transactions, pagination, retries |
| `schemas.py` | `RawTransaction` (as returned) and `NormalizedPunch` (Phase 2 wire contract) |
| `exceptions.py` | one error class per failure mode the sync loop reacts to |
| `probe.py` | the read-only Phase 1 CLI |
| `tests/` | offline unit tests |
| `setup_probe.ps1` | creates `.venv` and installs requirements into it (never global) |
| `run_probe.ps1` | runs the probe, writes a sanitized log to `logs/`, propagates the exit code |
| `package_probe.ps1` | builds `dist/CoreOps-EasyTime-Probe.zip` for the admin PC (repo side) |

`package_probe.ps1` stays in the repository - it is the script that *builds* the
admin package, so it is not itself shipped inside the ZIP.

Phase 2 adds `mapper.py`, `sync.py`, `state_store.py` and `service.py` - not
before the punch-state mapping is confirmed in writing.

## Related docs

- `docs/attendance/easytime-integration.md` - architecture and phase plan
- `docs/attendance/punch-state-mapping.md` - **fill this in from probe output**
- `docs/attendance/attendance-policy-open-decisions.md` - management sign-off list
