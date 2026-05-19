"""NFR-003 — multiprocess concurrent-append correctness.

These tests spawn real subprocesses (``multiprocessing.Pool``) so the
``fcntl.LOCK_EX`` critical section in ``scripts.common.state_log.append``
is exercised across separate processes. Threads would not test the
cross-process fcntl lock — by design we use ``multiprocessing``.

Start method is forced to ``spawn`` for portability between macOS
(default ``spawn``) and Linux (default ``fork``).

If either test fails it is **not** a flaky test — it is the NFR-003
guarantee surfacing a real bug. Do not mark these tests flaky.

Test pacing:
- 10 workers × 10 unique records → 100-line write with zero races.
- 10 workers × 1 duplicate record → exactly 1 line written (idempotency
  holds under concurrent writers).

Production state at ``/data/services/openclaw/state`` is never touched;
each test writes inside ``tmp_path``. The subprocess receives the temp
path via the worker argument and assigns it to its own copy of
``state_log.STATE_DIR``.
"""
from __future__ import annotations

import json
import multiprocessing
import pathlib
import sys
import time
from pathlib import Path

import pytest


# Force spawn start method for cross-platform parity. Idempotent — repeat
# calls with force=True are safe and avoid the "context already set" error.
multiprocessing.set_start_method("spawn", force=True)


# Ensure the worker subprocess can locate the repo root (where
# ``scripts/common/state_log.py`` lives). Conftest already inserts this
# onto sys.path for the parent; pickling sys.path into the spawn child is
# not automatic, so we resolve REPO_ROOT here too and pass it through.
REPO_ROOT = Path(__file__).resolve().parent.parent.parent


# ---------------------------------------------------------------------------
# Module-level worker helpers (must be pickleable for spawn).
# ---------------------------------------------------------------------------

def _append_worker(
    repo_root: str, state_dir_path: str, worker_id: int, records_per_worker: int
) -> int:
    """Each subprocess appends ``records_per_worker`` unique records.

    Returns the number of records this worker attempted (for sanity).
    """
    if repo_root not in sys.path:
        sys.path.insert(0, repo_root)
    from scripts.common import state_log

    state_log.STATE_DIR = pathlib.Path(state_dir_path)
    for i in range(records_per_worker):
        state_log.append("habits", {
            "domain": "habits",
            "task_id": worker_id * 100 + i + 1,  # +1 to keep task_id > 0
            "title": f"task {worker_id}-{i}",
            "date": "2026-05-19",
            "state": "complete",
            "source": "test",
            "note": None,
            "timestamp": f"2026-05-19T11:00:{i:02d}+00:00",
        })
    return records_per_worker


def _dup_append_worker(
    repo_root: str, state_dir_path: str, worker_id: int
) -> int:
    """All workers attempt the SAME (task_id, date, state) record."""
    if repo_root not in sys.path:
        sys.path.insert(0, repo_root)
    from scripts.common import state_log

    state_log.STATE_DIR = pathlib.Path(state_dir_path)
    state_log.append("habits", {
        "domain": "habits",
        "task_id": 42,
        "title": "shared",
        "date": "2026-05-19",
        "state": "complete",
        "source": "test",
        "note": None,
        "timestamp": "2026-05-19T11:00:00+00:00",
    })
    return worker_id


# ---------------------------------------------------------------------------
# NFR-003 — concurrent append across 10 workers, 100 unique records.
# ---------------------------------------------------------------------------

def test_concurrent_append_100_trials_no_corruption(tmp_path):
    """10 workers × 10 records → 100 lines, all unique, all valid JSON."""
    state_dir = tmp_path / "state"
    workers = 10
    records_per_worker = 10
    total = workers * records_per_worker

    start = time.monotonic()
    with multiprocessing.Pool(workers) as pool:
        results = pool.starmap(
            _append_worker,
            [
                (str(REPO_ROOT), str(state_dir), wid, records_per_worker)
                for wid in range(workers)
            ],
        )
    elapsed = time.monotonic() - start

    assert results == [records_per_worker] * workers
    # 10s budget for the concurrent test per WP02 validation note.
    assert elapsed < 10.0, f"concurrent test too slow: {elapsed:.2f}s"

    path = state_dir / "habits-history.jsonl"
    assert path.exists()

    raw_lines = path.read_text(encoding="utf-8").splitlines()
    assert len(raw_lines) == total, (
        f"expected {total} lines, got {len(raw_lines)} — fcntl lock failed"
    )

    # Each line must parse as JSON (no truncation, no interleave).
    parsed = []
    for line in raw_lines:
        assert line.strip(), "no blank lines allowed mid-file"
        # No newlines inside a line (cheap interleave check).
        assert "\n" not in line
        # Length sanity: each JSON object is on the order of ~200 bytes.
        # If anything is wildly shorter than 100 chars it's suspicious.
        assert len(line) >= 100, f"suspiciously short line: {line!r}"
        parsed.append(json.loads(line))

    # Every task_id must appear exactly once and cover the expected range.
    seen_task_ids = sorted(r["task_id"] for r in parsed)
    expected_task_ids = sorted(
        wid * 100 + i + 1
        for wid in range(workers)
        for i in range(records_per_worker)
    )
    assert seen_task_ids == expected_task_ids, (
        "task_id set mismatch — losses or duplicates indicate a lock bug"
    )


# ---------------------------------------------------------------------------
# Idempotency under concurrency.
# ---------------------------------------------------------------------------

def test_concurrent_append_same_record_dedups(tmp_path):
    """10 workers append the same (task_id, date, state) → exactly 1 line."""
    state_dir = tmp_path / "state"
    workers = 10

    with multiprocessing.Pool(workers) as pool:
        results = pool.starmap(
            _dup_append_worker,
            [(str(REPO_ROOT), str(state_dir), wid) for wid in range(workers)],
        )
    assert sorted(results) == list(range(workers))

    path = state_dir / "habits-history.jsonl"
    assert path.exists()
    lines = path.read_text(encoding="utf-8").splitlines()
    assert len(lines) == 1, (
        f"idempotency under concurrency violated: expected 1 line, "
        f"got {len(lines)}"
    )
    record = json.loads(lines[0])
    assert record["task_id"] == 42
    assert record["state"] == "complete"


# ---------------------------------------------------------------------------
# Safety pin.
# ---------------------------------------------------------------------------

def test_concurrent_tests_use_isolated_tmp_path(tmp_path):
    """Defensive: tmp_path never resolves to the production state path."""
    assert "/data/services/openclaw/state" not in str(tmp_path)
