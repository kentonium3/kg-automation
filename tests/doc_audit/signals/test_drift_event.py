"""Unit tests for :class:`doc_audit.signals.drift_event.DriftEventSignalSource`.

Locks in:

- The contract-mandated semantics (idempotent ``pending()``, atomic
  cursor write on ``commit()``, no side effects in ``pending()``).
- The cycle-2 requirement that the adapter routes through the
  helper's atomic primitives (:func:`find_mapping`,
  :func:`file_doc_audit_issue`, :func:`append_unmapped`,
  :func:`write_cursor_atomic`) rather than re-implementing
  classification or issue filing locally.

Tests construct a per-test ``drift-events.jsonl`` and cursor under
``tmp_path`` (via the ``tmp_config`` fixture from ``conftest.py``).
No real ``/data/services/security-monitor/...`` paths are touched.
"""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any
from unittest import mock

import pytest

from doc_audit.signals.drift_event import DriftEventSignalSource


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _write_events(events_path: Path, events: list[dict]) -> None:
    events_path.write_text(
        "\n".join(json.dumps(e) for e in events) + ("\n" if events else ""),
        encoding="utf-8",
    )


def _write_cursor(cursor_path: Path, value: int) -> None:
    cursor_path.write_text(str(value), encoding="utf-8")


def _event(line: int, baseline: str | None = None) -> dict:
    return {
        "timestamp": f"2026-05-20T10:0{line}:00Z",
        "source": "audit.sh",
        "event_type": "baseline_drift",
        "baseline_name": baseline if baseline is not None else f"baseline-{line}.txt",
        "diff_b64": "ZGlmZi1nb2VzLWhlcmU=",
    }


def _write_mapping(
    mapping_path: Path,
    *,
    match: dict[str, Any] | None = None,
    mapping_id: str = "test-map-01",
    doc_targets: list[str] | None = None,
    labels: list[str] | None = None,
) -> None:
    """Write a minimal ``signal-to-doc-map.json`` for tests.

    Default ``match`` is ``{"event_type": "baseline_drift"}`` so the
    representative events in this file all match.
    """
    payload = {
        "mappings": [
            {
                "id": mapping_id,
                "match": match
                if match is not None
                else {"event_type": "baseline_drift"},
                "doc_targets": doc_targets
                if doc_targets is not None
                else ["docs/example.md"],
                "rationale": "test rationale",
                "issue_title_prefix": "[doc-audit] drift detected",
                "issue_labels": labels if labels is not None else ["doc-audit"],
            }
        ]
    }
    mapping_path.write_text(json.dumps(payload), encoding="utf-8")


def _write_empty_mapping(mapping_path: Path) -> None:
    """Write a ``signal-to-doc-map.json`` whose mapping table is empty.

    Use this when the test wants every event to fall through to the
    unmapped path.
    """
    mapping_path.write_text(json.dumps({"mappings": []}), encoding="utf-8")


# ---------------------------------------------------------------------------
# 1. Empty file
# ---------------------------------------------------------------------------


def test_pending_empty_file(tmp_config: Any) -> None:
    """Empty ``drift-events.jsonl`` + cursor=0 → ``pending()`` returns ``[]``."""
    _write_empty_mapping(Path(tmp_config.paths.signal_to_doc_map))
    source = DriftEventSignalSource(tmp_config)
    assert source.pending() == []


# ---------------------------------------------------------------------------
# 2. One event
# ---------------------------------------------------------------------------


def test_pending_one_event(tmp_config: Any) -> None:
    """Cursor=0 + 1-line file → ``pending()`` returns 1 Signal."""
    _write_events(Path(tmp_config.paths.drift_events), [_event(1)])
    _write_mapping(Path(tmp_config.paths.signal_to_doc_map))
    source = DriftEventSignalSource(tmp_config)
    signals = source.pending()
    assert len(signals) == 1
    sig = signals[0]
    assert sig.kind == "drift_event"
    assert sig.priority == 40
    assert sig.source == "drift_event"
    assert sig.payload["line_number"] == 0
    assert sig.payload["baseline_name"] == "baseline-1.txt"
    assert sig.payload["raw_event"]["timestamp"] == "2026-05-20T10:01:00Z"
    # mapping_id from find_mapping is recorded on the signal payload.
    assert sig.payload["mapping_id"] == "test-map-01"


# ---------------------------------------------------------------------------
# 3. Skip processed events
# ---------------------------------------------------------------------------


def test_pending_skip_processed(tmp_config: Any) -> None:
    """Cursor=5 + 7-event file → ``pending()`` returns 2 Signals (events 5, 6)."""
    _write_events(
        Path(tmp_config.paths.drift_events),
        [_event(i) for i in range(7)],
    )
    _write_cursor(Path(tmp_config.paths.drift_cursor), 5)
    _write_mapping(Path(tmp_config.paths.signal_to_doc_map))
    source = DriftEventSignalSource(tmp_config)
    signals = source.pending()
    assert len(signals) == 2
    assert signals[0].payload["line_number"] == 5
    assert signals[1].payload["line_number"] == 6


# ---------------------------------------------------------------------------
# 4. Idempotency
# ---------------------------------------------------------------------------


def test_pending_idempotent(tmp_config: Any) -> None:
    """Two ``pending()`` calls return the same list; cursor doesn't move."""
    _write_events(
        Path(tmp_config.paths.drift_events),
        [_event(i) for i in range(3)],
    )
    _write_mapping(Path(tmp_config.paths.signal_to_doc_map))
    source = DriftEventSignalSource(tmp_config)
    first = source.pending()
    second = source.pending()
    assert first == second
    # Cursor file should still report 0 (or be absent).
    cursor_path = Path(tmp_config.paths.drift_cursor)
    if cursor_path.exists():
        assert cursor_path.read_text(encoding="utf-8").strip() == "0"


# ---------------------------------------------------------------------------
# 5. commit() advances the cursor (mapped event → file_doc_audit_issue)
# ---------------------------------------------------------------------------


def test_commit_advances_cursor_mapped(tmp_config: Any) -> None:
    """After ``commit()`` on a mapped event, cursor advances past it.

    A fresh adapter on the same paths sees only the remaining events.
    ``file_doc_audit_issue`` is stubbed so we don't shell out to ``gh``.
    """
    _write_events(
        Path(tmp_config.paths.drift_events),
        [_event(i) for i in range(3)],
    )
    _write_mapping(Path(tmp_config.paths.signal_to_doc_map))
    source = DriftEventSignalSource(tmp_config)
    signals = source.pending()
    assert len(signals) == 3

    with mock.patch(
        "doc_audit.signals.drift_event.file_doc_audit_issue",
        return_value=(True, "https://example/issues/1"),
    ) as mock_file:
        source.commit(signals[0], "success")

    # The helper's filing primitive must have been called exactly once.
    assert mock_file.call_count == 1

    # Cursor file now reports 1 (past line 0).
    assert (
        Path(tmp_config.paths.drift_cursor)
        .read_text(encoding="utf-8")
        .strip()
        == "1"
    )

    # A fresh adapter instance sees only events 1, 2.
    fresh = DriftEventSignalSource(tmp_config)
    remaining = fresh.pending()
    assert len(remaining) == 2
    assert remaining[0].payload["line_number"] == 1
    assert remaining[1].payload["line_number"] == 2


# ---------------------------------------------------------------------------
# 6. Missing drift-events.jsonl
# ---------------------------------------------------------------------------


def test_pending_handles_missing_file(tmp_config: Any) -> None:
    """Missing events file → ``pending()`` returns ``[]`` (no error)."""
    events_path = Path(tmp_config.paths.drift_events)
    if events_path.exists():
        events_path.unlink()
    _write_mapping(Path(tmp_config.paths.signal_to_doc_map))
    source = DriftEventSignalSource(tmp_config)
    assert source.pending() == []


# ---------------------------------------------------------------------------
# 7. Missing cursor file
# ---------------------------------------------------------------------------


def test_pending_handles_missing_cursor(tmp_config: Any) -> None:
    """Absent cursor file → treated as cursor=0."""
    _write_events(
        Path(tmp_config.paths.drift_events),
        [_event(0), _event(1)],
    )
    _write_mapping(Path(tmp_config.paths.signal_to_doc_map))
    cursor_path = Path(tmp_config.paths.drift_cursor)
    if cursor_path.exists():
        cursor_path.unlink()
    source = DriftEventSignalSource(tmp_config)
    signals = source.pending()
    assert len(signals) == 2
    assert signals[0].payload["line_number"] == 0
    assert signals[1].payload["line_number"] == 1


# ---------------------------------------------------------------------------
# 8. Atomic cursor write (tempfile + rename) via helper primitive
# ---------------------------------------------------------------------------


def test_commit_partial_writes_correctly(tmp_config: Any) -> None:
    """``commit()`` advances cursor atomically via ``os.replace``.

    We spy on ``os.replace`` inside the helper module to confirm the
    helper's atomic write path runs (no partial cursor state on disk
    if the process is interrupted mid-write).
    """
    _write_events(
        Path(tmp_config.paths.drift_events),
        [_event(0), _event(1)],
    )
    _write_mapping(Path(tmp_config.paths.signal_to_doc_map))
    source = DriftEventSignalSource(tmp_config)
    signals = source.pending()

    real_replace = os.replace
    replace_calls: list[tuple[str, str]] = []

    def spy_replace(src: str, dst: str) -> None:
        replace_calls.append((str(src), str(dst)))
        real_replace(src, dst)

    with mock.patch(
        "doc_audit.signals.drift_event.file_doc_audit_issue",
        return_value=(True, "https://example/issues/1"),
    ), mock.patch(
        "doc_audit.helpers.handle_drift_events.os.replace",
        side_effect=spy_replace,
    ):
        source.commit(signals[0], "success")

    assert len(replace_calls) == 1
    # The destination MUST be the cursor file itself.
    assert replace_calls[0][1] == str(tmp_config.paths.drift_cursor)
    # And the cursor reflects the advance.
    assert (
        Path(tmp_config.paths.drift_cursor)
        .read_text(encoding="utf-8")
        .strip()
        == "1"
    )


# ---------------------------------------------------------------------------
# 9. commit on a signal whose cursor is already past is a no-op
# ---------------------------------------------------------------------------


def test_commit_idempotent_when_already_advanced(tmp_config: Any) -> None:
    """Re-committing a signal whose line is below cursor is a safe no-op.

    The second commit MUST NOT invoke ``file_doc_audit_issue`` or
    ``append_unmapped`` again — once the cursor is past, we're done.
    """
    _write_events(
        Path(tmp_config.paths.drift_events),
        [_event(0), _event(1)],
    )
    _write_mapping(Path(tmp_config.paths.signal_to_doc_map))
    source = DriftEventSignalSource(tmp_config)
    signals = source.pending()

    with mock.patch(
        "doc_audit.signals.drift_event.file_doc_audit_issue",
        return_value=(True, "https://example/issues/1"),
    ) as mock_file, mock.patch(
        "doc_audit.signals.drift_event.append_unmapped"
    ) as mock_unmapped:
        source.commit(signals[0], "success")
        # Re-commit must not raise and must not advance further.
        source.commit(signals[0], "success")

    # File primitive called exactly once across both commits.
    assert mock_file.call_count == 1
    assert mock_unmapped.call_count == 0
    assert (
        Path(tmp_config.paths.drift_cursor)
        .read_text(encoding="utf-8")
        .strip()
        == "1"
    )


# ---------------------------------------------------------------------------
# 10. Malformed JSON line is skipped without breaking the iteration
# ---------------------------------------------------------------------------


def test_pending_skips_malformed_json(
    tmp_config: Any,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """A malformed JSON line is logged + skipped, not raised."""
    events_path = Path(tmp_config.paths.drift_events)
    events_path.write_text(
        json.dumps(_event(0)) + "\n"
        + "{not-json-at-all\n"
        + json.dumps(_event(2)) + "\n",
        encoding="utf-8",
    )
    _write_mapping(Path(tmp_config.paths.signal_to_doc_map))
    source = DriftEventSignalSource(tmp_config)
    signals = source.pending()
    # Two valid signals (lines 0 and 2); the bad line 1 is skipped.
    assert len(signals) == 2
    line_numbers = {sig.payload["line_number"] for sig in signals}
    assert line_numbers == {0, 2}
    captured = capsys.readouterr()
    assert "malformed" in captured.err.lower()


# ---------------------------------------------------------------------------
# 11. commit raises if payload lacks line_number
# ---------------------------------------------------------------------------


def test_commit_rejects_signal_without_line_number(
    tmp_config: Any,
    sample_signal_drift_event: Any,
) -> None:
    """A foreign Signal (no ``line_number`` payload key) is rejected."""
    _write_mapping(Path(tmp_config.paths.signal_to_doc_map))
    source = DriftEventSignalSource(tmp_config)
    with pytest.raises(ValueError, match="line_number"):
        source.commit(sample_signal_drift_event, "success")


# ---------------------------------------------------------------------------
# 12. commit() invokes file_doc_audit_issue for a mapped event
# ---------------------------------------------------------------------------


def test_commit_mapped_event_calls_file_doc_audit_issue(
    tmp_config: Any,
) -> None:
    """commit() must invoke the helper's filing primitive (not local code).

    The helper's :func:`file_doc_audit_issue` is the canonical issue
    filer. The adapter must call it, not re-implement gh shell-out.
    """
    _write_events(Path(tmp_config.paths.drift_events), [_event(0)])
    _write_mapping(Path(tmp_config.paths.signal_to_doc_map))

    source = DriftEventSignalSource(tmp_config)
    signals = source.pending()

    with mock.patch(
        "doc_audit.signals.drift_event.file_doc_audit_issue",
        return_value=(True, "https://example/issues/42"),
    ) as mock_file:
        source.commit(signals[0], "success")

    mock_file.assert_called_once()
    # Positional args: (event_dict, mapping, repo)
    call_args = mock_file.call_args
    event_arg = call_args.args[0] if call_args.args else call_args.kwargs.get("event")
    mapping_arg = call_args.args[1] if len(call_args.args) > 1 else call_args.kwargs.get("mapping")
    # event is the raw event we wrote.
    assert event_arg["baseline_name"] == "baseline-0.txt"
    # mapping is a helper Mapping instance with our id.
    assert mapping_arg.id == "test-map-01"
    # repo positional is the config's repo.
    repo_arg = call_args.args[2] if len(call_args.args) > 2 else call_args.kwargs.get("repo")
    assert repo_arg == tmp_config.github.repo
    # dry_run must be False (real filing).
    assert call_args.kwargs.get("dry_run") is False


# ---------------------------------------------------------------------------
# 13. commit() invokes append_unmapped for an unmapped event
# ---------------------------------------------------------------------------


def test_commit_unmapped_event_calls_append_unmapped(
    tmp_config: Any,
) -> None:
    """No matching mapping → ``commit()`` routes via ``append_unmapped``.

    This mirrors what :func:`process_events` does for unmapped events.
    """
    _write_events(Path(tmp_config.paths.drift_events), [_event(0)])
    _write_empty_mapping(Path(tmp_config.paths.signal_to_doc_map))

    source = DriftEventSignalSource(tmp_config)
    signals = source.pending()

    with mock.patch(
        "doc_audit.signals.drift_event.append_unmapped"
    ) as mock_append, mock.patch(
        "doc_audit.signals.drift_event.file_doc_audit_issue"
    ) as mock_file:
        source.commit(signals[0], "success")

    mock_append.assert_called_once()
    # Positional args: (unmapped_path, event)
    args = mock_append.call_args.args
    assert Path(args[0]) == Path(tmp_config.paths.drift_unmapped)
    assert args[1]["baseline_name"] == "baseline-0.txt"
    # Filing primitive MUST NOT be called on unmapped events.
    mock_file.assert_not_called()
    # Cursor still advances.
    assert (
        Path(tmp_config.paths.drift_cursor)
        .read_text(encoding="utf-8")
        .strip()
        == "1"
    )


# ---------------------------------------------------------------------------
# 14. find_mapping is what classifies events (not local logic)
# ---------------------------------------------------------------------------


def test_pending_uses_helper_find_mapping(tmp_config: Any) -> None:
    """Classification path is the helper's ``find_mapping`` (spied)."""
    _write_events(Path(tmp_config.paths.drift_events), [_event(0)])
    _write_mapping(Path(tmp_config.paths.signal_to_doc_map))

    # Wrap the real find_mapping so we observe the call without
    # changing classification behavior.
    from doc_audit.helpers import handle_drift_events as helper_mod

    with mock.patch(
        "doc_audit.signals.drift_event.find_mapping",
        wraps=helper_mod.find_mapping,
    ) as spy_find:
        source = DriftEventSignalSource(tmp_config)
        signals = source.pending()

    assert len(signals) == 1
    # find_mapping called once per event during enumeration.
    assert spy_find.call_count == 1
    # And the resulting mapping_id was recorded on the signal payload.
    assert signals[0].payload["mapping_id"] == "test-map-01"


def test_commit_uses_helper_find_mapping(tmp_config: Any) -> None:
    """commit() consults find_mapping again to route the event canonically."""
    _write_events(Path(tmp_config.paths.drift_events), [_event(0)])
    _write_mapping(Path(tmp_config.paths.signal_to_doc_map))

    source = DriftEventSignalSource(tmp_config)
    signals = source.pending()

    from doc_audit.helpers import handle_drift_events as helper_mod

    with mock.patch(
        "doc_audit.signals.drift_event.find_mapping",
        wraps=helper_mod.find_mapping,
    ) as spy_find, mock.patch(
        "doc_audit.signals.drift_event.file_doc_audit_issue",
        return_value=(True, "url"),
    ):
        source.commit(signals[0], "success")

    # find_mapping consulted in commit() too (one extra call beyond
    # any pending() enumeration that already ran).
    assert spy_find.call_count >= 1


# ---------------------------------------------------------------------------
# 15. file_doc_audit_issue failure leaves cursor unchanged
# ---------------------------------------------------------------------------


def test_commit_filing_failure_does_not_advance_cursor(
    tmp_config: Any,
) -> None:
    """A failed ``file_doc_audit_issue`` MUST NOT advance the cursor.

    The driver retries the event next tick if filing fails — matching
    :func:`process_events` which breaks out of its loop on error to
    avoid passing the cursor over an unfiled event.
    """
    _write_events(Path(tmp_config.paths.drift_events), [_event(0)])
    _write_mapping(Path(tmp_config.paths.signal_to_doc_map))

    source = DriftEventSignalSource(tmp_config)
    signals = source.pending()

    with mock.patch(
        "doc_audit.signals.drift_event.file_doc_audit_issue",
        return_value=(False, "simulated gh failure"),
    ):
        with pytest.raises(RuntimeError, match="file_doc_audit_issue failed"):
            source.commit(signals[0], "success")

    # Cursor MUST NOT have advanced.
    cursor_path = Path(tmp_config.paths.drift_cursor)
    if cursor_path.exists():
        assert cursor_path.read_text(encoding="utf-8").strip() == "0"
    # And a fresh adapter still sees the event as pending.
    fresh = DriftEventSignalSource(tmp_config)
    remaining = fresh.pending()
    assert len(remaining) == 1
    assert remaining[0].payload["line_number"] == 0


# ---------------------------------------------------------------------------
# 16. write_cursor_atomic is invoked from the helper module
# ---------------------------------------------------------------------------


def test_commit_uses_helper_write_cursor_atomic(tmp_config: Any) -> None:
    """commit() routes cursor persistence through the helper's primitive.

    This guarantees the adapter cannot drift away from the helper's
    atomic-write semantics (tempfile + ``os.replace``).
    """
    _write_events(Path(tmp_config.paths.drift_events), [_event(0)])
    _write_mapping(Path(tmp_config.paths.signal_to_doc_map))

    source = DriftEventSignalSource(tmp_config)
    signals = source.pending()

    with mock.patch(
        "doc_audit.signals.drift_event.write_cursor_atomic"
    ) as mock_writer, mock.patch(
        "doc_audit.signals.drift_event.file_doc_audit_issue",
        return_value=(True, "url"),
    ):
        source.commit(signals[0], "success")

    mock_writer.assert_called_once()
    args = mock_writer.call_args.args
    assert Path(args[0]) == Path(tmp_config.paths.drift_cursor)
    assert args[1] == 1


# ---------------------------------------------------------------------------
# 17. Cycle 3 monotonicity — in-order commits advance the cursor one step
# ---------------------------------------------------------------------------


def test_commit_in_order_advances_normally(tmp_config: Any) -> None:
    """Happy path: committing signals in line-number order advances cursor.

    Drains the cursor monotonically through committed events with no
    skipped lines. Establishes the baseline against which the
    out-of-order tests below contrast.
    """
    # Three back-to-back events at lines 0, 1, 2; cursor starts at 0.
    _write_events(
        Path(tmp_config.paths.drift_events),
        [_event(i) for i in range(3)],
    )
    _write_mapping(Path(tmp_config.paths.signal_to_doc_map))

    source = DriftEventSignalSource(tmp_config)
    signals = source.pending()
    assert {s.payload["line_number"] for s in signals} == {0, 1, 2}

    with mock.patch(
        "doc_audit.signals.drift_event.file_doc_audit_issue",
        return_value=(True, "https://example/issues/1"),
    ):
        source.commit(signals[0], "success")
        # After committing line 0, cursor must read 1 — drain stops at
        # the next uncommitted signal line (line 1).
        assert (
            Path(tmp_config.paths.drift_cursor)
            .read_text(encoding="utf-8")
            .strip()
            == "1"
        )
        source.commit(signals[1], "success")
        assert (
            Path(tmp_config.paths.drift_cursor)
            .read_text(encoding="utf-8")
            .strip()
            == "2"
        )
        source.commit(signals[2], "success")
        # All three committed → cursor advances to 3 (past last event).
        assert (
            Path(tmp_config.paths.drift_cursor)
            .read_text(encoding="utf-8")
            .strip()
            == "3"
        )

    # Fresh adapter sees nothing pending.
    fresh = DriftEventSignalSource(tmp_config)
    assert fresh.pending() == []


# ---------------------------------------------------------------------------
# 18. Cycle 3 monotonicity — committing line 8 first MUST NOT skip lines 5, 11
# ---------------------------------------------------------------------------


def test_commit_out_of_order_does_not_skip_earlier_events(
    tmp_config: Any,
) -> None:
    """Critical regression: out-of-order commits must not lose events.

    The driver sorts pending signals by ``(priority, created_utc)``,
    not by drift-event line number. If two events share a priority
    bucket and timestamps are tied or out of order, the driver may
    hand the adapter a later-line signal before earlier-line signals.
    The adapter must NEVER advance the cursor past an uncommitted
    earlier event — otherwise next tick's ``pending()`` will miss it.

    Setup: events at lines 5, 8, 11 (lines 0-4, 6-7, 9-10 are blank
    padding). Initial cursor=4. Commit signals out of line order
    (line 8 first, then 11, then 5). Final cursor must land at 12 in
    one atomic drain on the line-5 commit — proving the late-arriving
    earlier event "fills the gap" and zero events are lost.
    """
    events_path = Path(tmp_config.paths.drift_events)
    # Build a file with events at lines 5, 8, 11; other lines blank.
    # Lines 0-4 are blank, line 5 = event, lines 6-7 blank, line 8 =
    # event, lines 9-10 blank, line 11 = event. 12 total lines.
    lines: list[str] = []
    for index in range(12):
        if index in (5, 8, 11):
            lines.append(json.dumps(_event(index)))
        else:
            lines.append("")
    events_path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    _write_cursor(Path(tmp_config.paths.drift_cursor), 4)
    _write_mapping(Path(tmp_config.paths.signal_to_doc_map))

    source = DriftEventSignalSource(tmp_config)
    signals = source.pending()
    assert {s.payload["line_number"] for s in signals} == {5, 8, 11}

    # Index signals by their line_number so we can commit out of order
    # without relying on enumeration order.
    by_line = {s.payload["line_number"]: s for s in signals}

    with mock.patch(
        "doc_audit.signals.drift_event.file_doc_audit_issue",
        return_value=(True, "https://example/issues/x"),
    ):
        # Commit line 8 first — cursor must NOT jump to 9 (which would
        # skip line 5). Drain may pass over the blank line 4 since it
        # is non-signal, but must stop at line 5 (uncommitted signal).
        source.commit(by_line[8], "success")
        cursor_after_8 = int(
            Path(tmp_config.paths.drift_cursor)
            .read_text(encoding="utf-8")
            .strip()
        )
        assert cursor_after_8 <= 5, (
            f"cursor advanced to {cursor_after_8} after committing line 8 — "
            "MUST NOT pass uncommitted line 5"
        )

        # Commit line 11 next — same invariant: line 5 still
        # uncommitted, cursor must NOT advance past 5.
        source.commit(by_line[11], "success")
        cursor_after_11 = int(
            Path(tmp_config.paths.drift_cursor)
            .read_text(encoding="utf-8")
            .strip()
        )
        assert cursor_after_11 <= 5, (
            f"cursor advanced to {cursor_after_11} after committing line 11 — "
            "MUST NOT pass uncommitted line 5"
        )

        # Now commit the late-arriving earlier event at line 5 — the
        # drain should jump through 5 → 6 → 7 → 8 → 9 → 10 → 11 → 12
        # in a single atomic write.
        source.commit(by_line[5], "success")

    final_cursor = int(
        Path(tmp_config.paths.drift_cursor)
        .read_text(encoding="utf-8")
        .strip()
    )
    assert final_cursor == 12, (
        f"after all three commits cursor must be 12 (past last event "
        f"line 11), got {final_cursor}"
    )

    # And — the canonical "no event lost" assertion: a fresh adapter
    # instance simulates the next tick. It must see NOTHING pending,
    # which is only possible if all three commits actually landed and
    # advanced the cursor through them.
    fresh = DriftEventSignalSource(tmp_config)
    assert fresh.pending() == []


# ---------------------------------------------------------------------------
# 19. Cycle 3 monotonicity — explicit gap-fill scenario
# ---------------------------------------------------------------------------


def test_commit_fills_gap_when_earlier_arrives_later(
    tmp_config: Any,
) -> None:
    """Drain only advances on the commit that fills the gap.

    Distinct from the previous test in that we explicitly assert the
    cursor does NOT move at all on the first two (later-line)
    commits, then jumps in one atomic drain when the earliest
    uncommitted line is finally committed.

    Tight scenario: events at consecutive lines 5, 6, 7; cursor=5.
    Commit line 6 first (cursor must stay at 5), then line 7 (cursor
    still at 5), then line 5 (cursor jumps to 8).
    """
    _write_events(
        Path(tmp_config.paths.drift_events),
        [
            *[{} for _ in range(5)],
        ],
    )
    # Replace the file with 8 lines: 5 blanks then 3 events at 5/6/7.
    events_path = Path(tmp_config.paths.drift_events)
    rows: list[str] = []
    for index in range(8):
        if index in (5, 6, 7):
            rows.append(json.dumps(_event(index)))
        else:
            rows.append("")
    events_path.write_text("\n".join(rows) + "\n", encoding="utf-8")
    _write_cursor(Path(tmp_config.paths.drift_cursor), 5)
    _write_mapping(Path(tmp_config.paths.signal_to_doc_map))

    source = DriftEventSignalSource(tmp_config)
    signals = source.pending()
    by_line = {s.payload["line_number"]: s for s in signals}
    assert set(by_line) == {5, 6, 7}

    cursor_path = Path(tmp_config.paths.drift_cursor)
    initial = int(cursor_path.read_text(encoding="utf-8").strip())
    assert initial == 5

    with mock.patch(
        "doc_audit.signals.drift_event.file_doc_audit_issue",
        return_value=(True, "https://example/issues/y"),
    ):
        # Commit line 6 first — cursor must STAY at 5 because line 5
        # (the next signal-bearing line) has not been committed yet.
        source.commit(by_line[6], "success")
        assert int(cursor_path.read_text(encoding="utf-8").strip()) == 5

        # Commit line 7 — cursor still at 5.
        source.commit(by_line[7], "success")
        assert int(cursor_path.read_text(encoding="utf-8").strip()) == 5

        # Now commit line 5 — drain must jump cursor 5 → 6 → 7 → 8 in
        # a single atomic write.
        source.commit(by_line[5], "success")
        assert int(cursor_path.read_text(encoding="utf-8").strip()) == 8

    # Fresh adapter sees no pending signals — confirms zero events lost.
    fresh = DriftEventSignalSource(tmp_config)
    assert fresh.pending() == []


# ---------------------------------------------------------------------------
# Moment 0 wiring tests (#391 / WP02)
# ---------------------------------------------------------------------------

import dataclasses

from doc_audit.config import DriftInterpretationConfig
from doc_audit.judgment.drift_interpretation import DriftInterpretationError


def _config_with_moment0_enabled(base_config: Any) -> Any:
    """Return a copy of ``base_config`` with drift_interpretation.enabled=True."""
    enabled_block = dataclasses.replace(base_config.drift_interpretation, enabled=True)
    return dataclasses.replace(base_config, drift_interpretation=enabled_block)


def test_moment0_disabled_falls_through_to_file_doc_audit_issue(
    tmp_config: Any,
) -> None:
    """FR-010: flag disabled → JudgmentClient NEVER instantiated, file_doc_audit_issue invoked."""
    _write_events(Path(tmp_config.paths.drift_events), [_event(0)])
    _write_mapping(Path(tmp_config.paths.signal_to_doc_map))

    source = DriftEventSignalSource(tmp_config)
    signals = source.pending()

    # Patch JudgmentClient at the module level — if it gets constructed
    # the assertion below catches it.
    with mock.patch(
        "doc_audit.signals.drift_event._build_judgment_client"
    ) as mock_client_cls, mock.patch(
        "doc_audit.signals.drift_event.route_drift_event"
    ) as mock_route, mock.patch(
        "doc_audit.signals.drift_event.file_doc_audit_issue",
        return_value=(True, "https://example/issues/1"),
    ) as mock_file:
        source.commit(signals[0], "success")

    mock_client_cls.assert_not_called()  # FR-010 — no JudgmentClient construction
    mock_route.assert_not_called()  # pre-#362 path taken
    mock_file.assert_called_once()


def test_moment0_enabled_calls_route_drift_event(tmp_config: Any) -> None:
    """Flag enabled + mapping matches → route_drift_event invoked with correct kwargs."""
    cfg = _config_with_moment0_enabled(tmp_config)
    _write_events(Path(cfg.paths.drift_events), [_event(0)])
    _write_mapping(Path(cfg.paths.signal_to_doc_map))

    source = DriftEventSignalSource(cfg)
    signals = source.pending()

    with mock.patch(
        "doc_audit.signals.drift_event._build_judgment_client"
    ) as mock_client_cls, mock.patch(
        "doc_audit.signals.drift_event.route_drift_event"
    ) as mock_route, mock.patch(
        "doc_audit.signals.drift_event.file_doc_audit_issue"
    ) as mock_file:
        source.commit(signals[0], "success")

    mock_client_cls.assert_called_once()  # JudgmentClient was constructed
    mock_route.assert_called_once()  # Moment 0 path taken
    mock_file.assert_not_called()  # pre-#362 path NOT taken

    # Verify kwargs passed to route_drift_event
    kwargs = mock_route.call_args.kwargs
    assert kwargs["mapping"].id == "test-map-01"
    assert kwargs["config"] is cfg
    assert kwargs["repo"] == cfg.github.repo
    assert kwargs["cursor_line"] == 0
    assert "event_id" in kwargs
    assert kwargs["event_id"].startswith("0:")


def test_moment0_retry_exhausted_writes_ledger_and_falls_back(
    tmp_config: Any,
) -> None:
    """DriftInterpretationError raised → RETRY_EXHAUSTED ledger row + fallback file_doc_audit_issue."""
    cfg = _config_with_moment0_enabled(tmp_config)
    _write_events(Path(cfg.paths.drift_events), [_event(0)])
    _write_mapping(Path(cfg.paths.signal_to_doc_map))

    source = DriftEventSignalSource(cfg)
    signals = source.pending()

    err = DriftInterpretationError("retry exhausted")
    err.attempts = 3

    with mock.patch(
        "doc_audit.signals.drift_event._build_judgment_client"
    ), mock.patch(
        "doc_audit.signals.drift_event.route_drift_event",
        side_effect=err,
    ), mock.patch(
        "doc_audit.signals.drift_event.ledger_append"
    ) as mock_ledger, mock.patch(
        "doc_audit.signals.drift_event.file_doc_audit_issue",
        return_value=(True, "https://example/issues/2"),
    ) as mock_file:
        source.commit(signals[0], "success")

    # Ledger row written with verdict=RETRY_EXHAUSTED
    mock_ledger.assert_called_once()
    entry = mock_ledger.call_args.args[0] if mock_ledger.call_args.args else mock_ledger.call_args.kwargs.get("entry")
    assert entry.verdict == "RETRY_EXHAUSTED"
    assert entry.confidence is None
    assert entry.outcome == "retry_exhausted"
    assert entry.retry_count == 3

    # Fallback file_doc_audit_issue called with extra_body
    mock_file.assert_called_once()
    assert "extra_body" in mock_file.call_args.kwargs
    assert mock_file.call_args.kwargs["extra_body"]  # non-empty diagnostic block


def test_moment0_judgment_client_memoized_per_tick(tmp_config: Any) -> None:
    """JudgmentClient constructed once per adapter even across multiple commits."""
    cfg = _config_with_moment0_enabled(tmp_config)
    _write_events(Path(cfg.paths.drift_events), [_event(0), _event(1)])
    _write_mapping(Path(cfg.paths.signal_to_doc_map))

    source = DriftEventSignalSource(cfg)
    signals = source.pending()
    by_line = {s.payload["line_number"]: s for s in signals}

    with mock.patch(
        "doc_audit.signals.drift_event._build_judgment_client"
    ) as mock_client_cls, mock.patch(
        "doc_audit.signals.drift_event.route_drift_event"
    ):
        source.commit(by_line[0], "success")
        source.commit(by_line[1], "success")

    # Constructed exactly once across both commits.
    assert mock_client_cls.call_count == 1


def test_moment0_disabled_advances_cursor_normally(tmp_config: Any) -> None:
    """Flag disabled → cursor advances exactly as in pre-#362 behavior."""
    _write_events(Path(tmp_config.paths.drift_events), [_event(0), _event(1)])
    _write_mapping(Path(tmp_config.paths.signal_to_doc_map))

    source = DriftEventSignalSource(tmp_config)
    signals = source.pending()

    with mock.patch(
        "doc_audit.signals.drift_event.file_doc_audit_issue",
        return_value=(True, "https://example/issues/3"),
    ):
        source.commit(signals[0], "success")
        source.commit(signals[1], "success")

    cursor = int(Path(tmp_config.paths.drift_cursor).read_text(encoding="utf-8").strip())
    assert cursor == 2


def test_moment0_enabled_advances_cursor_on_success(tmp_config: Any) -> None:
    """Flag enabled + Moment 0 success → cursor advances same as pre-#362."""
    cfg = _config_with_moment0_enabled(tmp_config)
    _write_events(Path(cfg.paths.drift_events), [_event(0)])
    _write_mapping(Path(cfg.paths.signal_to_doc_map))

    source = DriftEventSignalSource(cfg)
    signals = source.pending()

    with mock.patch(
        "doc_audit.signals.drift_event._build_judgment_client"
    ), mock.patch(
        "doc_audit.signals.drift_event.route_drift_event"
    ):
        source.commit(signals[0], "success")

    cursor = int(Path(cfg.paths.drift_cursor).read_text(encoding="utf-8").strip())
    assert cursor == 1


def test_moment0_enabled_advances_cursor_on_retry_exhausted_fallback(
    tmp_config: Any,
) -> None:
    """Cursor advances after RETRY_EXHAUSTED fallback succeeds (FR-006)."""
    cfg = _config_with_moment0_enabled(tmp_config)
    _write_events(Path(cfg.paths.drift_events), [_event(0)])
    _write_mapping(Path(cfg.paths.signal_to_doc_map))

    source = DriftEventSignalSource(cfg)
    signals = source.pending()

    err = DriftInterpretationError("retry exhausted")
    err.attempts = 3

    with mock.patch(
        "doc_audit.signals.drift_event._build_judgment_client"
    ), mock.patch(
        "doc_audit.signals.drift_event.route_drift_event",
        side_effect=err,
    ), mock.patch(
        "doc_audit.signals.drift_event.ledger_append"
    ), mock.patch(
        "doc_audit.signals.drift_event.file_doc_audit_issue",
        return_value=(True, "https://example/issues/4"),
    ):
        source.commit(signals[0], "success")

    cursor = int(Path(cfg.paths.drift_cursor).read_text(encoding="utf-8").strip())
    assert cursor == 1


def test_moment0_idempotent_recommit_does_not_invoke_route(
    tmp_config: Any,
) -> None:
    """Re-committing a line already past cursor must NOT call route_drift_event."""
    cfg = _config_with_moment0_enabled(tmp_config)
    _write_events(Path(cfg.paths.drift_events), [_event(0)])
    _write_mapping(Path(cfg.paths.signal_to_doc_map))
    _write_cursor(Path(cfg.paths.drift_cursor), 5)  # already past line 0

    source = DriftEventSignalSource(cfg)
    signals = source.pending()
    assert signals == []  # cursor=5, file has 1 line → no pending

    # Forge a stale signal payload to exercise the re-commit path.
    from doc_audit.data_model import Signal
    stale = Signal(
        id="drift_event::stale",
        source="drift_event",
        kind="drift_event",
        priority=40,
        payload={"line_number": 0, "raw_event": _event(0)},
        created_utc="2026-05-20T10:00:00Z",
    )

    with mock.patch(
        "doc_audit.signals.drift_event._build_judgment_client"
    ) as mock_client_cls, mock.patch(
        "doc_audit.signals.drift_event.route_drift_event"
    ) as mock_route:
        source.commit(stale, "success")

    mock_client_cls.assert_not_called()
    mock_route.assert_not_called()
