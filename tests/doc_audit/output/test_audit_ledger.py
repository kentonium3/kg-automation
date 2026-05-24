"""Unit tests for ``doc_audit.output.audit_ledger``.

Covers WP01 acceptance for the commit-audit ledger:

- Round-trip serialization across all four verdict shapes.
- Field order preserved in the on-disk JSON line.
- Atomic append (single-writer) with flush + fsync.
- Schema validation on append (verdict, outcome, confidence range,
  RETRY_EXHAUSTED ↔ None confidence pairing, audit_issue).
- ``judgment_required_posted`` is a valid outcome (audit-ledger-only).
- ``read_window`` cutoff semantics, empty-file handling, corrupt-line
  skip.
- ``compute_triage_rate`` / ``compute_outcome_breakdown`` correctness.
- CLI exit codes 0 / 1 / 3 across the two subcommands.
"""

from __future__ import annotations

import json
import os
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

from doc_audit.output import audit_ledger
from doc_audit.output.audit_ledger import (
    DEFAULT_LEDGER_PATH,
    FIELD_ORDER,
    SCHEMA_VERSION,
    VALID_OUTCOMES,
    VALID_VERDICTS,
    AuditLedgerEntry,
    append,
    compute_outcome_breakdown,
    compute_triage_rate,
    main,
    read_window,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _iso(now: datetime) -> str:
    return now.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _make_entry(
    *,
    audit_issue: int = 412,
    doc_path: str = "docs/runbooks/habits-ops.md",
    timestamp_utc: str | None = None,
    commit_sha: str = "a1b2c3d",
    verdict: str = "NO_CHANGE_NEEDED",
    confidence: float | None = 0.92,
    outcome: str = "auto_closed",
    schema_version: int = SCHEMA_VERSION,
) -> AuditLedgerEntry:
    if timestamp_utc is None:
        timestamp_utc = _iso(datetime.now(timezone.utc))
    return AuditLedgerEntry(
        audit_issue=audit_issue,
        doc_path=doc_path,
        timestamp_utc=timestamp_utc,
        commit_sha=commit_sha,
        verdict=verdict,
        confidence=confidence,
        outcome=outcome,
        schema_version=schema_version,
    )


# ---------------------------------------------------------------------------
# Module surface
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
        "judgment_required_posted",
        "retry_exhausted",
    } == set(VALID_OUTCOMES)
    assert DEFAULT_LEDGER_PATH == Path(
        "/data/services/openclaw/state/doc_audit/audit-events-ledger.jsonl"
    )


def test_judgment_required_posted_is_valid_outcome() -> None:
    """The audit-ledger-unique outcome must be valid for append()."""
    assert "judgment_required_posted" in VALID_OUTCOMES


def test_dataclass_is_frozen() -> None:
    entry = _make_entry()
    with pytest.raises((AttributeError, Exception)):
        entry.verdict = "PROPOSED_EDIT"  # type: ignore[misc]


# ---------------------------------------------------------------------------
# append() round-trip + field order
# ---------------------------------------------------------------------------


def test_append_round_trip_no_change_needed(tmp_path: Path) -> None:
    ledger = tmp_path / "ledger.jsonl"
    entry = _make_entry()
    append(entry, ledger_path=ledger)
    raw = ledger.read_text(encoding="utf-8")
    assert raw.endswith("\n")
    assert raw.count("\n") == 1
    parsed = json.loads(raw.strip())
    for field_name in FIELD_ORDER:
        assert parsed[field_name] == getattr(entry, field_name), field_name


def test_append_field_order_matches_contract(tmp_path: Path) -> None:
    ledger = tmp_path / "ledger.jsonl"
    entry = _make_entry()
    append(entry, ledger_path=ledger)
    raw = ledger.read_text(encoding="utf-8").strip()
    parsed = json.loads(raw)
    assert list(parsed.keys()) == list(FIELD_ORDER)


def test_append_compact_serialization(tmp_path: Path) -> None:
    ledger = tmp_path / "ledger.jsonl"
    append(_make_entry(), ledger_path=ledger)
    raw = ledger.read_text(encoding="utf-8")
    body = raw[:-1]
    assert ", " not in body
    assert ": " not in body


def test_append_creates_parent_dir(tmp_path: Path) -> None:
    ledger = tmp_path / "nested" / "dir" / "ledger.jsonl"
    append(_make_entry(), ledger_path=ledger)
    assert ledger.is_file()


def test_append_multiple_rows_separated_by_newline(tmp_path: Path) -> None:
    ledger = tmp_path / "ledger.jsonl"
    append(_make_entry(audit_issue=1), ledger_path=ledger)
    append(_make_entry(audit_issue=2), ledger_path=ledger)
    raw = ledger.read_text(encoding="utf-8")
    assert raw.count("\n") == 2
    lines = [line for line in raw.split("\n") if line]
    assert len(lines) == 2
    e1 = json.loads(lines[0])
    e2 = json.loads(lines[1])
    assert e1["audit_issue"] == 1
    assert e2["audit_issue"] == 2


def test_append_round_trip_all_verdicts(tmp_path: Path) -> None:
    ledger = tmp_path / "ledger.jsonl"
    cases = [
        _make_entry(
            audit_issue=1,
            verdict="NO_CHANGE_NEEDED",
            confidence=0.92,
            outcome="auto_closed",
        ),
        _make_entry(
            audit_issue=2,
            verdict="PROPOSED_EDIT",
            confidence=0.88,
            outcome="pr_filed",
        ),
        _make_entry(
            audit_issue=3,
            verdict="JUDGMENT_REQUIRED",
            confidence=0.45,
            outcome="judgment_required_posted",
        ),
        _make_entry(
            audit_issue=4,
            verdict="RETRY_EXHAUSTED",
            confidence=None,
            outcome="retry_exhausted",
        ),
    ]
    for entry in cases:
        append(entry, ledger_path=ledger)

    entries = read_window(ledger_path=ledger, days=3650)
    assert len(entries) == 4
    by_id = {e.audit_issue: e for e in entries}
    for original in cases:
        rt = by_id[original.audit_issue]
        for field_name in FIELD_ORDER:
            assert getattr(rt, field_name) == getattr(original, field_name)


def test_append_accepts_judgment_required_posted_outcome(tmp_path: Path) -> None:
    """Sanity check: the audit-ledger-unique outcome appends without error."""
    ledger = tmp_path / "ledger.jsonl"
    entry = _make_entry(
        verdict="JUDGMENT_REQUIRED",
        confidence=0.45,
        outcome="judgment_required_posted",
    )
    append(entry, ledger_path=ledger)
    entries = read_window(ledger_path=ledger, days=1)
    assert len(entries) == 1
    assert entries[0].outcome == "judgment_required_posted"


# ---------------------------------------------------------------------------
# validation-on-append (BEFORE write)
# ---------------------------------------------------------------------------


def test_append_rejects_invalid_verdict(tmp_path: Path) -> None:
    ledger = tmp_path / "ledger.jsonl"
    bad = _make_entry(verdict="INVALID_VERDICT")
    with pytest.raises(ValueError, match="invalid verdict"):
        append(bad, ledger_path=ledger)
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


def test_append_rejects_bool_confidence(tmp_path: Path) -> None:
    """bool is an int subclass — must NOT slip past the type check."""
    ledger = tmp_path / "ledger.jsonl"
    bad = _make_entry(confidence=True)  # type: ignore[arg-type]
    with pytest.raises(ValueError, match="confidence must be a number"):
        append(bad, ledger_path=ledger)


def test_append_rejects_none_confidence_for_non_retry_verdict(tmp_path: Path) -> None:
    ledger = tmp_path / "ledger.jsonl"
    bad = _make_entry(verdict="PROPOSED_EDIT", confidence=None)
    with pytest.raises(ValueError, match="must be a float"):
        append(bad, ledger_path=ledger)


def test_append_rejects_non_none_confidence_for_retry_exhausted(tmp_path: Path) -> None:
    ledger = tmp_path / "ledger.jsonl"
    bad = _make_entry(
        verdict="RETRY_EXHAUSTED",
        confidence=0.5,
        outcome="retry_exhausted",
    )
    with pytest.raises(ValueError, match="must be None when verdict is RETRY_EXHAUSTED"):
        append(bad, ledger_path=ledger)


def test_append_rejects_wrong_schema_version(tmp_path: Path) -> None:
    ledger = tmp_path / "ledger.jsonl"
    bad = _make_entry(schema_version=2)
    with pytest.raises(ValueError, match="schema_version must be 1"):
        append(bad, ledger_path=ledger)


def test_append_rejects_non_int_audit_issue(tmp_path: Path) -> None:
    ledger = tmp_path / "ledger.jsonl"
    bad = _make_entry(audit_issue="412")  # type: ignore[arg-type]
    with pytest.raises(ValueError, match="audit_issue must be an int"):
        append(bad, ledger_path=ledger)


def test_append_rejects_zero_audit_issue(tmp_path: Path) -> None:
    ledger = tmp_path / "ledger.jsonl"
    bad = _make_entry(audit_issue=0)
    with pytest.raises(ValueError, match="audit_issue must be a positive int"):
        append(bad, ledger_path=ledger)


def test_append_rejects_negative_audit_issue(tmp_path: Path) -> None:
    ledger = tmp_path / "ledger.jsonl"
    bad = _make_entry(audit_issue=-5)
    with pytest.raises(ValueError, match="audit_issue must be a positive int"):
        append(bad, ledger_path=ledger)


def test_append_rejects_bool_audit_issue(tmp_path: Path) -> None:
    """bool is an int subclass — guard against True/False slipping in."""
    ledger = tmp_path / "ledger.jsonl"
    bad = _make_entry(audit_issue=True)  # type: ignore[arg-type]
    with pytest.raises(ValueError, match="audit_issue must be an int"):
        append(bad, ledger_path=ledger)


def test_append_rejects_empty_doc_path(tmp_path: Path) -> None:
    ledger = tmp_path / "ledger.jsonl"
    bad = _make_entry(doc_path="")
    with pytest.raises(ValueError, match="doc_path must be"):
        append(bad, ledger_path=ledger)


def test_append_rejects_empty_timestamp(tmp_path: Path) -> None:
    ledger = tmp_path / "ledger.jsonl"
    bad = _make_entry(timestamp_utc="")
    with pytest.raises(ValueError, match="timestamp_utc must be"):
        append(bad, ledger_path=ledger)


def test_append_rejects_empty_commit_sha(tmp_path: Path) -> None:
    ledger = tmp_path / "ledger.jsonl"
    bad = _make_entry(commit_sha="")
    with pytest.raises(ValueError, match="commit_sha must be"):
        append(bad, ledger_path=ledger)


# ---------------------------------------------------------------------------
# read_window
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
    ledger = tmp_path / "ledger.jsonl"
    now = datetime.now(timezone.utc)
    recent = _make_entry(
        audit_issue=100,
        timestamp_utc=_iso(now - timedelta(days=1)),
    )
    middle = _make_entry(
        audit_issue=200,
        timestamp_utc=_iso(now - timedelta(days=3)),
    )
    old = _make_entry(
        audit_issue=300,
        timestamp_utc=_iso(now - timedelta(days=10)),
    )
    append(old, ledger_path=ledger)
    append(middle, ledger_path=ledger)
    append(recent, ledger_path=ledger)

    entries = read_window(ledger_path=ledger, days=7)
    ids = [e.audit_issue for e in entries]
    assert ids == [200, 100]


def test_read_window_returns_chronological_order(tmp_path: Path) -> None:
    ledger = tmp_path / "ledger.jsonl"
    now = datetime.now(timezone.utc)
    e1 = _make_entry(audit_issue=1, timestamp_utc=_iso(now - timedelta(hours=3)))
    e2 = _make_entry(audit_issue=2, timestamp_utc=_iso(now - timedelta(hours=2)))
    e3 = _make_entry(audit_issue=3, timestamp_utc=_iso(now - timedelta(hours=1)))
    for entry in (e1, e2, e3):
        append(entry, ledger_path=ledger)
    entries = read_window(ledger_path=ledger, days=1)
    assert [e.audit_issue for e in entries] == [1, 2, 3]


def test_read_window_skips_corrupt_line(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    ledger = tmp_path / "ledger.jsonl"
    now = datetime.now(timezone.utc)
    valid_a = _make_entry(audit_issue=10, timestamp_utc=_iso(now - timedelta(hours=2)))
    valid_b = _make_entry(audit_issue=20, timestamp_utc=_iso(now - timedelta(hours=1)))
    append(valid_a, ledger_path=ledger)
    with ledger.open("a", encoding="utf-8") as f:
        f.write("not-json-not-anything\n")
    append(valid_b, ledger_path=ledger)

    entries = read_window(ledger_path=ledger, days=1)
    ids = [e.audit_issue for e in entries]
    assert ids == [10, 20]
    captured = capsys.readouterr()
    assert "corrupt" in captured.err.lower() or "skipping" in captured.err.lower()


def test_read_window_handles_missing_trailing_newline(tmp_path: Path) -> None:
    ledger = tmp_path / "ledger.jsonl"
    now = datetime.now(timezone.utc)
    valid = _make_entry(audit_issue=99, timestamp_utc=_iso(now - timedelta(hours=1)))
    serialized = audit_ledger._entry_to_json(valid)
    ledger.write_text(serialized, encoding="utf-8")
    entries = read_window(ledger_path=ledger, days=1)
    assert [e.audit_issue for e in entries] == [99]


def test_read_window_ignores_unknown_fields(tmp_path: Path) -> None:
    ledger = tmp_path / "ledger.jsonl"
    now = datetime.now(timezone.utc)
    base = _make_entry(timestamp_utc=_iso(now - timedelta(hours=1)))
    payload = audit_ledger._entry_to_dict(base)
    payload["future_field_we_dont_know_about"] = "ignored"
    ledger.write_text(json.dumps(payload) + "\n", encoding="utf-8")
    entries = read_window(ledger_path=ledger, days=1)
    assert len(entries) == 1
    assert entries[0].audit_issue == base.audit_issue


def test_read_window_skips_malformed_timestamp(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    ledger = tmp_path / "ledger.jsonl"
    now = datetime.now(timezone.utc)
    good = _make_entry(audit_issue=1, timestamp_utc=_iso(now - timedelta(hours=1)))
    append(good, ledger_path=ledger)
    bad_payload = audit_ledger._entry_to_dict(good)
    bad_payload["audit_issue"] = 2
    bad_payload["timestamp_utc"] = "not-a-real-timestamp"
    with ledger.open("a", encoding="utf-8") as f:
        f.write(json.dumps(bad_payload) + "\n")
    entries = read_window(ledger_path=ledger, days=1)
    ids = [e.audit_issue for e in entries]
    assert 1 in ids
    assert 2 not in ids


def test_read_window_missing_required_field_logs_corrupt(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """A ledger row missing a required field is treated as corrupt."""
    ledger = tmp_path / "ledger.jsonl"
    # Write a row that's valid JSON but missing the doc_path field.
    ledger.write_text(
        json.dumps(
            {
                "schema_version": 1,
                "audit_issue": 9,
                "timestamp_utc": _iso(datetime.now(timezone.utc)),
                "commit_sha": "abc",
                "verdict": "NO_CHANGE_NEEDED",
                "confidence": 0.9,
                "outcome": "auto_closed",
                # doc_path intentionally missing
            }
        )
        + "\n",
        encoding="utf-8",
    )
    entries = read_window(ledger_path=ledger, days=1)
    assert entries == []
    err = capsys.readouterr().err
    assert "corrupt" in err.lower() or "skipping" in err.lower()


# ---------------------------------------------------------------------------
# Metrics: compute_triage_rate / compute_outcome_breakdown
# ---------------------------------------------------------------------------


def _populate_ledger_for_metrics(ledger: Path) -> None:
    """10-row fixture: 3 PROPOSED_EDIT, 4 JUDGMENT_REQUIRED, 2 NO_CHANGE_NEEDED, 1 RETRY_EXHAUSTED."""
    now = datetime.now(timezone.utc)
    rows = (
        ("PROPOSED_EDIT", 0.85, "auto_committed"),
        ("PROPOSED_EDIT", 0.88, "pr_filed"),
        ("PROPOSED_EDIT", 0.90, "pr_filed"),
        ("JUDGMENT_REQUIRED", 0.45, "judgment_required_posted"),
        ("JUDGMENT_REQUIRED", 0.50, "judgment_required_posted"),
        ("JUDGMENT_REQUIRED", 0.55, "judgment_required_posted"),
        ("JUDGMENT_REQUIRED", 0.60, "judgment_required_posted"),
        ("NO_CHANGE_NEEDED", 0.95, "auto_closed"),
        ("NO_CHANGE_NEEDED", 0.97, "auto_closed"),
        ("RETRY_EXHAUSTED", None, "retry_exhausted"),
    )
    for i, (verdict, conf, outcome) in enumerate(rows):
        entry = _make_entry(
            audit_issue=400 + i,
            timestamp_utc=_iso(now - timedelta(minutes=i)),
            verdict=verdict,
            confidence=conf,
            outcome=outcome,
        )
        append(entry, ledger_path=ledger)


def test_compute_triage_rate_known_ledger(tmp_path: Path) -> None:
    ledger = tmp_path / "ledger.jsonl"
    _populate_ledger_for_metrics(ledger)
    rate = compute_triage_rate(ledger_path=ledger, days=1)
    # 4 JUDGMENT_REQUIRED out of 10
    assert rate == pytest.approx(0.40)


def test_compute_triage_rate_empty(tmp_path: Path) -> None:
    ledger = tmp_path / "ledger.jsonl"
    ledger.write_text("", encoding="utf-8")
    assert compute_triage_rate(ledger_path=ledger, days=7) == 0.0


def test_compute_outcome_breakdown_known_ledger(tmp_path: Path) -> None:
    ledger = tmp_path / "ledger.jsonl"
    _populate_ledger_for_metrics(ledger)
    breakdown = compute_outcome_breakdown(ledger_path=ledger, days=1)
    assert breakdown == {
        "auto_committed": 1,
        "pr_filed": 2,
        "judgment_required_posted": 4,
        "auto_closed": 2,
        "retry_exhausted": 1,
    }


def test_compute_outcome_breakdown_empty(tmp_path: Path) -> None:
    ledger = tmp_path / "ledger.jsonl"
    ledger.write_text("", encoding="utf-8")
    assert compute_outcome_breakdown(ledger_path=ledger, days=7) == {}


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


def test_cli_help_exits_zero(capsys: pytest.CaptureFixture[str]) -> None:
    with pytest.raises(SystemExit) as excinfo:
        main(["--help"])
    assert excinfo.value.code == 0


@pytest.mark.parametrize("subcommand", ["summary", "tail"])
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
    assert "Audit ledger summary" in out
    assert "Verdicts:" in out
    assert "Outcomes:" in out
    assert "judgment_required_posted" in out


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
    # 10 entries fit within the default tail size of 10 — every one prints.
    assert "400" in out
    assert "409" in out


def test_cli_empty_ledger_returns_zero(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    ledger = tmp_path / "absent.jsonl"
    rc = main(["--ledger-path", str(ledger), "summary"])
    assert rc == 0


def test_cli_unreadable_ledger_returns_one(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    ledger = tmp_path / "ledger.jsonl"
    _populate_ledger_for_metrics(ledger)
    if os.geteuid() == 0:
        pytest.skip("permission tests are no-ops when running as root")
    ledger.chmod(0o000)
    try:
        rc = main(["--ledger-path", str(ledger), "summary"])
    finally:
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
