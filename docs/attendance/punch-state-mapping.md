# Punch-State Mapping

**Status: EMPTY ON PURPOSE. Nothing may consume this table until it is filled in
from live probe output and signed off by the EasyTime administrator.**

## Why this file exists and why it is blank

The punch-state code is site-configurable in EasyTime. `0 = IN, 1 = OUT` is
common but is *not* guaranteed - some installations use 2/3 for break in/out,
some return 4/5 for overtime in/out, and some devices are configured so every
punch is state `0` and direction is inferred by the software.

Getting this wrong does not fail loudly. It silently inverts sessions: an
employee who worked 8 hours is recorded as having been outside for 8 hours, for
every employee, for the whole month. That is why the connector returns the raw
code and refuses to translate it (`connectors/easytime/schemas.py`), and why the
server-side mapper reads this table instead of a constant.

## How to fill it in

1. On the admin PC: `python probe.py --date <a busy date> --save-report`
2. Section 5 of the output lists every code seen, its count and any label.
3. For each code, open the same punches in the EasyTime UI and confirm what the
   UI calls them.
4. Fill the table below. Leave nothing as "assumed".
5. The administrator signs off at the bottom.

## Confirmed mapping

| EasyTime code | EasyTime UI label | CoreOps meaning | Counts toward worked time | Confirmed by | Date |
|---|---|---|---|---|---|
| _(pending probe)_ | | `IN` / `OUT` / `IGNORE` | yes / no | | |

CoreOps meanings available in Phase 3:

| Meaning | Effect in the session engine |
|---|---|
| `IN` | opens a session |
| `OUT` | closes the open session |
| `IGNORE` | recorded as a raw punch, excluded from session building |

Any code that appears in ingestion but not in this table raises an
`UNKNOWN_PUNCH_STATE` exception for review. It is never guessed at and never
dropped.

## Verification type (informational)

`verify_type` (fingerprint / face / card / password) is stored for audit only.
It never affects a calculation. Fill in if the probe reports values:

| Code | Meaning |
|---|---|
| _(pending probe)_ | |

## Sign-off

| Item | Value |
|---|---|
| EasyTime Pro version | _(pending)_ |
| Number of devices | _(pending)_ |
| Device models | _(pending)_ |
| Probe report file | _(pending)_ |
| Confirmed by (administrator) | _(pending)_ |
| Date | _(pending)_ |
