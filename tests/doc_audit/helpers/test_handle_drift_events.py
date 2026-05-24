"""Unit tests for the importable surfaces of ``handle_drift_events.py``.

Per mission #343 WP01 (T005): lock in the new import surface so future
refactors don't regress it. The helper was lifted from
``scripts/openclaw/agents/felix-doc-auditor/`` to
``scripts/doc_audit/helpers/`` and now exposes ``process_events`` as
the library entry point alongside the existing module-level building
blocks (``find_mapping``, ``write_cursor_atomic``, etc.).

Mission #362 (drift-event-auto-resolution-01KS8J32, WP04) extends
``process_events`` with Moment 0 LLM judgment. The pre-#362 test cases
below remain unchanged — they verify the C-002 backward-compatibility
contract. New tests cover the six verdict paths
(PROPOSED_EDIT × {Tier A, Tier B, Judgment}, JUDGMENT_REQUIRED,
NO_CHANGE_NEEDED, RETRY_EXHAUSTED), cursor advancement on every path
(including RETRY_EXHAUSTED to prevent infinite loops), the
``--reset-cursor`` CLI flag, and the byte-identical pre-#362 fallback
when ``enabled = false``.

Tests are import-driven only — no CLI subprocesses, no real network or
``gh`` calls. ``file_doc_audit_issue`` is exercised via ``--dry-run``
shape (``process_events`` propagates ``dry_run=True``) so the
subprocess call is never made.
"""
from __future__ import annotations

import json
import os
import stat
from pathlib import Path
from unittest import mock

import pytest

import subprocess

from doc_audit.helpers.handle_drift_events import (
    Mapping,
    ProcessResult,
    RoutingOutcome,
    append_unmapped,
    decode_diff,
    file_doc_audit_issue,
    find_mapping,
    load_mappings,
    main,
    process_events,
    read_cursor,
    write_cursor_atomic,
)

FIXTURES_DIR = Path(__file__).resolve().parent / "fixtures"


def _load_mappings_fixture() -> list[Mapping]:
    return load_mappings(FIXTURES_DIR / "signal_to_doc_map_sample.json")


# ---------------------------------------------------------------------------
# Mapping load + lookup
# ---------------------------------------------------------------------------


def test_load_mappings_returns_dataclasses():
    mappings = _load_mappings_fixture()
    assert len(mappings) == 2
    assert all(isinstance(m, Mapping) for m in mappings)
    assert mappings[0].id == "openclaw-cron-drift"
    assert mappings[0].match == {
        "source": "audit.sh",
        "baseline_name": "openclaw-cron.txt",
    }


def test_find_mapping_matches_by_subset_of_event_keys():
    mappings = _load_mappings_fixture()
    event = {
        "source": "audit.sh",
        "baseline_name": "openclaw-cron.txt",
        "timestamp": "2026-05-20T10:00:00Z",
        "diff": "anything",
    }
    matched = find_mapping(event, mappings)
    assert matched is not None
    assert matched.id == "openclaw-cron-drift"


def test_find_mapping_returns_none_when_no_subset_matches():
    mappings = _load_mappings_fixture()
    event = {"source": "audit.sh", "baseline_name": "nonexistent.txt"}
    assert find_mapping(event, mappings) is None


# ---------------------------------------------------------------------------
# decode_diff
# ---------------------------------------------------------------------------


def test_decode_diff_returns_plain_diff_when_present():
    event = {"diff": "diff content"}
    assert decode_diff(event) == "diff content"


def test_decode_diff_decodes_base64_when_provided():
    # base64 of "diff content"
    event = {"diff_b64": "ZGlmZiBjb250ZW50"}
    assert decode_diff(event) == "diff content"


def test_decode_diff_returns_empty_when_neither_present():
    assert decode_diff({}) == ""


# ---------------------------------------------------------------------------
# Cursor atomic write
# ---------------------------------------------------------------------------


def test_write_cursor_atomic_creates_and_reads_back(tmp_path: Path):
    cursor_path = tmp_path / "cursor"
    write_cursor_atomic(cursor_path, 42)
    assert cursor_path.read_text() == "42"
    assert read_cursor(cursor_path) == 42


def test_write_cursor_atomic_overwrites_existing(tmp_path: Path):
    cursor_path = tmp_path / "cursor"
    cursor_path.write_text("7")
    write_cursor_atomic(cursor_path, 99)
    assert cursor_path.read_text() == "99"


def test_read_cursor_returns_zero_when_missing(tmp_path: Path):
    assert read_cursor(tmp_path / "does-not-exist") == 0


def test_read_cursor_returns_zero_when_malformed(tmp_path: Path):
    p = tmp_path / "cursor"
    p.write_text("not-an-int\n")
    assert read_cursor(p) == 0


def test_write_cursor_atomic_no_stray_tmp_files(tmp_path: Path):
    cursor_path = tmp_path / "cursor"
    write_cursor_atomic(cursor_path, 5)
    leftover_tmps = [p for p in tmp_path.iterdir() if p.name.endswith(".tmp") or ".tmp." in p.name]
    assert leftover_tmps == []


# ---------------------------------------------------------------------------
# append_unmapped
# ---------------------------------------------------------------------------


def test_append_unmapped_creates_parent_dir_and_appends(tmp_path: Path):
    unmapped = tmp_path / "nested" / "unmapped.jsonl"
    event1 = {"source": "audit.sh", "baseline_name": "a.txt"}
    event2 = {"source": "audit.sh", "baseline_name": "b.txt"}
    append_unmapped(unmapped, event1)
    append_unmapped(unmapped, event2)
    lines = unmapped.read_text().strip().splitlines()
    assert json.loads(lines[0]) == event1
    assert json.loads(lines[1]) == event2


# ---------------------------------------------------------------------------
# process_events end-to-end (dry-run + mocked gh) — pre-#362 path
# ---------------------------------------------------------------------------


def _write_fixture_events(target: Path) -> None:
    source = FIXTURES_DIR / "drift_events_sample.jsonl"
    target.write_text(source.read_text(encoding="utf-8"), encoding="utf-8")


def test_process_events_no_events_file(tmp_path: Path):
    result = process_events(
        events_path=tmp_path / "missing.jsonl",
        cursor_path=tmp_path / "cursor",
        mapping_path=FIXTURES_DIR / "signal_to_doc_map_sample.json",
        unmapped_path=tmp_path / "unmapped.jsonl",
        dry_run=True,
    )
    assert isinstance(result, ProcessResult)
    assert result.processed == 0
    assert result.exit_code == 0


def test_process_events_missing_mapping_returns_exit_code_2(tmp_path: Path):
    events = tmp_path / "events.jsonl"
    _write_fixture_events(events)
    result = process_events(
        events_path=events,
        cursor_path=tmp_path / "cursor",
        mapping_path=tmp_path / "missing-mapping.json",
        unmapped_path=tmp_path / "unmapped.jsonl",
        dry_run=True,
    )
    assert result.exit_code == 2
    assert result.processed == 0


def test_process_events_dry_run_mixed_matched_and_unmapped(tmp_path: Path):
    events = tmp_path / "events.jsonl"
    _write_fixture_events(events)
    cursor = tmp_path / "cursor"
    unmapped = tmp_path / "unmapped.jsonl"
    result = process_events(
        events_path=events,
        cursor_path=cursor,
        mapping_path=FIXTURES_DIR / "signal_to_doc_map_sample.json",
        unmapped_path=unmapped,
        dry_run=True,
    )
    assert result.exit_code == 0
    assert result.processed == 3
    # Two events match (openclaw-cron + listening-ports); one is unmapped.
    assert result.matched_filed == 2
    assert result.unmapped == 1
    assert result.errors == 0
    # Cursor is NOT written in dry-run mode
    assert not cursor.exists()
    # Unmapped log should contain exactly one event
    unmapped_lines = unmapped.read_text().strip().splitlines()
    assert len(unmapped_lines) == 1
    assert json.loads(unmapped_lines[0])["baseline_name"] == "unknown-baseline.txt"


def test_process_events_real_run_advances_cursor_atomically(tmp_path: Path, monkeypatch):
    events = tmp_path / "events.jsonl"
    _write_fixture_events(events)
    cursor = tmp_path / "cursor"
    unmapped = tmp_path / "unmapped.jsonl"

    # Mock subprocess.run for gh issue create so no network call happens.
    fake_run = mock.MagicMock(
        return_value=mock.MagicMock(
            returncode=0,
            stdout="https://github.com/kentonium3/kg-automation/issues/12345\n",
            stderr="",
        )
    )
    monkeypatch.setattr(
        "doc_audit.helpers.handle_drift_events.subprocess.run", fake_run
    )

    result = process_events(
        events_path=events,
        cursor_path=cursor,
        mapping_path=FIXTURES_DIR / "signal_to_doc_map_sample.json",
        unmapped_path=unmapped,
        dry_run=False,
    )

    assert result.exit_code == 0
    assert result.processed == 3
    assert result.matched_filed == 2
    assert result.unmapped == 1
    # Cursor is written and reflects new position
    assert cursor.exists()
    assert int(cursor.read_text()) == 3
    assert result.new_cursor == 3
    # gh issue create was invoked for the matched events
    assert fake_run.call_count == 2


def test_process_events_idempotent_when_cursor_at_end(tmp_path: Path):
    events = tmp_path / "events.jsonl"
    _write_fixture_events(events)
    cursor = tmp_path / "cursor"
    cursor.write_text("3")  # already past the fixture's 3 events
    unmapped = tmp_path / "unmapped.jsonl"

    result = process_events(
        events_path=events,
        cursor_path=cursor,
        mapping_path=FIXTURES_DIR / "signal_to_doc_map_sample.json",
        unmapped_path=unmapped,
        dry_run=True,
    )
    assert result.exit_code == 0
    assert result.processed == 0
    assert result.new_cursor == 3


# ---------------------------------------------------------------------------
# file_doc_audit_issue (dry-run + mocked gh)
# ---------------------------------------------------------------------------


def test_file_doc_audit_issue_dry_run_does_not_invoke_subprocess(monkeypatch):
    mappings = _load_mappings_fixture()
    event = {"source": "audit.sh", "baseline_name": "openclaw-cron.txt", "timestamp": "T"}
    fake_run = mock.MagicMock()
    monkeypatch.setattr(
        "doc_audit.helpers.handle_drift_events.subprocess.run", fake_run
    )
    ok, output = file_doc_audit_issue(event, mappings[0], "x/y", dry_run=True)
    assert ok is True
    assert "[dry-run]" in output
    assert fake_run.call_count == 0


def test_file_doc_audit_issue_real_run_uses_subprocess(monkeypatch):
    mappings = _load_mappings_fixture()
    event = {"source": "audit.sh", "baseline_name": "openclaw-cron.txt", "timestamp": "T"}
    fake_run = mock.MagicMock(
        return_value=mock.MagicMock(
            returncode=0,
            stdout="https://github.com/kentonium3/kg-automation/issues/42\n",
            stderr="",
        )
    )
    monkeypatch.setattr(
        "doc_audit.helpers.handle_drift_events.subprocess.run", fake_run
    )
    ok, output = file_doc_audit_issue(event, mappings[0], "x/y", dry_run=False)
    assert ok is True
    assert "issues/42" in output
    assert fake_run.call_count == 1


# ---------------------------------------------------------------------------
# Cycle 3 additions — file_doc_audit_issue failure legs (lines 227-230)
# ---------------------------------------------------------------------------


def test_file_doc_audit_issue_returns_failure_on_called_process_error(monkeypatch):
    """gh exit non-zero → (False, "gh issue create failed: ...")."""
    mappings = _load_mappings_fixture()
    event = {"source": "audit.sh", "baseline_name": "openclaw-cron.txt", "timestamp": "T"}
    err = subprocess.CalledProcessError(1, ["gh"], stderr="boom from gh")
    fake_run = mock.MagicMock(side_effect=err)
    monkeypatch.setattr(
        "doc_audit.helpers.handle_drift_events.subprocess.run", fake_run
    )
    ok, output = file_doc_audit_issue(event, mappings[0], "x/y", dry_run=False)
    assert ok is False
    assert "gh issue create failed" in output
    assert "boom from gh" in output


def test_file_doc_audit_issue_returns_failure_on_timeout(monkeypatch):
    """gh exceeds 60s → (False, "gh issue create timed out after 60s")."""
    mappings = _load_mappings_fixture()
    event = {"source": "audit.sh", "baseline_name": "openclaw-cron.txt", "timestamp": "T"}
    err = subprocess.TimeoutExpired(cmd=["gh"], timeout=60)
    fake_run = mock.MagicMock(side_effect=err)
    monkeypatch.setattr(
        "doc_audit.helpers.handle_drift_events.subprocess.run", fake_run
    )
    ok, output = file_doc_audit_issue(event, mappings[0], "x/y", dry_run=False)
    assert ok is False
    assert "timed out" in output


# ---------------------------------------------------------------------------
# decode_diff — base64 failure branch (lines 147-148)
# ---------------------------------------------------------------------------


def test_decode_diff_returns_placeholder_on_bad_base64():
    event = {"diff_b64": "!!! not valid base64 !!!"}
    out = decode_diff(event)
    # The except branch returns a literal placeholder string.
    assert out == "<diff decode failed>"


# ---------------------------------------------------------------------------
# write_cursor_atomic — exception cleanup (lines 126-131)
# ---------------------------------------------------------------------------


def test_write_cursor_atomic_cleans_up_temp_file_on_failure(tmp_path: Path, monkeypatch):
    cursor_path = tmp_path / "cursor"

    def boom(*args, **kwargs):
        raise OSError("simulated fdopen failure")

    monkeypatch.setattr(
        "doc_audit.helpers.handle_drift_events.os.fdopen", boom
    )
    with pytest.raises(OSError):
        write_cursor_atomic(cursor_path, 1)
    # No leftover .tmp files
    leftovers = [p for p in tmp_path.iterdir() if ".tmp" in p.name]
    assert leftovers == []


# ---------------------------------------------------------------------------
# process_events — additional branches
# ---------------------------------------------------------------------------


def test_process_events_skips_empty_lines(tmp_path: Path):
    """Empty/whitespace-only lines are skipped without failing."""
    events = tmp_path / "events.jsonl"
    events.write_text("\n\n  \n", encoding="utf-8")
    cursor = tmp_path / "cursor"
    result = process_events(
        events_path=events,
        cursor_path=cursor,
        mapping_path=FIXTURES_DIR / "signal_to_doc_map_sample.json",
        unmapped_path=tmp_path / "unmapped.jsonl",
        dry_run=True,
    )
    assert result.exit_code == 0
    # Empty lines count as processed (cursor advances over them) but
    # contribute zero to matched/unmapped/errors.
    assert result.matched_filed == 0
    assert result.unmapped == 0
    assert result.errors == 0


def test_process_events_skips_malformed_json_lines(tmp_path: Path):
    """Malformed JSON lines emit WARN and are skipped without error."""
    events = tmp_path / "events.jsonl"
    events.write_text("not-json-here\n{}\n", encoding="utf-8")
    cursor = tmp_path / "cursor"
    result = process_events(
        events_path=events,
        cursor_path=cursor,
        mapping_path=FIXTURES_DIR / "signal_to_doc_map_sample.json",
        unmapped_path=tmp_path / "unmapped.jsonl",
        dry_run=True,
    )
    assert result.exit_code == 0
    # 2 lines processed; both effectively no-ops in terms of matched/unmapped.
    # The `{}` line has no matching mapping → goes to unmapped.
    assert result.processed == 2
    assert result.matched_filed == 0
    assert result.unmapped == 1


def test_process_events_warns_when_new_events_exceed_limit(tmp_path: Path, capsys):
    """More new lines than --limit → warns and processes the first `limit` only."""
    events = tmp_path / "events.jsonl"
    fixture_lines = (FIXTURES_DIR / "drift_events_sample.jsonl").read_text(
        encoding="utf-8"
    )
    # Repeat the fixture lines a few times so there are clearly more than limit.
    events.write_text(fixture_lines * 3, encoding="utf-8")
    cursor = tmp_path / "cursor"
    result = process_events(
        events_path=events,
        cursor_path=cursor,
        mapping_path=FIXTURES_DIR / "signal_to_doc_map_sample.json",
        unmapped_path=tmp_path / "unmapped.jsonl",
        dry_run=True,
        limit=2,
    )
    # Only `limit` events processed.
    assert result.processed == 2
    captured = capsys.readouterr()
    assert "exceeds --limit" in captured.err


def test_process_events_breaks_on_file_issue_failure_so_cursor_stalls(
    tmp_path: Path, monkeypatch
):
    """If gh issue create fails on a matched event, processing breaks and cursor stops."""
    events = tmp_path / "events.jsonl"
    _write_fixture_events(events)
    cursor = tmp_path / "cursor"
    unmapped = tmp_path / "unmapped.jsonl"

    # First subprocess call fails — simulates gh issue create failure.
    fake_run = mock.MagicMock(
        side_effect=subprocess.CalledProcessError(1, ["gh"], stderr="boom")
    )
    monkeypatch.setattr(
        "doc_audit.helpers.handle_drift_events.subprocess.run", fake_run
    )

    result = process_events(
        events_path=events,
        cursor_path=cursor,
        mapping_path=FIXTURES_DIR / "signal_to_doc_map_sample.json",
        unmapped_path=unmapped,
        dry_run=False,
    )

    assert result.exit_code == 1
    assert result.errors == 1
    # Loop broke after the first matched event errored — second event was not
    # processed at all (processed counter NOT incremented after `break`).
    assert result.processed == 0
    # Cursor was nonetheless written by the SUMMARY branch.
    assert cursor.exists()
    # new_cursor reflects whatever the function recorded (cursor + processed).
    assert result.new_cursor == 0


# ---------------------------------------------------------------------------
# main() CLI wrapper (lines 389-431) — pre-#362 surface
# ---------------------------------------------------------------------------


def test_main_dry_run_exit_code_zero(tmp_path: Path, monkeypatch):
    events = tmp_path / "events.jsonl"
    _write_fixture_events(events)
    cursor = tmp_path / "cursor"
    unmapped = tmp_path / "unmapped.jsonl"

    # Force pre-#362 mode so we exercise the legacy CLI surface verbatim.
    # Patch doc_audit.config.load_config to raise FileNotFoundError; main()
    # catches that and falls back to pre-#362 behavior.
    def _no_config(*a, **kw):
        raise FileNotFoundError("no config in test env")

    monkeypatch.setattr("doc_audit.config.load_config", _no_config)

    rc = main(
        [
            "--events", str(events),
            "--cursor", str(cursor),
            "--mapping", str(FIXTURES_DIR / "signal_to_doc_map_sample.json"),
            "--unmapped", str(unmapped),
            "--dry-run",
        ]
    )
    assert rc == 0


def test_main_returns_exit_code_2_when_mapping_missing(tmp_path: Path):
    events = tmp_path / "events.jsonl"
    _write_fixture_events(events)
    rc = main(
        [
            "--events", str(events),
            "--cursor", str(tmp_path / "cursor"),
            "--mapping", str(tmp_path / "missing.json"),
            "--unmapped", str(tmp_path / "unmapped.jsonl"),
            "--dry-run",
        ]
    )
    assert rc == 2


# ---------------------------------------------------------------------------
# Mission #362 (WP04) — Moment 0 integration tests
# ---------------------------------------------------------------------------


class _StubDriftIntCfg:
    """Minimal stand-in for ``DriftInterpretationConfig``.

    Tests build a stub rather than importing the real dataclass so the
    config module's defaults / validation don't entangle the tests.
    """

    def __init__(
        self,
        *,
        enabled: bool,
        ledger_path: Path,
        model: str = "claude-haiku-4-5-test",
        api_key_path: str = "/tmp/fake-key",
        timeout_seconds: int = 30,
        confidence_threshold: float = 0.80,
    ) -> None:
        self.enabled = enabled
        self.ledger_path = str(ledger_path)
        self.model = model
        self.api_key_path = api_key_path
        self.timeout_seconds = timeout_seconds
        self.confidence_threshold = confidence_threshold


class _StubConfig:
    def __init__(self, drift_interpretation: _StubDriftIntCfg) -> None:
        self.drift_interpretation = drift_interpretation


def _make_event_file(
    tmp_path: Path,
    *,
    events: list[dict] | None = None,
) -> Path:
    """Write a one-event drift-events.jsonl file mapping the
    ``openclaw-cron-drift`` fixture so the loop finds a mapping.
    """
    events = events or [
        {
            "source": "audit.sh",
            "baseline_name": "openclaw-cron.txt",
            "timestamp": "2026-05-20T10:00:00Z",
            "diff": "@@ -1,1 +1,1 @@\n-old line\n+new line\n",
        }
    ]
    events_path = tmp_path / "events.jsonl"
    events_path.write_text(
        "\n".join(json.dumps(e) for e in events) + "\n", encoding="utf-8"
    )
    return events_path


def _stub_verdict(verdict_value: str, **kwargs):
    """Build a fake :class:`DriftVerdict` with the requested shape."""
    from doc_audit.judgment.drift_interpretation import DriftVerdict

    base = {
        "verdict": verdict_value,
        "confidence": 0.92,
        "rationale": "stub-rationale",
    }
    if verdict_value == "PROPOSED_EDIT":
        base["proposed_edit"] = kwargs.pop(
            "proposed_edit",
            {
                "doc_path": "docs/design/architecture/data/service-inventory.json",
                "current_value": "old line",
                "proposed_value": "new line",
            },
        )
    if verdict_value == "JUDGMENT_REQUIRED":
        base["question"] = kwargs.pop(
            "question", "Was this drift intentional?"
        )
    base.update(kwargs)
    return DriftVerdict(**base)


def _flag_disabled_config(tmp_path: Path) -> _StubConfig:
    return _StubConfig(
        _StubDriftIntCfg(
            enabled=False,
            ledger_path=tmp_path / "ledger.jsonl",
        )
    )


def _flag_enabled_config(tmp_path: Path) -> _StubConfig:
    return _StubConfig(
        _StubDriftIntCfg(
            enabled=True,
            ledger_path=tmp_path / "ledger.jsonl",
        )
    )


def test_process_events_flag_disabled_runs_pre_362_path(
    tmp_path: Path, monkeypatch
):
    """``enabled = false`` MUST file pre-#362 ``[doc-audit]`` issues only.

    Verifies the C-002 backward-compat invariant: ``file_doc_audit_issue``
    runs verbatim and Moment 0 is NEVER invoked.
    """
    events_path = _make_event_file(tmp_path)
    cursor = tmp_path / "cursor"

    fake_gh = mock.MagicMock(
        return_value=mock.MagicMock(
            returncode=0,
            stdout="https://github.com/kentonium3/kg-automation/issues/42\n",
            stderr="",
        )
    )
    # Pre-#362 path: subprocess is called from handle_drift_events
    # (file_doc_audit_issue lives there). After the
    # moment0-integration-fix refactor, drift_moment0 has its own
    # subprocess import for Moment 0 paths; the flag-disabled branch
    # never reaches it but we patch defensively.
    monkeypatch.setattr(
        "doc_audit.helpers.handle_drift_events.subprocess.run", fake_gh
    )

    # Sentinel: if Moment 0 ran, this would raise.
    def _explode(*args, **kwargs):
        raise AssertionError("Moment 0 must NOT be invoked when flag is off")

    monkeypatch.setattr(
        "doc_audit.judgment.drift_interpretation.interpret", _explode
    )

    result = process_events(
        events_path=events_path,
        cursor_path=cursor,
        mapping_path=FIXTURES_DIR / "signal_to_doc_map_sample.json",
        unmapped_path=tmp_path / "unmapped.jsonl",
        config=_flag_disabled_config(tmp_path),
        dry_run=False,
    )

    assert result.exit_code == 0
    assert result.matched_filed == 1
    assert result.proposed_edit_routed == 0
    assert result.judgment_required_filed == 0
    assert result.no_change_needed_closed == 0
    assert result.retry_exhausted == 0
    assert int(cursor.read_text()) == 1


def test_process_events_no_change_needed_writes_ledger_only(
    tmp_path: Path, monkeypatch
):
    """NO_CHANGE_NEEDED → no GitHub artifact + one ledger row, cursor advances."""
    events_path = _make_event_file(tmp_path)
    cursor = tmp_path / "cursor"
    ledger_path = tmp_path / "ledger.jsonl"

    # Stub Moment 0: deterministic NO_CHANGE_NEEDED verdict.
    monkeypatch.setattr(
        "doc_audit.judgment.drift_interpretation.interpret",
        lambda *args, **kwargs: _stub_verdict("NO_CHANGE_NEEDED"),
    )
    # subprocess.run is the gh chokepoint — it must NOT be invoked.
    # Patch both modules because gh/git calls now route through
    # drift_moment0 (post moment0-integration-fix refactor).
    forbidden_gh = mock.MagicMock(
        side_effect=AssertionError("NO_CHANGE_NEEDED must not invoke gh")
    )
    monkeypatch.setattr(
        "doc_audit.helpers.handle_drift_events.subprocess.run", forbidden_gh
    )
    monkeypatch.setattr(
        "doc_audit.routing.drift_moment0.subprocess.run", forbidden_gh
    )

    config = _flag_enabled_config(tmp_path)
    config.drift_interpretation.ledger_path = str(ledger_path)

    result = process_events(
        events_path=events_path,
        cursor_path=cursor,
        mapping_path=FIXTURES_DIR / "signal_to_doc_map_sample.json",
        unmapped_path=tmp_path / "unmapped.jsonl",
        config=config,
        judgment_client=object(),
        repo_root=tmp_path,
        dry_run=False,
    )

    assert result.exit_code == 0
    assert result.no_change_needed_closed == 1
    assert result.matched_filed == 0
    assert int(cursor.read_text()) == 1
    ledger_rows = ledger_path.read_text(encoding="utf-8").strip().splitlines()
    assert len(ledger_rows) == 1
    row = json.loads(ledger_rows[0])
    assert row["verdict"] == "NO_CHANGE_NEEDED"
    assert row["outcome"] == "auto_closed"
    assert row["tier_classification_outcome"] is None
    assert row["github_issue_number"] is None
    assert row["confidence"] == 0.92


def test_process_events_judgment_required_files_issue(
    tmp_path: Path, monkeypatch
):
    """JUDGMENT_REQUIRED → file ``[doc-audit]`` issue + ledger row."""
    events_path = _make_event_file(tmp_path)
    cursor = tmp_path / "cursor"
    ledger_path = tmp_path / "ledger.jsonl"

    captured_question: dict[str, str] = {}

    def fake_subprocess_run(cmd, *args, **kwargs):
        # Capture the gh body so we can assert the question made it in.
        if "--body" in cmd:
            body_idx = cmd.index("--body") + 1
            captured_question["body"] = cmd[body_idx]
        return mock.MagicMock(
            returncode=0,
            stdout="https://github.com/kentonium3/kg-automation/issues/777\n",
            stderr="",
        )

    # gh calls now route through drift_moment0; patch both for safety.
    monkeypatch.setattr(
        "doc_audit.helpers.handle_drift_events.subprocess.run",
        fake_subprocess_run,
    )
    monkeypatch.setattr(
        "doc_audit.routing.drift_moment0.subprocess.run",
        fake_subprocess_run,
    )

    monkeypatch.setattr(
        "doc_audit.judgment.drift_interpretation.interpret",
        lambda *args, **kwargs: _stub_verdict(
            "JUDGMENT_REQUIRED",
            confidence=0.55,
            question="Is the new openclaw-cron schedule the right answer here?",
        ),
    )

    config = _flag_enabled_config(tmp_path)
    config.drift_interpretation.ledger_path = str(ledger_path)

    result = process_events(
        events_path=events_path,
        cursor_path=cursor,
        mapping_path=FIXTURES_DIR / "signal_to_doc_map_sample.json",
        unmapped_path=tmp_path / "unmapped.jsonl",
        config=config,
        judgment_client=object(),
        repo_root=tmp_path,
        dry_run=False,
    )

    assert result.exit_code == 0
    assert result.judgment_required_filed == 1
    row = json.loads(
        ledger_path.read_text(encoding="utf-8").strip().splitlines()[0]
    )
    assert row["verdict"] == "JUDGMENT_REQUIRED"
    assert row["outcome"] == "issue_filed"
    assert row["github_issue_number"] == 777
    assert "Is the new openclaw-cron schedule" in captured_question.get("body", "")
    assert int(cursor.read_text()) == 1


def test_process_events_proposed_edit_tier_a_auto_commits(
    tmp_path: Path, monkeypatch
):
    """PROPOSED_EDIT + tier_classification → TIER_A → auto-commit ledger row."""
    events_path = _make_event_file(tmp_path)
    cursor = tmp_path / "cursor"
    ledger_path = tmp_path / "ledger.jsonl"

    # Build a fake repo root with the doc target file so the Tier A
    # applier has something to bump.
    fake_repo = tmp_path / "repo"
    target_rel = "docs/design/architecture/data/service-inventory.json"
    target_abs = fake_repo / target_rel
    target_abs.parent.mkdir(parents=True, exist_ok=True)
    target_abs.write_text(
        "before old line after\nunrelated\n", encoding="utf-8"
    )

    monkeypatch.setattr(
        "doc_audit.judgment.drift_interpretation.interpret",
        lambda *args, **kwargs: _stub_verdict("PROPOSED_EDIT"),
    )

    from doc_audit.data_model import EditTier

    def fake_classify(client, proposed_edit, **kwargs):
        return EditTier.TIER_A, "tier_a rationale", None

    monkeypatch.setattr(
        "doc_audit.judgment.tier_classification.classify", fake_classify
    )

    # Mock git invocations (add / commit) — return success without
    # touching git state for real. Post-refactor, the git calls happen
    # from drift_moment0; patch both modules so we catch any path.
    def fake_subprocess_run(cmd, *args, **kwargs):
        return mock.MagicMock(returncode=0, stdout="", stderr="")

    monkeypatch.setattr(
        "doc_audit.helpers.handle_drift_events.subprocess.run",
        fake_subprocess_run,
    )
    monkeypatch.setattr(
        "doc_audit.routing.drift_moment0.subprocess.run",
        fake_subprocess_run,
    )

    config = _flag_enabled_config(tmp_path)
    config.drift_interpretation.ledger_path = str(ledger_path)

    result = process_events(
        events_path=events_path,
        cursor_path=cursor,
        mapping_path=FIXTURES_DIR / "signal_to_doc_map_sample.json",
        unmapped_path=tmp_path / "unmapped.jsonl",
        config=config,
        judgment_client=object(),
        repo_root=fake_repo,
        dry_run=False,
    )

    assert result.exit_code == 0
    assert result.proposed_edit_routed == 1
    row = json.loads(
        ledger_path.read_text(encoding="utf-8").strip().splitlines()[0]
    )
    assert row["verdict"] == "PROPOSED_EDIT"
    assert row["outcome"] == "auto_committed"
    assert row["tier_classification_outcome"] == "tier_a"
    # File was actually mutated by the applier.
    assert "new line" in target_abs.read_text(encoding="utf-8")
    assert int(cursor.read_text()) == 1


def test_process_events_proposed_edit_tier_b_files_pr(
    tmp_path: Path, monkeypatch
):
    """PROPOSED_EDIT + TIER_B → file pending-approval issue."""
    events_path = _make_event_file(tmp_path)
    cursor = tmp_path / "cursor"
    ledger_path = tmp_path / "ledger.jsonl"

    fake_repo = tmp_path / "repo"
    target_rel = "docs/design/architecture/data/service-inventory.json"
    target_abs = fake_repo / target_rel
    target_abs.parent.mkdir(parents=True, exist_ok=True)
    target_abs.write_text("before old line after\n", encoding="utf-8")

    monkeypatch.setattr(
        "doc_audit.judgment.drift_interpretation.interpret",
        lambda *args, **kwargs: _stub_verdict("PROPOSED_EDIT"),
    )

    from doc_audit.data_model import EditTier

    monkeypatch.setattr(
        "doc_audit.judgment.tier_classification.classify",
        lambda *args, **kwargs: (EditTier.TIER_B, "tier_b rationale", None),
    )

    def fake_subprocess_run(cmd, *args, **kwargs):
        return mock.MagicMock(
            returncode=0,
            stdout="https://github.com/kentonium3/kg-automation/issues/555\n",
            stderr="",
        )

    # Post-refactor: gh calls route through drift_moment0.
    monkeypatch.setattr(
        "doc_audit.helpers.handle_drift_events.subprocess.run",
        fake_subprocess_run,
    )
    monkeypatch.setattr(
        "doc_audit.routing.drift_moment0.subprocess.run",
        fake_subprocess_run,
    )

    config = _flag_enabled_config(tmp_path)
    config.drift_interpretation.ledger_path = str(ledger_path)

    result = process_events(
        events_path=events_path,
        cursor_path=cursor,
        mapping_path=FIXTURES_DIR / "signal_to_doc_map_sample.json",
        unmapped_path=tmp_path / "unmapped.jsonl",
        config=config,
        judgment_client=object(),
        repo_root=fake_repo,
        dry_run=False,
    )

    assert result.exit_code == 0
    assert result.proposed_edit_routed == 1
    row = json.loads(
        ledger_path.read_text(encoding="utf-8").strip().splitlines()[0]
    )
    assert row["verdict"] == "PROPOSED_EDIT"
    assert row["outcome"] == "pr_filed"
    assert row["tier_classification_outcome"] == "tier_b"
    assert row["github_issue_number"] == 555


def test_process_events_proposed_edit_judgment_fallback_files_debt_issue(
    tmp_path: Path, monkeypatch
):
    """PROPOSED_EDIT + tier_classification=JUDGMENT → file debt-style issue."""
    events_path = _make_event_file(tmp_path)
    cursor = tmp_path / "cursor"
    ledger_path = tmp_path / "ledger.jsonl"

    fake_repo = tmp_path / "repo"
    target_rel = "docs/design/architecture/data/service-inventory.json"
    target_abs = fake_repo / target_rel
    target_abs.parent.mkdir(parents=True, exist_ok=True)
    target_abs.write_text("before old line after\n", encoding="utf-8")

    monkeypatch.setattr(
        "doc_audit.judgment.drift_interpretation.interpret",
        lambda *args, **kwargs: _stub_verdict("PROPOSED_EDIT"),
    )

    from doc_audit.data_model import EditTier

    monkeypatch.setattr(
        "doc_audit.judgment.tier_classification.classify",
        lambda *args, **kwargs: (EditTier.JUDGMENT, "judgment rationale", None),
    )

    _fake_gh_888 = lambda *args, **kwargs: mock.MagicMock(
        returncode=0,
        stdout="https://github.com/kentonium3/kg-automation/issues/888\n",
        stderr="",
    )
    monkeypatch.setattr(
        "doc_audit.helpers.handle_drift_events.subprocess.run", _fake_gh_888,
    )
    monkeypatch.setattr(
        "doc_audit.routing.drift_moment0.subprocess.run", _fake_gh_888,
    )

    config = _flag_enabled_config(tmp_path)
    config.drift_interpretation.ledger_path = str(ledger_path)

    result = process_events(
        events_path=events_path,
        cursor_path=cursor,
        mapping_path=FIXTURES_DIR / "signal_to_doc_map_sample.json",
        unmapped_path=tmp_path / "unmapped.jsonl",
        config=config,
        judgment_client=object(),
        repo_root=fake_repo,
        dry_run=False,
    )

    assert result.exit_code == 0
    assert result.judgment_required_filed == 1
    row = json.loads(
        ledger_path.read_text(encoding="utf-8").strip().splitlines()[0]
    )
    assert row["verdict"] == "PROPOSED_EDIT"
    assert row["outcome"] == "issue_filed"
    assert row["tier_classification_outcome"] == "judgment"
    assert row["github_issue_number"] == 888


def test_process_events_retry_exhausted_falls_back_and_advances_cursor(
    tmp_path: Path, monkeypatch
):
    """``DriftInterpretationError`` (retry exhausted) → fallback issue + ledger row + cursor advances.

    Cursor advancement on RETRY_EXHAUSTED is load-bearing: without it,
    a persistently-failing event would loop forever.
    """
    events_path = _make_event_file(tmp_path)
    cursor = tmp_path / "cursor"
    ledger_path = tmp_path / "ledger.jsonl"

    from doc_audit.judgment.drift_interpretation import DriftInterpretationError

    def _raise(*args, **kwargs):
        raise DriftInterpretationError(
            "retry exhausted", attempts=4
        )

    monkeypatch.setattr(
        "doc_audit.judgment.drift_interpretation.interpret", _raise
    )

    monkeypatch.setattr(
        "doc_audit.helpers.handle_drift_events.subprocess.run",
        lambda *args, **kwargs: mock.MagicMock(
            returncode=0,
            stdout="https://github.com/kentonium3/kg-automation/issues/999\n",
            stderr="",
        ),
    )

    config = _flag_enabled_config(tmp_path)
    config.drift_interpretation.ledger_path = str(ledger_path)

    result = process_events(
        events_path=events_path,
        cursor_path=cursor,
        mapping_path=FIXTURES_DIR / "signal_to_doc_map_sample.json",
        unmapped_path=tmp_path / "unmapped.jsonl",
        config=config,
        judgment_client=object(),
        repo_root=tmp_path,
        dry_run=False,
    )

    assert result.exit_code == 0
    assert result.retry_exhausted == 1
    # Cursor MUST advance so the loop doesn't loop forever (FR-008/9).
    assert int(cursor.read_text()) == 1
    row = json.loads(
        ledger_path.read_text(encoding="utf-8").strip().splitlines()[0]
    )
    assert row["verdict"] == "RETRY_EXHAUSTED"
    assert row["outcome"] == "retry_exhausted"
    assert row["confidence"] is None
    assert row["retry_count"] == 4


def test_process_events_cursor_advances_on_every_verdict_path(
    tmp_path: Path, monkeypatch
):
    """Two NO_CHANGE_NEEDED events + one JUDGMENT_REQUIRED → cursor advances to 3."""
    events_path = _make_event_file(
        tmp_path,
        events=[
            {
                "source": "audit.sh",
                "baseline_name": "openclaw-cron.txt",
                "timestamp": "2026-05-20T10:00:00Z",
                "diff": "@@ -1,1 +1,1 @@\n-a\n+b\n",
            },
            {
                "source": "audit.sh",
                "baseline_name": "listening-ports.txt",
                "timestamp": "2026-05-20T10:01:00Z",
                "diff": "@@ -1,1 +1,1 @@\n-c\n+d\n",
            },
            {
                "source": "audit.sh",
                "baseline_name": "openclaw-cron.txt",
                "timestamp": "2026-05-20T10:02:00Z",
                "diff": "@@ -1,1 +1,1 @@\n-e\n+f\n",
            },
        ],
    )
    cursor = tmp_path / "cursor"
    ledger_path = tmp_path / "ledger.jsonl"

    verdicts = iter(
        [
            _stub_verdict("NO_CHANGE_NEEDED"),
            _stub_verdict(
                "JUDGMENT_REQUIRED",
                confidence=0.50,
                question="ambiguous",
            ),
            _stub_verdict("NO_CHANGE_NEEDED"),
        ]
    )

    monkeypatch.setattr(
        "doc_audit.judgment.drift_interpretation.interpret",
        lambda *args, **kwargs: next(verdicts),
    )

    _fake_gh_123 = lambda *args, **kwargs: mock.MagicMock(
        returncode=0,
        stdout="https://github.com/kentonium3/kg-automation/issues/123\n",
        stderr="",
    )
    monkeypatch.setattr(
        "doc_audit.helpers.handle_drift_events.subprocess.run", _fake_gh_123,
    )
    monkeypatch.setattr(
        "doc_audit.routing.drift_moment0.subprocess.run", _fake_gh_123,
    )

    config = _flag_enabled_config(tmp_path)
    config.drift_interpretation.ledger_path = str(ledger_path)

    result = process_events(
        events_path=events_path,
        cursor_path=cursor,
        mapping_path=FIXTURES_DIR / "signal_to_doc_map_sample.json",
        unmapped_path=tmp_path / "unmapped.jsonl",
        config=config,
        judgment_client=object(),
        repo_root=tmp_path,
        dry_run=False,
    )

    assert result.exit_code == 0
    assert result.no_change_needed_closed == 2
    assert result.judgment_required_filed == 1
    assert int(cursor.read_text()) == 3
    ledger_rows = ledger_path.read_text(encoding="utf-8").strip().splitlines()
    assert len(ledger_rows) == 3


# ---------------------------------------------------------------------------
# --reset-cursor CLI flag (FR-014)
# ---------------------------------------------------------------------------


def test_main_reset_cursor_writes_zero_and_exits_zero(tmp_path: Path):
    cursor = tmp_path / "cursor"
    cursor.write_text("47")
    rc = main(["--reset-cursor", "--cursor", str(cursor)])
    assert rc == 0
    assert cursor.read_text() == "0"


def test_main_reset_cursor_is_idempotent(tmp_path: Path):
    cursor = tmp_path / "cursor"
    # Call twice; both should succeed and leave cursor at 0.
    rc1 = main(["--reset-cursor", "--cursor", str(cursor)])
    rc2 = main(["--reset-cursor", "--cursor", str(cursor)])
    assert rc1 == 0
    assert rc2 == 0
    assert cursor.read_text() == "0"


def test_main_reset_cursor_does_not_call_moment0_or_gh(
    tmp_path: Path, monkeypatch
):
    """--reset-cursor exits before the main loop — no LLM or gh side effects."""
    cursor = tmp_path / "cursor"

    sentinel_gh = mock.MagicMock(
        side_effect=AssertionError("gh must not run during --reset-cursor")
    )
    monkeypatch.setattr(
        "doc_audit.helpers.handle_drift_events.subprocess.run", sentinel_gh
    )

    def _explode(*args, **kwargs):
        raise AssertionError("Moment 0 must not run during --reset-cursor")

    monkeypatch.setattr(
        "doc_audit.judgment.drift_interpretation.interpret", _explode
    )

    rc = main(["--reset-cursor", "--cursor", str(cursor)])
    assert rc == 0


def test_main_help_exits_zero_and_shows_reset_cursor_flag(capsys):
    """--help exits 0 and lists --reset-cursor alongside the pre-#362 flags."""
    with pytest.raises(SystemExit) as exc_info:
        main(["--help"])
    assert exc_info.value.code == 0
    captured = capsys.readouterr()
    out = captured.out + captured.err
    assert "--reset-cursor" in out
    # Pre-#362 surface preserved (C-002): all four legacy flags still present.
    for flag in ("--events", "--cursor", "--mapping", "--unmapped", "--repo"):
        assert flag in out
