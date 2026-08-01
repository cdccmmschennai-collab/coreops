"""Single-instance run lock.

Two things must hold on a Windows admin PC:

  * a second invocation while a run is active exits clearly, and
  * a run that was killed leaves nothing that blocks the next one.

The second is what rules out a PID file. ``os.kill(pid, 0)`` - the usual
liveness probe - calls ``TerminateProcess`` on Windows, so the "check" would
kill whatever process now owns that PID. An OS file lock is released by the
kernel when the holder dies, so there is no stale state to interpret.
"""
from __future__ import annotations

import json
import os
import subprocess
import sys
import textwrap

import pytest

from exceptions import RunLockUnavailable
from runlock import RunLock

CONNECTOR_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


class TestAcquire:
    def test_acquires_and_creates_the_file(self, tmp_path):
        path = tmp_path / "locks" / "sync.lock"

        with RunLock(path, run_id="abc123", mode="incremental") as lock:
            assert lock.held
            assert path.exists()

    def test_records_diagnostics(self, tmp_path):
        path = tmp_path / "sync.lock"

        with RunLock(path, run_id="abc123", mode="reconcile"):
            data = json.loads(path.read_text(encoding="utf-8"))

        assert data["pid"] == os.getpid()
        assert data["run_id"] == "abc123"
        assert data["mode"] == "reconcile"
        assert data["acquired_at"]

    def test_release_is_idempotent(self, tmp_path):
        lock = RunLock(tmp_path / "sync.lock")
        lock.acquire()
        lock.release()
        lock.release()

        assert not lock.held

    def test_the_lock_can_be_retaken_after_release(self, tmp_path):
        path = tmp_path / "sync.lock"
        with RunLock(path, run_id="first"):
            pass
        with RunLock(path, run_id="second") as second:
            assert second.held


class TestOverlap:
    def test_a_second_run_is_rejected_while_the_first_holds_it(self, tmp_path):
        path = tmp_path / "sync.lock"

        with RunLock(path, run_id="first", mode="incremental"):
            with pytest.raises(RunLockUnavailable) as exc:
                RunLock(path, run_id="second").acquire()

        assert str(path) in str(exc.value)

    def test_the_rejection_names_the_holder(self, tmp_path):
        path = tmp_path / "sync.lock"

        with RunLock(path, run_id="first", mode="incremental"):
            with pytest.raises(RunLockUnavailable) as exc:
                RunLock(path, run_id="second").acquire()

        assert f"pid {os.getpid()}" in str(exc.value)

    def test_the_second_run_does_not_corrupt_the_holder_s_diagnostics(self, tmp_path):
        path = tmp_path / "sync.lock"

        with RunLock(path, run_id="first", mode="incremental"):
            with pytest.raises(RunLockUnavailable):
                RunLock(path, run_id="second").acquire()
            data = json.loads(path.read_text(encoding="utf-8"))

        assert data["run_id"] == "first"

    def test_different_lock_paths_do_not_block_each_other(self, tmp_path):
        with RunLock(tmp_path / "a.lock", run_id="a"):
            with RunLock(tmp_path / "b.lock", run_id="b") as second:
                assert second.held


class TestStaleLocks:
    def test_a_leftover_file_from_a_dead_run_is_acquired_immediately(self, tmp_path):
        """A killed run leaves the FILE but not the LOCK.

        This is the stale-lock case, and it needs no timeout, no PID probe and
        no recovery logic: the kernel released the lock when the process died.
        """
        path = tmp_path / "sync.lock"
        path.write_text(
            json.dumps(
                {
                    "pid": 999999,
                    "host": "SOME-OLD-PC",
                    "run_id": "crashed",
                    "mode": "incremental",
                    "acquired_at": "2020-01-01T00:00:00+00:00",
                }
            ),
            encoding="utf-8",
        )

        with RunLock(path, run_id="fresh") as lock:
            assert lock.held
            assert json.loads(path.read_text(encoding="utf-8"))["run_id"] == "fresh"

    @pytest.mark.parametrize("contents", ["", "not json at all", "[]", '{"no_pid": 1}'])
    def test_an_unreadable_lock_file_does_not_crash_the_next_run(self, tmp_path, contents):
        path = tmp_path / "sync.lock"
        path.write_text(contents, encoding="utf-8")

        with RunLock(path, run_id="fresh") as lock:
            assert lock.held

    def test_a_garbage_lock_file_still_yields_a_clean_rejection_message(self, tmp_path):
        path = tmp_path / "sync.lock"

        with RunLock(path, run_id="first"):
            path.write_text("corrupted by something else", encoding="utf-8")
            with pytest.raises(RunLockUnavailable) as exc:
                RunLock(path, run_id="second").acquire()

        assert "Another connector run holds" in str(exc.value)


class TestCrossProcess:
    """The real scenario: two separate `python sync.py` invocations.

    Same-process tests already prove the conflict, but Task Scheduler starts a
    new process, and on Windows lock semantics differ between handles in one
    process and handles in two. This asserts the case that actually ships.
    """

    def test_a_second_process_cannot_take_a_held_lock(self, tmp_path):
        path = tmp_path / "sync.lock"
        script = textwrap.dedent(
            f"""
            import sys
            sys.path.insert(0, {CONNECTOR_DIR!r})
            from exceptions import RunLockUnavailable
            from runlock import RunLock
            try:
                RunLock({str(path)!r}, run_id="other-process").acquire()
            except RunLockUnavailable:
                sys.exit(3)
            sys.exit(0)
            """
        )

        with RunLock(path, run_id="holder", mode="incremental"):
            completed = subprocess.run(
                [sys.executable, "-c", script], capture_output=True, text=True, timeout=60
            )

        assert completed.returncode == 3, completed.stderr

    def test_the_lock_is_free_once_the_holding_process_exits(self, tmp_path):
        path = tmp_path / "sync.lock"
        script = textwrap.dedent(
            f"""
            import sys
            sys.path.insert(0, {CONNECTOR_DIR!r})
            from runlock import RunLock
            lock = RunLock({str(path)!r}, run_id="short-lived")
            lock.acquire()
            # Exit WITHOUT releasing - the kernel has to clean this up.
            sys.exit(0)
            """
        )
        completed = subprocess.run(
            [sys.executable, "-c", script], capture_output=True, text=True, timeout=60
        )
        assert completed.returncode == 0, completed.stderr

        with RunLock(path, run_id="next") as lock:
            assert lock.held
