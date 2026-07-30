"""EasyTime Pro API probe - READ ONLY, run on the administrator PC.

Phase 1 of the biometric integration. It answers the questions that must be
settled before a single line of attendance logic is written:

  1. Is EasyTime reachable at the configured URL?
  2. Which authentication endpoint does THIS installed version accept?
  3. Which transactions endpoint exists, and does it paginate?
  4. Do intermediate punches come back, or only first-IN / last-OUT?
  5. What punch-state codes does this site actually emit, and what do they mean?
  6. Are the timestamps local wall-clock, and do they match the EasyTime UI?
  7. Do EasyTime employee codes match CoreOps employee codes exactly?

What it will NOT do: write to EasyTime, write to CoreOps, touch production
attendance, print a password or token, or print employee names. Employee codes
are masked unless you pass --show-codes (needed for the CoreOps code-match
check, and only ever run on the admin PC).

Usage (from connectors/easytime, with .env filled in):

    python probe.py --date 2026-07-28
    python probe.py --date 2026-07-28 --emp-code EMP069 --show-codes
    python probe.py --discover            # find the right endpoints first
    python probe.py --check-config        # validate .env without calling out
    python probe.py --date 2026-07-28 --save-report

--save-report writes a sanitized JSON summary to ./probe-output/ (git-ignored)
that can be attached to the Phase 1 report.
"""
from __future__ import annotations

import argparse
import json
import logging
import sys
from collections import Counter, defaultdict
from datetime import date, datetime
from pathlib import Path

from client import EasyTimeClient
from config import (
    AUTH_PATH_CANDIDATES,
    CONNECTOR_DIR,
    TRANSACTIONS_PATH_CANDIDATES,
    EasyTimeConfig,
    load_config,
)
from exceptions import EasyTimeError
from schemas import RawTransaction, mask_code, parse_timestamp, strip_pii

OUTPUT_DIR = CONNECTOR_DIR / "probe-output"

logger = logging.getLogger("easytime.probe")


# -- output helpers ---------------------------------------------------------
def heading(text: str) -> None:
    print(f"\n{text}\n{'-' * len(text)}")


def check(label: str, ok: bool | None, detail: str = "") -> None:
    mark = {True: "[PASS]", False: "[FAIL]", None: "[????]"}[ok]
    print(f"  {mark} {label}" + (f" - {detail}" if detail else ""))


# -- probe steps ------------------------------------------------------------
def step_config(config: EasyTimeConfig) -> None:
    heading("1. Connector configuration")
    for key, value in config.redacted().items():
        print(f"  {key:<20} {value}")


def step_discover(config: EasyTimeConfig) -> dict:
    """Try every candidate endpoint and report which ones exist.

    Auth candidates are probed with the real credentials (a 200 is the answer we
    want); transaction candidates are probed unauthenticated first, where a 401
    is still proof the path exists.
    """
    heading("2. Endpoint discovery")
    findings: dict[str, list[dict]] = {"auth": [], "transactions": []}

    with EasyTimeClient(config) as client:
        for mode, paths in AUTH_PATH_CANDIDATES.items():
            for path in paths:
                try:
                    status, body = client.probe_path(
                        "POST",
                        path,
                        json={"username": config.username, "password": config.password},
                    )
                except EasyTimeError as exc:
                    check(f"{mode:<5} POST {path}", None, str(exc))
                    continue
                has_token = isinstance(body, dict) and any(
                    k in body for k in ("token", "access", "access_token", "jwt")
                )
                check(
                    f"{mode:<5} POST {path}",
                    status == 200 and has_token,
                    f"HTTP {status}"
                    + (
                        f", keys={sorted(body.keys())}"
                        if isinstance(body, dict)
                        else ""
                    ),
                )
                findings["auth"].append(
                    {"mode": mode, "path": path, "status": status, "token_returned": has_token}
                )

        for path in TRANSACTIONS_PATH_CANDIDATES:
            try:
                status, _ = client.probe_path("GET", path, params={"page_size": 1})
            except EasyTimeError as exc:
                check(f"GET   {path}", None, str(exc))
                continue
            check(
                f"GET   {path}",
                status in (200, 401, 403),
                f"HTTP {status}" + (" (exists, needs auth)" if status in (401, 403) else ""),
            )
            findings["transactions"].append({"path": path, "status": status})

    print(
        "\n  Pin the working paths in .env (EASYTIME_AUTH_PATH / "
        "EASYTIME_TRANSACTIONS_PATH) so the sync loop never guesses."
    )
    return findings


def step_authenticate(client: EasyTimeClient) -> None:
    heading("3. Authentication")
    client.authenticate()
    check("Access token obtained", True, f"path={client.auth_path_used}")
    client.refresh()
    check("Token refresh / re-auth", client.is_authenticated)


def step_fetch(
    client: EasyTimeClient,
    day: date,
    emp_code: str | None,
    page_size: int,
) -> list[RawTransaction]:
    heading(f"4. Transactions for {day.isoformat()}" + (f" (emp {mask_code(emp_code)})" if emp_code else ""))
    txns = list(
        client.iter_transactions(day, day, employee_code=emp_code, page_size=page_size)
    )
    check("Transactions endpoint reached", True, f"path={client.transactions_path_used}")
    check("Records returned", bool(txns), f"{client.last_record_count} record(s)")
    check(
        "Pagination followed",
        None if client.last_page_count <= 1 else True,
        f"{client.last_page_count} page(s) at page_size={page_size}"
        + (" - re-run with a smaller --page-size to force a second page"
           if client.last_page_count <= 1 else ""),
    )
    if client.last_parse_errors:
        check("All records parseable", False, f"{len(client.last_parse_errors)} failed")
        for message in client.last_parse_errors[:5]:
            print(f"       - {message}")
    else:
        check("All records parseable", True)
    return txns


def step_punch_states(txns: list[RawTransaction]) -> dict:
    heading("5. Punch-state codes seen (MEANING MUST BE CONFIRMED BY THE ADMIN)")
    counts: Counter[str] = Counter()
    displays: dict[str, set[str]] = defaultdict(set)
    for txn in txns:
        code = txn.punch_state_raw if txn.punch_state_raw is not None else "(none)"
        counts[code] += 1
        if txn.punch_state_display:
            displays[code].add(txn.punch_state_display)
    if not counts:
        check("Punch-state codes present", None, "no records to inspect")
        return {}
    for code, count in sorted(counts.items()):
        label = ", ".join(sorted(displays.get(code, ()))) or "NO LABEL RETURNED"
        print(f"  code {code!r:<8} x{count:<4} label: {label}")
    print(
        "\n  Cross-check every code above against the EasyTime UI for the same\n"
        "  punches and record the result in docs/attendance/punch-state-mapping.md.\n"
        "  CoreOps will not translate a code that is not in that document."
    )
    return {code: sorted(displays.get(code, ())) for code in counts}


def step_timeline(txns: list[RawTransaction], show_codes: bool) -> None:
    heading("6. Per-employee timeline (intermediate punches check)")
    by_employee: dict[str, list[RawTransaction]] = defaultdict(list)
    for txn in txns:
        by_employee[txn.employee_code].append(txn)
    if not by_employee:
        check("Timeline", None, "no records")
        return
    for code, rows in sorted(by_employee.items()):
        rows.sort(key=lambda t: t.punch_time_raw)
        shown = code if show_codes else mask_code(code)
        print(f"\n  {shown}  ({len(rows)} punch(es))")
        for row in rows:
            state = row.punch_state_display or f"code={row.punch_state_raw}"
            print(
                f"    {row.punch_time_raw:<21} {state:<18} "
                f"id={row.external_transaction_id:<10} "
                f"terminal={row.terminal_alias or row.terminal_serial_number or '-'}"
            )
    multi = sum(1 for rows in by_employee.values() if len(rows) > 2)
    check(
        "Intermediate punches returned (more than first-IN/last-OUT)",
        None if multi == 0 else True,
        f"{multi} employee(s) with 3+ punches"
        + (" - pick a date where someone left and returned" if multi == 0 else ""),
    )


def step_timezone(txns: list[RawTransaction], config: EasyTimeConfig) -> None:
    heading("7. Timestamp format and timezone")
    if not txns:
        check("Timestamps", None, "no records")
        return
    sample = txns[0]
    parsed = parse_timestamp(sample.punch_time_raw)
    check("Timestamp parsed", parsed is not None, f"raw={sample.punch_time_raw!r}")
    has_offset = any(marker in sample.punch_time_raw for marker in ("+", "Z"))
    check(
        "Naive local wall-clock (no UTC offset in the payload)",
        not has_offset,
        "an offset was present - the mapper must honour it instead of TIMEZONE"
        if has_offset
        else f"will be interpreted as {config.timezone}",
    )
    print(
        f"\n  CONFIRM WITH THE ADMIN: open the same punch in the EasyTime UI.\n"
        f"  The UI must show {sample.punch_time_raw} for transaction "
        f"{sample.external_transaction_id}.\n"
        f"  If it differs, the device clock or a server-side conversion is in play\n"
        f"  and the connector must NOT be enabled until that is understood."
    )


def step_sample_payload(txns: list[RawTransaction]) -> None:
    heading("8. One sanitized raw record (names/templates stripped)")
    if not txns:
        print("  (no records)")
        return
    print(json.dumps(strip_pii(txns[0].raw), indent=2, default=str, sort_keys=True))


def save_report(payload: dict) -> Path:
    OUTPUT_DIR.mkdir(exist_ok=True)
    stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    path = OUTPUT_DIR / f"probe-{stamp}.json"
    path.write_text(json.dumps(payload, indent=2, default=str, sort_keys=True), encoding="utf-8")
    return path


# -- entry point ------------------------------------------------------------
def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Read-only probe of the EasyTime Pro third-party API.",
    )
    parser.add_argument("--date", help="Date to fetch, YYYY-MM-DD (default: today).")
    parser.add_argument("--emp-code", help="Limit to one EasyTime employee code.")
    parser.add_argument("--page-size", type=int, help="Override the page size.")
    parser.add_argument(
        "--discover",
        action="store_true",
        help="Probe every candidate endpoint and exit.",
    )
    parser.add_argument(
        "--check-config",
        action="store_true",
        help="Validate .env and exit without any network call.",
    )
    parser.add_argument(
        "--show-codes",
        action="store_true",
        help="Print full employee codes (needed for the CoreOps code-match check).",
    )
    parser.add_argument(
        "--save-report",
        action="store_true",
        help="Write a sanitized JSON summary to ./probe-output/.",
    )
    parser.add_argument("--verbose", action="store_true", help="Debug logging.")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    logging.basicConfig(
        level=logging.DEBUG if args.verbose else logging.INFO,
        format="%(levelname)s %(name)s %(message)s",
    )

    try:
        config = load_config(require_credentials=not args.check_config)
    except EasyTimeError as exc:
        print(f"[FAIL] {exc}")
        return 2

    print(f"EasyTime probe - {datetime.now().isoformat(timespec='seconds')}")
    step_config(config)

    if args.check_config:
        print("\nConfiguration parsed. No network call was made.")
        return 0

    report: dict = {"config": config.redacted(), "run_at": datetime.now().isoformat()}

    try:
        if args.discover:
            report["discovery"] = step_discover(config)
            if args.save_report:
                print(f"\nReport written to {save_report(report)}")
            return 0

        day = date.fromisoformat(args.date) if args.date else date.today()
        with EasyTimeClient(config) as client:
            step_authenticate(client)
            report["auth_path"] = client.auth_path_used
            txns = step_fetch(client, day, args.emp_code, args.page_size or config.page_size)
            report["transactions_path"] = client.transactions_path_used
            report["record_count"] = client.last_record_count
            report["page_count"] = client.last_page_count
            report["parse_errors"] = client.last_parse_errors
            report["punch_states"] = step_punch_states(txns)
            step_timeline(txns, args.show_codes)
            step_timezone(txns, config)
            step_sample_payload(txns)
            report["sample"] = [
                t.sanitized(mask_employee=not args.show_codes) for t in txns[:20]
            ]
    except EasyTimeError as exc:
        print(f"\n[FAIL] {type(exc).__name__}: {exc}")
        return 1

    heading("Next steps")
    print(
        "  1. Fill in docs/attendance/punch-state-mapping.md from section 5.\n"
        "  2. Confirm every open item in "
        "docs/attendance/attendance-policy-open-decisions.md.\n"
        "  3. Send the sanitized report; Phase 2 (ingestion) starts only after review."
    )
    if args.save_report:
        print(f"\nReport written to {save_report(report)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
