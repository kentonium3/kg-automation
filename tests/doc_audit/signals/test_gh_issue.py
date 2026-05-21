"""Unit tests for :class:`doc_audit.signals.gh_issue.GHIssueSignalSource`.

Lock in the priority assignments, label-filter semantics, idempotency
cache, and credential-error propagation per
``contracts/signal-source.contract.md``.

Tests patch ``subprocess.run`` (used by ``gh_issue._run_gh_issue_list``)
to return canned outputs sourced from
``tests/doc_audit/fixtures/gh_responses/``. No live ``gh`` invocation
occurs.
"""

from __future__ import annotations

import json
import subprocess
from pathlib import Path
from typing import Any

import pytest

from doc_audit.signals.gh_issue import GHIssueSignalSource


FIXTURES_DIR = (
    Path(__file__).resolve().parent.parent / "fixtures" / "gh_responses"
)


def _load_fixture(name: str) -> str:
    return (FIXTURES_DIR / f"{name}.json").read_text(encoding="utf-8")


def _completed(stdout: str) -> subprocess.CompletedProcess:
    return subprocess.CompletedProcess(
        args=["gh", "issue", "list"],
        returncode=0,
        stdout=stdout,
        stderr="",
    )


def _patch_gh(
    monkeypatch: pytest.MonkeyPatch,
    *,
    by_label: dict[str, str],
) -> list[list[Any]]:
    """Patch ``subprocess.run`` to route by ``--label <name>``.

    ``by_label`` maps label name → fixture file name (without .json).
    Returns a list to which each invocation's argv is appended so
    tests can assert on call sequencing.
    """
    calls: list[list[Any]] = []

    def fake_run(
        cmd: list[Any],
        *args: Any,
        **kwargs: Any,
    ) -> subprocess.CompletedProcess:
        calls.append(list(cmd))
        # Find the value after "--label"
        try:
            label_index = cmd.index("--label")
            label_value = cmd[label_index + 1]
        except (ValueError, IndexError):
            label_value = ""
        fixture_name = by_label.get(label_value)
        if fixture_name is None:
            # Default empty response for un-routed labels.
            return _completed("[]")
        return _completed(_load_fixture(fixture_name))

    monkeypatch.setattr(subprocess, "run", fake_run)
    return calls


# ---------------------------------------------------------------------------
# 1. Empty queue
# ---------------------------------------------------------------------------


def test_pending_empty_queue(
    tmp_config: Any,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """All three gh queries return ``[]`` → ``pending()`` returns ``[]``."""
    _patch_gh(
        monkeypatch,
        by_label={
            "audit-pending-approval": "issue_list_doc_audit_empty",
            "doc-audit": "issue_list_doc_audit_empty",
        },
    )
    source = GHIssueSignalSource(tmp_config)
    assert source.pending() == []


# ---------------------------------------------------------------------------
# 2. One Doc audit signal
# ---------------------------------------------------------------------------


def test_pending_one_doc_audit(
    tmp_config: Any,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """``Doc audit:`` issue → one ``doc_audit`` Signal with priority 20."""
    _patch_gh(
        monkeypatch,
        by_label={
            "audit-pending-approval": "issue_list_doc_audit_empty",
            "doc-audit": "issue_list_doc_audit_basic",
        },
    )
    source = GHIssueSignalSource(tmp_config)
    signals = source.pending()

    # Fixture has 2 Doc-audit issues (no Weekly). We expect both,
    # both at kind=doc_audit priority=20.
    doc_audits = [s for s in signals if s.kind == "doc_audit"]
    assert len(doc_audits) == 2
    for sig in doc_audits:
        assert sig.priority == 20
        assert sig.source == "gh_issue"
        assert sig.id.startswith("gh-issue:")
        assert sig.payload["issue_number"] in (4242, 4250)
        assert sig.payload["title"].startswith("Doc audit:")
        assert "area_labels" in sig.payload
    assert all(s.kind != "weekly_doc_audit" for s in signals)


# ---------------------------------------------------------------------------
# 3. One Weekly doc audit signal
# ---------------------------------------------------------------------------


def test_pending_one_weekly(
    tmp_config: Any,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """``Weekly doc audit —`` issue → ``weekly_doc_audit`` priority 30."""
    _patch_gh(
        monkeypatch,
        by_label={
            "audit-pending-approval": "issue_list_doc_audit_empty",
            "doc-audit": "issue_list_weekly_audit",
        },
    )
    source = GHIssueSignalSource(tmp_config)
    signals = source.pending()

    weekly = [s for s in signals if s.kind == "weekly_doc_audit"]
    assert len(weekly) == 1
    assert weekly[0].priority == 30
    assert weekly[0].payload["title"].startswith("Weekly doc audit —")
    # The same fixture should NOT also yield a doc_audit signal
    # (the title prefix filter is exclusive).
    assert all(s.kind != "doc_audit" for s in signals)


# ---------------------------------------------------------------------------
# 4. Pending approval WITH decision label
# ---------------------------------------------------------------------------


def test_pending_pending_approval_with_decision(
    tmp_config: Any,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """audit-pending-approval + audit-approve → priority 10 signal."""
    _patch_gh(
        monkeypatch,
        by_label={
            "audit-pending-approval": (
                "issue_list_pending_approval_with_decision"
            ),
            "doc-audit": "issue_list_doc_audit_empty",
        },
    )
    source = GHIssueSignalSource(tmp_config)
    signals = source.pending()

    approvals = [s for s in signals if s.kind == "pending_approval"]
    assert len(approvals) == 1
    sig = approvals[0]
    assert sig.priority == 10
    assert sig.source == "gh_issue"
    assert sig.payload["issue_number"] == 4243
    assert "audit-approve" in sig.payload["labels"]
    assert sig.payload["area_labels"] == ["area/felix-core"]


# ---------------------------------------------------------------------------
# 5. Pending approval WITHOUT decision label
# ---------------------------------------------------------------------------


def test_pending_pending_approval_without_decision(
    tmp_config: Any,
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    """A pending-approval with no decision label is skipped."""
    # Synthesize a fixture inline with NO decision label.
    no_decision_fixture = tmp_path / "no_decision.json"
    no_decision_fixture.write_text(
        json.dumps(
            [
                {
                    "number": 4280,
                    "title": "Pending approval: Tier-B edits for #4270",
                    "body": "...",
                    "labels": [
                        {"name": "audit-pending-approval"},
                        {"name": "area/felix-core"},
                    ],
                    "createdAt": "2026-05-20T12:00:00Z",
                }
            ]
        ),
        encoding="utf-8",
    )

    def fake_run(cmd, *args, **kwargs):  # type: ignore[no-untyped-def]
        if "--label" in cmd:
            label = cmd[cmd.index("--label") + 1]
            if label == "audit-pending-approval":
                return _completed(
                    no_decision_fixture.read_text(encoding="utf-8")
                )
        return _completed("[]")

    monkeypatch.setattr(subprocess, "run", fake_run)
    source = GHIssueSignalSource(tmp_config)
    signals = source.pending()
    # No pending_approval signal should be emitted.
    assert [s for s in signals if s.kind == "pending_approval"] == []


# ---------------------------------------------------------------------------
# 6. Skip Doc audit: with status:in-progress
# ---------------------------------------------------------------------------


def test_pending_skips_in_progress(
    tmp_config: Any,
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    """``Doc audit:`` issues with ``status:in-progress`` are skipped."""
    in_progress_fixture = tmp_path / "in_progress.json"
    in_progress_fixture.write_text(
        json.dumps(
            [
                {
                    "number": 4290,
                    "title": "Doc audit: abc1234 (felix-core)",
                    "body": "...",
                    "labels": [
                        {"name": "doc-audit"},
                        {"name": "status:in-progress"},
                    ],
                    "createdAt": "2026-05-20T15:00:00Z",
                },
                {
                    "number": 4291,
                    "title": "Doc audit: def5678 (vikunja)",
                    "body": "...",
                    "labels": [
                        {"name": "doc-audit"},
                    ],
                    "createdAt": "2026-05-20T15:30:00Z",
                },
            ]
        ),
        encoding="utf-8",
    )

    def fake_run(cmd, *args, **kwargs):  # type: ignore[no-untyped-def]
        if "--label" in cmd:
            label = cmd[cmd.index("--label") + 1]
            if label == "doc-audit":
                return _completed(
                    in_progress_fixture.read_text(encoding="utf-8")
                )
        return _completed("[]")

    monkeypatch.setattr(subprocess, "run", fake_run)
    source = GHIssueSignalSource(tmp_config)
    signals = source.pending()
    doc_audits = [s for s in signals if s.kind == "doc_audit"]
    # Only #4291 (not in-progress) should be emitted.
    assert len(doc_audits) == 1
    assert doc_audits[0].payload["issue_number"] == 4291


# ---------------------------------------------------------------------------
# 7. Idempotency: pending() twice returns same list
# ---------------------------------------------------------------------------


def test_pending_idempotent(
    tmp_config: Any,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """``pending()`` cached after first call — second call same result."""
    calls = _patch_gh(
        monkeypatch,
        by_label={
            "audit-pending-approval": "issue_list_doc_audit_empty",
            "doc-audit": "issue_list_doc_audit_basic",
        },
    )
    source = GHIssueSignalSource(tmp_config)
    first = source.pending()
    second = source.pending()
    assert first == second
    # Three gh calls happened on the first invocation; the cache
    # prevents the second invocation from issuing more.
    assert len(calls) == 3


# ---------------------------------------------------------------------------
# 8. commit() is a no-op
# ---------------------------------------------------------------------------


def test_commit_noop(
    tmp_config: Any,
    monkeypatch: pytest.MonkeyPatch,
    sample_signal_gh_issue: Any,
) -> None:
    """``commit()`` returns None and never invokes gh."""
    calls = _patch_gh(
        monkeypatch,
        by_label={
            "audit-pending-approval": "issue_list_doc_audit_empty",
            "doc-audit": "issue_list_doc_audit_empty",
        },
    )
    source = GHIssueSignalSource(tmp_config)
    # Trigger one fetch so we know what the baseline call count is.
    source.pending()
    baseline = len(calls)

    result = source.commit(sample_signal_gh_issue, "success")
    assert result is None
    # No new gh invocations.
    assert len(calls) == baseline


# ---------------------------------------------------------------------------
# 9. pending() re-raises subprocess errors
# ---------------------------------------------------------------------------


def test_pending_raises_on_gh_error(
    tmp_config: Any,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """``gh`` non-zero exit → ``subprocess.CalledProcessError`` propagates."""

    def fake_run(cmd, *args, **kwargs):  # type: ignore[no-untyped-def]
        raise subprocess.CalledProcessError(
            returncode=1,
            cmd=cmd,
            output="",
            stderr="HTTP 401: Bad credentials",
        )

    monkeypatch.setattr(subprocess, "run", fake_run)
    source = GHIssueSignalSource(tmp_config)
    with pytest.raises(subprocess.CalledProcessError):
        source.pending()


# ---------------------------------------------------------------------------
# 10. Bonus: non-JSON gh output → ValueError
# ---------------------------------------------------------------------------


def test_pending_raises_on_non_json_output(
    tmp_config: Any,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Garbled ``gh`` stdout raises a clear error rather than silently empty."""

    def fake_run(cmd, *args, **kwargs):  # type: ignore[no-untyped-def]
        return _completed("not-json-at-all")

    monkeypatch.setattr(subprocess, "run", fake_run)
    source = GHIssueSignalSource(tmp_config)
    with pytest.raises(ValueError, match="non-JSON"):
        source.pending()
