"""One-shot synchronization: EasyTime -> normalize -> CoreOps -> cursor.

This module holds the orchestration and none of the I/O plumbing. It is
importable, deterministic given its inputs, and never calls ``sys.exit`` or
``argparse`` - ``sync.py`` owns the process. That split is what makes the
partial-failure and replay paths testable without a scheduler, a biometric
device or a VPS.

**The invariant, stated once.**

    The incremental cursor advances only after CoreOps has confirmed every
    batch in the run.

Not "the last batch". Every batch. If batch 1 of 3 succeeds and batch 2 fails,
the cursor stays where it was, the run fails, and the next run re-fetches the
whole window - re-sending batch 1 along with it. That replay is the design, not
a wart: Phase 2 deduplicates on ``UNIQUE (provider, external_transaction_id)``,
so the punches from batch 1 come back as ``duplicates`` and nothing is stored
twice. The alternative - advancing past a window that was only partly ingested
- loses punches permanently and silently.

**Three modes, one code path.**

    incremental  cursor minus SYNC_LOOKBACK_MINUTES .. now      (the schedule)
    reconcile    the last N calendar days .. now                (the late-punch net)
    backfill     an explicit --from-date .. --to-date           (manual repair)

All three fetch, normalize, batch and POST identically. They differ only in how
the window is chosen and in what they are allowed to write back to the cursor.

**What this module does not do**, and has no code path to do: infer IN or OUT,
pair punches, drop an intermediate punch, compute a duration or a session, or
touch official attendance. It moves raw events and counts them.
"""
from __future__ import annotations

import logging
import time
import uuid
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta
from zoneinfo import ZoneInfo

import mapper
from client import EasyTimeClient
from config import PROVIDER, ConnectorConfig
from coreops_client import CoreOpsClient, PunchBatch
from exceptions import (
    ConnectorConfigError,
    ConnectorStateError,
    CoreOpsAuthError,
    CoreOpsEndpointError,
    CoreOpsPayloadError,
    CoreOpsResponseError,
    CoreOpsServerError,
    EasyTimeAuthError,
    EasyTimeError,
    RunLockUnavailable,
)
from exit_codes import (
    EXIT_ANOTHER_RUN_ACTIVE,
    EXIT_COREOPS_AUTH,
    EXIT_COREOPS_FAILURE,
    EXIT_COREOPS_PAYLOAD_REJECTED,
    EXIT_EASYTIME_AUTH,
    EXIT_EASYTIME_FAILURE,
    EXIT_INVALID_CONFIG,
    EXIT_LOCAL_STATE_FAILURE,
    EXIT_SUCCESS,
)
from state import StateStore, SyncState, utc_now_text

logger = logging.getLogger("easytime.sync")

MODE_INCREMENTAL = "incremental"
MODE_RECONCILE = "reconcile"
MODE_BACKFILL = "backfill"
MODES = (MODE_INCREMENTAL, MODE_RECONCILE, MODE_BACKFILL)

STATUS_SUCCESS = "success"
STATUS_FAILED = "failed"


@dataclass(frozen=True)
class FetchWindow:
    """The resolved source range for one run, plus why it is what it is.

    Both bounds are timezone-AWARE in the connector's configured timezone. The
    naive conversion happens once, at the EasyTime call, because that API
    speaks naive local wall-clock text and nothing else.
    """

    source_from: datetime
    source_to: datetime
    reason: str
    clamped: bool = False

    @property
    def span_days(self) -> float:
        return mapper.span_days(self.source_from, self.source_to)

    def as_text(self) -> str:
        return f"{self.source_from.isoformat()} .. {self.source_to.isoformat()}"


@dataclass
class SyncOutcome:
    """Everything one run did, in the shape the log line and the report need."""

    run_id: str
    mode: str
    connector_id: str
    window: FetchWindow
    pages: int = 0
    fetched: int = 0
    normalized: int = 0
    rejected_locally: int = 0
    rejection_reasons: list[str] = field(default_factory=list)
    batches_planned: int = 0
    batches_sent: int = 0
    # Connector-side keys (deterministic, ours) and the CoreOps sync-batch row
    # ids they resolved to (server-side, UUIDs). Kept apart on purpose: they
    # answer different questions when an operator is reconciling a run by hand.
    batch_keys: list[str] = field(default_factory=list)
    batch_ids: list[str] = field(default_factory=list)
    received: int = 0
    inserted: int = 0
    duplicates: int = 0
    unmapped: int = 0
    invalid: int = 0
    duration_seconds: float = 0.0
    status: str = STATUS_SUCCESS
    exit_code: int = EXIT_SUCCESS
    error_code: str | None = None
    cursor_advanced_to: str | None = None

    def counts(self) -> dict:
        return {
            "received": self.received,
            "inserted": self.inserted,
            "duplicates": self.duplicates,
            "unmapped": self.unmapped,
            "invalid": self.invalid,
        }

    def log_line(self) -> str:
        """The single structured line that summarises a run.

        Same ``key=value`` shape as the backend's ingestion logger, so both
        ends of one batch read alike.
        """
        return (
            f"sync.run mode={self.mode} connector_id={self.connector_id} "
            f"source_from={self.window.source_from.isoformat()} "
            f"source_to={self.window.source_to.isoformat()} "
            f"pages={self.pages} fetched={self.fetched} normalized={self.normalized} "
            f"rejected_locally={self.rejected_locally} "
            f"batches_planned={self.batches_planned} batches_sent={self.batches_sent} "
            f"received={self.received} inserted={self.inserted} "
            f"duplicates={self.duplicates} unmapped={self.unmapped} "
            f"invalid={self.invalid} duration_s={self.duration_seconds:.2f} "
            f"status={self.status} exit={self.exit_code}"
        )


# ---------------------------------------------------------------------------
# Window planning - a pure function, so every range rule is unit-testable
# without touching a network or a clock.
# ---------------------------------------------------------------------------

def plan_window(
    *,
    mode: str,
    config: ConnectorConfig,
    state: SyncState,
    now: datetime,
    from_date: date | None = None,
    to_date: date | None = None,
    reconcile_days: int | None = None,
    force: bool = False,
) -> FetchWindow:
    """Resolve the source range for this run.

    ``now`` must be timezone-aware; it is converted into the connector's
    timezone before anything is computed, so the caller can pass UTC.
    """
    tz = ZoneInfo(config.easytime.timezone)
    if now.tzinfo is None:
        raise ConnectorConfigError("plan_window requires an aware `now`.")
    now = now.astimezone(tz)
    sync = config.sync

    if mode == MODE_INCREMENTAL:
        return _plan_incremental(sync=sync, state=state, now=now, tz=tz)
    if mode == MODE_RECONCILE:
        return _plan_reconcile(sync=sync, now=now, days=reconcile_days)
    if mode == MODE_BACKFILL:
        return _plan_backfill(
            sync=sync, tz=tz, from_date=from_date, to_date=to_date, force=force
        )
    raise ConnectorConfigError(f"Unknown sync mode {mode!r}; expected one of {MODES}.")


def _plan_incremental(*, sync, state: SyncState, now: datetime, tz: ZoneInfo) -> FetchWindow:
    """cursor - lookback .. now, or a bounded first-run window.

    The overlap is the whole point. EasyTime accepts a punch that a device
    uploads minutes (the probe saw: hours) after it happened, so a window that
    started exactly where the last one ended would step over anything that
    landed in between. Re-fetching ``SYNC_LOOKBACK_MINUTES`` costs duplicates,
    and duplicates are free.
    """
    clamped = False
    if state.has_cursor:
        cursor = _parse_iso(state.last_successful_source_to, tz=tz)
        source_from = cursor - timedelta(minutes=sync.lookback_minutes)
        reason = (
            f"cursor {cursor.isoformat()} minus {sync.lookback_minutes}m overlap"
        )
    else:
        # NEVER "everything EasyTime has". A first run on a system with three
        # years of history would fetch three years, and the operator would find
        # out when the request timed out.
        source_from = now - timedelta(hours=sync.first_run_lookback_hours)
        reason = (
            f"first run: previous {sync.first_run_lookback_hours}h "
            "(no cursor stored yet)"
        )

    source_to = now
    limit = timedelta(days=sync.max_range_days)
    if source_to - source_from > limit:
        # A long outage must not turn into one enormous request. Clamping makes
        # the connector catch up in bounded steps: this run covers the oldest
        # max_range_days, moves the cursor there, and the next run continues.
        source_to = source_from + limit
        clamped = True
        reason += (
            f"; clamped to {sync.max_range_days}d (the cursor is far behind - "
            "later runs will continue catching up)"
        )

    if source_to <= source_from:
        # A cursor in the future means the clock moved backwards or the state
        # file was hand-edited. Re-fetching the overlap window is the safe
        # interpretation; extending into the future is not.
        source_to = source_from + timedelta(minutes=max(1, sync.lookback_minutes))
        reason += "; cursor is ahead of now - re-fetching the overlap window only"

    return FetchWindow(source_from, source_to, reason, clamped=clamped)


def _plan_reconcile(*, sync, now: datetime, days: int | None) -> FetchWindow:
    """The last N calendar days, from local midnight, up to now.

    Calendar days rather than a rolling N*24h so the pass covers whole working
    days regardless of what time the scheduled task fires. With the default
    N=7 the window is midnight six days ago to now: seven calendar days.

    This is the mechanism that actually recovers the late punches the live
    probe found - the ones EasyTime uploaded the following morning, after the
    incremental run for that evening had already completed and moved on.
    """
    span = days if days is not None else sync.reconciliation_days
    if span < 1:
        raise ConnectorConfigError(f"--reconcile-days must be at least 1; got {span}.")
    if span > sync.max_range_days:
        raise ConnectorConfigError(
            f"--reconcile-days {span} exceeds SYNC_MAX_RANGE_DAYS "
            f"({sync.max_range_days})."
        )
    start_day = (now - timedelta(days=span - 1)).replace(
        hour=0, minute=0, second=0, microsecond=0
    )
    return FetchWindow(
        start_day,
        now,
        f"reconciliation: the last {span} calendar day(s) from local midnight",
    )


def _plan_backfill(
    *, sync, tz: ZoneInfo, from_date: date | None, to_date: date | None, force: bool
) -> FetchWindow:
    """An explicit, bounded, operator-chosen range.

    Both dates are REQUIRED. There is deliberately no default and no "since
    the beginning" option: an unbounded backfill against a live EasyTime
    install is the one command in this connector that can take an office PC
    down, and it should never be reachable by forgetting an argument.
    """
    if from_date is None or to_date is None:
        raise ConnectorConfigError(
            "Backfill requires BOTH --from-date and --to-date (YYYY-MM-DD). There "
            "is no default range on purpose."
        )
    if to_date < from_date:
        raise ConnectorConfigError(
            f"--to-date {to_date.isoformat()} is before --from-date "
            f"{from_date.isoformat()}."
        )
    span = (to_date - from_date).days + 1
    if span > sync.max_range_days and not force:
        raise ConnectorConfigError(
            f"Backfill range is {span} days, over the {sync.max_range_days}-day "
            "limit (SYNC_MAX_RANGE_DAYS). Split it into smaller runs, or pass "
            "--force if you are certain this EasyTime install can serve it."
        )

    source_from = datetime.combine(from_date, datetime.min.time(), tzinfo=tz)
    # Inclusive end of the last day, matching how the EasyTime client formats a
    # bare date bound (23:59:59).
    source_to = datetime.combine(to_date, datetime.min.time(), tzinfo=tz) + timedelta(
        hours=23, minutes=59, seconds=59
    )
    return FetchWindow(
        source_from,
        source_to,
        f"manual backfill: {from_date.isoformat()} .. {to_date.isoformat()} "
        f"({span} day(s))" + (" [forced over the range limit]" if force and span > sync.max_range_days else ""),
    )


def _parse_iso(value: str | None, *, tz: ZoneInfo) -> datetime:
    """A stored cursor -> an aware datetime in the connector timezone."""
    if not value:
        raise ConnectorStateError("The stored cursor is empty but was reported as set.")
    try:
        parsed = datetime.fromisoformat(value)
    except ValueError as exc:
        raise ConnectorStateError(
            f"The stored cursor {value!r} is not a valid ISO 8601 timestamp. Fix or "
            "remove the state database; the connector will not guess."
        ) from exc
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=tz)
    return parsed.astimezone(tz)


# ---------------------------------------------------------------------------
# The run itself
# ---------------------------------------------------------------------------

def run_sync(
    *,
    config: ConnectorConfig,
    store: StateStore,
    mode: str = MODE_INCREMENTAL,
    now: datetime | None = None,
    from_date: date | None = None,
    to_date: date | None = None,
    reconcile_days: int | None = None,
    force: bool = False,
    run_id: str | None = None,
    easytime_factory: Callable[[], EasyTimeClient] | None = None,
    coreops_factory: Callable[[], CoreOpsClient] | None = None,
) -> SyncOutcome:
    """Execute one complete synchronization run.

    Returns a ``SyncOutcome`` on success. On failure it records the error slug
    in the local state and re-raises, leaving the cursor untouched; ``sync.py``
    turns the exception into an exit code.

    The client factories exist for the tests, which inject
    ``httpx.MockTransport`` on both sides. Production passes neither.
    """
    if mode not in MODES:
        raise ConnectorConfigError(f"Unknown sync mode {mode!r}; expected one of {MODES}.")

    run_id = run_id or uuid.uuid4().hex[:12]
    started = time.monotonic()
    tz = ZoneInfo(config.easytime.timezone)
    now = (now or datetime.now(tz)).astimezone(tz)
    connector_id = config.coreops.connector_id

    state = store.read(connector_id)
    window = plan_window(
        mode=mode,
        config=config,
        state=state,
        now=now,
        from_date=from_date,
        to_date=to_date,
        reconcile_days=reconcile_days,
        force=force,
    )
    outcome = SyncOutcome(
        run_id=run_id, mode=mode, connector_id=connector_id, window=window
    )
    logger.info(
        "sync.start mode=%s connector_id=%s window=%s reason=%s",
        mode,
        connector_id,
        window.as_text(),
        window.reason,
    )

    try:
        transactions, pages, parse_errors = _fetch(config, window, tz, easytime_factory)
        outcome.pages = pages
        outcome.fetched = len(transactions) + len(parse_errors)

        punches, rejected = mapper.normalize_all(transactions, provider=PROVIDER, tz=tz)
        # Records EasyTime returned that the client could not even parse into a
        # RawTransaction count as locally rejected too - they were fetched and
        # they are not going to CoreOps, so they belong in the same number.
        outcome.rejection_reasons = [*parse_errors, *rejected]
        outcome.rejected_locally = len(outcome.rejection_reasons)
        outcome.normalized = len(punches)
        if outcome.rejected_locally:
            logger.warning(
                "sync.local_rejects count=%d first=%s",
                outcome.rejected_locally,
                outcome.rejection_reasons[0],
            )

        # Every punch in the window goes, in source order. No filtering by
        # position, state or time of day - the "intermediate" punches are the
        # ones a naive integration would drop, and they are exactly the ones
        # that make a later session calculation possible.
        batches = _build_batches(config, window, punches)
        outcome.batches_planned = len(batches)

        _send_all(config, batches, outcome, coreops_factory)
        _commit(store, config, mode, window, outcome)

    except (EasyTimeError, ConnectorStateError) as exc:
        outcome.status = STATUS_FAILED
        outcome.exit_code = exit_code_for(exc)
        outcome.error_code = _error_slug(outcome.exit_code)
        outcome.duration_seconds = time.monotonic() - started
        _record_failure(store, connector_id, outcome)
        logger.error("%s error=%s", outcome.log_line(), type(exc).__name__)
        raise

    outcome.duration_seconds = time.monotonic() - started
    logger.info(outcome.log_line())
    return outcome


def _fetch(
    config: ConnectorConfig,
    window: FetchWindow,
    tz: ZoneInfo,
    factory: Callable[[], EasyTimeClient] | None,
) -> tuple[list, int, list[str]]:
    """Authenticate and pull every page in the window.

    ``authenticate()`` is called explicitly rather than left to the lazy call
    inside ``iter_transactions``, so a credential failure surfaces as
    ``EasyTimeAuthError`` (exit 4) instead of being reported as whatever the
    first transactions request happened to return.
    """
    client = factory() if factory else EasyTimeClient(config.easytime)
    with client:
        client.authenticate()
        transactions = list(
            client.iter_transactions(
                mapper.to_naive_local(window.source_from, tz),
                mapper.to_naive_local(window.source_to, tz),
                page_size=config.easytime.page_size,
            )
        )
        return transactions, client.last_page_count, list(client.last_parse_errors)


def _build_batches(
    config: ConnectorConfig, window: FetchWindow, punches: list
) -> list[PunchBatch]:
    """Sort deterministically, chunk to the backend limit, key each chunk.

    Sorting before chunking is what makes a retry reproduce the same chunks and
    therefore the same batch keys. Chunking respects ``SYNC_BATCH_SIZE``, which
    ``config`` has already validated against the backend's 1000-punch ceiling.
    """
    ordered = mapper.sort_punches(punches)
    source_from = window.source_from.isoformat()
    source_to = window.source_to.isoformat()

    batches: list[PunchBatch] = []
    for number, group in enumerate(mapper.chunk(ordered, config.coreops.batch_size), start=1):
        batches.append(
            PunchBatch(
                connector_id=config.coreops.connector_id,
                batch_key=mapper.batch_key(
                    connector_id=config.coreops.connector_id,
                    provider=PROVIDER,
                    source_from=source_from,
                    source_to=source_to,
                    batch_number=number,
                    external_transaction_ids=[p.external_transaction_id for p in group],
                ),
                source_from_time=source_from,
                source_to_time=source_to,
                punches=group,
            )
        )
    return batches


def _send_all(
    config: ConnectorConfig,
    batches: list[PunchBatch],
    outcome: SyncOutcome,
    factory: Callable[[], CoreOpsClient] | None,
) -> None:
    """POST every batch in order, accumulating the backend's counters.

    Sequential, not concurrent, and it stops at the first failure. Two reasons:
    an office PC's uplink is not the bottleneck worth optimising, and a failure
    part-way through leaves an unambiguous story - batches 1..n-1 are stored,
    the rest are not, the cursor did not move, and the next run repeats all of
    them.

    An empty window opens no connection at all: there is nothing to say.
    """
    if not batches:
        logger.info("sync.no_punches - nothing to send, the window was empty")
        return

    client = factory() if factory else CoreOpsClient(config.coreops)
    with client:
        for batch in batches:
            result = client.send_batch(batch)
            outcome.batches_sent += 1
            outcome.batch_keys.append(batch.batch_key)
            outcome.batch_ids.append(result.batch_id)
            outcome.received += result.received
            outcome.inserted += result.inserted
            outcome.duplicates += result.duplicates
            outcome.unmapped += result.unmapped
            outcome.invalid += result.invalid


def _commit(
    store: StateStore,
    config: ConnectorConfig,
    mode: str,
    window: FetchWindow,
    outcome: SyncOutcome,
) -> None:
    """Advance the cursor - the last thing a run does, and only on full success.

    Which modes move the incremental cursor:

    * ``incremental`` moves it to this window's end. An EMPTY window still
      moves it: nothing happened in those minutes, and re-asking forever would
      make the connector permanently stuck on the first quiet night.
    * ``reconcile`` does NOT. Its window ends at ``now`` but starts days in the
      past; writing it to the cursor would be harmless, while writing an older
      end would silently rewind. It stamps ``last_reconciliation_at`` instead.
    * ``backfill`` does NOT, for the same reason and more strongly - its window
      is arbitrary and usually historical.
    """
    connector_id = config.coreops.connector_id
    advance_to = window.source_to.isoformat() if mode == MODE_INCREMENTAL else None

    store.record_success(
        connector_id,
        counts=outcome.counts(),
        batch_key=outcome.batch_keys[-1] if outcome.batch_keys else None,
        coreops_batch_id=outcome.batch_ids[-1] if outcome.batch_ids else None,
        source_to=advance_to,
    )
    if mode == MODE_RECONCILE:
        store.record_reconciliation(connector_id)
    outcome.cursor_advanced_to = advance_to


def _record_failure(store: StateStore, connector_id: str, outcome: SyncOutcome) -> None:
    """Best-effort failure stamp. Never masks the exception being raised.

    If the state store is what failed, there is nowhere to write the fact that
    the state store failed; the exception on its way up already says so.
    """
    if outcome.error_code is None:
        return
    try:
        store.record_error(connector_id, error_code=outcome.error_code)
    except ConnectorStateError:
        logger.warning("could not record the failure in the local state store")


# ---------------------------------------------------------------------------
# Exception -> exit code. One table, so the CLI and the tests agree.
# ---------------------------------------------------------------------------

_EXIT_BY_EXCEPTION: tuple[tuple[type[BaseException], int], ...] = (
    # Most specific first: ConnectorConfigError subclasses EasyTimeConfigError,
    # and every CoreOps class subclasses EasyTimeError.
    (RunLockUnavailable, EXIT_ANOTHER_RUN_ACTIVE),
    (ConnectorStateError, EXIT_LOCAL_STATE_FAILURE),
    (CoreOpsAuthError, EXIT_COREOPS_AUTH),
    (CoreOpsPayloadError, EXIT_COREOPS_PAYLOAD_REJECTED),
    # A 404 is a deployment/URL problem on the CoreOps side, reported with the
    # server-failure code and a message that names both possible causes.
    (CoreOpsEndpointError, EXIT_COREOPS_FAILURE),
    (CoreOpsResponseError, EXIT_COREOPS_FAILURE),
    (CoreOpsServerError, EXIT_COREOPS_FAILURE),
    (EasyTimeAuthError, EXIT_EASYTIME_AUTH),
    (ConnectorConfigError, EXIT_INVALID_CONFIG),
)


def exit_code_for(exc: BaseException) -> int:
    """The process exit code for a connector exception."""
    from exceptions import CoreOpsError, EasyTimeConfigError

    for exc_type, code in _EXIT_BY_EXCEPTION:
        if isinstance(exc, exc_type):
            return code
    if isinstance(exc, EasyTimeConfigError):
        return EXIT_INVALID_CONFIG
    if isinstance(exc, CoreOpsError):
        return EXIT_COREOPS_FAILURE
    if isinstance(exc, EasyTimeError):
        # Transport, HTTP and response-shape failures against EasyTime.
        return EXIT_EASYTIME_FAILURE
    raise exc


def _error_slug(code: int) -> str | None:
    from exit_codes import error_code

    return error_code(code)


def utc_stamp() -> str:
    """Re-exported so callers do not import ``state`` for one helper."""
    return utc_now_text()
