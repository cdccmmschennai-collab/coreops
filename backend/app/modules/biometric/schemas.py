"""Biometric ingestion pydantic schemas - the connector wire contract.

Deliberate design choice: every punch field arrives as a STRING and is parsed
per record in the service, rather than being typed `datetime` here. A single
device with a bad clock, or one malformed row in a 500-punch page, must cost one
`invalid` record - not a 422 that throws away 499 good punches the connector
would then have to re-derive. Structural problems (wrong types, an empty batch,
an oversized batch, an unsupported provider) still fail fast with 422.

Field names follow the master spec (`raw_punch_state`, `verify_type`). The
Phase 1 connector DTO `NormalizedPunch` calls the state field `punch_state`, so
both spellings are accepted via AliasChoices and the connector needs no change.
"""
import uuid
from datetime import datetime

from pydantic import AliasChoices, BaseModel, ConfigDict, Field, field_validator

from app.modules.biometric.constants import (
    MAX_BATCH_KEY_LEN,
    MAX_BATCH_SIZE,
    MAX_CONNECTOR_ID_LEN,
    MAX_EMPLOYEE_CODE_LEN,
    MAX_EXTERNAL_ID_LEN,
    MAX_SHORT_FIELD_LEN,
    MAX_STATE_FIELD_LEN,
    MAX_TIMESTAMP_TEXT_LEN,
    SUPPORTED_PROVIDERS,
)


class PunchIn(BaseModel):
    """One normalized punch as pushed by the office-side connector."""

    model_config = ConfigDict(extra="ignore", populate_by_name=True)

    external_transaction_id: str = Field(max_length=MAX_EXTERNAL_ID_LEN)
    employee_code: str = Field(
        max_length=MAX_EMPLOYEE_CODE_LEN,
        validation_alias=AliasChoices("employee_code", "external_employee_code"),
    )
    punch_time: str = Field(max_length=MAX_TIMESTAMP_TEXT_LEN)

    # Vendor state code, verbatim. `null` is explicitly valid - the live probe
    # observed punch_state_display = null on every record.
    raw_punch_state: str | None = Field(
        default=None,
        max_length=MAX_STATE_FIELD_LEN,
        validation_alias=AliasChoices("raw_punch_state", "punch_state"),
    )
    punch_state_display: str | None = Field(
        default=None, max_length=MAX_STATE_FIELD_LEN
    )
    terminal_alias: str | None = Field(default=None, max_length=MAX_SHORT_FIELD_LEN)
    terminal_serial_number: str | None = Field(
        default=None, max_length=MAX_SHORT_FIELD_LEN
    )
    verify_type: str | None = Field(
        default=None,
        max_length=MAX_STATE_FIELD_LEN,
        validation_alias=AliasChoices("verify_type", "verification_type"),
    )
    source: str | None = Field(default=None, max_length=MAX_STATE_FIELD_LEN)
    upload_time: str | None = Field(default=None, max_length=MAX_TIMESTAMP_TEXT_LEN)

    # Sanitized before storage: PII and secret-shaped keys are stripped and the
    # size is capped (see service._sanitize_raw_payload).
    raw_payload: dict | None = None


class PunchBatchIn(BaseModel):
    """One connector POST: a window of punches plus the batch identity."""

    model_config = ConfigDict(extra="ignore")

    provider: str = Field(max_length=30)
    connector_id: str = Field(min_length=1, max_length=MAX_CONNECTOR_ID_LEN)
    # Optional. When omitted the backend DERIVES a deterministic key from the
    # batch content, so a retry of an identical payload still resolves the same
    # sync-batch row (see service.derive_batch_key).
    batch_key: str | None = Field(default=None, max_length=MAX_BATCH_KEY_LEN)
    source_from_time: str | None = Field(default=None, max_length=MAX_TIMESTAMP_TEXT_LEN)
    source_to_time: str | None = Field(default=None, max_length=MAX_TIMESTAMP_TEXT_LEN)
    punches: list[PunchIn] = Field(min_length=1, max_length=MAX_BATCH_SIZE)

    @field_validator("provider")
    @classmethod
    def _supported_provider(cls, value: str) -> str:
        normalized = value.strip().lower()
        if normalized not in SUPPORTED_PROVIDERS:
            raise ValueError(
                f"Unsupported provider; expected one of {sorted(SUPPORTED_PROVIDERS)}."
            )
        return normalized


class PunchBatchResult(BaseModel):
    """Deterministic ingestion counters.

    Invariant: ``inserted + duplicates + invalid == received``.

    ``unmapped`` is NOT part of that sum - it counts how many of the newly
    INSERTED rows carry ``employee_id = NULL``. An unmapped punch is stored, it
    is simply not attributable to a CoreOps employee yet.
    """

    batch_id: uuid.UUID
    received: int
    inserted: int
    duplicates: int
    unmapped: int
    invalid: int
    status: str


# ── administrative read/write surfaces (project_manager only, no frontend) ──

class EmployeeMappingCreate(BaseModel):
    provider: str = Field(max_length=30)
    external_employee_code: str = Field(min_length=1, max_length=MAX_EMPLOYEE_CODE_LEN)
    employee_id: uuid.UUID

    @field_validator("provider")
    @classmethod
    def _supported_provider(cls, value: str) -> str:
        normalized = value.strip().lower()
        if normalized not in SUPPORTED_PROVIDERS:
            raise ValueError(
                f"Unsupported provider; expected one of {sorted(SUPPORTED_PROVIDERS)}."
            )
        return normalized


class EmployeeMappingOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    provider: str
    external_employee_code: str
    employee_id: uuid.UUID
    employee_code: str | None = None
    employee_name: str | None = None
    is_active: bool
    verified_at: datetime | None = None
    verified_by_user_id: uuid.UUID | None = None
    created_at: datetime
    updated_at: datetime


class EmployeeMappingPage(BaseModel):
    items: list[EmployeeMappingOut]
    total: int
    limit: int
    offset: int


class SyncBatchOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    provider: str
    connector_id: str
    batch_key: str
    source_from_time: datetime | None = None
    source_to_time: datetime | None = None
    started_at: datetime
    completed_at: datetime | None = None
    records_received: int
    records_inserted: int
    records_duplicates: int
    records_unmapped: int
    records_invalid: int
    status: str
    error_code: str | None = None
    error_message: str | None = None


class SyncBatchPage(BaseModel):
    items: list[SyncBatchOut]
    total: int
    limit: int
    offset: int
