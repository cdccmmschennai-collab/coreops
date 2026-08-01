"""Vendor response shapes and the normalized punch DTO.

Two deliberately separate layers:

``RawTransaction``   exactly what EasyTime returned, field-for-field, with the
                     original timestamp string preserved. Nothing is inferred.
``NormalizedPunch``  the only shape CoreOps will ever accept (Phase 2). It is
                     defined here so the wire contract is visible from day one,
                     but Phase 1 does NOT populate ``punch_state`` semantics -
                     see the note below.

Why the split: the punch-state code -> IN/OUT meaning is site-configurable in
EasyTime and MUST be confirmed by ``probe.py`` against the real installation
before any calculation depends on it (docs/attendance/punch-state-mapping.md).
Guessing "0 = IN, 1 = OUT" is the single most likely way to silently corrupt an
entire month of attendance, so this module keeps the raw code and refuses to
translate it. The authoritative mapper lands in Phase 2, driven by the mapping
table the probe produces.

Nothing here imports the CoreOps backend - the connector is standalone.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Any

# Timestamp formats seen across ZKTeco/EasyTime builds. All are LOCAL, naive.
_TIMESTAMP_FORMATS = (
    "%Y-%m-%d %H:%M:%S",
    "%Y-%m-%dT%H:%M:%S",
    "%Y-%m-%d %H:%M",
    "%Y/%m/%d %H:%M:%S",
)

# Field aliases per build. First match wins; unknown payloads raise in `parse`
# rather than silently producing a punch with a missing employee code.
_ALIASES: dict[str, tuple[str, ...]] = {
    "external_transaction_id": ("id", "transaction_id", "trans_id", "pk"),
    "employee_code": ("emp_code", "employee_code", "badgenumber", "user_id", "pin"),
    "punch_time": ("punch_time", "checktime", "check_time", "event_time", "time"),
    "punch_state": ("punch_state", "checktype", "check_type", "state", "status"),
    "punch_state_display": ("punch_state_display", "checktype_display", "state_display"),
    "verify_type": ("verify_type", "verifycode", "verify_mode", "verified"),
    "terminal_serial_number": ("terminal_sn", "sn", "device_sn", "serial_number"),
    "terminal_alias": ("terminal_alias", "device_alias", "terminal_name", "device_name"),
    "area_alias": ("area_alias", "area_name"),
    "upload_time": ("upload_time", "uploadtime", "created_at"),
    "source": ("source", "punch_source", "data_source"),
    "first_name": ("first_name", "emp_first_name", "name"),
    "last_name": ("last_name", "emp_last_name"),
}

# Personally identifying fields the probe must never print or persist. CoreOps
# needs a code and a timestamp, nothing else (master prompt section 24).
PII_FIELDS = frozenset({"first_name", "last_name", "name", "emp_name", "photo", "face", "template"})


def _pick(payload: dict, key: str) -> Any:
    for alias in _ALIASES[key]:
        if alias in payload and payload[alias] not in (None, ""):
            return payload[alias]
    return None


def parse_timestamp(value: str) -> datetime | None:
    """Parse a vendor timestamp as a NAIVE local datetime, or None.

    Deliberately returns naive: the connector does not know the device's
    timezone from the payload. The wall-clock reading is attached to
    ``TIMEZONE`` from the connector .env only at normalization time, and the
    probe reports the raw string so the admin can confirm it matches what the
    EasyTime UI shows for the same punch.
    """
    if not isinstance(value, str):
        return None
    raw = value.strip()
    if not raw:
        return None
    # Trim a trailing zone/offset if a build ever emits one; the probe flags it.
    for fmt in _TIMESTAMP_FORMATS:
        try:
            return datetime.strptime(raw, fmt)
        except ValueError:
            continue
    return None


@dataclass(frozen=True)
class RawTransaction:
    """One EasyTime transaction, as returned. ``raw`` keeps the full payload."""

    external_transaction_id: str
    employee_code: str
    punch_time_raw: str
    punch_state_raw: str | None
    punch_state_display: str | None
    verify_type: str | None
    terminal_serial_number: str | None
    terminal_alias: str | None
    area_alias: str | None
    upload_time_raw: str | None
    source: str | None
    raw: dict = field(repr=False, default_factory=dict)

    @property
    def punch_time(self) -> datetime | None:
        return parse_timestamp(self.punch_time_raw)

    @classmethod
    def parse(cls, payload: dict) -> "RawTransaction":
        """Build from one API record. Raises ValueError on an unusable record.

        A record without an id, employee code or timestamp is unusable: the id
        is what makes ingestion idempotent, and the other two are the whole
        point. Callers collect these failures and report them rather than
        dropping records silently.
        """
        external_id = _pick(payload, "external_transaction_id")
        emp_code = _pick(payload, "employee_code")
        punch_time = _pick(payload, "punch_time")
        missing = [
            name
            for name, value in (
                ("transaction id", external_id),
                ("employee code", emp_code),
                ("punch time", punch_time),
            )
            if value is None
        ]
        if missing:
            raise ValueError(
                "Transaction is missing required field(s): " + ", ".join(missing)
            )
        state = _pick(payload, "punch_state")
        return cls(
            external_transaction_id=str(external_id),
            employee_code=str(emp_code).strip(),
            punch_time_raw=str(punch_time),
            punch_state_raw=None if state is None else str(state),
            punch_state_display=_opt_str(_pick(payload, "punch_state_display")),
            verify_type=_opt_str(_pick(payload, "verify_type")),
            terminal_serial_number=_opt_str(_pick(payload, "terminal_serial_number")),
            terminal_alias=_opt_str(_pick(payload, "terminal_alias")),
            area_alias=_opt_str(_pick(payload, "area_alias")),
            upload_time_raw=_opt_str(_pick(payload, "upload_time")),
            source=_opt_str(_pick(payload, "source")),
            raw=payload,
        )

    def sanitized(self, *, mask_employee: bool = True) -> dict:
        """Log/report-safe dict: no names, no templates, code optionally masked."""
        return {
            "external_transaction_id": self.external_transaction_id,
            "employee_code": mask_code(self.employee_code) if mask_employee else self.employee_code,
            "punch_time_raw": self.punch_time_raw,
            "punch_state_raw": self.punch_state_raw,
            "punch_state_display": self.punch_state_display,
            "verify_type": self.verify_type,
            "terminal_serial_number": self.terminal_serial_number,
            "terminal_alias": self.terminal_alias,
            "upload_time_raw": self.upload_time_raw,
            "source": self.source,
        }


@dataclass(frozen=True)
class NormalizedPunch:
    """The Phase 2 wire contract: what the connector POSTs to CoreOps.

    ``punch_state`` stays the VENDOR CODE as a string. Translation to IN/OUT
    happens once, server-side, from a reviewed mapping table - so a wrong
    mapping is fixed by editing one table and recalculating, never by editing
    raw punches (master prompt section 21, rule 19).
    """

    provider: str
    external_transaction_id: str
    employee_code: str
    punch_time: str  # ISO 8601 WITH offset, e.g. 2026-07-29T09:30:00+05:30
    punch_state: str | None
    # Whatever label the vendor attached, or None. The live probe returned None
    # for every record; that None is SENT, not omitted, so the stored row says
    # "EasyTime supplied no label" rather than "the connector did not look".
    punch_state_display: str | None = None
    verify_type: str | None = None
    terminal_serial_number: str | None = None
    terminal_alias: str | None = None
    source: str | None = None
    upload_time: str | None = None
    raw_payload: dict = field(repr=False, default_factory=dict)

    def to_wire(self) -> dict:
        """The exact JSON object the Phase 2 endpoint expects for one punch.

        Field names are the backend's spelling (`raw_punch_state`,
        `verify_type`). ``punch_state``/``verification_type`` are accepted as
        aliases server-side, but writing the primary names here means the wire
        format matches the documentation, and a future removal of the aliases
        cannot break the connector.
        """
        return {
            "external_transaction_id": self.external_transaction_id,
            "employee_code": self.employee_code,
            "punch_time": self.punch_time,
            "raw_punch_state": self.punch_state,
            "punch_state_display": self.punch_state_display,
            "terminal_alias": self.terminal_alias,
            "terminal_serial_number": self.terminal_serial_number,
            "verify_type": self.verify_type,
            "source": self.source,
            "upload_time": self.upload_time,
            "raw_payload": self.raw_payload,
        }


def _opt_str(value: Any) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def mask_code(code: str) -> str:
    """EMP069 -> EMP**9. Keeps the prefix pattern visible for mapping checks
    without printing a full employee identifier into a shared report."""
    if len(code) <= 4:
        return code[0] + "*" * (len(code) - 1) if code else ""
    return f"{code[:3]}{'*' * (len(code) - 4)}{code[-1]}"


def strip_pii(payload: dict) -> dict:
    """Drop name/photo/template fields from a raw payload before it is printed
    or written to a probe report file."""
    return {k: v for k, v in payload.items() if k.lower() not in PII_FIELDS}
