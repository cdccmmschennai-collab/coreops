"""The sync.py command line: mode selection, exit codes, locking, logging.

Task Scheduler sees nothing but the exit code, so these tests are the contract
between the connector and whoever is on call.
"""
from __future__ import annotations

import json
from dataclasses import replace

import httpx
import pytest
from conftest import TEST_CONNECTOR_ID, TEST_CONNECTOR_TOKEN, live_transaction

import sync
from client import EasyTimeClient
from coreops_client import CoreOpsClient
from exceptions import (
    ConnectorStateError,
    CoreOpsAuthError,
    CoreOpsPayloadError,
    CoreOpsServerError,
    EasyTimeAuthError,
)
from exit_codes import (
    EXIT_ANOTHER_RUN_ACTIVE,
    EXIT_COREOPS_AUTH,
    EXIT_COREOPS_FAILURE,
    EXIT_COREOPS_PAYLOAD_REJECTED,
    EXIT_EASYTIME_AUTH,
    EXIT_INVALID_CONFIG,
    EXIT_LOCAL_STATE_FAILURE,
    EXIT_SUCCESS,
    label,
)
from runlock import RunLock
from state import StateStore


@pytest.fixture()
def cli(monkeypatch, connector_config):
    """sync.main with configuration loading stubbed out.

    Config LOADING is covered in test_config.py; this file is about what the
    CLI does once it has a config.
    """
    monkeypatch.setattr(sync, "load_connector_config", lambda **kw: connector_config)
    return connector_config


def easytime_stub(pages):
    def handler(request):
        if "token-auth" in request.url.path or "token-refresh" in request.url.path:
            return httpx.Response(200, json={"token": "jwt-test"})
        return httpx.Response(200, json={"data": pages, "next": None})

    return handler


def coreops_stub(status=200, body=None):
    def handler(request):
        if status != 200:
            return httpx.Response(status, text="simulated")
        payload = json.loads(request.content)
        n = len(payload["punches"])
        return httpx.Response(
            200,
            json=body
            or {
                "batch_id": "00000000-0000-4000-8000-000000000001",
                "received": n,
                "inserted": n,
                "duplicates": 0,
                "unmapped": 0,
                "invalid": 0,
                "status": "completed",
            },
        )

    return handler


@pytest.fixture()
def wired(monkeypatch, connector_config):
    """Point sync_service's real client construction at mock transports."""

    def wire(easytime_pages, coreops_status=200):
        import sync_service

        monkeypatch.setattr(
            sync_service,
            "EasyTimeClient",
            lambda cfg: EasyTimeClient(
                cfg, transport=httpx.MockTransport(easytime_stub(easytime_pages))
            ),
        )
        monkeypatch.setattr(
            sync_service,
            "CoreOpsClient",
            lambda cfg: CoreOpsClient(
                cfg,
                transport=httpx.MockTransport(coreops_stub(coreops_status)),
                sleep=lambda _s: None,
            ),
        )

    return wire


class TestModeSelection:
    @pytest.mark.parametrize(
        "argv",
        [
            [],
            ["--once", "--reconcile"],
            ["--once", "--status"],
            ["--reconcile", "--from-date", "2026-07-29", "--to-date", "2026-07-30"],
        ],
    )
    def test_ambiguous_or_missing_mode_is_a_configuration_error(self, cli, argv):
        # A bare `python sync.py` must not silently start syncing - someone
        # will double-click this file one day.
        assert sync.main(argv) == EXIT_INVALID_CONFIG

    def test_a_malformed_date_is_a_configuration_error(self, cli):
        assert sync.main(["--from-date", "29-07-2026", "--to-date", "2026-07-30"]) == (
            EXIT_INVALID_CONFIG
        )

    def test_reconcile_days_alone_selects_reconcile(self, cli, wired, capsys):
        wired([live_transaction(1)])

        assert sync.main(["--reconcile-days", "3", "--no-log-file"]) == EXIT_SUCCESS
        assert "reconcile" in capsys.readouterr().out


class TestReadOnlyModes:
    def test_status_prints_the_stored_state_and_no_secret(self, cli, capsys):
        with StateStore(cli.sync.state_path) as store:
            store.record_success(
                TEST_CONNECTOR_ID,
                counts={"received": 4, "inserted": 3, "duplicates": 1, "unmapped": 2, "invalid": 0},
                batch_key="et1-abc",
                coreops_batch_id="uuid-1",
                source_to="2026-07-30T14:00:00+05:30",
            )

        assert sync.main(["--status"]) == EXIT_SUCCESS

        out = capsys.readouterr().out
        assert "2026-07-30T14:00:00+05:30" in out
        assert "et1-abc" in out
        assert "last unmapped" in out
        assert TEST_CONNECTOR_TOKEN not in out
        assert "s3cret" not in out

    def test_status_works_before_the_first_run(self, cli, capsys):
        assert sync.main(["--status"]) == EXIT_SUCCESS
        assert "(never)" in capsys.readouterr().out

    def test_status_reports_a_broken_state_file(self, cli, capsys, monkeypatch):
        cli.sync.state_path.parent.mkdir(parents=True, exist_ok=True)
        cli.sync.state_path.write_bytes(b"not a database" * 100)

        assert sync.main(["--status"]) == EXIT_LOCAL_STATE_FAILURE

    def test_status_makes_no_network_call(self, cli, monkeypatch):
        def explode(*a, **kw):
            raise AssertionError("--status must not touch the network")

        monkeypatch.setattr(httpx.Client, "request", explode)
        monkeypatch.setattr(httpx.Client, "post", explode)

        assert sync.main(["--status"]) == EXIT_SUCCESS

    def test_check_config_prints_a_redacted_view(self, cli, capsys):
        assert sync.main(["--check-config"]) == EXIT_SUCCESS

        out = capsys.readouterr().out
        assert "No network call was made" in out
        assert TEST_CONNECTOR_TOKEN not in out
        assert "s3cret" not in out
        assert "***" in out


class TestSuccessfulRun:
    def test_once_returns_zero_and_prints_the_summary(self, cli, wired, capsys):
        wired([live_transaction(1), live_transaction(2)])

        assert sync.main(["--once", "--no-log-file"]) == EXIT_SUCCESS

        out = capsys.readouterr().out
        assert "transactions fetched" in out
        assert "cursor advanced to" in out
        assert "success (exit 0)" in out

    def test_the_cursor_is_visible_afterwards_via_status(self, cli, wired, capsys):
        wired([live_transaction(1)])
        sync.main(["--once", "--no-log-file"])
        capsys.readouterr()

        sync.main(["--status"])

        assert "(never)" not in capsys.readouterr().out.split("last reconciliation")[0]

    def test_backfill_announces_itself_before_running(self, cli, wired, capsys):
        wired([live_transaction(1)])

        assert sync.main(
            ["--from-date", "2026-07-29", "--to-date", "2026-07-29", "--no-log-file"]
        ) == EXIT_SUCCESS

        out = capsys.readouterr().out
        assert "BACKFILL" in out
        assert "cursor is NOT moved" in out


class TestFailureExitCodes:
    @pytest.mark.parametrize(
        "status,expected",
        [
            (401, EXIT_COREOPS_AUTH),
            (403, EXIT_COREOPS_AUTH),
            (404, EXIT_COREOPS_FAILURE),
            (422, EXIT_COREOPS_PAYLOAD_REJECTED),
            (503, EXIT_COREOPS_FAILURE),
        ],
    )
    def test_coreops_failures_map_to_their_codes(self, cli, wired, status, expected, capsys):
        wired([live_transaction(1)], coreops_status=status)

        assert sync.main(["--once", "--no-log-file"]) == expected
        assert label(expected) in capsys.readouterr().out

    def test_easytime_auth_failure(self, cli, monkeypatch, capsys):
        import sync_service

        def handler(request):
            return httpx.Response(401, json={"detail": "bad credentials"})

        monkeypatch.setattr(
            sync_service,
            "EasyTimeClient",
            lambda cfg: EasyTimeClient(cfg, transport=httpx.MockTransport(handler)),
        )

        assert sync.main(["--once", "--no-log-file"]) == EXIT_EASYTIME_AUTH

    def test_a_422_shows_the_sanitized_evidence(self, cli, monkeypatch, capsys):
        import sync_service

        def coreops_handler(request):
            return httpx.Response(422, json={"detail": "punches.0.punch_time: too long"})

        monkeypatch.setattr(
            sync_service,
            "EasyTimeClient",
            lambda cfg: EasyTimeClient(
                cfg, transport=httpx.MockTransport(easytime_stub([live_transaction(1)]))
            ),
        )
        monkeypatch.setattr(
            sync_service,
            "CoreOpsClient",
            lambda cfg: CoreOpsClient(
                cfg, transport=httpx.MockTransport(coreops_handler), sleep=lambda _s: None
            ),
        )

        assert sync.main(["--once", "--no-log-file"]) == EXIT_COREOPS_PAYLOAD_REJECTED

        out = capsys.readouterr().out
        assert "CoreOps said" in out
        assert "punch_time" in out

    def test_a_failure_leaves_the_cursor_alone(self, cli, wired):
        wired([live_transaction(1)], coreops_status=503)
        sync.main(["--once", "--no-log-file"])

        with StateStore(cli.sync.state_path) as store:
            assert store.read(TEST_CONNECTOR_ID).has_cursor is False


class TestLocking:
    def test_a_second_invocation_exits_with_the_lock_code(self, cli, wired, capsys):
        wired([live_transaction(1)])

        with RunLock(cli.sync.lock_path, run_id="holder", mode="incremental"):
            code = sync.main(["--once", "--no-log-file"])

        assert code == EXIT_ANOTHER_RUN_ACTIVE
        out = capsys.readouterr().out
        assert "[SKIP]" in out
        assert "Another connector run holds" in out

    def test_a_blocked_invocation_does_not_touch_the_cursor(self, cli, wired):
        wired([live_transaction(1)])

        with RunLock(cli.sync.lock_path, run_id="holder"):
            sync.main(["--once", "--no-log-file"])

        with StateStore(cli.sync.state_path) as store:
            assert store.read(TEST_CONNECTOR_ID).has_cursor is False

    def test_the_lock_is_released_after_a_successful_run(self, cli, wired):
        wired([live_transaction(1)])
        assert sync.main(["--once", "--no-log-file"]) == EXIT_SUCCESS

        with RunLock(cli.sync.lock_path, run_id="next") as lock:
            assert lock.held

    def test_the_lock_is_released_after_a_failed_run(self, cli, wired):
        wired([live_transaction(1)], coreops_status=503)
        sync.main(["--once", "--no-log-file"])

        with RunLock(cli.sync.lock_path, run_id="next") as lock:
            assert lock.held


class TestLogging:
    def test_a_dated_log_file_is_written(self, cli, wired):
        wired([live_transaction(1)])

        assert sync.main(["--once"]) == EXIT_SUCCESS

        logs = list(cli.sync.log_dir.glob("sync-*.log"))
        assert len(logs) == 1
        assert "sync.run" in logs[0].read_text(encoding="utf-8")

    def test_the_log_line_carries_the_operational_counters(self, cli, wired):
        wired([live_transaction(1), live_transaction(2)])
        sync.main(["--once"])

        text = next(cli.sync.log_dir.glob("sync-*.log")).read_text(encoding="utf-8")

        for key in (
            "mode=",
            "connector_id=",
            "source_from=",
            "source_to=",
            "pages=",
            "fetched=",
            "normalized=",
            "rejected_locally=",
            "batches_sent=",
            "received=",
            "inserted=",
            "duplicates=",
            "unmapped=",
            "invalid=",
            "duration_s=",
            "status=",
            "run=",
        ):
            assert key in text, f"{key} missing from the run log"

    def test_no_secret_reaches_the_log_file(self, cli, wired):
        wired([live_transaction(1)])
        sync.main(["--once"])

        text = next(cli.sync.log_dir.glob("sync-*.log")).read_text(encoding="utf-8")

        assert TEST_CONNECTOR_TOKEN not in text
        assert "s3cret" not in text  # the EasyTime password from the fixture
        assert "jwt-test" not in text  # the EasyTime access token
        assert "Authorization" not in text

    def test_no_secret_reaches_the_log_file_on_failure(self, cli, wired):
        wired([live_transaction(1)], coreops_status=503)
        sync.main(["--once"])

        text = next(cli.sync.log_dir.glob("sync-*.log")).read_text(encoding="utf-8")

        assert TEST_CONNECTOR_TOKEN not in text
        assert "s3cret" not in text

    def test_a_log_directory_that_cannot_be_created_does_not_stop_the_run(self, cli, wired):
        # Losing the ability to WRITE A LOG must never cost punches. Here the
        # log "directory" is already a file, so mkdir cannot succeed.
        wired([live_transaction(1)])
        cli.sync.log_dir.parent.mkdir(parents=True, exist_ok=True)
        cli.sync.log_dir.write_text("in the way", encoding="utf-8")

        assert sync.main(["--once"]) == EXIT_SUCCESS

        with StateStore(cli.sync.state_path) as store:
            assert store.read(TEST_CONNECTOR_ID).has_cursor, "the punches still landed"
