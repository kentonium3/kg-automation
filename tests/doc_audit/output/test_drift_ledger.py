"""Unit tests for ``doc_audit.output.drift_ledger``.

Covers WP02 acceptance per contracts/ledger-schema.md and
contracts/cli.md:

- Round-trip serialization across all four verdict shapes.
- Field order preserved in the on-disk JSON line.
- Atomic append (single-writer) with flush + fsync.
- Schema validation on append (verdict, outcome, confidence range,
  RETRY_EXHAUSTED ↔ None confidence pairing, tier_classification_outcome).
- ``read_window`` cutoff semantics, empty-file handling, corrupt-line
  skip, and tail-from-end performance on a large ledger.
- ``compute_triage_rate`` / ``compute_reliability`` /
  ``compute_outcome_breakdown`` correctness.
- CLI exit codes 0 / 1 / 3 across the three subcommands.
"""

from __future__ import annotations

import io
import json
import os
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

# The package-level conftest at tests/doc_audit/conftest.py installs
# ``scripts/`` on ``sys.path`` so the bare ``doc_audit`` import below
# resolves to ``scripts/doc_audit/``.
from doc_audit.output import drift_ledger
from doc_audit.output.drift_ledger import (
    DEFAULT_LEDGER_PATH,
    FIELD_ORDER,
    SCHEMA_VERSION,
    VALID_OUTCOMES,
    VALID_VERDICTS,
    AuditLedgerEntry,
    append,
    compute_outcome_breakdown,
    compute_reliability,
    compute_triage_rate,
    main,
    read_window,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _iso(now: datetime) -> str:
    """Format a datetime as ISO 8601 with a ``Z`` suffix."""
    return now.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _make_entry(
    *,
    event_id: str = "47:2026-05-22T03:00:07Z",
    timestamp_utc: str | None = None,
    baseline: str = "openclaw-cron",
    mapping_id: str = "openclaw-cron-drift",
    verdict: str = "NO_CHANGE_NEEDED",
    confidence: float | None = 0.92,
    outcome: str = "auto_closed",
    doc_paths: list[str] | None = None,
    retry_count: int = 0,
    latency_ms: int = 11342,
    tier_classification_outcome: str | None = None,
    github_issue_number: int | None = None,
    schema_version: int = SCHEMA_VERSION,
) -> AuditLedgerEntry:
    if timestamp_utc is None:
        timestamp_utc = _iso(datetime.now(timezone.utc))
    if doc_paths is None:
        doc_paths = ["docs/design/architecture/data/service-inventory.json"]
    return AuditLedgerEntry(
        event_id=event_id,
        timestamp_utc=timestamp_utc,
        baseline=baseline,
        mapping_id=mapping_id,
        verdict=verdict,
        confidence=confidence,
        outcome=outcome,
        doc_paths=doc_paths,
        retry_count=retry_count,
        latency_ms=latency_ms,
        tier_classification_outcome=tier_classification_outcome,
        github_issue_number=github_issue_number,
        schema_version=schema_version,
    )


# ---------------------------------------------------------------------------
# T008 — module surface
# ---------------------------------------------------------------------------


def test_module_constants_present() -> None:
    assert SCHEMA_VERSION == 1
    assert "PROPOSED_EDIT" in VALID_VERDICTS
    assert "JUDGMENT_REQUIRED" in VALID_VERDICTS
    assert "NO_CHANGE_NEEDED" in VALID_VERDICTS
    assert "RETRY_EXHAUSTED" in VALID_VERDICTS
    assert {
        "auto_committed",
        "pr_filed",
        "issue_filed",
        "auto_closed",
        "retry_exhausted",
    } == set(VALID_OUTCOMES)
    assert DEFAULT_LEDGER_PATH == Path(
        "/data/services/security-monitor/logs/drift-events-ledger.jsonl"
    )


def test_dataclass_is_frozen() -> None:
    entry = _make_entry()
    with pytest.raises((AttributeError, Exception)):
        entry.verdict = "PROPOSED_EDIT"  # type: ignore[misc]


# ---------------------------------------------------------------------------
# T009 — append() round-trip + field order
# ---------------------------------------------------------------------------


def test_append_round_trip_no_change_needed(tmp_path: Path) -> None:
    ledger = tmp_path / "ledger.jsonl"
    entry = _make_entry()
    append(entry, ledger_path=ledger)
    # Read raw line — exactly one row, ``\n``-terminated.
    raw = ledger.read_text(encoding="utf-8")
    assert raw.endswith("\n")
    assert raw.count("\n") == 1
    # Parse and assert equality across all 13 fields.
    parsed = json.loads(raw.strip())
    for field_name in FIELD_ORDER:
        assert parsed[field_name] == getattr(entry, field_name), field_name


def test_append_field_order_matches_contract(tmp_path: Path) -> None:
    """The on-disk JSON line MUST emit keys in :data:`FIELD_ORDER`."""
    ledger = tmp_path / "ledger.jsonl"
    entry = _make_entry()
    append(entry, ledger_path=ledger)
    raw = ledger.read_text(encoding="utf-8").strip()
    parsed = json.loads(raw)
    assert list(parsed.keys()) == list(FIELD_ORDER)


def test_append_compact_serialization(tmp_path: Path) -> None:
    """JSON is compact: no spaces between separators, no trailing WS."""
    ledger = tmp_path / "ledger.jsonl"
    append(_make_entry(), ledger_path=ledger)
    raw = ledger.read_text(encoding="utf-8")
    # Strip the trailing ``\n``; the body itself contains no spaces
    # outside string literals.
    body = raw[:-1]
    # No ``", "`` separators in the compact form. Use a marker that
    # cannot appear inside any string literal in the fixture entry.
    assert ", " not in body
    assert ": " not in body


def test_append_creates_parent_dir(tmp_path: Path) -> None:
    ledger = tmp_path / "nested" / "dir" / "ledger.jsonl"
    append(_make_entry(), ledger_path=ledger)
    assert ledger.is_file()


def test_append_multiple_rows_separated_by_newline(tmp_path: Path) -> None:
    """Two consecutive appends produce two complete lines."""
    ledger = tmp_path / "ledger.jsonl"
    append(_make_entry(event_id="event-1"), ledger_path=ledger)
    append(_make_entry(event_id="event-2"), ledger_path=ledger)
    raw = ledger.read_text(encoding="utf-8")
    assert raw.count("\n") == 2
    lines = [line for line in raw.split("\n") if line]
    assert len(lines) == 2
    e1 = json.loads(lines[0])
    e2 = json.loads(lines[1])
    assert e1["event_id"] == "event-1"
    assert e2["event_id"] == "event-2"


def test_append_round_trip_all_four_verdicts(tmp_path: Path) -> None:
    """Every verdict shape survives a serialize/parse round-trip."""
    ledger = tmp_path / "ledger.jsonl"
    cases = [
        _make_entry(
            verdict="NO_CHANGE_NEEDED",
            confidence=0.92,
            outcome="auto_closed",
            tier_classification_outcome=None,
            github_issue_number=None,
        ),
        _make_entry(
            event_id="48:t",
            verdict="PROPOSED_EDIT",
            confidence=0.88,
            outcome="pr_filed",
            tier_classification_outcome="tier_b",
            github_issue_number=374,
        ),
        _make_entry(
            event_id="49:t",
            verdict="JUDGMENT_REQUIRED",
            confidence=0.45,
            outcome="issue_filed",
            tier_classification_outcome=None,
            github_issue_number=375,
        ),
        _make_entry(
            event_id="50:t",
            verdict="RETRY_EXHAUSTED",
            confidence=None,
            outcome="retry_exhausted",
            retry_count=3,
            latency_ms=242100,
            tier_classification_outcome=None,
            github_issue_number=376,
        ),
    ]
    for entry in cases:
        append(entry, ledger_path=ledger)

    # Use a wide window to capture all entries.
    entries = read_window(ledger_path=ledger, days=3650)
    assert len(entries) == 4
    by_id = {e.event_id: e for e in entries}
    for original in cases:
        rt = by_id[original.event_id]
        for field_name in FIELD_ORDER:
            assert getattr(rt, field_name) == getattr(original, field_name)


# ---------------------------------------------------------------------------
# T009 — validation-on-append (BEFORE write)
# ---------------------------------------------------------------------------


def test_append_rejects_invalid_verdict(tmp_path: Path) -> None:
    ledger = tmp_path / "ledger.jsonl"
    bad = _make_entry(verdict="INVALID_VERDICT")
    with pytest.raises(ValueError, match="invalid verdict"):
        append(bad, ledger_path=ledger)
    # File MUST NOT have been created (validation runs before any
    # filesystem touch).
    assert not ledger.exists()


def test_append_rejects_invalid_outcome(tmp_path: Path) -> None:
    ledger = tmp_path / "ledger.jsonl"
    bad = _make_entry(outcome="invented_outcome")
    with pytest.raises(ValueError, match="invalid outcome"):
        append(bad, ledger_path=ledger)


def test_append_rejects_out_of_range_confidence(tmp_path: Path) -> None:
    ledger = tmp_path / "ledger.jsonl"
    bad = _make_entry(confidence=1.5)
    with pytest.raises(ValueError, match=r"confidence must be in \[0\.0, 1\.0\]"):
        append(bad, ledger_path=ledger)


def test_append_rejects_negative_confidence(tmp_path: Path) -> None:
    ledger = tmp_path / "ledger.jsonl"
    bad = _make_entry(confidence=-0.01)
    with pytest.raises(ValueError, match=r"confidence must be in \[0\.0, 1\.0\]"):
        append(bad, ledger_path=ledger)


def test_append_rejects_none_confidence_for_non_retry_verdict(
    tmp_path: Path,
) -> None:
    ledger = tmp_path / "ledger.jsonl"
    bad = _make_entry(verdict="PROPOSED_EDIT", confidence=None)
    with pytest.raises(ValueError, match="must be a float"):
        append(bad, ledger_path=ledger)


def test_append_rejects_non_none_confidence_for_retry_exhausted(
    tmp_path: Path,
) -> None:
    ledger = tmp_path / "ledger.jsonl"
    bad = _make_entry(
        verdict="RETRY_EXHAUSTED",
        confidence=0.5,
        outcome="retry_exhausted",
    )
    with pytest.raises(ValueError, match="must be None when verdict is RETRY_EXHAUSTED"):
        append(bad, ledger_path=ledger)


def test_append_rejects_invalid_tier_outcome(tmp_path: Path) -> None:
    ledger = tmp_path / "ledger.jsonl"
    bad = _make_entry(tier_classification_outcome="invented_tier")
    with pytest.raises(ValueError, match="invalid tier_classification_outcome"):
        append(bad, ledger_path=ledger)


def test_append_rejects_out_of_range_retry_count(tmp_path: Path) -> None:
    """retry_count outside [0, RETRY_MAX_ATTEMPTS] is rejected by validator."""
    from doc_audit.output.drift_ledger import RETRY_MAX_ATTEMPTS

    ledger = tmp_path / "ledger.jsonl"
    bad = _make_entry(retry_count=RETRY_MAX_ATTEMPTS + 1)
    with pytest.raises(ValueError, match="retry_count must be in"):
        append(bad, ledger_path=ledger)


def test_append_rejects_negative_latency(tmp_path: Path) -> None:
    ledger = tmp_path / "ledger.jsonl"
    bad = _make_entry(latency_ms=-1)
    with pytest.raises(ValueError, match="latency_ms must be non-negative"):
        append(bad, ledger_path=ledger)


def test_append_rejects_bad_doc_paths_shape(tmp_path: Path) -> None:
    ledger = tmp_path / "ledger.jsonl"
    bad = _make_entry(doc_paths=[1, 2])  # type: ignore[list-item]
    with pytest.raises(ValueError, match="doc_paths must be a list of strings"):
        append(bad, ledger_path=ledger)


def test_append_rejects_wrong_schema_version(tmp_path: Path) -> None:
    ledger = tmp_path / "ledger.jsonl"
    bad = _make_entry(schema_version=2)
    with pytest.raises(ValueError, match="schema_version must be 1"):
        append(bad, ledger_path=ledger)


def test_append_rejects_empty_event_id(tmp_path: Path) -> None:
    ledger = tmp_path / "ledger.jsonl"
    bad = _make_entry(event_id="")
    with pytest.raises(ValueError, match="event_id must be"):
        append(bad, ledger_path=ledger)


def test_append_rejects_empty_baseline(tmp_path: Path) -> None:
    ledger = tmp_path / "ledger.jsonl"
    bad = _make_entry(baseline="")
    with pytest.raises(ValueError, match="baseline must be"):
        append(bad, ledger_path=ledger)


def test_append_rejects_empty_mapping_id(tmp_path: Path) -> None:
    ledger = tmp_path / "ledger.jsonl"
    bad = _make_entry(mapping_id="")
    with pytest.raises(ValueError, match="mapping_id must be"):
        append(bad, ledger_path=ledger)


def test_append_rejects_empty_timestamp(tmp_path: Path) -> None:
    ledger = tmp_path / "ledger.jsonl"
    bad = _make_entry(timestamp_utc="")
    with pytest.raises(ValueError, match="timestamp_utc must be"):
        append(bad, ledger_path=ledger)


# ---------------------------------------------------------------------------
# T010 — read_window
# ---------------------------------------------------------------------------


def test_read_window_empty_file(tmp_path: Path) -> None:
    ledger = tmp_path / "ledger.jsonl"
    ledger.write_text("", encoding="utf-8")
    assert read_window(ledger_path=ledger, days=7) == []


def test_read_window_missing_file(tmp_path: Path) -> None:
    ledger = tmp_path / "absent.jsonl"
    assert not ledger.exists()
    assert read_window(ledger_path=ledger, days=7) == []


def test_read_window_cutoff_honored(tmp_path: Path) -> None:
    """Entries older than ``now - days`` are excluded."""
    ledger = tmp_path / "ledger.jsonl"
    now = datetime.now(timezone.utc)
    recent = _make_entry(
        event_id="recent",
        timestamp_utc=_iso(now - timedelta(days=1)),
    )
    middle = _make_entry(
        event_id="middle",
        timestamp_utc=_iso(now - timedelta(days=3)),
    )
    old = _make_entry(
        event_id="old",
        timestamp_utc=_iso(now - timedelta(days=10)),
    )
    # Write oldest first so the file mirrors chronological write order.
    append(old, ledger_path=ledger)
    append(middle, ledger_path=ledger)
    append(recent, ledger_path=ledger)

    entries = read_window(ledger_path=ledger, days=7)
    ids = [e.event_id for e in entries]
    assert ids == ["middle", "recent"]


def test_read_window_returns_chronological_order(tmp_path: Path) -> None:
    ledger = tmp_path / "ledger.jsonl"
    now = datetime.now(timezone.utc)
    e1 = _make_entry(
        event_id="e1", timestamp_utc=_iso(now - timedelta(hours=3))
    )
    e2 = _make_entry(
        event_id="e2", timestamp_utc=_iso(now - timedelta(hours=2))
    )
    e3 = _make_entry(
        event_id="e3", timestamp_utc=_iso(now - timedelta(hours=1))
    )
    for entry in (e1, e2, e3):
        append(entry, ledger_path=ledger)
    entries = read_window(ledger_path=ledger, days=1)
    assert [e.event_id for e in entries] == ["e1", "e2", "e3"]


def test_read_window_skips_corrupt_line(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    ledger = tmp_path / "ledger.jsonl"
    now = datetime.now(timezone.utc)
    # Write a valid entry, then a corrupt line, then another valid entry.
    valid_a = _make_entry(
        event_id="a", timestamp_utc=_iso(now - timedelta(hours=2))
    )
    valid_b = _make_entry(
        event_id="b", timestamp_utc=_iso(now - timedelta(hours=1))
    )
    append(valid_a, ledger_path=ledger)
    with ledger.open("a", encoding="utf-8") as f:
        f.write("not-json-not-anything\n")
    append(valid_b, ledger_path=ledger)

    entries = read_window(ledger_path=ledger, days=1)
    ids = [e.event_id for e in entries]
    assert ids == ["a", "b"]
    captured = capsys.readouterr()
    assert "corrupt" in captured.err.lower() or "skipping" in captured.err.lower()


def test_read_window_handles_missing_trailing_newline(tmp_path: Path) -> None:
    """A file that does not end with ``\\n`` is still fully parseable."""
    ledger = tmp_path / "ledger.jsonl"
    now = datetime.now(timezone.utc)
    valid = _make_entry(
        event_id="last", timestamp_utc=_iso(now - timedelta(hours=1))
    )
    # Write a row without a trailing newline (simulating torn write
    # of a file that previously had one row terminated cleanly).
    serialized = drift_ledger._entry_to_json(valid)
    ledger.write_text(serialized, encoding="utf-8")
    entries = read_window(ledger_path=ledger, days=1)
    assert [e.event_id for e in entries] == ["last"]


def test_read_window_large_file_performance(tmp_path: Path) -> None:
    """Synthesize 10K entries; ``days=1`` returns the recent subset quickly."""
    ledger = tmp_path / "ledger.jsonl"
    now = datetime.now(timezone.utc)
    # 9000 entries from 30 days ago, 1000 entries from the last 12 hours.
    # Writing direct to the file (skipping ``append``) keeps the test
    # fast — we're exercising read_window, not append.
    lines: list[str] = []
    for i in range(9000):
        e = _make_entry(
            event_id=f"old-{i}",
            timestamp_utc=_iso(now - timedelta(days=30)),
        )
        lines.append(drift_ledger._entry_to_json(e))
    for i in range(1000):
        e = _make_entry(
            event_id=f"new-{i}",
            timestamp_utc=_iso(
                now - timedelta(hours=12) + timedelta(seconds=i)
            ),
        )
        lines.append(drift_ledger._entry_to_json(e))
    ledger.write_text("\n".join(lines) + "\n", encoding="utf-8")

    start = time.perf_counter()
    entries = read_window(ledger_path=ledger, days=1)
    elapsed = time.perf_counter() - start

    assert len(entries) == 1000
    # Tail-from-end should be fast — well under the 2s budget noted in
    # the WP02 prompt.
    assert elapsed < 2.0, f"read_window too slow: {elapsed:.2f}s"


def test_read_window_ignores_unknown_fields(tmp_path: Path) -> None:
    """Forward-compat: unknown JSON fields are dropped, not rejected."""
    ledger = tmp_path / "ledger.jsonl"
    now = datetime.now(timezone.utc)
    base = _make_entry(timestamp_utc=_iso(now - timedelta(hours=1)))
    payload = drift_ledger._entry_to_dict(base)
    payload["future_field_we_dont_know_about"] = "ignored"
    ledger.write_text(json.dumps(payload) + "\n", encoding="utf-8")
    entries = read_window(ledger_path=ledger, days=1)
    assert len(entries) == 1
    assert entries[0].event_id == base.event_id


def test_read_window_skips_malformed_timestamp(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    ledger = tmp_path / "ledger.jsonl"
    now = datetime.now(timezone.utc)
    good = _make_entry(
        event_id="good", timestamp_utc=_iso(now - timedelta(hours=1))
    )
    append(good, ledger_path=ledger)
    # Craft a row with a bad timestamp (bypasses validation by writing
    # raw JSON).
    bad_payload = drift_ledger._entry_to_dict(good)
    bad_payload["event_id"] = "bad-ts"
    bad_payload["timestamp_utc"] = "not-a-real-timestamp"
    with ledger.open("a", encoding="utf-8") as f:
        f.write(json.dumps(bad_payload) + "\n")
    entries = read_window(ledger_path=ledger, days=1)
    ids = [e.event_id for e in entries]
    assert "good" in ids
    assert "bad-ts" not in ids


# ---------------------------------------------------------------------------
# T011 — compute_triage_rate / compute_reliability / compute_outcome_breakdown
# ---------------------------------------------------------------------------


def _populate_ledger_for_metrics(ledger: Path) -> None:
    """Build a 10-row fixture ledger covering all metric scenarios.

    4× JUDGMENT_REQUIRED, 3× PROPOSED_EDIT, 2× NO_CHANGE_NEEDED, 1×
    RETRY_EXHAUSTED. All timestamps within the last day so a ``days=1``
    window captures every row.
    """
    now = datetime.now(timezone.utc)
    rows = (
        ("PROPOSED_EDIT", 0.85, "auto_committed", "tier_a"),
        ("PROPOSED_EDIT", 0.88, "pr_filed", "tier_b"),
        ("PROPOSED_EDIT", 0.90, "pr_filed", "tier_b"),
        ("JUDGMENT_REQUIRED", 0.45, "issue_filed", None),
        ("JUDGMENT_REQUIRED", 0.50, "issue_filed", None),
        ("JUDGMENT_REQUIRED", 0.55, "issue_filed", None),
        ("JUDGMENT_REQUIRED", 0.60, "issue_filed", None),
        ("NO_CHANGE_NEEDED", 0.95, "auto_closed", None),
        ("NO_CHANGE_NEEDED", 0.97, "auto_closed", None),
        ("RETRY_EXHAUSTED", None, "retry_exhausted", None),
    )
    for i, (verdict, conf, outcome, tier) in enumerate(rows):
        entry = _make_entry(
            event_id=f"row-{i}",
            timestamp_utc=_iso(now - timedelta(minutes=i)),
            verdict=verdict,
            confidence=conf,
            outcome=outcome,
            tier_classification_outcome=tier,
            retry_count=3 if verdict == "RETRY_EXHAUSTED" else 0,
            github_issue_number=(
                400 + i if outcome in {"issue_filed", "pr_filed"} else None
            ),
        )
        append(entry, ledger_path=ledger)


def test_compute_triage_rate_known_ledger(tmp_path: Path) -> None:
    ledger = tmp_path / "ledger.jsonl"
    _populate_ledger_for_metrics(ledger)
    rate = compute_triage_rate(ledger_path=ledger, days=1)
    # 4 JUDGMENT_REQUIRED out of 10 total
    assert rate == pytest.approx(0.40)


def test_compute_triage_rate_empty(tmp_path: Path) -> None:
    ledger = tmp_path / "ledger.jsonl"
    ledger.write_text("", encoding="utf-8")
    assert compute_triage_rate(ledger_path=ledger, days=7) == 0.0


def test_compute_reliability_known_ledger(tmp_path: Path) -> None:
    ledger = tmp_path / "ledger.jsonl"
    _populate_ledger_for_metrics(ledger)
    reliability = compute_reliability(ledger_path=ledger, days=1)
    # 1 RETRY_EXHAUSTED out of 10 total → 1 - 0.10 = 0.90
    assert reliability == pytest.approx(0.90)


def test_compute_reliability_empty(tmp_path: Path) -> None:
    ledger = tmp_path / "ledger.jsonl"
    ledger.write_text("", encoding="utf-8")
    assert compute_reliability(ledger_path=ledger, days=7) == 1.0


def test_compute_outcome_breakdown_known_ledger(tmp_path: Path) -> None:
    ledger = tmp_path / "ledger.jsonl"
    _populate_ledger_for_metrics(ledger)
    breakdown = compute_outcome_breakdown(ledger_path=ledger, days=1)
    assert breakdown == {
        "auto_committed": 1,
        "pr_filed": 2,
        "issue_filed": 4,
        "auto_closed": 2,
        "retry_exhausted": 1,
    }


def test_compute_outcome_breakdown_empty(tmp_path: Path) -> None:
    ledger = tmp_path / "ledger.jsonl"
    ledger.write_text("", encoding="utf-8")
    assert compute_outcome_breakdown(ledger_path=ledger, days=7) == {}


# ---------------------------------------------------------------------------
# T012 — CLI
# ---------------------------------------------------------------------------


def test_cli_help_exits_zero(
    capsys: pytest.CaptureFixture[str],
) -> None:
    """Top-level ``--help`` exits 0 via argparse's help path."""
    with pytest.raises(SystemExit) as excinfo:
        main(["--help"])
    assert excinfo.value.code == 0


@pytest.mark.parametrize(
    "subcommand", ["summary", "tail", "triage-rate"]
)
def test_cli_subcommand_help_exits_zero(
    subcommand: str, capsys: pytest.CaptureFixture[str]
) -> None:
    with pytest.raises(SystemExit) as excinfo:
        main([subcommand, "--help"])
    assert excinfo.value.code == 0


def test_cli_summary_exits_zero_against_fixture(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    ledger = tmp_path / "ledger.jsonl"
    _populate_ledger_for_metrics(ledger)
    rc = main(
        [
            "--ledger-path",
            str(ledger),
            "--days",
            "1",
            "summary",
        ]
    )
    assert rc == 0
    out = capsys.readouterr().out
    assert "Ledger summary" in out
    assert "Verdicts:" in out
    assert "Outcomes:" in out


def test_cli_tail_exits_zero_against_fixture(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    ledger = tmp_path / "ledger.jsonl"
    _populate_ledger_for_metrics(ledger)
    rc = main(
        [
            "--ledger-path",
            str(ledger),
            "--days",
            "1",
            "tail",
        ]
    )
    assert rc == 0
    out = capsys.readouterr().out
    # The 10 entries fit within the default tail size of 10 — every
    # one prints. The output is multi-line indented JSON.
    assert "row-0" in out
    assert "row-9" in out


def test_cli_triage_rate_exits_zero_against_fixture(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    ledger = tmp_path / "ledger.jsonl"
    _populate_ledger_for_metrics(ledger)
    rc = main(
        [
            "--ledger-path",
            str(ledger),
            "--days",
            "1",
            "triage-rate",
        ]
    )
    assert rc == 0
    out = capsys.readouterr().out
    assert "Triage rate" in out
    # 4/10 = 40.0%
    assert "40.0%" in out


def test_cli_empty_ledger_returns_zero(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """Subcommands handle empty/absent ledger gracefully (exit 0)."""
    ledger = tmp_path / "absent.jsonl"
    rc = main(
        [
            "--ledger-path",
            str(ledger),
            "summary",
        ]
    )
    assert rc == 0


def test_cli_unreadable_ledger_returns_one(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """A ledger path that exists but is unreadable maps to exit 1."""
    ledger = tmp_path / "ledger.jsonl"
    _populate_ledger_for_metrics(ledger)
    # Chmod 000 — only effective for the non-root case. Skip on
    # privileged test runs.
    if os.geteuid() == 0:
        pytest.skip("permission tests are no-ops when running as root")
    ledger.chmod(0o000)
    try:
        rc = main(
            [
                "--ledger-path",
                str(ledger),
                "summary",
            ]
        )
    finally:
        # Restore so pytest can clean up the tmp dir.
        ledger.chmod(0o644)
    assert rc == 1


def test_cli_bad_subcommand_returns_three(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    rc = main(["does-not-exist"])
    assert rc == 3


def test_cli_bad_flag_returns_three(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    rc = main(["--bogus-flag", "summary"])
    assert rc == 3


def test_cli_missing_subcommand_returns_three(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    rc = main([])
    assert rc == 3
