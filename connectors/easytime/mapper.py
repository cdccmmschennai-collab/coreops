"""RawTransaction -> NormalizedPunch, and nothing more than that.

This is the file where it would be easiest to destroy a month of attendance,
so it is the file with the strictest rules. It does exactly four things:

1. Attaches the configured timezone offset to the naive vendor wall-clock text.
2. Copies the vendor's punch-state code across VERBATIM, including ``"0"``.
3. Strips PII from the raw payload before it leaves this PC.
4. Sorts and chunks punches deterministically for transmission.

Things it must never do, and there is no code path here that could:

* infer IN or OUT from a code, a position, an ordinal or a time of day;
* drop an "intermediate" punch - every punch in the window is sent;
* compute a duration, a session, a pair, a first/last, or an attendance status;
* rewrite, round or shift a timestamp.

The live probe (10.2.2) returned punch state ``"0"`` on EVERY record with a null
display label, so IN/OUT is genuinely unresolved. Guessing here would be
invisible: the numbers would look plausible and be wrong. See
docs/attendance/punch-state-mapping.md.
"""
from __future__ import annotations

import hashlib
from collections.abc import Iterable, Iterator, Sequence
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

from schemas import NormalizedPunch, RawTransaction, parse_timestamp, strip_pii

# Version tag inside every batch key. If the key algorithm ever changes, this
# changes with it, so old and new keys can never collide in
# `biometric_sync_batches`.
BATCH_KEY_VERSION = "et1"

# Cap on what the connector puts in raw_payload. The backend sanitizes and caps
# again (MAX_RAW_PAYLOAD_KEYS / _CHARS), but sending less over the wire in the
# first place is cheaper and leaks less if a request is ever logged in transit.
MAX_RAW_PAYLOAD_KEYS = 30
MAX_RAW_PAYLOAD_VALUE_LEN = 300


class NormalizationError(ValueError):
    """One record could not be normalized. Counted locally, never guessed at.

    The message carries the transaction id and the reason - never the employee
    name and never the full raw record.
    """


def _payload_for_wire(txn: RawTransaction) -> dict:
    """The vendor record, reduced to scalars that are safe to transmit.

    Dropped: PII keys (``strip_pii``), nested objects and arrays - the only
    realistic hiding place for a base64 biometric template - and any string
    long enough to BE one. Long strings are dropped whole rather than
    truncated, because half a template is still biometric material.
    """
    clean: dict = {}
    for key, value in strip_pii(txn.raw).items():
        if len(clean) >= MAX_RAW_PAYLOAD_KEYS:
            break
        if not isinstance(key, str):
            continue
        if value is None or isinstance(value, (bool, int, float)):
            clean[key] = value
        elif isinstance(value, str) and len(value) <= MAX_RAW_PAYLOAD_VALUE_LEN:
            clean[key] = value
    return clean


def normalize(txn: RawTransaction, *, provider: str, tz: ZoneInfo) -> NormalizedPunch:
    """One vendor transaction -> the CoreOps wire shape.

    ``punch_time`` is emitted as ISO 8601 **with** the offset (for example
    ``2026-07-29T10:12:10+05:30``). EasyTime reports naive local wall-clock
    text, and the offset is applied exactly once, here, from the connector's
    ``TIMEZONE`` setting. Sending it explicitly means the backend never has to
    fall back to its own ``ATTENDANCE_TIMEZONE`` guess - and if the two ever
    disagreed, the punch would still land on the correct instant.

    An unparseable ``punch_time`` raises: a punch with no trustworthy time is
    not a punch. An unparseable ``upload_time`` does not - it is arrival
    metadata, and losing it must never cost a real attendance event.
    """
    punch_time = parse_timestamp(txn.punch_time_raw)
    if punch_time is None:
        raise NormalizationError(
            f"transaction {txn.external_transaction_id}: unparseable punch_time "
            f"{txn.punch_time_raw!r}"
        )
    if not txn.employee_code:
        raise NormalizationError(
            f"transaction {txn.external_transaction_id}: empty employee code"
        )

    upload_time = parse_timestamp(txn.upload_time_raw or "")

    return NormalizedPunch(
        provider=provider,
        external_transaction_id=txn.external_transaction_id,
        employee_code=txn.employee_code,
        punch_time=_iso_local(punch_time, tz),
        # Verbatim. "0" stays "0"; None stays None.
        punch_state=txn.punch_state_raw,
        punch_state_display=txn.punch_state_display,
        verify_type=txn.verify_type,
        terminal_serial_number=txn.terminal_serial_number,
        terminal_alias=txn.terminal_alias,
        source=txn.source,
        upload_time=_iso_local(upload_time, tz) if upload_time else None,
        raw_payload=_payload_for_wire(txn),
    )


def _iso_local(value: datetime, tz: ZoneInfo) -> str:
    """Attach ``tz`` to a naive wall-clock reading and render ISO 8601.

    ``fold`` is left at its default, so a time that occurs twice in a DST
    transition resolves to the first occurrence. Asia/Kolkata has no DST, which
    is why this is a footnote rather than a policy; it is written down so that
    deploying to an office that does have DST is a conscious decision.
    """
    if value.tzinfo is None:
        value = value.replace(tzinfo=tz)
    return value.isoformat()


def normalize_all(
    transactions: Iterable[RawTransaction], *, provider: str, tz: ZoneInfo
) -> tuple[list[NormalizedPunch], list[str]]:
    """Normalize every transaction. Returns (punches, rejection reasons).

    Rejections are RETURNED, not raised and not swallowed: one malformed record
    must not cost the other 499, and it must not vanish either. The caller logs
    the count and the reasons.
    """
    punches: list[NormalizedPunch] = []
    rejected: list[str] = []
    for txn in transactions:
        try:
            punches.append(normalize(txn, provider=provider, tz=tz))
        except NormalizationError as exc:
            rejected.append(str(exc))
    return punches, rejected


def sort_punches(punches: Sequence[NormalizedPunch]) -> list[NormalizedPunch]:
    """Deterministic order: punch time, then external transaction id.

    Determinism is what makes the batch key reproducible - the same window
    fetched twice must chunk identically, or a retry would produce a different
    key and open a second `biometric_sync_batches` row for the same work.

    The id tiebreak is compared as a zero-padded string so "9" sorts before
    "10" when the ids are numeric, without assuming they always are.
    """
    return sorted(punches, key=lambda p: (p.punch_time, _id_sort_key(p.external_transaction_id)))


def _id_sort_key(value: str) -> tuple[int, str]:
    """(0, padded-number) for numeric ids, (1, text) for anything else."""
    return (0, value.rjust(20, "0")) if value.isdigit() else (1, value)


def chunk(punches: Sequence[NormalizedPunch], size: int) -> Iterator[list[NormalizedPunch]]:
    """Split into batches of at most ``size``, preserving order."""
    if size < 1:
        raise ValueError("batch size must be at least 1")
    for start in range(0, len(punches), size):
        yield list(punches[start : start + size])


def batch_key(
    *,
    connector_id: str,
    provider: str,
    source_from: str,
    source_to: str,
    batch_number: int,
    external_transaction_ids: Sequence[str],
) -> str:
    """Deterministic operational identity for one POST.

    ``et1-<sha256 hex>`` over, in order and NUL-separated:

        version tag | connector id | provider | source_from | source_to
                    | batch_number | each external transaction id, in batch order

    Properties this buys, all of which the sync loop depends on:

    * **Retry stability.** Re-sending the same batch produces the same key, so
      CoreOps updates the existing `biometric_sync_batches` row instead of
      opening a new one for work that already has a record.
    * **Chunk distinctness.** ``batch_number`` and the id list both change
      between chunks, so batch 2 can never be mistaken for batch 1.
    * **No secrets.** The token, the password and the JWT are not inputs; the
      key is safe to print, log and store.
    * **No clock, no randomness.** Nothing here reads the wall clock. A key
      derived from ``time.time()`` would differ on every retry, which is
      precisely the property that must not exist.

    Length is 4 + 64 = 68 characters, inside the backend's 128-char column.

    This key is about REQUEST identity only. Punch-level idempotency is, and
    stays, ``UNIQUE (provider, external_transaction_id)`` in Postgres - which
    is why a lost or mismatched batch key can never cause a duplicate punch.
    """
    digest = hashlib.sha256()
    for part in (
        BATCH_KEY_VERSION,
        connector_id,
        provider,
        source_from,
        source_to,
        str(batch_number),
    ):
        digest.update(part.encode("utf-8"))
        digest.update(b"\x00")
    for external_id in external_transaction_ids:
        digest.update(external_id.encode("utf-8"))
        digest.update(b"\x00")
    return f"{BATCH_KEY_VERSION}-{digest.hexdigest()}"


def to_naive_local(value: datetime, tz: ZoneInfo) -> datetime:
    """An aware datetime -> the naive local wall-clock text EasyTime queries in.

    ``client._fmt_bound`` formats whatever it is given with ``%Y-%m-%d
    %H:%M:%S``; handing it an aware UTC datetime would query the wrong five and
    a half hours.
    """
    return value.astimezone(tz).replace(tzinfo=None)


def span_days(start: datetime, end: datetime) -> float:
    """Fetch-window width in days, used by the range guard."""
    return (end - start) / timedelta(days=1)
