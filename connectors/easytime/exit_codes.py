"""Process exit codes for sync.py.

The connector is driven by Windows Task Scheduler, which can see nothing except
the exit code. Every code therefore has to answer one question on its own:
**who has to do something about this?**

    0  nobody - it worked
    2  whoever edits .env on this PC
    3  nobody - a previous run is still going
    4  whoever owns the EasyTime integration account
    5  whoever owns the EasyTime Pro service on this PC
    6  whoever holds the CoreOps connector token
    7  whoever maintains the connector code (a contract bug)
    8  whoever operates the CoreOps VPS
    9  whoever administers this PC's ProgramData directory

Codes 1 and >9 are deliberately unused: 1 is what Python itself returns for an
unhandled traceback, so keeping it free means "exit 1" always reads as "the
connector crashed in a way it did not anticipate".

These numbers are part of the operational contract (scheduled-task retry rules
and the alerting runbook key off them). Change one only with the documentation.
"""
from __future__ import annotations

EXIT_SUCCESS = 0
EXIT_INVALID_CONFIG = 2
EXIT_ANOTHER_RUN_ACTIVE = 3
EXIT_EASYTIME_AUTH = 4
EXIT_EASYTIME_FAILURE = 5
EXIT_COREOPS_AUTH = 6
EXIT_COREOPS_PAYLOAD_REJECTED = 7
EXIT_COREOPS_FAILURE = 8
EXIT_LOCAL_STATE_FAILURE = 9

# Human-readable label per code, printed in the run summary and used by the
# tests so a renumbering cannot silently pass.
EXIT_LABELS = {
    EXIT_SUCCESS: "success",
    EXIT_INVALID_CONFIG: "invalid configuration",
    EXIT_ANOTHER_RUN_ACTIVE: "another run is active",
    EXIT_EASYTIME_AUTH: "EasyTime authentication failure",
    EXIT_EASYTIME_FAILURE: "EasyTime transport/API failure",
    EXIT_COREOPS_AUTH: "CoreOps authentication failure",
    EXIT_COREOPS_PAYLOAD_REJECTED: "CoreOps payload rejection",
    EXIT_COREOPS_FAILURE: "CoreOps transport/server failure",
    EXIT_LOCAL_STATE_FAILURE: "local state failure",
}

# Stable slugs written to the local state store's `last_error_code`. Kept
# separate from the numeric codes so the state row stays readable by a human
# who is not holding this file.
ERROR_CODE_BY_EXIT = {
    EXIT_INVALID_CONFIG: "invalid_config",
    EXIT_ANOTHER_RUN_ACTIVE: "another_run_active",
    EXIT_EASYTIME_AUTH: "easytime_auth",
    EXIT_EASYTIME_FAILURE: "easytime_failure",
    EXIT_COREOPS_AUTH: "coreops_auth",
    EXIT_COREOPS_PAYLOAD_REJECTED: "coreops_payload_rejected",
    EXIT_COREOPS_FAILURE: "coreops_failure",
    EXIT_LOCAL_STATE_FAILURE: "local_state_failure",
}


def label(code: int) -> str:
    return EXIT_LABELS.get(code, f"unknown ({code})")


def error_code(code: int) -> str | None:
    return ERROR_CODE_BY_EXIT.get(code)
