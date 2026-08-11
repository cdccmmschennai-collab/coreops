"""CoreOps EasyTime connector - one-shot synchronization CLI.

Phase 3. Fetches raw punches from EasyTime Pro on this PC, normalizes them, and
POSTs them to the CoreOps Phase 2 ingestion endpoint. That is the whole job.

    python sync.py --once                              incremental (the schedule)
    python sync.py --reconcile                         the last SYNC_RECONCILIATION_DAYS
    python sync.py --reconcile-days 7                  an explicit reconciliation span
    python sync.py --from-date 2026-07-29 --to-date 2026-07-30    manual backfill
    python sync.py --status                            local health, no network
    python sync.py --check-config                      validate .env, no network

**One shot, never a daemon.** Each invocation does one window and exits with a
code (see exit_codes.py). Windows Task Scheduler provides the schedule; a
long-lived Python process on an office PC is a thing that silently dies in
March and is noticed in June.

What this connector does NOT do, and cannot be configured to do:

    * infer IN or OUT from a punch state - the live probe returned "0" for
      every punch with a null label, so the direction is genuinely unknown
    * build sessions, pair punches, or drop "intermediate" ones
    * compute working hours, breaks, overtime, late arrival or early departure
    * write to official attendance, or to EasyTime, or to anything but the one
      ingestion endpoint

It moves raw events. Interpretation is a later phase's decision, made once,
server-side, from a mapping table that a human has signed off.
"""
from __future__ import annotations

import argparse
import logging
import sys
import uuid
from datetime import date, datetime, timezone

from config import ConnectorConfig, load_connector_config, resolve_env_path
from exceptions import ConnectorConfigError, EasyTimeError, RunLockUnavailable
from exit_codes import (
    EXIT_ANOTHER_RUN_ACTIVE,
    EXIT_INVALID_CONFIG,
    EXIT_LOCAL_STATE_FAILURE,
    EXIT_SUCCESS,
    label,
)
from logging_setup import configure_logging
from runlock import RunLock
from state import StateStore
from sync_service import (
    MODE_BACKFILL,
    MODE_INCREMENTAL,
    MODE_RECONCILE,
    exit_code_for,
    run_sync,
)

logger = logging.getLogger("easytime.sync.cli")


# -- console helpers (same visual language as probe.py) ----------------------
def heading(text: str) -> None:
    print(f"\n{text}\n{'-' * len(text)}")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="sync.py",
        description=(
            "One-shot EasyTime -> CoreOps punch synchronization. Raw punches only: "
            "no IN/OUT inference, no sessions, no working-hours calculation."
        ),
    )
    mode = parser.add_argument_group("mode (choose exactly one)")
    mode.add_argument(
        "--once",
        action="store_true",
        help="Incremental run: from the stored cursor minus the overlap, up to now.",
    )
    mode.add_argument(
        "--reconcile",
        action="store_true",
        help="Re-send the last SYNC_RECONCILIATION_DAYS days. Catches late uploads.",
    )
    mode.add_argument(
        "--reconcile-days",
        type=int,
        metavar="N",
        help="Reconcile over N days instead of SYNC_RECONCILIATION_DAYS.",
    )
    mode.add_argument("--from-date", metavar="YYYY-MM-DD", help="Backfill start (inclusive).")
    mode.add_argument("--to-date", metavar="YYYY-MM-DD", help="Backfill end (inclusive).")
    mode.add_argument(
        "--status",
        action="store_true",
        help="Print the local sync state and exit. No network call.",
    )
    mode.add_argument(
        "--check-config",
        action="store_true",
        help="Validate the .env and exit. No network call.",
    )

    parser.add_argument(
        "--force",
        action="store_true",
        help="Allow a backfill range longer than SYNC_MAX_RANGE_DAYS. Use sparingly.",
    )
    parser.add_argument("--verbose", action="store_true", help="Debug logging.")
    parser.add_argument(
        "--no-log-file",
        action="store_true",
        help="Console only; do not write to the log directory.",
    )
    return parser


def _parse_date(value: str | None, flag: str) -> date | None:
    """Argument errors are raised as ConnectorConfigError, not SystemExit, so
    they land on exit code 2 (invalid configuration) like every other bad
    input, rather than argparse's generic 2-that-means-something-else."""
    if value is None:
        return None
    try:
        return date.fromisoformat(value)
    except ValueError as exc:
        raise ConnectorConfigError(f"{flag} must be YYYY-MM-DD; got {value!r}.") from exc


def resolve_mode(args: argparse.Namespace) -> str:
    """Exactly one mode, chosen explicitly.

    There is no default. ``python sync.py`` with no arguments does nothing and
    says so - a bare invocation that silently started syncing would be a
    surprise waiting for whoever double-clicks the file.
    """
    selected = [
        name
        for name, chosen in (
            ("--once", args.once),
            ("--reconcile", args.reconcile or args.reconcile_days is not None),
            ("--from-date/--to-date", bool(args.from_date or args.to_date)),
            ("--status", args.status),
            ("--check-config", args.check_config),
        )
        if chosen
    ]
    if len(selected) != 1:
        raise ConnectorConfigError(
            "Choose exactly one mode: --once, --reconcile[-days N], "
            "--from-date/--to-date, --status or --check-config."
            + (f" Got: {', '.join(selected)}." if selected else "")
        )
    chosen = selected[0]
    if chosen == "--once":
        return MODE_INCREMENTAL
    if chosen == "--reconcile":
        return MODE_RECONCILE
    if chosen == "--from-date/--to-date":
        return MODE_BACKFILL
    return "status" if chosen == "--status" else "check-config"


# -- the read-only modes -----------------------------------------------------
def print_status(config: ConnectorConfig) -> int:
    """Local health, from the state file only. Never contacts CoreOps.

    Deliberately offline: "is the connector alive?" must be answerable when the
    reason it is not alive is that the network is down.
    """
    heading("CoreOps EasyTime connector - local status")
    try:
        with StateStore(config.sync.state_path) as store:
            state = store.read(config.coreops.connector_id)
            schema = store.schema_version()
    except EasyTimeError as exc:
        print(f"  [FAIL] {exc}")
        return EXIT_LOCAL_STATE_FAILURE

    for key, value in state.as_display().items():
        print(f"  {key:<24} {value}")

    env_file, env_source = resolve_env_path()
    print()
    print(f"  {'config file':<24} {env_file} ({env_source})")
    print(f"  {'state database':<24} {config.sync.state_path} (schema v{schema})")
    print(f"  {'log directory':<24} {config.sync.log_dir}")
    print(f"  {'lock file':<24} {config.sync.lock_path}")
    print(f"  {'CoreOps endpoint':<24} {config.coreops.batch_url or '(not configured)'}")
    print()
    print("  No token or password is stored in the state database or shown here.")
    return EXIT_SUCCESS


def print_config(config: ConnectorConfig) -> int:
    heading("CoreOps EasyTime connector - configuration")
    # Which file was read, and by which rule. Printed first because "the
    # connector is reading a different file than the one I edited" is the
    # failure this mode exists to rule out. The path is not a secret; nothing
    # from inside the file is printed unredacted.
    path, source = resolve_env_path()
    print(f"\n  [source]")
    print(f"    {'config file':<24} {path}")
    print(f"    {'chosen by':<24} {source}")
    for section, values in config.redacted().items():
        print(f"\n  [{section}]")
        for key, value in values.items():
            print(f"    {key:<24} {value}")
    print("\n  Configuration parsed. No network call was made.")
    return EXIT_SUCCESS


# -- the run summary ---------------------------------------------------------
def print_outcome(outcome, log_path) -> None:
    heading(f"Run summary ({outcome.mode})")
    rows = (
        ("run id", outcome.run_id),
        ("connector id", outcome.connector_id),
        ("source range", outcome.window.as_text()),
        ("range chosen because", outcome.window.reason),
        ("EasyTime pages", outcome.pages),
        ("transactions fetched", outcome.fetched),
        ("normalized", outcome.normalized),
        ("rejected locally", outcome.rejected_locally),
        ("CoreOps batches sent", f"{outcome.batches_sent}/{outcome.batches_planned}"),
        ("received", outcome.received),
        ("inserted", outcome.inserted),
        ("duplicates", outcome.duplicates),
        ("unmapped", outcome.unmapped),
        ("invalid", outcome.invalid),
        ("duration", f"{outcome.duration_seconds:.2f}s"),
        ("cursor advanced to", outcome.cursor_advanced_to or "(unchanged)"),
    )
    for key, value in rows:
        print(f"  {key:<22} {value}")
    if log_path:
        print(f"  {'log file':<22} {log_path}")
    print(f"\n  Result: {label(outcome.exit_code)} (exit {outcome.exit_code})")


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    run_id = uuid.uuid4().hex[:12]

    try:
        mode = resolve_mode(args)
        # Read-only modes must work on a PC whose .env is not finished yet:
        # that is exactly when someone runs --status to find out what is wrong.
        read_only = mode in ("status", "check-config")
        config = load_connector_config(require_credentials=not read_only)
        from_date = _parse_date(args.from_date, "--from-date")
        to_date = _parse_date(args.to_date, "--to-date")
    except EasyTimeError as exc:
        print(f"[FAIL] {exc}")
        return EXIT_INVALID_CONFIG

    log_path = configure_logging(
        run_id=run_id,
        log_dir=None if (args.no_log_file or read_only) else config.sync.log_dir,
        verbose=args.verbose,
        # Log lines go to stderr; the run summary is the stdout surface. Keeping
        # them apart means run_sync.ps1's log file and the operator's console
        # do not each show every line twice.
        console=True,
    )

    if mode == "status":
        return print_status(config)
    if mode == "check-config":
        return print_config(config)

    if mode == MODE_BACKFILL:
        # A backfill is a deliberate act. Say out loud what it is about to do,
        # in the console, before it does it.
        print(
            f"\nBACKFILL: {args.from_date} .. {args.to_date} "
            f"(inclusive, {config.easytime.timezone}). This re-sends every punch in "
            "that range; CoreOps will report already-stored punches as duplicates "
            "and store nothing twice. The incremental cursor is NOT moved."
        )

    try:
        with StateStore(config.sync.state_path) as store:
            # The lock is taken AFTER the state store opens (so a broken state
            # path fails as a state error, not as a lock error) and around
            # everything that talks to EasyTime or CoreOps.
            with RunLock(config.sync.lock_path, run_id=run_id, mode=mode):
                outcome = run_sync(
                    config=config,
                    store=store,
                    mode=mode,
                    now=datetime.now(timezone.utc),
                    from_date=from_date,
                    to_date=to_date,
                    reconcile_days=args.reconcile_days,
                    force=args.force,
                    run_id=run_id,
                )
    except RunLockUnavailable as exc:
        # Expected, not exceptional: a 5-minute schedule overlapping one slow
        # run is normal. Exit quietly with a code the scheduler can read.
        print(f"\n[SKIP] {exc}")
        return EXIT_ANOTHER_RUN_ACTIVE
    except EasyTimeError as exc:
        code = exit_code_for(exc)
        print(f"\n[FAIL] {type(exc).__name__}: {exc}")
        body = getattr(exc, "body_excerpt", "")
        if body:
            # Sanitized upstream by redaction.excerpt - safe to show, and it is
            # the only evidence of WHICH field CoreOps objected to.
            print(f"        CoreOps said: {body}")
        print(f"\n  Result: {label(code)} (exit {code})")
        if log_path:
            print(f"  Log file: {log_path}")
        return code

    print_outcome(outcome, log_path)
    return outcome.exit_code


if __name__ == "__main__":
    sys.exit(main())
