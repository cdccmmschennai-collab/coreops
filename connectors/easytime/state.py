"""Durable local sync state - the connector's cursor and its last-run record.

SQLite, one file, typically::

    C:\\ProgramData\\CoreOps\\EasyTimeConnector\\data\\state.db

Why SQLite and not a JSON file: the cursor update has to be atomic against a
process that can be killed at any instant (Task Scheduler's "stop if it runs
too long", a reboot, a power cut on an office PC). A JSON write is
read-modify-write and can leave a truncated file; SQLite gives a real
transaction and a rollback journal for free, in the standard library, with no
extra dependency on the admin PC.

**The one rule this file exists to enforce:**

    The cursor advances only after CoreOps has confirmed, for every batch in
    the run, that it stored the punches.

Everything else follows from it. If the process dies between fetch and upload,
nothing was written and the next run re-fetches the same window. If it dies
after a successful upload but before the cursor update, the next run re-fetches
a window it has already sent - and that is *safe*, not merely tolerable,
because Phase 2 deduplicates on
``UNIQUE (provider, external_transaction_id)``. Replay costs duplicates, which
are free; a cursor that runs ahead of the data costs punches, which are not.

No secret is ever stored here. Not the EasyTime password, not the JWT, not the
CoreOps token. The file holds timestamps, counters and a batch id.
"""
from __future__ import annotations

import sqlite3
from dataclasses import dataclass, replace
from datetime import datetime, timezone
from pathlib import Path

from exceptions import ConnectorStateError

# Bumped whenever the schema changes; `_MIGRATIONS` gains the matching step.
SCHEMA_VERSION = 1


@dataclass(frozen=True)
class SyncState:
    """A snapshot of one connector's local state. Immutable by construction."""

    connector_id: str
    last_successful_sync_time: str | None = None
    last_successful_source_to: str | None = None
    last_batch_key: str | None = None
    last_coreops_batch_id: str | None = None
    last_records_received: int = 0
    last_records_inserted: int = 0
    last_records_duplicates: int = 0
    last_records_unmapped: int = 0
    last_records_invalid: int = 0
    last_success_at: str | None = None
    last_reconciliation_at: str | None = None
    last_error_code: str | None = None
    last_error_at: str | None = None

    @property
    def has_cursor(self) -> bool:
        """False on a first run, which is what triggers the bounded first-run
        lookback instead of an unbounded history fetch."""
        return bool(self.last_successful_source_to)

    def as_display(self) -> dict:
        """Ordered, human-readable view for ``sync.py --status``.

        Everything in here is safe to print: there is nothing else in the row.
        """
        return {
            "connector_id": self.connector_id,
            "last successful sync": self.last_successful_sync_time or "(never)",
            "last source range end": self.last_successful_source_to or "(never)",
            "last batch key": self.last_batch_key or "(none)",
            "last CoreOps batch id": self.last_coreops_batch_id or "(none)",
            "last received": self.last_records_received,
            "last inserted": self.last_records_inserted,
            "last duplicates": self.last_records_duplicates,
            "last unmapped": self.last_records_unmapped,
            "last invalid": self.last_records_invalid,
            "last success at": self.last_success_at or "(never)",
            "last reconciliation": self.last_reconciliation_at or "(never)",
            "last error code": self.last_error_code or "(none)",
            "last error at": self.last_error_at or "(never)",
        }


_COLUMNS = (
    "last_successful_sync_time",
    "last_successful_source_to",
    "last_batch_key",
    "last_coreops_batch_id",
    "last_records_received",
    "last_records_inserted",
    "last_records_duplicates",
    "last_records_unmapped",
    "last_records_invalid",
    "last_success_at",
    "last_reconciliation_at",
    "last_error_code",
    "last_error_at",
)

_CREATE_META = """
CREATE TABLE IF NOT EXISTS schema_meta (
    key   TEXT PRIMARY KEY,
    value TEXT NOT NULL
)
"""

_CREATE_STATE = """
CREATE TABLE IF NOT EXISTS sync_state (
    connector_id              TEXT PRIMARY KEY,
    last_successful_sync_time TEXT,
    last_successful_source_to TEXT,
    last_batch_key            TEXT,
    last_coreops_batch_id     TEXT,
    last_records_received     INTEGER NOT NULL DEFAULT 0,
    last_records_inserted     INTEGER NOT NULL DEFAULT 0,
    last_records_duplicates   INTEGER NOT NULL DEFAULT 0,
    last_records_unmapped     INTEGER NOT NULL DEFAULT 0,
    last_records_invalid      INTEGER NOT NULL DEFAULT 0,
    last_success_at           TEXT,
    last_reconciliation_at    TEXT,
    last_error_code           TEXT,
    last_error_at             TEXT,
    updated_at                TEXT NOT NULL
)
"""


def utc_now_text() -> str:
    """The single timestamp format this store uses: ISO 8601, UTC, aware."""
    return datetime.now(timezone.utc).isoformat()


class StateStore:
    """Read and write the local cursor. One instance per run.

    Opened lazily and closed explicitly (or by the context manager), so a
    ``--status`` call that only reads holds the file for milliseconds.
    """

    def __init__(self, path: Path) -> None:
        self.path = Path(path)
        self._conn: sqlite3.Connection | None = None

    def __enter__(self) -> "StateStore":
        self.initialize()
        return self

    def __exit__(self, *exc: object) -> None:
        self.close()

    # -- lifecycle -----------------------------------------------------------
    def initialize(self) -> None:
        """Create the file, the directory and the schema; apply any upgrade.

        Safe to call repeatedly, and safe to call concurrently with a reader.
        """
        try:
            self.path.parent.mkdir(parents=True, exist_ok=True)
        except OSError as exc:
            raise ConnectorStateError(
                f"Cannot create the state directory {self.path.parent}: "
                f"{type(exc).__name__}. Check the permissions on this path."
            ) from exc

        conn = self._connect()
        try:
            with conn:
                conn.execute(_CREATE_META)
                conn.execute(_CREATE_STATE)
            self._apply_migrations(conn)
        except sqlite3.DatabaseError as exc:
            raise ConnectorStateError(
                f"The state database {self.path} could not be initialized "
                f"({type(exc).__name__}). If the file is corrupt, move it aside - "
                "the connector will start from a fresh cursor and re-fetch the "
                "first-run window. It is NOT deleted automatically."
            ) from exc

    def _connect(self) -> sqlite3.Connection:
        if self._conn is not None:
            return self._conn
        try:
            conn = sqlite3.connect(self.path, timeout=15.0)
            conn.row_factory = sqlite3.Row
            # WAL survives a hard kill better than the rollback journal and
            # lets --status read while a sync run holds a write.
            conn.execute("PRAGMA journal_mode=WAL")
            # Durability over speed: this file is written once per run, and the
            # scenario it exists for is the machine losing power.
            conn.execute("PRAGMA synchronous=FULL")
        except sqlite3.DatabaseError as exc:
            raise ConnectorStateError(
                f"Cannot open the state database {self.path} "
                f"({type(exc).__name__}). If it is not a SQLite file, or is "
                "corrupt, move it aside and re-run."
            ) from exc
        self._conn = conn
        return conn

    def _apply_migrations(self, conn: sqlite3.Connection) -> None:
        """Bring an existing file up to ``SCHEMA_VERSION``.

        A file from a NEWER connector is refused rather than downgraded: a
        future column this build cannot see could carry a cursor meaning this
        build would get wrong.
        """
        row = conn.execute(
            "SELECT value FROM schema_meta WHERE key = 'schema_version'"
        ).fetchone()
        current = int(row["value"]) if row else 0

        if current > SCHEMA_VERSION:
            raise ConnectorStateError(
                f"The state database {self.path} was written by a newer connector "
                f"(schema {current}, this build understands {SCHEMA_VERSION}). "
                "Upgrade the connector rather than downgrading the file."
            )
        # Version 1 is the tables created above. Later versions add their ALTER
        # statements here, guarded by `if current < N`.
        if current < SCHEMA_VERSION:
            with conn:
                conn.execute(
                    "INSERT INTO schema_meta (key, value) VALUES ('schema_version', ?) "
                    "ON CONFLICT(key) DO UPDATE SET value = excluded.value",
                    (str(SCHEMA_VERSION),),
                )

    def close(self) -> None:
        if self._conn is not None:
            self._conn.close()
            self._conn = None

    # -- reads ---------------------------------------------------------------
    def read(self, connector_id: str) -> SyncState:
        """The stored state, or an empty one for a connector never seen here."""
        conn = self._connect()
        try:
            row = conn.execute(
                "SELECT * FROM sync_state WHERE connector_id = ?", (connector_id,)
            ).fetchone()
        except sqlite3.DatabaseError as exc:
            raise ConnectorStateError(
                f"Cannot read the state database {self.path} ({type(exc).__name__})."
            ) from exc
        if row is None:
            return SyncState(connector_id=connector_id)
        return SyncState(
            connector_id=connector_id,
            **{column: row[column] for column in _COLUMNS},
        )

    def schema_version(self) -> int:
        row = self._connect().execute(
            "SELECT value FROM schema_meta WHERE key = 'schema_version'"
        ).fetchone()
        return int(row["value"]) if row else 0

    # -- writes --------------------------------------------------------------
    def record_success(
        self,
        connector_id: str,
        *,
        counts: dict,
        batch_key: str | None,
        coreops_batch_id: str | None,
        source_to: str | None,
        at: str | None = None,
    ) -> SyncState:
        """Commit the outcome of a fully successful run, atomically.

        ``source_to=None`` records the run WITHOUT moving the incremental
        cursor. That is how reconciliation and backfill report themselves: they
        look backwards over ground the cursor has already covered, so advancing
        it from their window would skip everything between their end and the
        real cursor.

        One statement, one transaction: the row is either entirely the previous
        run's or entirely this one's. There is no interleaved state in which the
        cursor has moved but the counters have not.
        """
        now = at or utc_now_text()
        current = self.read(connector_id)
        updated = replace(
            current,
            last_successful_sync_time=now,
            last_successful_source_to=source_to or current.last_successful_source_to,
            last_batch_key=batch_key or current.last_batch_key,
            last_coreops_batch_id=coreops_batch_id or current.last_coreops_batch_id,
            last_records_received=int(counts.get("received", 0)),
            last_records_inserted=int(counts.get("inserted", 0)),
            last_records_duplicates=int(counts.get("duplicates", 0)),
            last_records_unmapped=int(counts.get("unmapped", 0)),
            last_records_invalid=int(counts.get("invalid", 0)),
            last_success_at=now,
            # A success clears the previous failure, so `--status` never shows a
            # stale error next to a fresh success.
            last_error_code=None,
            last_error_at=None,
        )
        self._write(updated, now)
        return updated

    def record_reconciliation(self, connector_id: str, *, at: str | None = None) -> SyncState:
        """Stamp the completion of a reconciliation pass."""
        now = at or utc_now_text()
        updated = replace(self.read(connector_id), last_reconciliation_at=now)
        self._write(updated, now)
        return updated

    def record_error(
        self, connector_id: str, *, error_code: str, at: str | None = None
    ) -> SyncState:
        """Record a failure WITHOUT touching the cursor or the last-success
        fields. A failed run must leave no trace that could be mistaken for
        progress."""
        now = at or utc_now_text()
        updated = replace(
            self.read(connector_id), last_error_code=error_code, last_error_at=now
        )
        self._write(updated, now)
        return updated

    def _write(self, state: SyncState, now: str) -> None:
        conn = self._connect()
        columns = ", ".join(_COLUMNS)
        placeholders = ", ".join("?" for _ in _COLUMNS)
        assignments = ", ".join(f"{c} = excluded.{c}" for c in _COLUMNS)
        values = [getattr(state, column) for column in _COLUMNS]
        try:
            with conn:
                conn.execute(
                    f"INSERT INTO sync_state (connector_id, {columns}, updated_at) "
                    f"VALUES (?, {placeholders}, ?) "
                    f"ON CONFLICT(connector_id) DO UPDATE SET {assignments}, "
                    "updated_at = excluded.updated_at",
                    [state.connector_id, *values, now],
                )
        except sqlite3.DatabaseError as exc:
            raise ConnectorStateError(
                f"Cannot write the state database {self.path} "
                f"({type(exc).__name__}). The cursor was NOT advanced; the next run "
                "will re-fetch the same window, which is safe."
            ) from exc
