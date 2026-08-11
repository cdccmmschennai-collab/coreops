"""Connector test fixtures.

The connector is a standalone script directory, not an installed package, so
the tests put its directory on sys.path exactly the way `python probe.py` does.
Every test here is OFFLINE: httpx.MockTransport stands in for EasyTime, so the
suite runs on any machine with no biometric system in sight.
"""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

CONNECTOR_DIR = Path(__file__).resolve().parents[1]
if str(CONNECTOR_DIR) not in sys.path:
    sys.path.insert(0, str(CONNECTOR_DIR))

from config import (  # noqa: E402
    ConnectorConfig,
    CoreOpsConfig,
    EasyTimeConfig,
    SyncConfig,
)


@pytest.fixture()
def config() -> EasyTimeConfig:
    """A fully pinned config - tests exercise behaviour, not path discovery."""
    return EasyTimeConfig(
        base_url="http://127.0.0.1:8080",
        username="coreops_integration",
        password="s3cret",
        auth_mode="jwt",
        auth_path="/api/jwt-api-token-auth/",
        refresh_path="/api/jwt-api-token-refresh/",
        transactions_path="/iclock/api/transactions/",
        retries=2,
        page_size=2,
        timeout_seconds=1.0,
    )


@pytest.fixture()
def discovering_config(config: EasyTimeConfig) -> EasyTimeConfig:
    """No pinned paths - the client must walk its candidate lists."""
    return config.with_paths(auth_path="", refresh_path="", transactions_path="")


def transaction(
    txn_id: int,
    emp_code: str = "EMP069",
    punch_time: str = "2026-07-28 09:30:00",
    punch_state: str = "0",
    display: str | None = "Check In",
) -> dict:
    """One EasyTime-shaped transaction record."""
    return {
        "id": txn_id,
        "emp_code": emp_code,
        "first_name": "Should",
        "last_name": "BeStripped",
        "punch_time": punch_time,
        "punch_state": punch_state,
        "punch_state_display": display,
        "verify_type": "1",
        "terminal_sn": "CDC-DEV-01",
        "terminal_alias": "Main Gate",
        "upload_time": "2026-07-28 09:30:04",
        "source": "1",
    }


def live_transaction(txn_id: int, emp_code: str = "61", punch_time: str = "2026-07-29 10:12:10") -> dict:
    """A record shaped like what the LIVE 10.2.2 probe actually returned.

    The difference from ``transaction`` matters: every observed punch had state
    ``"0"`` with ``punch_state_display: null``, and the employee code was a bare
    number, not a CoreOps ``EMP***`` code. Phase 3 tests assert against this
    shape so a change that only works on the tidy fixture cannot pass.
    """
    return {
        "id": txn_id,
        "emp_code": emp_code,
        "first_name": "Should",
        "last_name": "BeStripped",
        "punch_time": punch_time,
        "punch_state": "0",
        "punch_state_display": None,
        "verify_type": "1",
        "terminal_sn": "CDC-DEV-01",
        "terminal_alias": "F22/ID",
        "upload_time": "2026-07-30 07:02:00",  # uploaded the FOLLOWING morning
        "source": "1",
    }


# -- Phase 3 fixtures --------------------------------------------------------
# The token is long enough for redaction.contains_secret and distinctive enough
# that a leak into a log file or a URL is unambiguous in an assertion.
TEST_CONNECTOR_TOKEN = "test-connector-token-NEVER-LOG-THIS-0123456789"
TEST_CONNECTOR_ID = "admin-pc-test"


@pytest.fixture()
def coreops_config() -> CoreOpsConfig:
    return CoreOpsConfig(
        api_url="https://coreops.example.test/api/v1",
        connector_token=TEST_CONNECTOR_TOKEN,
        connector_id=TEST_CONNECTOR_ID,
        timeout_seconds=1.0,
        retries=3,
        batch_size=2,  # small, so batching is exercised by two or three punches
    )


@pytest.fixture()
def sync_config(tmp_path) -> SyncConfig:
    """Every path lands under tmp_path - no test ever touches ProgramData."""
    return SyncConfig(
        lookback_minutes=15,
        reconciliation_days=7,
        first_run_lookback_hours=24,
        max_range_days=31,
        state_path=tmp_path / "data" / "state.db",
        log_dir=tmp_path / "logs",
        lock_path=tmp_path / "data" / "sync.lock",
    )


@pytest.fixture()
def connector_config(config, coreops_config, sync_config) -> ConnectorConfig:
    return ConnectorConfig(easytime=config, coreops=coreops_config, sync=sync_config)
