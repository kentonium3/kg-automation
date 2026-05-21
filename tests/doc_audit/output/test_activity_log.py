"""Unit tests for ``doc_audit.output.activity_log``.

Verifies the append-only writer against the canonical-format fixture
at ``tests/doc_audit/output/fixtures/activity_log_sample.txt`` captured
from office2 on 2026-05-20. Format drift is operator-visible (Kent
reads these in the Obsidian vault), so byte-for-byte equivalence with
the fixture is load-bearing.
"""
from __future__ import annotations

from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

import pytest

from doc_audit.data_model import AuditIssue, TickResult
from doc_audit.output import activity_log


FIXTURES_DIR = Path(__file__).resolve().parent / "fixtures"
CANONICAL_SAMPLE_PATH = FIXTURES_DIR / "activity_log_sample.txt"


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_audit(
    issue_number: int = 347,
    title: str = "Doc audit: cf0e0b9 (area/biz-ops)",
    in_scope_docs: list[str] | None = None,
) -> AuditIssue:
    if in_scope_docs is None:
        in_scope_docs = ["docs/a.md", "docs/b.md", "docs/c.md"]
    return AuditIssue(
        issue_number=issue_number,
        title=title,
        is_weekly=False,
        triggering_sha="cf0e0b9",
        area_labels=["area/biz-ops"],
        in_scope_docs=in_scope_docs,
        lock_acquired_at_utc=None,
    )


def _make_result() -> TickResult:
    return TickResult(
        started_utc="2026-05-20T19:15:33Z",
        ended_utc="2026-05-20T19:15:34Z",
        status="success",
        signals_seen=1,
        signals_processed=1,
        tier_a_commits=[],
        pending_approvals_filed=[],
        pending_approvals_applied=[],
        debt_filed=[],
        drift_events_consumed=0,
        errors=[],
        judgment_calls={},
        token_usage={},
    )


@pytest.fixture
def frozen_now(monkeypatch):
    """Freeze ``_now_local`` at the canonical fixture's timestamp."""
    frozen = datetime(2026, 5, 20, 15, 15, 33, tzinfo=ZoneInfo("America/New_York"))
    monkeypatch.setattr(activity_log, "_now_local", lambda: frozen)
    return frozen


@pytest.fixture
def canonical_outcome() -> dict:
    """Per-audit outcome dict matching the captured fixture."""
    return {
        "in_scope_docs": 3,
        "docs_reviewed": 3,
        "hc_edits_proposed": 0,
        "pending_approval_issue": "none",
        "edits_committed": 0,
        "debt_issues_created": 0,
        "debt_issue_refs": "",
        "missing_artifacts": 0,
        "human_review_items": 0,
        "decision_applied": "none",
        "error_count": 0,
    }


# ---------------------------------------------------------------------------
# Byte-for-byte fixture match
# ---------------------------------------------------------------------------


def test_canonical_fixture_present():
    """Sanity check: the captured fixture exists and is non-empty."""
    assert CANONICAL_SAMPLE_PATH.is_file()
    content = CANONICAL_SAMPLE_PATH.read_text(encoding="utf-8")
    assert content
    assert content.startswith("## Audit run — 2026-05-20T15:15:33-0400\n")


def test_single_entry_matches_canonical_fixture_byte_for_byte(
    tmp_config, frozen_now, canonical_outcome
):
    """One append produces a file equal to the canonical sample.

    Cycle 2 (WP05): each entry now ends with an inter-entry blank
    line (``\\n\\n``) so consecutive entries render with one blank
    line between them. The captured fixture is a single end-of-file
    snapshot that does NOT include that trailing blank line, so the
    expected content is ``fixture + "\\n"``.
    """
    audit = _make_audit()
    log_path = activity_log.append_audit_entry(
        tmp_config, _make_result(), audit, canonical_outcome
    )
    actual = log_path.read_text(encoding="utf-8")
    expected = CANONICAL_SAMPLE_PATH.read_text(encoding="utf-8") + "\n"
    assert actual == expected, (
        "Activity-log output drifted from canonical fixture "
        "(expected fixture + trailing blank line).\n"
        f"--- expected ---\n{expected!r}\n--- actual ---\n{actual!r}"
    )


# ---------------------------------------------------------------------------
# File lifecycle
# ---------------------------------------------------------------------------


def test_file_created_empty_then_appended_no_frontmatter(
    tmp_config, frozen_now, canonical_outcome
):
    """First call creates an empty file; no YAML frontmatter prepended."""
    audit = _make_audit()
    log_path = activity_log.append_audit_entry(
        tmp_config, _make_result(), audit, canonical_outcome
    )
    content = log_path.read_text(encoding="utf-8")
    # The file should start with the audit entry header, NOT '---' (YAML).
    assert content.startswith("## Audit run —")
    assert "---\n" not in content.splitlines(keepends=True)[:1]


def test_filename_uses_local_tz_date(tmp_config, frozen_now, canonical_outcome):
    """Filename uses local-tz date (2026-05-20 from America/New_York)."""
    audit = _make_audit()
    log_path = activity_log.append_audit_entry(
        tmp_config, _make_result(), audit, canonical_outcome
    )
    assert log_path.name == "doc-auditor-2026-05-20.md"
    assert log_path.parent == Path(tmp_config.paths.activity_log_dir)


def test_multiple_appends_accumulate(
    tmp_config, monkeypatch, canonical_outcome
):
    """Multiple appends preserve all entries in order."""
    # Two different timestamps, same day.
    ts1 = datetime(2026, 5, 20, 10, 0, 0, tzinfo=ZoneInfo("America/New_York"))
    ts2 = datetime(2026, 5, 20, 14, 30, 0, tzinfo=ZoneInfo("America/New_York"))
    times = iter([ts1, ts2])
    monkeypatch.setattr(activity_log, "_now_local", lambda: next(times))

    audit_a = _make_audit(issue_number=100, title="Doc audit: aaa (area/x)")
    audit_b = _make_audit(issue_number=101, title="Doc audit: bbb (area/y)")

    log_path = activity_log.append_audit_entry(
        tmp_config, _make_result(), audit_a, canonical_outcome
    )
    log_path2 = activity_log.append_audit_entry(
        tmp_config, _make_result(), audit_b, canonical_outcome
    )

    assert log_path == log_path2  # same day → same file
    content = log_path.read_text(encoding="utf-8")
    assert "## Audit run — 2026-05-20T10:00:00-0400" in content
    assert "## Audit run — 2026-05-20T14:30:00-0400" in content
    assert content.count("## Audit run") == 2
    # Issue numbers appear in entry order.
    idx_a = content.index("Audit issue: #100")
    idx_b = content.index("Audit issue: #101")
    assert idx_a < idx_b


def test_append_multiple_audits_has_blank_line_between_entries(
    tmp_config, monkeypatch, canonical_outcome
):
    """Two consecutive entries are separated by exactly one blank line.

    Cycle 2 of WP05 review (Codex finding): the WP05 validation
    checklist requires one blank line between subsequent audit
    entries so the daily log is operator-readable in the Obsidian
    vault. Each entry must end with ``\\n\\n``; the resulting file
    must contain the literal pattern ``\\n\\n## Audit run`` between
    entries (single blank line, not zero, not two).
    """
    ts1 = datetime(2026, 5, 20, 15, 15, 33, tzinfo=ZoneInfo("America/New_York"))
    ts2 = datetime(2026, 5, 20, 15, 20, 1, tzinfo=ZoneInfo("America/New_York"))
    times = iter([ts1, ts2])
    monkeypatch.setattr(activity_log, "_now_local", lambda: next(times))

    audit_a = _make_audit(issue_number=347)
    audit_b = _make_audit(
        issue_number=348,
        title="Doc audit: deadbee (area/biz-ops)",
    )

    log_path = activity_log.append_audit_entry(
        tmp_config, _make_result(), audit_a, canonical_outcome
    )
    activity_log.append_audit_entry(
        tmp_config, _make_result(), audit_b, canonical_outcome
    )

    content = log_path.read_text(encoding="utf-8")

    # Exactly one blank line between the two ``## Audit run`` blocks:
    # the inter-entry separator is ``\n\n## Audit run`` (single
    # blank line), not ``\n## Audit run`` (no blank line) or
    # ``\n\n\n## Audit run`` (two blank lines).
    assert "\n\n## Audit run — 2026-05-20T15:20:01-0400" in content, (
        "Expected one blank line between consecutive entries; "
        f"actual content:\n{content!r}"
    )
    assert "\n\n\n## Audit run" not in content, (
        "Found two blank lines between entries; expected exactly one."
    )
    # Sanity: both entries are present and headed correctly.
    assert content.count("## Audit run") == 2
    assert "- Audit issue: #347\n" in content
    assert "- Audit issue: #348\n" in content

    # Multi-entry shape derived from the single-entry fixture: two
    # copies of the fixture body, each ending with ``\n\n``. The
    # captured fixture is one end-of-file snapshot (single ``\n``);
    # the writer adds an inter-entry blank line to it.
    fixture_body = CANONICAL_SAMPLE_PATH.read_text(encoding="utf-8")
    entry1 = fixture_body + "\n"  # +blank line
    entry2 = (
        fixture_body
        .replace("2026-05-20T15:15:33-0400", "2026-05-20T15:20:01-0400")
        .replace("Audit issue: #347", "Audit issue: #348")
        .replace(
            "Title: Doc audit: cf0e0b9 (area/biz-ops)",
            "Title: Doc audit: deadbee (area/biz-ops)",
        )
    ) + "\n"
    assert content == entry1 + entry2, (
        "Multi-entry layout drifted from the expected "
        "fixture-derived shape.\n"
        f"--- expected ---\n{(entry1 + entry2)!r}\n"
        f"--- actual ---\n{content!r}"
    )


def test_appends_to_existing_file_do_not_reinit(
    tmp_config, frozen_now, canonical_outcome
):
    """Pre-existing file is not re-initialized (content preserved)."""
    activity_dir = Path(tmp_config.paths.activity_log_dir)
    existing = activity_dir / "doc-auditor-2026-05-20.md"
    existing.write_text("PRESERVED-CONTENT\n", encoding="utf-8")

    audit = _make_audit()
    log_path = activity_log.append_audit_entry(
        tmp_config, _make_result(), audit, canonical_outcome
    )
    content = log_path.read_text(encoding="utf-8")
    assert content.startswith("PRESERVED-CONTENT\n")
    assert "## Audit run —" in content


def test_creates_parent_dir_if_missing(
    tmp_config, monkeypatch, frozen_now, canonical_outcome, tmp_path
):
    """If the activity_log_dir doesn't exist yet, it's created."""
    # Point at a not-yet-existing dir.
    from dataclasses import replace as _replace
    nested = tmp_path / "nested" / "logs"
    new_paths = _replace(tmp_config.paths, activity_log_dir=str(nested))
    new_config = _replace(tmp_config, paths=new_paths)

    audit = _make_audit()
    log_path = activity_log.append_audit_entry(
        new_config, _make_result(), audit, canonical_outcome
    )
    assert log_path.exists()
    assert log_path.parent == nested


# ---------------------------------------------------------------------------
# Format invariants
# ---------------------------------------------------------------------------


def test_timestamp_offset_has_no_colon(tmp_config, frozen_now, canonical_outcome):
    """TZ offset is ``-0400`` (no colon), matching the captured fixture."""
    audit = _make_audit()
    log_path = activity_log.append_audit_entry(
        tmp_config, _make_result(), audit, canonical_outcome
    )
    content = log_path.read_text(encoding="utf-8")
    # The first header line must end with `-0400` or `-0500`, NOT `-04:00`.
    first_header = content.splitlines()[0]
    assert first_header.endswith("-0400") or first_header.endswith("-0500")
    assert ":00" not in first_header.split("T")[-1].split(":", 1)[1].split("-")[-1]


def test_entry_with_defaulted_outcome_fields(
    tmp_config, frozen_now
):
    """Outcome dict with no recognized keys still produces a valid entry."""
    audit = _make_audit(in_scope_docs=["docs/x.md"])
    log_path = activity_log.append_audit_entry(
        tmp_config, _make_result(), audit, {}
    )
    content = log_path.read_text(encoding="utf-8")
    # In-scope docs falls back to len(audit.in_scope_docs)
    assert "In-scope docs: 1" in content
    assert "Docs reviewed: 0" in content
    assert "Pending-approval issue filed: none" in content
    assert "Decision applied this tick: none" in content
    assert "Errors: 0" in content


def test_entry_with_debt_refs_appended(
    tmp_config, frozen_now
):
    """When ``debt_issue_refs`` is non-empty, it's appended after the count."""
    audit = _make_audit()
    log_path = activity_log.append_audit_entry(
        tmp_config,
        _make_result(),
        audit,
        {"debt_issues_created": 2, "debt_issue_refs": "#341, #342"},
    )
    content = log_path.read_text(encoding="utf-8")
    assert "- Debt issues created: 2 #341, #342" in content


def test_entry_with_empty_debt_refs_omits_tail(
    tmp_config, frozen_now
):
    """Empty ``debt_issue_refs`` does NOT add a trailing space."""
    audit = _make_audit()
    log_path = activity_log.append_audit_entry(
        tmp_config,
        _make_result(),
        audit,
        {"debt_issues_created": 0, "debt_issue_refs": ""},
    )
    content = log_path.read_text(encoding="utf-8")
    assert "- Debt issues created: 0\n" in content
    # No trailing space before the newline.
    assert "- Debt issues created: 0 \n" not in content
