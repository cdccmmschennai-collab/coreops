"""Normalization, ordering and the deterministic batch key.

The rule that dominates this file: the connector carries the vendor's punch
state across unchanged and sends every punch it fetched. There is no code path
here that infers IN/OUT or drops an intermediate punch, and these tests exist to
keep it that way.
"""
from __future__ import annotations

from zoneinfo import ZoneInfo

import pytest
from conftest import live_transaction, transaction

import mapper
from mapper import NormalizationError
from schemas import RawTransaction

IST = ZoneInfo("Asia/Kolkata")


def raw(**overrides) -> RawTransaction:
    payload = live_transaction(overrides.pop("txn_id", 1))
    payload.update(overrides)
    return RawTransaction.parse(payload)


class TestNormalize:
    def test_attaches_the_configured_offset(self):
        punch = mapper.normalize(raw(), provider="easytime", tz=IST)

        assert punch.punch_time == "2026-07-29T10:12:10+05:30"

    def test_upload_time_is_normalized_separately_and_not_conflated(self):
        # The live probe found punches uploaded the FOLLOWING morning. The two
        # timestamps answer different questions and must stay distinct.
        punch = mapper.normalize(raw(), provider="easytime", tz=IST)

        assert punch.punch_time.startswith("2026-07-29")
        assert punch.upload_time.startswith("2026-07-30")

    def test_state_zero_is_preserved_verbatim(self):
        punch = mapper.normalize(raw(), provider="easytime", tz=IST)

        assert punch.punch_state == "0"

    def test_null_display_label_stays_null(self):
        punch = mapper.normalize(raw(), provider="easytime", tz=IST)

        assert punch.punch_state_display is None

    def test_no_in_out_field_is_invented(self):
        punch = mapper.normalize(raw(), provider="easytime", tz=IST)
        wire = punch.to_wire()

        assert "direction" not in wire
        assert "is_in" not in wire
        assert "punch_type" not in wire
        assert set(wire) == {
            "external_transaction_id",
            "employee_code",
            "punch_time",
            "raw_punch_state",
            "punch_state_display",
            "terminal_alias",
            "terminal_serial_number",
            "verify_type",
            "source",
            "upload_time",
            "raw_payload",
        }

    def test_carries_the_device_identity(self):
        punch = mapper.normalize(raw(), provider="easytime", tz=IST)

        assert punch.terminal_alias == "F22/ID"
        assert punch.terminal_serial_number == "CDC-DEV-01"
        assert punch.verify_type == "1"

    def test_an_unparseable_punch_time_is_rejected_not_guessed(self):
        with pytest.raises(NormalizationError) as exc:
            mapper.normalize(raw(punch_time="yesterday-ish"), provider="easytime", tz=IST)

        assert "punch_time" in str(exc.value)

    def test_an_unparseable_upload_time_does_not_cost_the_punch(self):
        # Arrival metadata is not worth an attendance event.
        punch = mapper.normalize(raw(upload_time="???"), provider="easytime", tz=IST)

        assert punch.upload_time is None
        assert punch.punch_time == "2026-07-29T10:12:10+05:30"

    def test_missing_upload_time_is_none(self):
        payload = live_transaction(1)
        del payload["upload_time"]
        punch = mapper.normalize(RawTransaction.parse(payload), provider="easytime", tz=IST)

        assert punch.upload_time is None


class TestPayloadHygiene:
    def test_names_never_leave_this_pc(self):
        punch = mapper.normalize(raw(), provider="easytime", tz=IST)

        assert "first_name" not in punch.raw_payload
        assert "last_name" not in punch.raw_payload
        assert "BeStripped" not in str(punch.raw_payload)

    def test_nested_structures_are_dropped(self):
        # The only realistic hiding place for a base64 biometric template.
        payload = live_transaction(1)
        payload["extra"] = {"face_template": "AAAA"}
        payload["list"] = [1, 2, 3]
        punch = mapper.normalize(RawTransaction.parse(payload), provider="easytime", tz=IST)

        assert "extra" not in punch.raw_payload
        assert "list" not in punch.raw_payload

    def test_an_oversized_string_is_dropped_whole_not_truncated(self):
        # Half a biometric template is still biometric material.
        payload = live_transaction(1)
        payload["biophoto"] = "x" * 5000
        punch = mapper.normalize(RawTransaction.parse(payload), provider="easytime", tz=IST)

        assert "biophoto" not in punch.raw_payload

    def test_the_scalar_vendor_fields_survive(self):
        punch = mapper.normalize(raw(), provider="easytime", tz=IST)

        assert punch.raw_payload["emp_code"] == "61"
        assert punch.raw_payload["punch_state"] == "0"


class TestNormalizeAll:
    def test_rejections_are_returned_not_raised_and_not_swallowed(self):
        good = RawTransaction.parse(live_transaction(1))
        bad = RawTransaction.parse(live_transaction(2, punch_time="2026-07-29 10:12:10"))
        bad = RawTransaction.parse({**live_transaction(2), "punch_time": "nonsense"})

        punches, rejected = mapper.normalize_all([good, bad], provider="easytime", tz=IST)

        assert len(punches) == 1
        assert len(rejected) == 1
        assert "2" in rejected[0]

    def test_one_bad_record_does_not_cost_the_rest(self):
        rows = [RawTransaction.parse(live_transaction(n)) for n in range(1, 6)]
        rows.append(RawTransaction.parse({**live_transaction(99), "punch_time": "bad"}))

        punches, rejected = mapper.normalize_all(rows, provider="easytime", tz=IST)

        assert len(punches) == 5
        assert len(rejected) == 1


class TestOrderingAndChunking:
    def test_sorts_by_time_then_id(self):
        rows = [
            raw(txn_id=3, punch_time="2026-07-29 17:00:00"),
            raw(txn_id=1, punch_time="2026-07-29 09:00:00"),
            raw(txn_id=2, punch_time="2026-07-29 09:00:00"),
        ]
        punches, _ = mapper.normalize_all(rows, provider="easytime", tz=IST)
        ordered = mapper.sort_punches(punches)

        assert [p.external_transaction_id for p in ordered] == ["1", "2", "3"]

    def test_numeric_ids_sort_numerically_not_lexically(self):
        rows = [
            raw(txn_id=10, punch_time="2026-07-29 09:00:00"),
            raw(txn_id=9, punch_time="2026-07-29 09:00:00"),
        ]
        punches, _ = mapper.normalize_all(rows, provider="easytime", tz=IST)

        assert [p.external_transaction_id for p in mapper.sort_punches(punches)] == ["9", "10"]

    def test_sorting_is_stable_across_repeated_calls(self):
        rows = [raw(txn_id=n, punch_time="2026-07-29 09:00:00") for n in (5, 2, 9, 1)]
        punches, _ = mapper.normalize_all(rows, provider="easytime", tz=IST)

        first = [p.external_transaction_id for p in mapper.sort_punches(punches)]
        second = [p.external_transaction_id for p in mapper.sort_punches(list(reversed(punches)))]

        assert first == second

    def test_chunk_respects_the_size_and_keeps_order(self):
        rows = [raw(txn_id=n, punch_time=f"2026-07-29 09:0{n}:00") for n in range(5)]
        punches, _ = mapper.normalize_all(rows, provider="easytime", tz=IST)
        chunks = list(mapper.chunk(mapper.sort_punches(punches), 2))

        assert [len(c) for c in chunks] == [2, 2, 1]
        assert chunks[0][0].external_transaction_id == "0"

    def test_chunk_of_an_empty_list_yields_nothing(self):
        assert list(mapper.chunk([], 10)) == []

    def test_chunk_rejects_a_zero_size(self):
        with pytest.raises(ValueError):
            list(mapper.chunk([1, 2], 0))


class TestBatchKey:
    BASE = dict(
        connector_id="admin-pc-01",
        provider="easytime",
        source_from="2026-07-29T00:00:00+05:30",
        source_to="2026-07-29T23:59:59+05:30",
        batch_number=1,
        external_transaction_ids=["1", "2", "3"],
    )

    def test_is_stable_for_identical_input(self):
        assert mapper.batch_key(**self.BASE) == mapper.batch_key(**self.BASE)

    def test_does_not_depend_on_the_clock(self):
        import time

        first = mapper.batch_key(**self.BASE)
        time.sleep(0.01)
        assert mapper.batch_key(**self.BASE) == first

    @pytest.mark.parametrize(
        "field,value",
        [
            ("connector_id", "admin-pc-02"),
            ("provider", "other"),
            ("source_from", "2026-07-28T00:00:00+05:30"),
            ("source_to", "2026-07-30T23:59:59+05:30"),
            ("batch_number", 2),
            ("external_transaction_ids", ["1", "2", "4"]),
        ],
    )
    def test_every_input_changes_the_key(self, field, value):
        assert mapper.batch_key(**{**self.BASE, field: value}) != mapper.batch_key(**self.BASE)

    def test_order_of_the_ids_matters(self):
        # Ordering is fixed by sort_punches before the key is built, so a
        # different order means a genuinely different chunk.
        reordered = {**self.BASE, "external_transaction_ids": ["3", "2", "1"]}

        assert mapper.batch_key(**reordered) != mapper.batch_key(**self.BASE)

    def test_shape_and_length_fit_the_backend_column(self):
        key = mapper.batch_key(**self.BASE)

        assert key.startswith("et1-")
        assert len(key) == 68 <= 128  # backend MAX_BATCH_KEY_LEN

    def test_carries_no_secret(self):
        # Nothing secret is an input, so nothing secret can be an output. The
        # key is safe to print, log and store.
        key = mapper.batch_key(**self.BASE)

        assert "token" not in key
        assert all(c in "0123456789abcdef-et1" for c in key)


class TestTimezoneHelpers:
    def test_to_naive_local_converts_from_utc(self):
        from datetime import datetime, timezone

        utc = datetime(2026, 7, 29, 4, 42, 10, tzinfo=timezone.utc)

        assert mapper.to_naive_local(utc, IST) == datetime(2026, 7, 29, 10, 12, 10)

    def test_span_days(self):
        from datetime import datetime, timedelta

        start = datetime(2026, 7, 1, tzinfo=IST)

        assert mapper.span_days(start, start + timedelta(days=3)) == 3.0


class TestNothingIsInterpreted:
    def test_the_module_has_no_in_out_vocabulary(self):
        """A grep-style guard.

        If someone later adds "first punch is IN", it will almost certainly
        introduce one of these words. The live probe returned "0" for every
        punch with no label, so any such mapping would be a guess - and a guess
        that produces plausible-looking, wrong attendance.
        """
        source = (mapper.__file__ and open(mapper.__file__, encoding="utf-8").read()) or ""
        code = "\n".join(
            line for line in source.splitlines() if not line.strip().startswith(("#", "*"))
        )
        # The docstring names these words to say they are forbidden; strip it.
        code = code.split('"""', 2)[-1]

        for forbidden in ("check_in", "checkin", "is_in", "direction", "session"):
            assert forbidden not in code.lower(), f"{forbidden!r} appeared in mapper.py"
