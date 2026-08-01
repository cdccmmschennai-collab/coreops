# Punch-State Mapping

**Status: UNRESOLVED. The probe has now run against the live system and the
result did not resolve IN/OUT. Nothing may consume this table until it is filled
in and signed off by the EasyTime administrator.**

## Observed on the live system (Phase 1 probe, 2026-07-30)

```
Observed raw state:     0
Observed display state: null
Meaning:                unresolved
Do not infer IN/OUT
```

Every raw punch returned by the live EasyTime Pro 10.2.2 installation carried
`punch_state_raw = "0"`, and `punch_state_display` was `null` on every record.
Example - EasyTime employee code 61, all four punches on 2026-07-29:

| Punch time | `punch_state_raw` | `punch_state_display` |
|---|---|---|
| 10:12:10 | `0` | `null` |
| 13:05:44 | `0` | `null` |
| 13:28:31 | `0` | `null` |
| 17:48:54 | `0` | `null` |

A single constant state across an entire day means the device does **not**
encode direction in this field. Whatever distinguishes an entry from an exit
here, it is not `punch_state`. So:

- There is no code in this table to fill in yet - one value with no label is not
  a mapping, it is an absence of one.
- Direction cannot be recovered by alternating the punches either. Four punches
  do not tell you whether the person went out for lunch twice or came back late
  once, and "first = IN, last = OUT" silently discards the 13:05/13:28 pair.
- **Phase 2 therefore stores `raw_punch_state` verbatim and derives nothing.**
  `biometric_punches` has no direction column, no session and no duration.

Resolving this is a prerequisite for Phase 3, not a task inside it. The likely
next steps, none of which are assumptions CoreOps may make on its own:

1. Ask the administrator how the EasyTime UI renders these four punches. If the
   UI shows direction, EasyTime derives it somewhere and CoreOps must read the
   same source rather than re-derive it.
2. Check whether the devices are configured in a single-state ("attendance
   only") mode, and whether a per-terminal mode is available.
3. Check whether a different endpoint or report exposes a resolved direction.
4. If direction genuinely does not exist in the data, that is itself a decision
   for the business: what CoreOps computes from an undirected punch stream has
   to be agreed, not guessed.

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

**Still empty. `0` appears below as an observation, not as a mapping - its
CoreOps meaning is deliberately blank because it is not known.**

| EasyTime code | EasyTime UI label | CoreOps meaning | Counts toward worked time | Confirmed by | Date |
|---|---|---|---|---|---|
| `0` | _(none returned; `punch_state_display` is null)_ | _(unresolved)_ | _(unresolved)_ | _(pending)_ | _(pending)_ |

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
| _(pending administrator confirmation)_ | |

## Sign-off

| Item | Value |
|---|---|
| EasyTime Pro version | 10.2.2 |
| Base URL | `http://127.0.0.1` (administrator PC) |
| Authentication | JWT, `/api/jwt-api-token-auth/`, header scheme `JWT` |
| Transactions path | `/iclock/api/transactions/` |
| Timezone | Asia/Kolkata |
| Terminal alias observed | `F22/ID` |
| Number of devices | _(pending)_ |
| Device models | _(pending)_ |
| Probe report file | _(pending - attach the `probe-*.json` used)_ |
| Punch-state meaning confirmed by (administrator) | **_(pending - BLOCKS Phase 3)_** |
| Date | _(pending)_ |
