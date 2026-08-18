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
from datetime import date, datetime, time

from pydantic import AliasChoices, BaseModel, ConfigDict, Field, field_validator

from app.modules.biometric.constants import (
    CLASSIFICATION_NO_RECORD,
    DERIVATION_ANCHOR,
    MAX_BATCH_KEY_LEN,
    MAX_BATCH_SIZE,
    MAX_BULK_MAPPING_ITEMS,
    MAX_CONNECTOR_ID_LEN,
    MAX_EMPLOYEE_CODE_LEN,
    MAX_EXTERNAL_ID_LEN,
    MAX_SHORT_FIELD_LEN,
    MAX_STATE_FIELD_LEN,
    MAX_TIMESTAMP_TEXT_LEN,
    SHORTFALL_GRACE_MINUTES,
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


# ── Phase 5: external-code operations view + bulk mapping ───────────────────

class ExternalCodeOut(BaseModel):
    """One DISTINCT external employee code seen in biometric_punches.

    Punch counts and the first/last-seen window come from the raw punch table
    and are read-only: this view never touches a punch row.

    There is NO suggested employee. The only employee named here is one an
    active mapping row already points at; a code with no mapping reports no
    employee at all, and the PM picks one explicitly.
    """

    provider: str
    external_employee_code: str
    punch_count: int
    first_seen: datetime
    last_seen: datetime

    status: str  # mapped | unmapped

    mapping_id: uuid.UUID | None = None
    employee_id: uuid.UUID | None = None
    employee_code: str | None = None
    employee_name: str | None = None
    verified_at: datetime | None = None

    # How many of this code's stored punches already carry an employee_id.
    # Punches are immutable, so mapping a code does NOT change this for history
    # - later phases attribute historical punches through the mapping table.
    attributed_punch_count: int = 0

    # True when this code would resolve at ingestion time by the exact
    # employee_code fallback even with no mapping row (see
    # BIOMETRIC_EXACT_CODE_MATCH_ENABLED). Shown so "unmapped" is never
    # misleading.
    resolves_by_exact_code: bool = False


class ExternalCodePage(BaseModel):
    items: list[ExternalCodeOut]
    total: int
    limit: int
    offset: int
    # Totals for the WHOLE provider, not the current page - the PM needs to see
    # "12 of 46 mapped" while looking at page 2.
    total_codes: int
    mapped_codes: int
    unmapped_codes: int


class BulkMappingItem(BaseModel):
    external_employee_code: str = Field(min_length=1, max_length=MAX_EMPLOYEE_CODE_LEN)
    employee_id: uuid.UUID


class BulkMappingCreate(BaseModel):
    """An explicitly reviewed bulk import.

    The client sends the EXACT pairs a project manager confirmed. The server
    never derives a pair of its own - if it did, "bulk import" would become "the
    machine decided", which is the one thing this whole module is built to avoid.
    """

    provider: str = Field(max_length=30)
    items: list[BulkMappingItem] = Field(min_length=1, max_length=MAX_BULK_MAPPING_ITEMS)
    # Off by default: a bulk import may not silently re-point a code that
    # already maps to a DIFFERENT employee. Repointing stays a deliberate,
    # one-at-a-time act unless the caller opts in.
    allow_remap: bool = False

    @field_validator("provider")
    @classmethod
    def _supported_provider(cls, value: str) -> str:
        normalized = value.strip().lower()
        if normalized not in SUPPORTED_PROVIDERS:
            raise ValueError(
                f"Unsupported provider; expected one of {sorted(SUPPORTED_PROVIDERS)}."
            )
        return normalized


class BulkMappingItemResult(BaseModel):
    external_employee_code: str
    status: str  # mapped | unchanged | skipped
    reason: str | None = None
    employee_id: uuid.UUID | None = None
    mapping_id: uuid.UUID | None = None


class BulkMappingResult(BaseModel):
    """Per-item outcome plus totals. `mapped + unchanged + skipped == requested`."""

    provider: str
    requested: int
    mapped: int
    unchanged: int
    skipped: int
    items: list[BulkMappingItemResult]


# ── Phase 6: daily biometric summary (read-only, shadow) ────────────────────

class DailySummaryOut(BaseModel):
    """One employee, one attendance day: the FINALIZED result, for the
    employee's own Calendar.

    `first_in` / `last_out` are the earliest/latest punch of the day after
    re-scan collapsing (see `summary.py`), merged with the official
    `attendance_records` decision where the device recorded nothing - the SAME
    merge `_review_row` performs for the PM Records/detail screens (Phase 9C):
    device evidence always wins, a PM-entered time only fills a boundary the
    device left empty. `first_in_source`/`last_out_source` say which case this
    was. `attendance_records` remains the one place a human decision is
    written; nothing here writes it.

    `last_out` is null when only one punch survives collapsing AND no official
    check-out exists either. One device sighting alone cannot be both an
    arrival and a departure, and an OUT is never invented.
    """

    employee_id: uuid.UUID
    employee_code: str | None = None
    employee_name: str | None = None
    # Attendance day in ATTENDANCE_TIMEZONE (Asia/Kolkata), not UTC.
    summary_date: date
    first_in: datetime | None = None
    last_out: datetime | None = None
    # "device" | "pm" | null - which value first_in/last_out came from. See
    # service._merge_boundary. Pure biometric evidence (punch_count, kept_count,
    # punch_times below) is NEVER affected by this - only the finalized display
    # boundary is.
    first_in_source: str | None = None
    last_out_source: str | None = None
    # Debugging: raw punches for the day, and how many survived collapsing.
    punch_count: int = 0
    kept_count: int = 0
    # The surviving punches the boundary was taken FROM, so a human reviewer can
    # check the derivation instead of trusting it. Times only - never raw_payload.
    punch_times: list[datetime] = Field(default_factory=list)
    external_employee_codes: list[str] = Field(default_factory=list)

    # ── Phase 7: duration + conservative classification (computed, never stored)
    # Elapsed minutes between first_in and last_out - ONE session, no break
    # deduction, no overtime. Null (not 0) when both boundaries do not exist:
    # zero would read as a measurement, null is the truth.
    worked_minutes: int | None = None
    # The employee's CONTRACTED window for this day, from `offices.shift_start` /
    # `shift_end`. Instants, so a caller compares like with like against first_in.
    scheduled_start_at: datetime | None = None
    scheduled_end_at: datetime | None = None
    scheduled_minutes: int | None = None
    # `office` when the employee's office row supplied the window, `default` when
    # the module fallback did (employees.office_id is nullable). Never hidden.
    shift_source: str | None = None
    # present | incomplete | needs_review | no_record. NOT an AttendanceStatus:
    # biometric evidence carries no CAUSE, so half_day / permission / leave /
    # absent are never concluded here. See classification.py.
    classification: str = CLASSIFICATION_NO_RECORD
    # True when a human has to settle this day. Derived from the reasons below.
    review_required: bool = True
    # Ordered most-decisive first. Some are verdicts (missing_second_punch,
    # short_of_scheduled_duration), some are context that does not open a review
    # on its own (first_punch_after_shift_start).
    review_reasons: list[str] = Field(default_factory=list)

    # ── Phase 12: approved permission for this employee-day (joined, not derived)
    # APPROVED permission hours (1 or 2) held for this date, or null when there
    # are none. Read from `permission_requests` and shown BESIDE the day - it is
    # an additional attendance attribute, never a status, never a leave, and
    # never a punch. Every biometric field above is untouched by it: the times,
    # the counts and `worked_minutes` remain exactly the device evidence.
    permission_hours: int | None = None


class SummarySchedule(BaseModel):
    """The employee's contracted office hours - CoreOps' own data, not biometric.

    Carried on the page rather than per day because it is a property of the
    employee's office, constant across the range, and it must still be available
    for a day that has NO punches at all (where there is no item to hang it on).
    """

    office_name: str | None = None
    timezone: str | None = None
    shift_start: time | None = None
    shift_end: time | None = None
    break_minutes: int | None = None


class DailySummaryPage(BaseModel):
    items: list[DailySummaryOut]
    total: int
    # Echoed back so a caller can tell what was actually summarized.
    provider: str
    date_from: date
    date_to: date
    # How the boundary was derived. A constant today; it exists so that the day
    # real punch states arrive, consumers can see the meaning changed instead of
    # silently reinterpreting stored history.
    derivation: str = DERIVATION_ANCHOR
    # False while EasyTime reports no usable punch direction.
    punch_state_available: bool = False
    # Present only when exactly one employee is in scope, and only when that
    # employee is assigned to an office. Null is normal, not an error.
    schedule: SummarySchedule | None = None
    # Phase 7. Minutes a day was allowed to fall short of its scheduled window and
    # still count as `present`. Echoed because it is the single number that decides
    # how many days land in review, and it is 0 only because the late-arrival grace
    # period (O-3) is an unanswered management question - not because 0 is a rule.
    grace_minutes: int = SHORTFALL_GRACE_MINUTES


# ── Phase 8: PM daily review (read-only) ────────────────────────────────────

class DailyReviewRowOut(BaseModel):
    """One employee's day, as the PM review screen needs it.

    Deliberately NARROWER than `DailySummaryOut`: no punch counts, no punch
    times, no external codes, no derivation slug. Those are evidence-inspection
    and debugging fields; this row answers "is this day settled, and if not
    why?", and shipping the rest would only invite a UI that displays it.

    Every value here is computed by the same engine the calendar uses. The
    frontend formats these numbers; it never recomputes them.
    """

    employee_id: uuid.UUID
    employee_code: str | None = None
    employee_name: str | None = None

    first_in: datetime | None = None
    last_out: datetime | None = None
    worked_minutes: int | None = None
    # "device" | "pm" | null - which value this DISPLAYED boundary came from.
    # A PM-entered time only ever fills a boundary the device did not record;
    # see service._merge_boundary. Biometric evidence itself is unaffected.
    first_in_source: str | None = None
    last_out_source: str | None = None

    scheduled_start_at: datetime | None = None
    scheduled_end_at: datetime | None = None
    scheduled_minutes: int | None = None

    classification: str
    # True only when the punches could not settle the day AND no human has ruled
    # on it yet. An official record clears this - that ruling IS the missing
    # information.
    review_required: bool
    # Whether the PM may supply this boundary. False when the device already
    # recorded it: biometric evidence is immutable and complete evidence cannot
    # be improved, so only a missing punch is fillable by hand.
    can_set_check_in: bool = False
    can_set_check_out: bool = False
    # Everything observed, most-decisive first - including context-only notes
    # such as `first_punch_after_shift_start`.
    review_reasons: list[str] = Field(default_factory=list)
    # The subset that actually requires attention. Split server-side so the UI
    # does not need its own copy of which reasons are blocking.
    blocking_reasons: list[str] = Field(default_factory=list)

    # The OFFICIAL record for this day, when a human has already ruled on it.
    # Null means nobody has decided yet - NOT that the employee was absent. The
    # biometric fields above are evidence and remain unchanged either way; this
    # is the decision layered on top, and only the attendance module writes it.
    attendance_record_id: uuid.UUID | None = None
    attendance_status: str | None = None
    attendance_check_in_at: datetime | None = None
    attendance_check_out_at: datetime | None = None
    # The reason the PM gave. Null when nobody explained the day.
    attendance_note: str | None = None

    # Phase 12. APPROVED permission hours (1 or 2) for this employee-day, or
    # null. An ATTRIBUTE of the day, joined from `permission_requests` - it does
    # not change `attendance_status`, `classification` or any boundary above,
    # and a permission is never presented as leave. Pending, rejected and
    # cancelled requests are not reported here at all.
    permission_hours: int | None = None


class DailyReviewCounts(BaseModel):
    """The whole day, counted BEFORE any classification filter is applied.

    Truthfully derivable from biometric evidence alone - which is why there is
    no `leave`, `permission` or `half_day` here. Those need the approved-exception
    data that Phase 9 integrates; inventing them from punch durations is exactly
    the guess this module refuses to make.
    """

    employees: int = 0
    review_required: int = 0
    present: int = 0
    incomplete: int = 0
    needs_review: int = 0
    no_record: int = 0


class DailyReviewPage(BaseModel):
    """One attendance day across every in-scope employee.

    NOT an attendance ledger and not a decision: no row here has been approved,
    finalized or written anywhere. `attendance_records` remains untouched and
    remains the official source.
    """

    review_date: date
    provider: str
    items: list[DailyReviewRowOut]
    # Rows AFTER filtering AND before pagination; `counts` describes the
    # unfiltered day. Frontend pagination math (`total`/`limit`/`offset`)
    # matches every other paginated list in this API.
    total: int
    limit: int
    offset: int
    counts: DailyReviewCounts


# ── Phase 9B: single-employee detail screen ─────────────────────────────────

class PunchEntryOut(BaseModel):
    """One surviving (post-dedup) punch on the detail page's evidence list.

    Always `source="device"` - nothing here is ever PM-entered. A PM-supplied
    boundary the device did not record lives on `row.attendance_check_in_at` /
    `row.attendance_check_out_at`, never as a row in this list: no synthetic
    punch is invented (see the module docstring).
    """

    punch_time: datetime
    # first_in | last_out | punch. Only the first and last surviving punch of
    # the day carry a boundary role - see PUNCH_ROLE_* in constants.py.
    role: str
    source: str = "device"


class DailyReviewDetailOut(BaseModel):
    """One employee, one day - the Phase 9B PM detail screen.

    `row` is the exact same shape `DailyReviewPage.items` uses, so the two
    screens can never disagree about what a saved decision looks like.
    """

    review_date: date
    provider: str
    row: DailyReviewRowOut
    punches: list[PunchEntryOut]


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
