"""Parsing, sanitization and timestamp handling.

These are the guards on the two rules that matter most in Phase 1: a record is
never invented from incomplete data, and no PII or full identifier leaks into a
report that gets emailed around.
"""
from __future__ import annotations

from datetime import datetime

import pytest
from conftest import transaction

from schemas import PII_FIELDS, RawTransaction, mask_code, parse_timestamp, strip_pii


class TestParse:
    def test_parses_a_full_record(self):
        txn = RawTransaction.parse(transaction(101))

        assert txn.external_transaction_id == "101"
        assert txn.employee_code == "EMP069"
        assert txn.punch_time == datetime(2026, 7, 28, 9, 30)
        assert txn.punch_state_raw == "0"
        assert txn.punch_state_display == "Check In"
        assert txn.terminal_alias == "Main Gate"

    @pytest.mark.parametrize(
        "aliases",
        [
            {"transaction_id": 7, "badgenumber": "EMP070", "checktime": "2026-07-28 10:00:00"},
            {"pk": 8, "user_id": "EMP071", "check_time": "2026-07-28 11:00:00"},
        ],
    )
    def test_accepts_alternate_field_names(self, aliases):
        # Different ZKTeco builds name the same fields differently; the probe
        # must still produce a usable record rather than reporting "no data".
        txn = RawTransaction.parse(aliases)

        assert txn.external_transaction_id in ("7", "8")
        assert txn.employee_code.startswith("EMP")

    @pytest.mark.parametrize(
        "missing_key", ["id", "emp_code", "punch_time"]
    )
    def test_rejects_a_record_missing_an_essential_field(self, missing_key):
        payload = transaction(102)
        del payload[missing_key]

        with pytest.raises(ValueError) as exc:
            RawTransaction.parse(payload)
        assert "missing required field" in str(exc.value)

    def test_blank_values_count_as_missing(self):
        payload = transaction(103)
        payload["emp_code"] = ""

        with pytest.raises(ValueError):
            RawTransaction.parse(payload)

    def test_punch_state_zero_is_preserved_not_treated_as_absent(self):
        # "0" is a real state code and falsy in Python - regression guard.
        txn = RawTransaction.parse(transaction(104, punch_state="0"))

        assert txn.punch_state_raw == "0"


class TestTimestamps:
    @pytest.mark.parametrize(
        "raw,expected",
        [
            ("2026-07-28 09:30:00", datetime(2026, 7, 28, 9, 30)),
            ("2026-07-28T09:30:00", datetime(2026, 7, 28, 9, 30)),
            ("2026-07-28 09:30", datetime(2026, 7, 28, 9, 30)),
            ("2026/07/28 09:30:00", datetime(2026, 7, 28, 9, 30)),
        ],
    )
    def test_known_formats(self, raw, expected):
        assert parse_timestamp(raw) == expected

    def test_parsed_time_is_naive(self):
        # The connector never invents a timezone: the offset is applied once,
        # from the connector's TIMEZONE setting, at normalization time.
        assert parse_timestamp("2026-07-28 09:30:00").tzinfo is None

    @pytest.mark.parametrize("raw", ["", "   ", "not-a-time", "28-07-2026", None, 12345])
    def test_unparseable_returns_none(self, raw):
        assert parse_timestamp(raw) is None


class TestSanitization:
    def test_strip_pii_removes_name_fields(self):
        cleaned = strip_pii(transaction(105))

        assert "first_name" not in cleaned
        assert "last_name" not in cleaned
        assert cleaned["emp_code"] == "EMP069"

    def test_pii_field_list_covers_biometric_templates(self):
        assert {"photo", "face", "template"} <= PII_FIELDS

    @pytest.mark.parametrize(
        "code,expected",
        [("EMP069", "EMP**9"), ("EMP225", "EMP**5"), ("E12", "E**"), ("", "")],
    )
    def test_mask_code(self, code, expected):
        assert mask_code(code) == expected

    def test_sanitized_masks_by_default(self):
        txn = RawTransaction.parse(transaction(106))

        assert txn.sanitized()["employee_code"] == "EMP**9"
        assert txn.sanitized(mask_employee=False)["employee_code"] == "EMP069"

    def test_sanitized_carries_no_name_fields(self):
        txn = RawTransaction.parse(transaction(107))

        assert not (set(txn.sanitized()) & PII_FIELDS)
