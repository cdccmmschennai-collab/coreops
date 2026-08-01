"""Durable sync state - initialization, the cursor rule, and crash safety.

The rule under test throughout: **the cursor advances only after a confirmed
CoreOps success**, and a failure leaves no trace that could be mistaken for
progress.
"""
from __future__ import annotations

import sqlite3

import pytest
from conftest import TEST_CONNECTOR_ID, TEST_CONNECTOR_TOKEN

from exceptions import ConnectorStateError
from state import SCHEMA_VERSION, StateStore, SyncState

COUNTS = {
    "received": 10,
    "inserted": 8,
    "duplicates": 2,
    "unmapped": 1,
    "invalid": 0,
}
WINDOW_END = "2026-07-30T14:00:00+05:30"


@pytest.fixture()
def store(tmp_path):
    with StateStore(tmp_path / "nested" / "state.db") as opened:
        yield opened


class TestInitialization:
    def test_creates_the_file_and_the_parent_directory(self, tmp_path):
        path = tmp_path / "a" / "b" / "state.db"

        with StateStore(path) as store:
            assert store.schema_version() == SCHEMA_VERSION

        assert path.exists()

    def test_is_idempotent(self, tmp_path):
        path = tmp_path / "state.db"
        with StateStore(path) as first:
            first.record_success(
                TEST_CONNECTOR_ID,
                counts=COUNTS,
                batch_key="et1-a",
                coreops_batch_id="uuid-a",
                source_to=WINDOW_END,
            )
        # Re-opening must not wipe anything.
        with StateStore(path) as second:
            assert second.read(TEST_CONNECTOR_ID).last_successful_source_to == WINDOW_END

    def test_unknown_connector_reads_as_empty_not_as_an_error(self, store):
        state = store.read("never-seen")

        assert isinstance(state, SyncState)
        assert state.has_cursor is False
        assert state.last_successful_source_to is None
        assert state.last_records_inserted == 0

    def test_a_file_from_a_newer_connector_is_refused(self, tmp_path):
        path = tmp_path / "state.db"
        with StateStore(path):
            pass
        conn = sqlite3.connect(path)
        with conn:
            conn.execute("UPDATE schema_meta SET value = '99' WHERE key = 'schema_version'")
        conn.close()

        with pytest.raises(ConnectorStateError) as exc:
            with StateStore(path):
                pass

        assert "newer connector" in str(exc.value)

    def test_a_corrupt_file_raises_rather_than_being_deleted(self, tmp_path):
        path = tmp_path / "state.db"
        path.write_bytes(b"this is definitely not a SQLite database" * 40)

        with pytest.raises(ConnectorStateError):
            with StateStore(path):
                pass

        # Deleting a cursor is an operator's decision (it means a re-fetch), so
        # the connector must never make it silently.
        assert path.exists()


class TestCursor:
    def test_success_writes_every_field(self, store):
        state = store.record_success(
            TEST_CONNECTOR_ID,
            counts=COUNTS,
            batch_key="et1-abc",
            coreops_batch_id="3f1a5b0e-0000-4000-8000-000000000001",
            source_to=WINDOW_END,
        )

        assert state.last_successful_source_to == WINDOW_END
        assert state.last_batch_key == "et1-abc"
        assert state.last_coreops_batch_id.endswith("0001")
        assert state.last_records_received == 10
        assert state.last_records_inserted == 8
        assert state.last_records_duplicates == 2
        assert state.last_records_unmapped == 1
        assert state.last_records_invalid == 0
        assert state.last_success_at
        assert state.has_cursor

    def test_the_write_survives_a_reopen(self, tmp_path):
        path = tmp_path / "state.db"
        with StateStore(path) as store:
            store.record_success(
                TEST_CONNECTOR_ID,
                counts=COUNTS,
                batch_key="et1-abc",
                coreops_batch_id="uuid-1",
                source_to=WINDOW_END,
            )
        with StateStore(path) as reopened:
            assert reopened.read(TEST_CONNECTOR_ID).last_successful_source_to == WINDOW_END

    def test_failure_does_not_advance_the_cursor(self, store):
        store.record_success(
            TEST_CONNECTOR_ID,
            counts=COUNTS,
            batch_key="et1-abc",
            coreops_batch_id="uuid-1",
            source_to=WINDOW_END,
        )

        store.record_error(TEST_CONNECTOR_ID, error_code="coreops_failure")
        state = store.read(TEST_CONNECTOR_ID)

        assert state.last_successful_source_to == WINDOW_END, "the cursor must not move"
        assert state.last_error_code == "coreops_failure"
        assert state.last_error_at
        # The last SUCCESS is still the last success - a failure does not
        # rewrite the record of what did work.
        assert state.last_records_inserted == 8

    def test_failure_before_any_success_leaves_no_cursor(self, store):
        store.record_error(TEST_CONNECTOR_ID, error_code="easytime_failure")
        state = store.read(TEST_CONNECTOR_ID)

        assert state.has_cursor is False
        assert state.last_error_code == "easytime_failure"

    def test_a_later_success_clears_the_previous_error(self, store):
        store.record_error(TEST_CONNECTOR_ID, error_code="coreops_failure")
        store.record_success(
            TEST_CONNECTOR_ID,
            counts=COUNTS,
            batch_key="et1-b",
            coreops_batch_id="uuid-2",
            source_to=WINDOW_END,
        )
        state = store.read(TEST_CONNECTOR_ID)

        assert state.last_error_code is None
        assert state.last_error_at is None

    def test_source_to_none_records_the_run_without_moving_the_cursor(self, store):
        """This is how reconcile and backfill report themselves."""
        store.record_success(
            TEST_CONNECTOR_ID,
            counts=COUNTS,
            batch_key="et1-a",
            coreops_batch_id="uuid-1",
            source_to=WINDOW_END,
        )

        store.record_success(
            TEST_CONNECTOR_ID,
            counts={"received": 3, "inserted": 0, "duplicates": 3, "unmapped": 0, "invalid": 0},
            batch_key="et1-recon",
            coreops_batch_id="uuid-recon",
            source_to=None,
        )
        state = store.read(TEST_CONNECTOR_ID)

        assert state.last_successful_source_to == WINDOW_END, "unchanged by design"
        assert state.last_records_duplicates == 3
        assert state.last_batch_key == "et1-recon"

    def test_two_connector_ids_do_not_share_a_cursor(self, store):
        store.record_success(
            "pc-one", counts=COUNTS, batch_key="k1", coreops_batch_id="u1", source_to=WINDOW_END
        )

        assert store.read("pc-two").has_cursor is False


class TestReconciliationStamp:
    def test_records_the_completion_time(self, store):
        assert store.read(TEST_CONNECTOR_ID).last_reconciliation_at is None

        state = store.record_reconciliation(TEST_CONNECTOR_ID)

        assert state.last_reconciliation_at
        assert store.read(TEST_CONNECTOR_ID).last_reconciliation_at

    def test_does_not_disturb_the_cursor(self, store):
        store.record_success(
            TEST_CONNECTOR_ID,
            counts=COUNTS,
            batch_key="et1-a",
            coreops_batch_id="uuid-1",
            source_to=WINDOW_END,
        )

        store.record_reconciliation(TEST_CONNECTOR_ID)

        assert store.read(TEST_CONNECTOR_ID).last_successful_source_to == WINDOW_END


class TestCrashSafety:
    def test_a_run_killed_before_the_write_leaves_the_old_cursor(self, tmp_path):
        """Fetch happened, upload happened, the process died before commit.

        The next run re-fetches the same window and re-sends it. That replay is
        safe because Phase 2 deduplicates on
        UNIQUE (provider, external_transaction_id) - duplicates cost nothing,
        while a cursor ahead of the data loses punches permanently.
        """
        path = tmp_path / "state.db"
        with StateStore(path) as store:
            store.record_success(
                TEST_CONNECTOR_ID,
                counts=COUNTS,
                batch_key="et1-a",
                coreops_batch_id="uuid-1",
                source_to="2026-07-30T14:00:00+05:30",
            )
        # ... a second run uploads successfully and is killed here, before
        # record_success. Nothing was written.
        with StateStore(path) as store:
            assert (
                store.read(TEST_CONNECTOR_ID).last_successful_source_to
                == "2026-07-30T14:00:00+05:30"
            )

    def test_replaying_the_same_success_is_idempotent(self, tmp_path):
        path = tmp_path / "state.db"
        with StateStore(path) as store:
            for _ in range(3):
                store.record_success(
                    TEST_CONNECTOR_ID,
                    counts=COUNTS,
                    batch_key="et1-a",
                    coreops_batch_id="uuid-1",
                    source_to=WINDOW_END,
                )
            rows = store._connect().execute("SELECT COUNT(*) FROM sync_state").fetchone()[0]

        assert rows == 1


class TestSecrets:
    def test_no_secret_is_ever_written_to_the_file(self, tmp_path):
        path = tmp_path / "state.db"
        with StateStore(path) as store:
            store.record_success(
                TEST_CONNECTOR_ID,
                counts=COUNTS,
                batch_key="et1-abc",
                coreops_batch_id="uuid-1",
                source_to=WINDOW_END,
            )
            store.record_error(TEST_CONNECTOR_ID, error_code="coreops_auth")

        blob = path.read_bytes()
        assert TEST_CONNECTOR_TOKEN.encode() not in blob
        assert b"password" not in blob.lower()
        assert b"s3cret" not in blob

    def test_the_status_view_carries_only_operational_facts(self, store):
        store.record_success(
            TEST_CONNECTOR_ID,
            counts=COUNTS,
            batch_key="et1-abc",
            coreops_batch_id="uuid-1",
            source_to=WINDOW_END,
        )
        display = store.read(TEST_CONNECTOR_ID).as_display()

        assert TEST_CONNECTOR_TOKEN not in str(display)
        assert set(display) == {
            "connector_id",
            "last successful sync",
            "last source range end",
            "last batch key",
            "last CoreOps batch id",
            "last received",
            "last inserted",
            "last duplicates",
            "last unmapped",
            "last invalid",
            "last success at",
            "last reconciliation",
            "last error code",
            "last error at",
        }
