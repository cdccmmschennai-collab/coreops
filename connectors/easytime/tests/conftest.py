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

from config import EasyTimeConfig  # noqa: E402


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
