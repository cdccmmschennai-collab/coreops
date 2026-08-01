"""One-shot sync orchestration: windows, batching, the cursor and the exit codes.

Fully offline. Both ends are ``httpx.MockTransport``: a fake EasyTime Pro and a
fake CoreOps VPS. What is under test is the sequencing between them, and one
rule above all others:

    The cursor advances only after CoreOps confirms EVERY batch.
"""
from __future__ import annotations

import json
from dataclasses import replace
from datetime import date, datetime, timedelta, timezone
from zoneinfo import ZoneInfo

import httpx
import pytest
from conftest import TEST_CONNECTOR_ID, live_transaction

import sync_service
from client import EasyTimeClient
from config import ConnectorConfig
from coreops_client import CoreOpsClient
from exceptions import (
    ConnectorConfigError,
    CoreOpsAuthError,
    CoreOpsPayloadError,
    CoreOpsServerError,
    EasyTimeAuthError,
    EasyTimeHTTPError,
)
from exit_codes import (
    EXIT_COREOPS_AUTH,
    EXIT_COREOPS_FAILURE,
    EXIT_COREOPS_PAYLOAD_REJECTED,
    EXIT_EASYTIME_AUTH,
    EXIT_EASYTIME_FAILURE,
    EXIT_INVALID_CONFIG,
    EXIT_LOCAL_STATE_FAILURE,
    EXIT_SUCCESS,
)
from state import StateStore
from sync_service import (
    MODE_BACKFILL,
    MODE_INCREMENTAL,
    MODE_RECONCILE,
    exit_code_for,
    plan_window,
    run_sync,
)

IST = ZoneInfo("Asia/Kolkata")
NOW = datetime(2026, 7, 30, 14, 0, 0, tzinfo=IST)


# ---------------------------------------------------------------------------
# Fake EasyTime and fake CoreOps
# ---------------------------------------------------------------------------

class FakeEasyTime:
    """Serves a fixed set of transactions, optionally across several pages."""

    def __init__(self, pages: list[list[dict]] | None = None, *, fail: str | None = None):
        self.pages = pages if pages is not None else [[]]
        self.fail = fail
        self.requests: list[httpx.Request] = []

    def handler(self, request: httpx.Request) -> httpx.Response:
        self.requests.append(request)
        if "token-auth" in request.url.path or "token-refresh" in request.url.path:
            if self.fail == "auth":
                return httpx.Response(401, json={"detail": "bad credentials"})
            return httpx.Response(200, json={"token": "jwt-test-token"})
        if self.fail == "transport":
            raise httpx.ConnectError("EasyTime Pro is not running", request=request)
        if self.fail == "server":
            return httpx.Response(500, text="internal error")

        page_index = int(request.url.params.get("page", 1)) - 1
        records = self.pages[page_index] if page_index < len(self.pages) else []
        next_url = (
            f"/iclock/api/transactions/?page={page_index + 2}"
            if page_index + 1 < len(self.pages)
            else None
        )
        return httpx.Response(200, json={"data": records, "next": next_url})

    def factory(self, config):
        return lambda: EasyTimeClient(config.easytime, transport=httpx.MockTransport(self.handler))


class FakeCoreOps:
    """Records every batch it is sent and replies with a plausible result.

    ``fail_on_batch`` makes the Nth POST fail, which is how the partial-failure
    and replay paths are exercised. ``stored`` mimics the backend's unique
    constraint, so a replayed punch comes back as a duplicate exactly as the
    real endpoint would report it.
    """

    def __init__(self, *, fail_on_batch: int | None = None, fail_status: int = 503):
        self.batches: list[dict] = []
        self.fail_on_batch = fail_on_batch
        self.fail_status = fail_status
        self.stored: set[str] = set()
        self.calls = 0
        self._key_order: list[str] = []

    def handler(self, request: httpx.Request) -> httpx.Response:
        self.calls += 1
        body = json.loads(request.content)
        self.batches.append(body)

        # The ordinal is derived from the deterministic BATCH KEY, not from the
        # request count, so a retry of batch 2 is still batch 2 and keeps
        # failing. Counting requests would let a retryable failure "succeed" on
        # its own retry and quietly defeat the test.
        if body["batch_key"] not in self._key_order:
            self._key_order.append(body["batch_key"])
        ordinal = self._key_order.index(body["batch_key"]) + 1

        if self.fail_on_batch is not None and ordinal == self.fail_on_batch:
            return httpx.Response(self.fail_status, text="simulated failure")

        received = len(body["punches"])
        inserted = 0
        duplicates = 0
        for punch in body["punches"]:
            key = punch["external_transaction_id"]
            if key in self.stored:
                duplicates += 1
            else:
                self.stored.add(key)
                inserted += 1
        return httpx.Response(
            200,
            json={
                "batch_id": f"00000000-0000-4000-8000-{self.calls:012d}",
                "received": received,
                "inserted": inserted,
                "duplicates": duplicates,
                "unmapped": 0,
                "invalid": 0,
                "status": "completed" if duplicates == 0 else "completed_with_errors",
            },
        )

    def factory(self, config):
        return lambda: CoreOpsClient(
            config.coreops,
            transport=httpx.MockTransport(self.handler),
            sleep=lambda _s: None,
        )

    @property
    def sent_ids(self) -> list[str]:
        return [
            punch["external_transaction_id"]
            for batch in self.batches
            for punch in batch["punches"]
        ]


@pytest.fixture()
def store(sync_config):
    with StateStore(sync_config.state_path) as opened:
        yield opened


def execute(
    connector_config: ConnectorConfig,
    store: StateStore,
    easytime: FakeEasyTime,
    coreops: FakeCoreOps,
    **kwargs,
):
    return run_sync(
        config=connector_config,
        store=store,
        now=kwargs.pop("now", NOW),
        easytime_factory=easytime.factory(connector_config),
        coreops_factory=coreops.factory(connector_config),
        **kwargs,
    )


# ---------------------------------------------------------------------------
# Window planning
# ---------------------------------------------------------------------------

class TestFirstRun:
    def test_uses_the_bounded_first_run_lookback(self, connector_config, store):
        window = plan_window(
            mode=MODE_INCREMENTAL,
            config=connector_config,
            state=store.read(TEST_CONNECTOR_ID),
            now=NOW,
        )

        assert window.source_from == NOW - timedelta(hours=24)
        assert window.source_to == NOW
        assert "first run" in window.reason

    def test_never_fetches_the_whole_history(self, connector_config, store):
        window = plan_window(
            mode=MODE_INCREMENTAL,
            config=connector_config,
            state=store.read(TEST_CONNECTOR_ID),
            now=NOW,
        )

        assert window.span_days <= connector_config.sync.max_range_days

    def test_the_lookback_is_configurable(self, connector_config, store):
        config = replace(
            connector_config,
            sync=replace(connector_config.sync, first_run_lookback_hours=6),
        )
        window = plan_window(
            mode=MODE_INCREMENTAL, config=config, state=store.read(TEST_CONNECTOR_ID), now=NOW
        )

        assert window.source_from == NOW - timedelta(hours=6)


class TestIncrementalOverlap:
    def test_re_fetches_the_lookback_window_before_the_cursor(self, connector_config, store):
        store.record_success(
            TEST_CONNECTOR_ID,
            counts={"received": 1, "inserted": 1, "duplicates": 0, "unmapped": 0, "invalid": 0},
            batch_key="et1-a",
            coreops_batch_id="uuid-1",
            source_to="2026-07-30T14:00:00+05:30",
        )

        window = plan_window(
            mode=MODE_INCREMENTAL,
            config=connector_config,
            state=store.read(TEST_CONNECTOR_ID),
            now=NOW + timedelta(minutes=5),
        )

        # The worked example from the spec: cursor 14:00, lookback 15m -> 13:45.
        assert window.source_from == datetime(2026, 7, 30, 13, 45, tzinfo=IST)

    def test_a_far_behind_cursor_is_clamped_not_fetched_in_one_go(self, connector_config, store):
        store.record_success(
            TEST_CONNECTOR_ID,
            counts={"received": 0, "inserted": 0, "duplicates": 0, "unmapped": 0, "invalid": 0},
            batch_key="et1-a",
            coreops_batch_id="uuid-1",
            source_to="2025-01-01T00:00:00+05:30",
        )

        window = plan_window(
            mode=MODE_INCREMENTAL,
            config=connector_config,
            state=store.read(TEST_CONNECTOR_ID),
            now=NOW,
        )

        assert window.clamped
        assert window.span_days == pytest.approx(connector_config.sync.max_range_days)
        assert "catching up" in window.reason

    def test_a_cursor_in_the_future_does_not_produce_an_inverted_window(
        self, connector_config, store
    ):
        store.record_success(
            TEST_CONNECTOR_ID,
            counts={"received": 0, "inserted": 0, "duplicates": 0, "unmapped": 0, "invalid": 0},
            batch_key="et1-a",
            coreops_batch_id="uuid-1",
            source_to="2027-01-01T00:00:00+05:30",
        )

        window = plan_window(
            mode=MODE_INCREMENTAL,
            config=connector_config,
            state=store.read(TEST_CONNECTOR_ID),
            now=NOW,
        )

        assert window.source_to > window.source_from


class TestReconcileWindow:
    def test_covers_the_configured_number_of_calendar_days(self, connector_config, store):
        window = plan_window(
            mode=MODE_RECONCILE,
            config=connector_config,
            state=store.read(TEST_CONNECTOR_ID),
            now=NOW,
        )

        assert window.source_from == datetime(2026, 7, 24, 0, 0, tzinfo=IST)
        assert window.source_to == NOW

    def test_an_explicit_span_overrides_the_setting(self, connector_config, store):
        window = plan_window(
            mode=MODE_RECONCILE,
            config=connector_config,
            state=store.read(TEST_CONNECTOR_ID),
            now=NOW,
            reconcile_days=3,
        )

        assert window.source_from == datetime(2026, 7, 28, 0, 0, tzinfo=IST)

    def test_a_span_over_the_range_limit_is_refused(self, connector_config, store):
        with pytest.raises(ConnectorConfigError):
            plan_window(
                mode=MODE_RECONCILE,
                config=connector_config,
                state=store.read(TEST_CONNECTOR_ID),
                now=NOW,
                reconcile_days=400,
            )


class TestBackfillWindow:
    def test_requires_both_dates(self, connector_config, store):
        with pytest.raises(ConnectorConfigError) as exc:
            plan_window(
                mode=MODE_BACKFILL,
                config=connector_config,
                state=store.read(TEST_CONNECTOR_ID),
                now=NOW,
                from_date=date(2026, 7, 29),
            )

        assert "BOTH" in str(exc.value)

    def test_covers_whole_inclusive_days(self, connector_config, store):
        window = plan_window(
            mode=MODE_BACKFILL,
            config=connector_config,
            state=store.read(TEST_CONNECTOR_ID),
            now=NOW,
            from_date=date(2026, 7, 29),
            to_date=date(2026, 7, 30),
        )

        assert window.source_from == datetime(2026, 7, 29, 0, 0, 0, tzinfo=IST)
        assert window.source_to == datetime(2026, 7, 30, 23, 59, 59, tzinfo=IST)

    def test_rejects_an_inverted_range(self, connector_config, store):
        with pytest.raises(ConnectorConfigError):
            plan_window(
                mode=MODE_BACKFILL,
                config=connector_config,
                state=store.read(TEST_CONNECTOR_ID),
                now=NOW,
                from_date=date(2026, 7, 30),
                to_date=date(2026, 7, 29),
            )

    def test_rejects_an_enormous_range_unless_forced(self, connector_config, store):
        kwargs = dict(
            mode=MODE_BACKFILL,
            config=connector_config,
            state=store.read(TEST_CONNECTOR_ID),
            now=NOW,
            from_date=date(2024, 1, 1),
            to_date=date(2026, 7, 30),
        )
        with pytest.raises(ConnectorConfigError) as exc:
            plan_window(**kwargs)
        assert "--force" in str(exc.value)

        forced = plan_window(**kwargs, force=True)
        assert forced.span_days > connector_config.sync.max_range_days


# ---------------------------------------------------------------------------
# The run
# ---------------------------------------------------------------------------

class TestSuccessfulRun:
    def test_empty_easytime_response_still_succeeds_and_advances_the_cursor(
        self, connector_config, store
    ):
        coreops = FakeCoreOps()
        outcome = execute(connector_config, store, FakeEasyTime([[]]), coreops)

        assert outcome.exit_code == EXIT_SUCCESS
        assert outcome.fetched == 0
        assert coreops.calls == 0, "an empty window opens no connection"
        # A quiet night must not leave the connector permanently stuck asking
        # about the same minutes.
        assert store.read(TEST_CONNECTOR_ID).last_successful_source_to == NOW.isoformat()

    def test_a_single_page_is_fetched_normalized_and_sent(self, connector_config, store):
        coreops = FakeCoreOps()
        easytime = FakeEasyTime([[live_transaction(1), live_transaction(2)]])

        outcome = execute(connector_config, store, easytime, coreops)

        assert outcome.fetched == 2
        assert outcome.normalized == 2
        assert outcome.received == 2
        assert outcome.inserted == 2
        assert outcome.exit_code == EXIT_SUCCESS

    def test_multiple_easytime_pages_are_all_collected(self, connector_config, store):
        easytime = FakeEasyTime(
            [
                [live_transaction(1), live_transaction(2)],
                [live_transaction(3), live_transaction(4)],
                [live_transaction(5)],
            ]
        )
        coreops = FakeCoreOps()

        outcome = execute(connector_config, store, easytime, coreops)

        assert outcome.pages == 3
        assert outcome.fetched == 5
        assert sorted(coreops.sent_ids, key=int) == ["1", "2", "3", "4", "5"]

    def test_multiple_coreops_batches_when_over_the_batch_size(self, connector_config, store):
        # batch_size is 2 in the fixture.
        easytime = FakeEasyTime([[live_transaction(n) for n in range(1, 6)]])
        coreops = FakeCoreOps()

        outcome = execute(connector_config, store, easytime, coreops)

        assert outcome.batches_planned == 3
        assert outcome.batches_sent == 3
        assert [len(b["punches"]) for b in coreops.batches] == [2, 2, 1]
        assert outcome.received == 5

    def test_batch_size_never_exceeds_the_backend_limit(self, connector_config, store):
        config = replace(
            connector_config, coreops=replace(connector_config.coreops, batch_size=1000)
        )
        easytime = FakeEasyTime([[live_transaction(n) for n in range(1, 12)]])
        coreops = FakeCoreOps()

        execute(config, store, easytime, coreops)

        assert all(len(b["punches"]) <= 1000 for b in coreops.batches)

    def test_the_run_reports_the_backend_counters(self, connector_config, store):
        easytime = FakeEasyTime([[live_transaction(1), live_transaction(2)]])
        coreops = FakeCoreOps()

        outcome = execute(connector_config, store, easytime, coreops)

        assert outcome.counts() == {
            "received": 2,
            "inserted": 2,
            "duplicates": 0,
            "unmapped": 0,
            "invalid": 0,
        }


class TestRawSemanticsArePreserved:
    def test_intermediate_punches_are_all_sent(self, connector_config, store):
        """Four punches for one person in one day: in, out for lunch, back, home.

        A naive integration keeps the first and the last. This one keeps all
        four - they are exactly the punches a later session calculation needs,
        and they cannot be recovered once dropped.
        """
        config = replace(
            connector_config, coreops=replace(connector_config.coreops, batch_size=100)
        )
        easytime = FakeEasyTime(
            [
                [
                    live_transaction(1, punch_time="2026-07-29 09:30:00"),
                    live_transaction(2, punch_time="2026-07-29 13:00:00"),
                    live_transaction(3, punch_time="2026-07-29 14:00:00"),
                    live_transaction(4, punch_time="2026-07-29 18:30:00"),
                ]
            ]
        )
        coreops = FakeCoreOps()

        execute(config, store, easytime, coreops)

        assert coreops.sent_ids == ["1", "2", "3", "4"]
        times = [p["punch_time"] for p in coreops.batches[0]["punches"]]
        assert times == [
            "2026-07-29T09:30:00+05:30",
            "2026-07-29T13:00:00+05:30",
            "2026-07-29T14:00:00+05:30",
            "2026-07-29T18:30:00+05:30",
        ]

    def test_raw_state_zero_and_null_display_reach_the_wire(self, connector_config, store):
        easytime = FakeEasyTime([[live_transaction(1)]])
        coreops = FakeCoreOps()

        execute(connector_config, store, easytime, coreops)

        punch = coreops.batches[0]["punches"][0]
        assert punch["raw_punch_state"] == "0"
        assert punch["punch_state_display"] is None

    def test_no_direction_is_ever_added(self, connector_config, store):
        easytime = FakeEasyTime([[live_transaction(n) for n in (1, 2, 3)]])
        coreops = FakeCoreOps()

        execute(connector_config, store, easytime, coreops)

        for batch in coreops.batches:
            for punch in batch["punches"]:
                assert punch["raw_punch_state"] == "0"
                assert "direction" not in punch


class TestLocalRejections:
    def test_a_record_with_a_bad_timestamp_is_counted_not_sent(self, connector_config, store):
        easytime = FakeEasyTime(
            [[live_transaction(1), {**live_transaction(2), "punch_time": "nonsense"}]]
        )
        coreops = FakeCoreOps()

        outcome = execute(connector_config, store, easytime, coreops)

        assert outcome.fetched == 2
        assert outcome.normalized == 1
        assert outcome.rejected_locally == 1
        assert coreops.sent_ids == ["1"]

    def test_a_record_the_client_cannot_parse_is_counted_too(self, connector_config, store):
        broken = live_transaction(2)
        del broken["emp_code"]
        easytime = FakeEasyTime([[live_transaction(1), broken]])
        coreops = FakeCoreOps()

        outcome = execute(connector_config, store, easytime, coreops)

        assert outcome.fetched == 2
        assert outcome.rejected_locally == 1
        assert outcome.normalized == 1

    def test_local_rejections_do_not_block_the_cursor(self, connector_config, store):
        # A malformed vendor record is not a reason to stop syncing forever.
        easytime = FakeEasyTime([[{**live_transaction(1), "punch_time": "nonsense"}]])
        coreops = FakeCoreOps()

        outcome = execute(connector_config, store, easytime, coreops)

        assert outcome.exit_code == EXIT_SUCCESS
        assert store.read(TEST_CONNECTOR_ID).has_cursor


class TestUnmappedResults:
    def test_an_unmapped_batch_is_a_success(self, connector_config, store):
        """Unmapped punches are STORED, just not attributed to an employee yet.

        The live probe found EasyTime codes ("61") that do not match CoreOps
        codes ("EMP225"), so unmapped is the expected steady state until an
        operator fills in the mapping table. Treating it as a failure would
        stop ingestion for the one reason ingestion matters most.
        """

        def handler(request):
            body = json.loads(request.content)
            n = len(body["punches"])
            return httpx.Response(
                200,
                json={
                    "batch_id": "00000000-0000-4000-8000-000000000001",
                    "received": n,
                    "inserted": n,
                    "duplicates": 0,
                    "unmapped": n,
                    "invalid": 0,
                    "status": "completed_with_errors",
                },
            )

        easytime = FakeEasyTime([[live_transaction(1), live_transaction(2)]])
        outcome = run_sync(
            config=connector_config,
            store=store,
            now=NOW,
            easytime_factory=easytime.factory(connector_config),
            coreops_factory=lambda: CoreOpsClient(
                connector_config.coreops,
                transport=httpx.MockTransport(handler),
                sleep=lambda _s: None,
            ),
        )

        assert outcome.exit_code == EXIT_SUCCESS
        assert outcome.unmapped == 2
        assert store.read(TEST_CONNECTOR_ID).last_records_unmapped == 2


class TestDeterministicBatchKeys:
    def test_the_same_window_produces_the_same_keys(self, connector_config, store):
        """A replay of an identical window must key identically.

        That is what lets CoreOps update the existing `biometric_sync_batches`
        rows instead of opening a second set for work that already has a
        record. Exercised through backfill because its window comes from
        explicit dates, so "the same window" is unambiguous.
        """
        rows = [live_transaction(n) for n in range(1, 6)]
        keys = []
        for _ in range(2):
            coreops = FakeCoreOps()
            run_sync(
                config=connector_config,
                store=store,
                mode=MODE_BACKFILL,
                now=NOW,
                from_date=date(2026, 7, 29),
                to_date=date(2026, 7, 29),
                easytime_factory=FakeEasyTime([rows]).factory(connector_config),
                coreops_factory=coreops.factory(connector_config),
            )
            keys.append([b["batch_key"] for b in coreops.batches])

        assert keys[0] == keys[1]
        assert len(keys[0]) == 3

    def test_each_chunk_gets_a_distinct_key(self, connector_config, store):
        easytime = FakeEasyTime([[live_transaction(n) for n in range(1, 6)]])
        coreops = FakeCoreOps()

        execute(connector_config, store, easytime, coreops)
        keys = [b["batch_key"] for b in coreops.batches]

        assert len(keys) == len(set(keys)) == 3

    def test_the_key_is_sent_and_is_well_formed(self, connector_config, store):
        coreops = FakeCoreOps()
        execute(connector_config, store, FakeEasyTime([[live_transaction(1)]]), coreops)

        assert coreops.batches[0]["batch_key"].startswith("et1-")


# ---------------------------------------------------------------------------
# Failure and replay
# ---------------------------------------------------------------------------

class TestPartialBatchFailure:
    def test_the_cursor_does_not_move_when_a_later_batch_fails(self, connector_config, store):
        easytime = FakeEasyTime([[live_transaction(n) for n in range(1, 6)]])
        coreops = FakeCoreOps(fail_on_batch=2)

        with pytest.raises(CoreOpsServerError):
            execute(connector_config, store, easytime, coreops)

        state = store.read(TEST_CONNECTOR_ID)
        assert state.has_cursor is False, "batch 1 succeeded, but the run did not"
        assert state.last_error_code == "coreops_failure"

    def test_batch_one_was_really_stored_and_the_replay_reports_duplicates(
        self, connector_config, store
    ):
        """The documented consequence of not advancing on partial success.

        Batch 1 is stored. The next run re-sends it. Phase 2's
        UNIQUE (provider, external_transaction_id) absorbs the replay as
        duplicates - nothing is stored twice, and nothing is lost.
        """
        rows = [live_transaction(n) for n in range(1, 6)]
        coreops = FakeCoreOps(fail_on_batch=2)
        with pytest.raises(CoreOpsServerError):
            execute(connector_config, store, FakeEasyTime([rows]), coreops)

        assert coreops.stored == {"1", "2"}  # batch 1 landed

        # The next run: same window (the cursor never moved), everything resent.
        coreops.fail_on_batch = None
        coreops.batches.clear()
        outcome = execute(connector_config, store, FakeEasyTime([rows]), coreops)

        assert outcome.exit_code == EXIT_SUCCESS
        assert outcome.duplicates == 2, "batch 1 comes back as duplicates"
        assert outcome.inserted == 3
        assert coreops.stored == {"1", "2", "3", "4", "5"}
        assert store.read(TEST_CONNECTOR_ID).has_cursor

    def test_a_failed_run_records_the_error_without_a_success_stamp(
        self, connector_config, store
    ):
        coreops = FakeCoreOps(fail_on_batch=1)
        with pytest.raises(CoreOpsServerError):
            execute(connector_config, store, FakeEasyTime([[live_transaction(1)]]), coreops)

        state = store.read(TEST_CONNECTOR_ID)
        assert state.last_error_at
        assert state.last_success_at is None


class TestFailureExitCodes:
    def test_easytime_auth_failure(self, connector_config, store):
        with pytest.raises(EasyTimeAuthError) as exc:
            execute(connector_config, store, FakeEasyTime(fail="auth"), FakeCoreOps())

        assert exit_code_for(exc.value) == EXIT_EASYTIME_AUTH

    def test_easytime_transport_failure(self, connector_config, store):
        with pytest.raises(Exception) as exc:
            execute(connector_config, store, FakeEasyTime(fail="transport"), FakeCoreOps())

        assert exit_code_for(exc.value) == EXIT_EASYTIME_FAILURE

    def test_easytime_server_failure(self, connector_config, store):
        with pytest.raises(EasyTimeHTTPError) as exc:
            execute(connector_config, store, FakeEasyTime(fail="server"), FakeCoreOps())

        assert exit_code_for(exc.value) == EXIT_EASYTIME_FAILURE

    def test_coreops_auth_failure(self, connector_config, store):
        coreops = FakeCoreOps(fail_on_batch=1, fail_status=401)
        with pytest.raises(CoreOpsAuthError) as exc:
            execute(connector_config, store, FakeEasyTime([[live_transaction(1)]]), coreops)

        assert exit_code_for(exc.value) == EXIT_COREOPS_AUTH
        assert store.read(TEST_CONNECTOR_ID).last_error_code == "coreops_auth"

    def test_coreops_payload_rejection(self, connector_config, store):
        coreops = FakeCoreOps(fail_on_batch=1, fail_status=422)
        with pytest.raises(CoreOpsPayloadError) as exc:
            execute(connector_config, store, FakeEasyTime([[live_transaction(1)]]), coreops)

        assert exit_code_for(exc.value) == EXIT_COREOPS_PAYLOAD_REJECTED
        assert store.read(TEST_CONNECTOR_ID).last_error_code == "coreops_payload_rejected"

    def test_coreops_404(self, connector_config, store):
        coreops = FakeCoreOps(fail_on_batch=1, fail_status=404)
        with pytest.raises(Exception) as exc:
            execute(connector_config, store, FakeEasyTime([[live_transaction(1)]]), coreops)

        assert exit_code_for(exc.value) == EXIT_COREOPS_FAILURE

    def test_bad_configuration(self):
        assert exit_code_for(ConnectorConfigError("nope")) == EXIT_INVALID_CONFIG

    def test_local_state_failure(self):
        from exceptions import ConnectorStateError

        assert exit_code_for(ConnectorStateError("nope")) == EXIT_LOCAL_STATE_FAILURE

    def test_an_unrecognised_exception_is_re_raised_not_mapped(self):
        # Better an "exit 1, unhandled traceback" than a wrong exit code that
        # a scheduled task would treat as a known, expected failure.
        with pytest.raises(RuntimeError):
            exit_code_for(RuntimeError("something new"))


# ---------------------------------------------------------------------------
# Reconciliation and backfill
# ---------------------------------------------------------------------------

class TestReconciliation:
    def test_it_recovers_a_punch_uploaded_the_following_morning(
        self, connector_config, store
    ):
        """The reason this mode exists.

        The live probe proved some punches reach EasyTime the next morning,
        after the incremental run for that evening has finished and moved on.
        The reconciliation pass sweeps the last seven days and picks them up.
        """
        config = replace(
            connector_config, coreops=replace(connector_config.coreops, batch_size=100)
        )
        coreops = FakeCoreOps()

        # Monday evening's incremental run sees only the punch that had arrived.
        execute(config, store, FakeEasyTime([[live_transaction(1)]]), coreops)
        assert coreops.stored == {"1"}

        # Overnight, the device uploads the evening's final punch.
        late = live_transaction(2, punch_time="2026-07-29 18:31:00")
        outcome = run_sync(
            config=config,
            store=store,
            mode=MODE_RECONCILE,
            now=NOW + timedelta(days=1),
            easytime_factory=FakeEasyTime([[live_transaction(1), late]]).factory(config),
            coreops_factory=coreops.factory(config),
        )

        assert "2" in coreops.stored
        assert outcome.inserted == 1
        assert outcome.duplicates == 1, "the already-stored punch replays harmlessly"

    def test_it_does_not_move_the_incremental_cursor(self, connector_config, store):
        coreops = FakeCoreOps()
        execute(connector_config, store, FakeEasyTime([[live_transaction(1)]]), coreops)
        cursor = store.read(TEST_CONNECTOR_ID).last_successful_source_to

        run_sync(
            config=connector_config,
            store=store,
            mode=MODE_RECONCILE,
            now=NOW,
            easytime_factory=FakeEasyTime([[live_transaction(1)]]).factory(connector_config),
            coreops_factory=coreops.factory(connector_config),
        )

        assert store.read(TEST_CONNECTOR_ID).last_successful_source_to == cursor

    def test_it_stamps_the_completion_time(self, connector_config, store):
        assert store.read(TEST_CONNECTOR_ID).last_reconciliation_at is None

        run_sync(
            config=connector_config,
            store=store,
            mode=MODE_RECONCILE,
            now=NOW,
            easytime_factory=FakeEasyTime([[live_transaction(1)]]).factory(connector_config),
            coreops_factory=FakeCoreOps().factory(connector_config),
        )

        assert store.read(TEST_CONNECTOR_ID).last_reconciliation_at

    def test_rerunning_it_is_safe_and_stores_nothing_twice(self, connector_config, store):
        config = replace(
            connector_config, coreops=replace(connector_config.coreops, batch_size=100)
        )
        rows = [live_transaction(n) for n in range(1, 4)]
        coreops = FakeCoreOps()

        for _ in range(3):
            outcome = run_sync(
                config=config,
                store=store,
                mode=MODE_RECONCILE,
                now=NOW,
                easytime_factory=FakeEasyTime([rows]).factory(config),
                coreops_factory=coreops.factory(config),
            )

        assert coreops.stored == {"1", "2", "3"}
        assert outcome.inserted == 0
        assert outcome.duplicates == 3

    def test_it_never_deletes_anything(self, connector_config, store):
        """There is no delete path. The connector only ever POSTs punches."""
        coreops = FakeCoreOps()
        run_sync(
            config=connector_config,
            store=store,
            mode=MODE_RECONCILE,
            now=NOW,
            easytime_factory=FakeEasyTime([[live_transaction(1)]]).factory(connector_config),
            coreops_factory=coreops.factory(connector_config),
        )

        assert coreops.stored == {"1"}
        assert sync_service.__doc__ is not None


class TestBackfill:
    def test_sends_through_the_same_endpoint_and_keys(self, connector_config, store):
        coreops = FakeCoreOps()
        outcome = run_sync(
            config=connector_config,
            store=store,
            mode=MODE_BACKFILL,
            now=NOW,
            from_date=date(2026, 7, 29),
            to_date=date(2026, 7, 30),
            easytime_factory=FakeEasyTime([[live_transaction(1)]]).factory(connector_config),
            coreops_factory=coreops.factory(connector_config),
        )

        assert outcome.exit_code == EXIT_SUCCESS
        assert coreops.batches[0]["batch_key"].startswith("et1-")
        assert coreops.batches[0]["source_from_time"] == "2026-07-29T00:00:00+05:30"

    def test_does_not_move_the_incremental_cursor(self, connector_config, store):
        run_sync(
            config=connector_config,
            store=store,
            mode=MODE_BACKFILL,
            now=NOW,
            from_date=date(2026, 7, 29),
            to_date=date(2026, 7, 29),
            easytime_factory=FakeEasyTime([[live_transaction(1)]]).factory(connector_config),
            coreops_factory=FakeCoreOps().factory(connector_config),
        )

        assert store.read(TEST_CONNECTOR_ID).has_cursor is False


# ---------------------------------------------------------------------------
# The query the connector actually sends to EasyTime
# ---------------------------------------------------------------------------

class TestEasyTimeQuery:
    def test_the_window_is_sent_as_naive_local_wall_clock(self, connector_config, store):
        easytime = FakeEasyTime([[]])
        execute(connector_config, store, easytime, FakeCoreOps())

        params = dict(easytime.requests[-1].url.params)
        # EasyTime speaks naive local text and nothing else; an aware UTC value
        # would silently query the wrong five and a half hours.
        assert params["start_time"] == "2026-07-29 14:00:00"
        assert params["end_time"] == "2026-07-30 14:00:00"
        assert "+" not in params["start_time"]

    def test_a_utc_now_is_converted_before_planning(self, connector_config, store):
        easytime = FakeEasyTime([[]])
        execute(
            connector_config,
            store,
            easytime,
            FakeCoreOps(),
            now=datetime(2026, 7, 30, 8, 30, tzinfo=timezone.utc),  # 14:00 IST
        )

        assert dict(easytime.requests[-1].url.params)["end_time"] == "2026-07-30 14:00:00"
