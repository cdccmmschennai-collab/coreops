"""Biometric ingestion vocabulary - providers, batch statuses, limits, redaction.

Single source of truth shared by the models, the migration's CHECK constraints,
the service and the tests, so a status string is never spelled twice.

Phase 2 deliberately defines NO punch-state semantics. `raw_punch_state` is
stored verbatim; the live probe returned "0" for every observed punch and
`punch_state_display` was null, so IN/OUT remains unresolved
(docs/attendance/punch-state-mapping.md).
"""
from datetime import time as _time

# ── providers ───────────────────────────────────────────────────────────────
PROVIDER_EASYTIME = "easytime"

# Only providers listed here may be ingested. Adding one is a code change, not
# a payload the connector can choose freely.
SUPPORTED_PROVIDERS = frozenset({PROVIDER_EASYTIME})


# ── sync batch statuses ─────────────────────────────────────────────────────
BATCH_PROCESSING = "processing"
BATCH_COMPLETED = "completed"
BATCH_COMPLETED_WITH_ERRORS = "completed_with_errors"
BATCH_FAILED = "failed"

BATCH_STATUSES = (
    BATCH_PROCESSING,
    BATCH_COMPLETED,
    BATCH_COMPLETED_WITH_ERRORS,
    BATCH_FAILED,
)


# ── batch error codes (stored on biometric_sync_batches.error_code) ─────────
ERROR_ALL_RECORDS_INVALID = "all_records_invalid"
ERROR_STORAGE_FAILURE = "storage_failure"


# ── per-record rejection reasons (counted as `invalid`, never persisted as a
#    punch). Kept as short stable slugs so operations can grep them. ─────────
INVALID_MISSING_TRANSACTION_ID = "missing_external_transaction_id"
INVALID_MISSING_EMPLOYEE_CODE = "missing_employee_code"
INVALID_PUNCH_TIME = "invalid_punch_time"
INVALID_PUNCH_TIME_OUT_OF_RANGE = "punch_time_out_of_range"
INVALID_DUPLICATE_IN_BATCH = "duplicate_in_batch"


# ── external-code mapping state (Phase 5) ───────────────────────────────────
# CoreOps proposes NO mapping. There is no suggestion tier, no code
# normalization ("EMP061" is not treated as "61"), and no name comparison
# anywhere in this module: a mapping row exists only where a project manager
# explicitly created it. Do not reintroduce an inferred pairing here - the
# closest thing that may ever exist is ADVICE a PM must confirm, and it must
# never become a runtime punch-attribution rule.
#
# Mapping state of one distinct external code, as reported by the operations
# view. Deliberately coarse: a code either has an ACTIVE mapping row or it does
# not.
CODE_STATUS_MAPPED = "mapped"
CODE_STATUS_UNMAPPED = "unmapped"


# ── bulk mapping outcomes (Phase 5) ─────────────────────────────────────────
BULK_MAPPED = "mapped"        # a new ACTIVE mapping row was written
BULK_UNCHANGED = "unchanged"  # the active mapping already named this employee
BULK_SKIPPED = "skipped"      # nothing was written; see the reason slug

# Why an item was skipped. Every one of these means "no row was written" - a
# bulk import never guesses its way past an ambiguity.
BULK_EMPLOYEE_NOT_FOUND = "employee_not_found"
BULK_DUPLICATE_CODE_IN_REQUEST = "duplicate_code_in_request"
BULK_DUPLICATE_EMPLOYEE_IN_REQUEST = "duplicate_employee_in_request"
BULK_EMPLOYEE_MAPPED_TO_OTHER_CODE = "employee_already_mapped_to_other_code"
BULK_REMAP_NOT_ALLOWED = "remap_not_allowed"

# One bulk request. The initial import covers ~50 EasyTime codes; this leaves
# generous headroom while keeping the whole operation one short transaction.
MAX_BULK_MAPPING_ITEMS = 500


# ── daily summary (Phase 6, read-only shadow) ───────────────────────────────
# How first_in / last_out were derived. EasyTime reports no punch direction in
# this deployment (punch_state is "0" on every row, one terminal), so the summary
# reports the OUTER BOUNDARY of the day - earliest and latest punch after
# re-scan collapsing - and says so. See summary.py for the evidence and the rule.
#
# This value is part of the API contract on purpose: if real punch states ever
# arrive, a new derivation slug must appear here so consumers can see that the
# meaning of a stored boundary changed, rather than silently reinterpreting it.
DERIVATION_ANCHOR = "anchor_earliest_latest"

# How many days one summary request may span. A month view needs 31; this allows
# a full quarter while keeping the punch scan bounded.
MAX_SUMMARY_RANGE_DAYS = 100


# ── worked duration + attendance classification (Phase 7, read-only) ────────
# Phase 7 sits ABOVE the Phase 6 boundary: given first_in / last_out and the
# employee's contracted shift, how long were they on site, and is that day
# objectively settled or does a human have to look at it?
#
# The vocabulary is deliberately its OWN, and deliberately NOT
# `attendance.models.AttendanceStatus`. That enum (present / absent / half_day /
# leave / holiday / weekend / comp_off) is the vocabulary of the OFFICIAL record,
# and every one of its interesting values encodes a CAUSE - why somebody was not
# at work. Biometric evidence never carries a cause: a 6-hour day is a 6-hour
# day, and whether it was half-day, permission, an early release or a missed
# punch is not in the punch stream. Borrowing that enum here would silently turn
# "we measured 6 hours" into "HR decided half day", which is the exact failure
# this module exists to prevent.
CLASSIFICATION_PRESENT = "present"          # objectively a complete scheduled day
CLASSIFICATION_INCOMPLETE = "incomplete"    # seen once; the day cannot be closed
CLASSIFICATION_NEEDS_REVIEW = "needs_review"  # measurable, but not objectively settled
CLASSIFICATION_NO_RECORD = "no_record"      # no punches at all - NOT "absent"

CLASSIFICATIONS = (
    CLASSIFICATION_PRESENT,
    CLASSIFICATION_INCOMPLETE,
    CLASSIFICATION_NEEDS_REVIEW,
    CLASSIFICATION_NO_RECORD,
)

# Why a day landed where it did. Stable slugs, so operations can grep them and a
# later review UI can group by them. A day may carry several.
REASON_NO_BIOMETRIC_RECORD = "no_biometric_record"
REASON_MISSING_SECOND_PUNCH = "missing_second_punch"
REASON_SHORT_OF_SCHEDULED = "short_of_scheduled_duration"
REASON_LATE_FIRST_PUNCH = "first_punch_after_shift_start"
REASON_EARLY_LAST_PUNCH = "last_punch_before_shift_end"
REASON_SHIFT_UNKNOWN = "shift_unknown"
REASON_UNSUPPORTED_SHIFT_WINDOW = "unsupported_shift_window"
REASON_SHIFT_TIMEZONE_INVALID = "shift_timezone_invalid"
REASON_DEFAULT_SHIFT_ASSUMED = "default_shift_assumed"

# Reasons that mean "a human must decide this day". The rest are OBSERVATIONS
# that travel with the row for context and do not, on their own, open a review.
#
# REASON_SHORT_OF_SCHEDULED IS DELIBERATELY NOT HERE (changed 2026-08-14, by
# management decision). It was blocking in Phase 7, which meant an 8h 18m day
# against a 8h 30m window went to review - and on real data that flagged four
# people for being twelve minutes short, which is noise, not review. The rule is
# now COMPLETENESS, not duration: two punches means the device saw the whole day
# and there is nothing for a human to add. The shortfall is still REPORTED as
# context so the information is not lost, it just no longer demands attention.
#
# Consequence, stated plainly: a 13:05 -> 17:20 day (4h 15m) is now `present`
# with a "short of scheduled duration" note, not `needs_review`. If a floor is
# wanted below which a short day DOES need review, that is a threshold decision -
# see SHORTFALL_GRACE_MINUTES.
BLOCKING_REVIEW_REASONS = frozenset(
    {
        REASON_NO_BIOMETRIC_RECORD,
        REASON_MISSING_SECOND_PUNCH,
        REASON_SHIFT_UNKNOWN,
        REASON_UNSUPPORTED_SHIFT_WINDOW,
        REASON_SHIFT_TIMEZONE_INVALID,
    }
)

# Where the compared shift window came from, reported per day so a reader never
# has to guess whether the comparison used real configuration or a fallback.
SHIFT_SOURCE_OFFICE = "office"
SHIFT_SOURCE_DEFAULT = "default"

# THE fallback shift, and the only place 09:00 / 17:30 is written in the backend.
# `offices.shift_start` / `shift_end` (migration 0007) is the real source of
# truth and always wins - this covers the nullable `employees.office_id` case
# only. It matches the value the live office rows already carry, so the fallback
# cannot quietly disagree with configuration.
#
# 09:00 -> 17:30 is 510 minutes. That is a START and an END, not a required
# duration: O-1 in docs/attendance/attendance-policy-open-decisions.md ("required
# daily working duration") is still OPEN, and Phase 7 therefore compares against
# the scheduled WINDOW rather than against an invented requirement.
DEFAULT_SHIFT_START = _time(9, 0)
DEFAULT_SHIFT_END = _time(17, 30)

# Minutes a day may fall short of its scheduled window and still count as a
# complete day. ZERO until O-3 (late-arrival grace period) is answered by
# management - a grace period is company policy, not something CoreOps may
# invent. Consequence, stated plainly: a 09:10 -> 17:10 day is 8h00 against a
# scheduled 8h30 and comes back `needs_review`, not `present`.
#
# This is the ONE place to change it. Nothing else compares a duration.
SHORTFALL_GRACE_MINUTES = 0

# Phase 7 deliberately does NOT deduct `offices.break_minutes` from worked time.
# O-2 ("does the 30-minute lunch count as worked time?") is open, and deducting
# it would silently change every day by 30 minutes. break_minutes is carried to
# the client as information and never enters a calculation.


# ── size limits ─────────────────────────────────────────────────────────────
# One connector POST. 1000 punches ≈ a busy full day for a few hundred staff,
# and keeps the single INSERT statement and its JSONB payloads well inside
# comfortable request/statement sizes.
MAX_BATCH_SIZE = 1000

MAX_EXTERNAL_ID_LEN = 128
MAX_EMPLOYEE_CODE_LEN = 64
MAX_CONNECTOR_ID_LEN = 100
MAX_BATCH_KEY_LEN = 128
MAX_SHORT_FIELD_LEN = 100
MAX_STATE_FIELD_LEN = 50
MAX_TIMESTAMP_TEXT_LEN = 64

# raw_payload guard rails. A biometric transaction is a handful of scalars; a
# payload larger than this is either a different object or an attack.
MAX_RAW_PAYLOAD_KEYS = 40
MAX_RAW_PAYLOAD_VALUE_LEN = 500
MAX_RAW_PAYLOAD_CHARS = 4000

# Punch timestamps outside this window around "now" are rejected per-record:
# a device with a wildly wrong clock must not poison a date range.
MAX_PUNCH_AGE_DAYS = 400
MAX_PUNCH_FUTURE_DAYS = 2

# An unmapped ratio at or above this marks the batch for review (audit event).
UNMAPPED_ALERT_RATIO = 0.5
UNMAPPED_ALERT_MIN_RECORDS = 5


# ── redaction ───────────────────────────────────────────────────────────────
# Personally identifying / biometric material. CoreOps needs a code and a
# timestamp; names, photos, face and fingerprint templates are dropped before
# raw_payload is persisted. Mirrors connectors/easytime/schemas.py PII_FIELDS.
PII_KEYS = frozenset(
    {
        "first_name",
        "last_name",
        "name",
        "emp_name",
        "employee_name",
        "nickname",
        "photo",
        "picture",
        "avatar",
        "face",
        "face_template",
        "fingerprint",
        "finger_template",
        "template",
        "biophoto",
        "biodata",
        "vein",
        "iris",
        "palm",
        "email",
        "mobile",
        "phone",
        "address",
    }
)

# Secret-shaped keys. Never persisted, never logged, never echoed in an error.
SECRET_KEY_MARKERS = (
    "password",
    "passwd",
    "secret",
    "token",
    "jwt",
    "authorization",
    "auth",
    "api_key",
    "apikey",
    "credential",
    "session",
    "cookie",
)

# Reserved raw_payload key holding the vendor's original timestamp text, so the
# exact string EasyTime returned survives normalization (section 9).
RAW_PUNCH_TIME_TEXT_KEY = "_punch_time_text"
RAW_UPLOAD_TIME_TEXT_KEY = "_upload_time_text"

# The connector authenticates with this header. Deliberately NOT `Authorization`
# so a connector token can never be mistaken for (or fall back to) a user JWT,
# and never a query parameter so it stays out of access logs and referrers.
CONNECTOR_TOKEN_HEADER = "X-CoreOps-Connector-Token"


# ── Phase 9B: PM decision reflection + detail page ──────────────────────────
# Whether a displayed IN/OUT boundary came from the device or was supplied by
# a PM where the device recorded none. Device evidence always wins - see
# service._merge_boundary. Biometric evidence itself is never written by a PM;
# this labels the DISPLAYED first_in/last_out only.
SOURCE_DEVICE = "device"
SOURCE_PM = "pm"

# The role a punch plays on the detail page's evidence list. Only the first
# and last surviving punch of the day carry a boundary role - intermediate
# punches are shown as context, never treated as a paired session (EasyTime
# reports no punch direction in this deployment; see summary.py).
PUNCH_ROLE_FIRST_IN = "first_in"
PUNCH_ROLE_LAST_OUT = "last_out"
PUNCH_ROLE_PUNCH = "punch"
