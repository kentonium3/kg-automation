"""Tests for WP03 — health rail + prescan terminal-state hygiene (#746).

Covers:
  * T014 — the ``processed-without-routing-log`` anomaly (silent-loss signature):
    a note whose status IS ``processed`` but whose filename is absent from the
    routing log, scanned across BOTH ``01-Inbox/`` and ``02-Inbox-Processed/``,
    honoring ``ARCHIVE_SCAN_CAP`` and the ``inbox-processing-`` daily-log
    exclusion; empty-disposition (kind=empty) and needs-review notes must NOT
    trip it.
  * T015 — ``needs-review`` is terminal (excluded from ``unprocessed_paths`` and
    from the health rail), and the note-level routing-log dedup is shifted to
    status: an ``unprocessed`` note whose filename is already in the log MUST
    still be listed for reprocessing so finalize can reconcile mid-flight blocks.
  * T016 — the anomaly rides in ``PrescanResult.archive_anomalies`` and appears
    in the emitted JSON.
"""
from __future__ import annotations

import io
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

# conftest.py puts scripts/inbox/ on sys.path and unifies the bare and packaged
# routing_log module identities, so ``import prescan`` / ``import routing_log``
# resolve and monkeypatching ``routing_log.DEFAULT_ROUTING_LOG_PATH`` reaches
# the copy prescan uses.
import routing_log as _routing_log_mod  # noqa: E402
sys.modules.setdefault("scripts.inbox.routing_log", _routing_log_mod)

import prescan  # noqa: E402
from routing_log import RoutingLogWriter  # noqa: E402


NOW = datetime(2026, 5, 12, 12, 0, 0, tzinfo=timezone.utc)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


class _FakeReader:
    """Minimal ``RoutingLogReader`` stand-in exposing note-level ``has()``."""

    def __init__(self, present: set[str] | None = None):
        self._present = set(present or set())

    def has(self, filename: str) -> bool:
        return filename in self._present


def _write_note(path: Path, status: str, body: str = "Body.\n") -> None:
    path.write_text(f"---\nstatus: {status}\n---\n\n{body}", encoding="utf-8")


def _run_prescan_against(
    inbox_dir: Path, processed_dir: Path, routing_log_path: Path, monkeypatch
) -> dict:
    """Run ``run_prescan()`` with paths overridden; return the parsed JSON dict."""
    registry = inbox_dir.parent / "registry.json"
    registry.write_text(
        json.dumps(
            {"paths": {"inbox": str(inbox_dir), "inbox_processed": str(processed_dir)}}
        ),
        encoding="utf-8",
    )
    monkeypatch.setenv("PRESCAN_REGISTRY_PATH", str(registry))
    log_dir = inbox_dir.parent / "logs"
    log_dir.mkdir(parents=True, exist_ok=True)
    monkeypatch.setenv("PRESCAN_LOG_DIR", str(log_dir))
    monkeypatch.setattr("routing_log.DEFAULT_ROUTING_LOG_PATH", routing_log_path)

    captured = io.StringIO()
    monkeypatch.setattr(sys, "stdout", captured)
    rc = prescan.run_prescan()
    sys.stdout = sys.__stdout__
    assert rc == 0, f"run_prescan returned {rc}"
    return json.loads(captured.getvalue().strip().splitlines()[-1])


# ---------------------------------------------------------------------------
# T015 — classify_file: needs-review is its own terminal classification
# ---------------------------------------------------------------------------


class TestNeedsReviewClassification:
    def test_needs_review_is_terminal_classification(self, tmp_path: Path):
        note = tmp_path / "triaged.md"
        _write_note(note, "needs-review")
        info = prescan.classify_file(note, NOW)
        assert info.classification == "needs-review"
        assert info.status_raw == "needs-review"
        # Terminal: not treated as unprocessed and not a parse failure.
        assert info.classification not in (
            "unprocessed",
            "unknown-treated-as-unprocessed",
        )
        assert info.parse_failure_reason is None


# ---------------------------------------------------------------------------
# T014 — scan_processed_without_routing_log (unit, precise)
# ---------------------------------------------------------------------------


class TestSilentLossRailUnit:
    def test_processed_unlogged_note_flagged(self, tmp_path: Path):
        inbox = tmp_path / "inbox"
        processed = tmp_path / "processed"
        inbox.mkdir()
        processed.mkdir()
        _write_note(inbox / "orphan.md", "processed")

        anomalies, warnings = prescan.scan_processed_without_routing_log(
            inbox, processed, NOW, _FakeReader(present=set())
        )
        assert len(anomalies) == 1
        a = anomalies[0]
        assert a.classification == "processed-without-routing-log"
        assert a.status_raw == "processed"
        assert a.warning == (
            "status:processed but no routing-log entry (silent-loss signature #746)"
        )
        assert "orphan.md" in a.path
        assert warnings == []

    def test_scans_both_inbox_and_archive(self, tmp_path: Path):
        inbox = tmp_path / "inbox"
        processed = tmp_path / "processed"
        inbox.mkdir()
        processed.mkdir()
        _write_note(inbox / "in-orphan.md", "processed")
        _write_note(processed / "arch-orphan.md", "processed")

        anomalies, _ = prescan.scan_processed_without_routing_log(
            inbox, processed, NOW, _FakeReader(present=set())
        )
        flagged = {Path(a.path).name for a in anomalies}
        assert flagged == {"in-orphan.md", "arch-orphan.md"}

    def test_logged_processed_note_not_flagged(self, tmp_path: Path):
        inbox = tmp_path / "inbox"
        processed = tmp_path / "processed"
        inbox.mkdir()
        processed.mkdir()
        _write_note(inbox / "routed.md", "processed")

        anomalies, _ = prescan.scan_processed_without_routing_log(
            inbox, processed, NOW, _FakeReader(present={"routed.md"})
        )
        assert anomalies == []

    def test_empty_disposition_note_not_flagged(self, tmp_path: Path):
        """An ``empty`` note is ``status:processed`` with a kind=empty log entry
        (its filename is present) → must NOT trip the rail."""
        inbox = tmp_path / "inbox"
        processed = tmp_path / "processed"
        inbox.mkdir()
        processed.mkdir()
        _write_note(inbox / "empty-note.md", "processed", body="")

        anomalies, _ = prescan.scan_processed_without_routing_log(
            inbox, processed, NOW, _FakeReader(present={"empty-note.md"})
        )
        assert anomalies == []

    def test_needs_review_note_not_flagged(self, tmp_path: Path):
        inbox = tmp_path / "inbox"
        processed = tmp_path / "processed"
        inbox.mkdir()
        processed.mkdir()
        _write_note(inbox / "parked.md", "needs-review")

        anomalies, _ = prescan.scan_processed_without_routing_log(
            inbox, processed, NOW, _FakeReader(present=set())
        )
        assert anomalies == []

    def test_unprocessed_note_not_flagged(self, tmp_path: Path):
        inbox = tmp_path / "inbox"
        processed = tmp_path / "processed"
        inbox.mkdir()
        processed.mkdir()
        _write_note(inbox / "todo.md", "unprocessed")

        anomalies, _ = prescan.scan_processed_without_routing_log(
            inbox, processed, NOW, _FakeReader(present=set())
        )
        assert anomalies == []

    def test_daily_log_files_excluded(self, tmp_path: Path):
        """``inbox-processing-*.md`` pipeline logs must never be scanned."""
        inbox = tmp_path / "inbox"
        processed = tmp_path / "processed"
        inbox.mkdir()
        processed.mkdir()
        # A daily-log file that would look like a processed-unlogged note.
        _write_note(processed / "inbox-processing-2026-05-12.md", "processed")

        anomalies, _ = prescan.scan_processed_without_routing_log(
            inbox, processed, NOW, _FakeReader(present=set())
        )
        assert anomalies == []

    def test_cap_honored(self, tmp_path: Path, monkeypatch):
        inbox = tmp_path / "inbox"
        processed = tmp_path / "processed"
        inbox.mkdir()
        processed.mkdir()
        for i in range(5):
            _write_note(inbox / f"orphan-{i}.md", "processed")
        monkeypatch.setattr(prescan, "ARCHIVE_SCAN_CAP", 2)

        anomalies, warnings = prescan.scan_processed_without_routing_log(
            inbox, processed, NOW, _FakeReader(present=set())
        )
        # Scan is bounded by the cap; a cap-applied warning is surfaced.
        assert len(anomalies) == 2
        assert any("cap_applied" in w for w in warnings)

    def test_missing_dirs_are_safe(self, tmp_path: Path):
        """A missing inbox or processed dir yields no anomalies (no crash)."""
        anomalies, warnings = prescan.scan_processed_without_routing_log(
            tmp_path / "nope-in", tmp_path / "nope-out", NOW, _FakeReader()
        )
        assert anomalies == []
        assert warnings == []


# ---------------------------------------------------------------------------
# T014 + T016 — end-to-end via run_prescan (JSON surface)
# ---------------------------------------------------------------------------


class TestSilentLossRailIntegration:
    def test_processed_unlogged_note_surfaced_in_json(
        self, tmp_path: Path, monkeypatch
    ):
        inbox = tmp_path / "inbox"
        processed = tmp_path / "processed"
        inbox.mkdir()
        processed.mkdir()
        _write_note(inbox / "orphan.md", "processed")
        log = tmp_path / "routing.jsonl"  # empty

        result = _run_prescan_against(inbox, processed, log, monkeypatch)

        rail_hits = [
            a
            for a in result["archive_anomalies"]
            if a["classification"] == "processed-without-routing-log"
        ]
        assert len(rail_hits) == 1
        assert "orphan.md" in rail_hits[0]["path"]
        assert "silent-loss signature #746" in rail_hits[0]["warning"]

    def test_correctly_finalized_corpus_has_zero_anomalies(
        self, tmp_path: Path, monkeypatch
    ):
        inbox = tmp_path / "inbox"
        processed = tmp_path / "processed"
        inbox.mkdir()
        processed.mkdir()
        # A routed processed note (recent → stays in inbox).
        _write_note(inbox / "routed.md", "processed")
        # An empty-disposition processed note with a kind=empty log entry.
        _write_note(inbox / "empty-note.md", "processed", body="")
        # A correctly processed+logged note already in the archive.
        _write_note(processed / "archived.md", "processed")

        log = tmp_path / "routing.jsonl"
        writer = RoutingLogWriter(log)
        writer.append(filename="routed.md", issue_number=1)
        writer.append(filename="empty-note.md", kind="empty", destination="")
        writer.append(filename="archived.md", issue_number=2)

        result = _run_prescan_against(inbox, processed, log, monkeypatch)

        assert result["archive_anomalies"] == []

    def test_needs_review_terminal_not_unprocessed_not_anomaly(
        self, tmp_path: Path, monkeypatch
    ):
        inbox = tmp_path / "inbox"
        processed = tmp_path / "processed"
        inbox.mkdir()
        processed.mkdir()
        _write_note(inbox / "parked.md", "needs-review")
        log = tmp_path / "routing.jsonl"  # empty

        result = _run_prescan_against(inbox, processed, log, monkeypatch)

        # FR-008: needs-review is terminal — never handed back for reprocessing.
        assert all("parked.md" not in p for p in result["unprocessed_paths"])
        # And it is not a health-rail anomaly (not `processed`).
        assert result["archive_anomalies"] == []

    def test_daily_log_exclusion_end_to_end(self, tmp_path: Path, monkeypatch):
        inbox = tmp_path / "inbox"
        processed = tmp_path / "processed"
        inbox.mkdir()
        processed.mkdir()
        # Daily-log file in the archive that superficially looks processed.
        _write_note(processed / "inbox-processing-2026-05-12.md", "processed")
        log = tmp_path / "routing.jsonl"  # empty

        result = _run_prescan_against(inbox, processed, log, monkeypatch)

        assert result["archive_anomalies"] == []


# ---------------------------------------------------------------------------
# T015 — dedup shift: mid-flight unprocessed note still reprocesses
# ---------------------------------------------------------------------------


class TestDedupShift:
    def test_unprocessed_note_with_log_entry_still_listed(
        self, tmp_path: Path, monkeypatch
    ):
        """An ``unprocessed`` note whose filename is ALREADY in the routing log
        (e.g. one block logged on a prior failed tick) MUST still be handed to
        the agent so finalize can reconcile the remaining blocks. The old
        note-level filename dedup would have stranded it — the D9 shift removes
        that filter."""
        inbox = tmp_path / "inbox"
        processed = tmp_path / "processed"
        inbox.mkdir()
        processed.mkdir()
        _write_note(inbox / "mid-flight.md", "unprocessed")

        log = tmp_path / "routing.jsonl"
        writer = RoutingLogWriter(log)
        # A prior partial route logged the filename (note-level / block 0).
        writer.append(filename="mid-flight.md", issue_number=7, block_index=0)

        result = _run_prescan_against(inbox, processed, log, monkeypatch)

        assert any("mid-flight.md" in p for p in result["unprocessed_paths"])
        # The note-level dedup filter is gone → nothing is skipped by filename.
        assert result["dedup_skipped"] == []
