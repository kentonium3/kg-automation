"""Unit tests for ``doc_audit.run`` to lift coverage above the 80% bar.

These tests focus on the smaller pieces of the driver (CLI flags,
parsing helpers, rate-limit detection, dispatch fall-throughs) that
the end-to-end integration tests don't exercise.

The integration tests in
``tests/doc_audit/test_integration_*.py`` cover the orchestration
loop's main paths; this file targets the corner branches.
"""
from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path
from typing import Any

import pytest

SCRIPTS = Path(__file__).resolve().parent.parent.parent / "scripts"
if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))

from doc_audit import run  # noqa: E402
from doc_audit.data_model import AuditIssue, Signal, TickResult  # noqa: E402
from doc_audit.helpers.handle_audit_routing import RoutingResult  # noqa: E402


# ---------------------------------------------------------------------------
# CLI flags
# ---------------------------------------------------------------------------


def test_version_flag_short_circuits(capsys: pytest.CaptureFixture):
    """``--version`` prints version and exits 0 WITHOUT loading config."""
    rc = run.main(["--version"])
    captured = capsys.readouterr()
    assert rc == 0
    assert run.__version__ in captured.out


def test_bad_config_exits_1(capsys: pytest.CaptureFixture, tmp_path: Path):
    """A missing config file exits 1 with a FATAL message on stderr."""
    bogus = tmp_path / "does-not-exist.toml"
    rc = run.main(["--config", str(bogus)])
    captured = capsys.readouterr()
    assert rc == 1
    assert "FATAL" in captured.err
    assert "config" in captured.err.lower()


# ---------------------------------------------------------------------------
# Time helpers
# ---------------------------------------------------------------------------


def test_now_iso_z_suffix():
    s = run._now_iso()
    assert s.endswith("Z")
    # Roughly 20 chars: 2026-05-20T12:34:56Z
    assert len(s) == 20


def test_compute_next_tick_z_suffix():
    s = run._compute_next_tick()
    assert s.endswith("Z")
    # Minutes and seconds are zeroed.
    assert s.endswith(":00:00Z")


# ---------------------------------------------------------------------------
# Rate-limit detection
# ---------------------------------------------------------------------------


def test_is_rate_limited_via_stderr_pattern():
    exc = subprocess.CalledProcessError(
        returncode=1,
        cmd=["gh"],
        output="",
        stderr="HTTP 403: API rate limit exceeded for installation",
    )
    assert run._is_rate_limited(exc) is True


def test_is_rate_limited_via_secondary_pattern():
    exc = subprocess.CalledProcessError(
        returncode=1,
        cmd=["gh"],
        output="You have triggered a secondary rate limit.",
        stderr="",
    )
    assert run._is_rate_limited(exc) is True


def test_is_rate_limited_via_header():
    exc = subprocess.CalledProcessError(
        returncode=1, cmd=["gh"], output="", stderr="X-RateLimit-Remaining: 0\n"
    )
    assert run._is_rate_limited(exc) is True


def test_is_rate_limited_via_class_name():
    class RateLimitError(Exception):
        pass

    assert run._is_rate_limited(RateLimitError("anthropic-style")) is True


def test_is_rate_limited_false_on_other_error():
    exc = subprocess.CalledProcessError(
        returncode=1, cmd=["gh"], output="", stderr="HTTP 500: server error"
    )
    assert run._is_rate_limited(exc) is False


# ---------------------------------------------------------------------------
# Audit parsing from payload
# ---------------------------------------------------------------------------


def test_parse_audit_from_payload_basic():
    payload = {
        "issue_number": 4242,
        "title": "Doc audit: abc1234 (felix-core)",
        "body": "",
        "labels": ["doc-audit", "area/felix-core"],
        "area_labels": ["area/felix-core"],
    }
    audit = run._parse_audit_from_payload(payload)
    assert audit.issue_number == 4242
    assert audit.triggering_sha == "abc1234"
    assert audit.is_weekly is False
    assert audit.area_labels == ["area/felix-core"]


def test_parse_audit_from_payload_weekly():
    payload = {
        "issue_number": 4300,
        "title": "Weekly doc audit — 2026-05-19",
        "area_labels": [],
    }
    audit = run._parse_audit_from_payload(payload)
    assert audit.is_weekly is True
    assert audit.triggering_sha is None


def test_parse_audit_from_payload_unparseable_title():
    payload = {
        "issue_number": 5555,
        "title": "Doc audit: (no sha)",  # SHA missing
    }
    audit = run._parse_audit_from_payload(payload)
    # Falls back gracefully — no crash, no SHA.
    assert audit.issue_number == 5555


# ---------------------------------------------------------------------------
# Pending-approval cross-reference index
# ---------------------------------------------------------------------------


def _make_pa_signal(
    *,
    pa_number: int,
    title: str = "",
    body: str = "",
) -> Signal:
    return Signal(
        id=f"gh-issue:{pa_number}",
        source="gh_issue",
        kind="pending_approval",
        priority=10,
        payload={
            "issue_number": pa_number,
            "title": title,
            "body": body,
            "labels": ["audit-pending-approval", "audit-approve"],
            "area_labels": ["area/felix-core"],
        },
        created_utc="2026-05-20T10:00:00Z",
    )


def test_pa_index_from_title():
    sig = _make_pa_signal(
        pa_number=7001,
        title="Audit #6500: pending approval — 1 edit(s)",
        body="",
    )
    index = run._build_pending_approval_index([sig])
    assert index == {6500: 7001}


def test_pa_index_from_body_refs():
    sig = _make_pa_signal(
        pa_number=7002,
        title="Pending approval",
        body="Refs #6501 originating audit",
    )
    index = run._build_pending_approval_index([sig])
    assert index == {6501: 7002}


def test_pa_index_ignores_non_pa_signals():
    audit_sig = Signal(
        id="gh-issue:9999",
        source="gh_issue",
        kind="doc_audit",
        priority=20,
        payload={"issue_number": 9999, "title": "Doc audit: xyz"},
        created_utc="2026-05-20T10:00:00Z",
    )
    pa_sig = _make_pa_signal(
        pa_number=7003, title="Audit #6502: pending approval", body=""
    )
    index = run._build_pending_approval_index([audit_sig, pa_sig])
    assert index == {6502: 7003}


def test_pa_index_skips_unparseable():
    sig = _make_pa_signal(
        pa_number=7004, title="No audit ref here", body="No refs either"
    )
    assert run._build_pending_approval_index([sig]) == {}


# ---------------------------------------------------------------------------
# Source construction
# ---------------------------------------------------------------------------


def test_build_sources_honors_source_flag(tmp_config: Any):
    import argparse
    args = argparse.Namespace(source="gh_issue", dry_run=False)
    sources = run._build_sources(tmp_config, args)
    assert len(sources) == 1
    assert sources[0].name == "gh_issue"


def test_build_sources_default_yields_both(tmp_config: Any):
    import argparse
    args = argparse.Namespace(source=None, dry_run=False)
    sources = run._build_sources(tmp_config, args)
    names = sorted(s.name for s in sources)
    assert names == ["drift_event", "gh_issue"]


def test_build_sources_drift_only(tmp_config: Any):
    import argparse
    args = argparse.Namespace(source="drift_event", dry_run=False)
    sources = run._build_sources(tmp_config, args)
    assert len(sources) == 1
    assert sources[0].name == "drift_event"


# ---------------------------------------------------------------------------
# Dispatch: unknown kind
# ---------------------------------------------------------------------------


def test_process_signal_unknown_kind_logs_error(tmp_config: Any):
    import argparse
    args = argparse.Namespace(source=None, dry_run=False)
    result = _empty_result()
    sig = Signal(
        id="gh-issue:1",
        source="gh_issue",
        kind="mystery",
        priority=99,
        payload={},
        created_utc="2026-05-20T10:00:00Z",
    )
    run._process_signal(sig, tmp_config, args, result)
    assert any("unknown signal kind" in e for e in result.errors)


# ---------------------------------------------------------------------------
# Self-apply gate
# ---------------------------------------------------------------------------


def test_pending_approval_self_apply_blocked(
    tmp_config: Any,
    monkeypatch: pytest.MonkeyPatch,
    mock_anthropic: Any,
):
    """When the timeline's most recent decision-label event was applied
    by the bot's own identity, the gate REFUSES the decision and strips
    the label. Per SKILL.md §8.6 (actor-verification): the check
    targets the labeled-event actor, NOT the issue author.

    Production conditions reflected by this fixture:
    - The bot (``kg-felix-bot``) is the AUTHOR of every
      ``audit-pending-approval`` issue (because the bot files them).
    - The gate must look at the timeline's labeled event, not at the
      issue author, to decide self-apply.
    - In this fixture the labeled-event actor IS the bot → gate trips.
    """
    pa = [
        {
            "number": 7100,
            "title": "Audit #6700: pending approval — 1 edit(s)",
            "body": "Refs #6700",
            "labels": [
                {"name": "audit-pending-approval"},
                {"name": "audit-approve"},
            ],
            "createdAt": "2026-05-20T10:00:00Z",
        }
    ]
    # Timeline: the most recent decision-label event was applied by the
    # bot itself → SELF-APPLY → gate violation.
    timeline_jq_result = {
        "label": "audit-approve",
        "actor": "kg-felix-bot",
        "at": "2026-05-20T10:05:00Z",
    }

    calls: list[list[str]] = []

    def fake_run_cmd(cmd, *args, **kwargs):
        cmd = list(cmd)
        calls.append(cmd)
        if len(cmd) >= 3 and cmd[1] == "issue" and cmd[2] == "list":
            labels = [
                cmd[i + 1] for i, tok in enumerate(cmd)
                if tok == "--label" and i + 1 < len(cmd)
            ]
            if "audit-pending-approval" in labels:
                return subprocess.CompletedProcess(
                    args=cmd, returncode=0, stdout=json.dumps(pa), stderr=""
                )
            return subprocess.CompletedProcess(
                args=cmd, returncode=0, stdout="[]", stderr=""
            )
        # Actor lookup now uses `gh api .../timeline`, NOT gh issue view.
        if (
            len(cmd) >= 3 and cmd[1] == "api"
            and "/timeline" in (cmd[2] or "")
        ):
            return subprocess.CompletedProcess(
                args=cmd, returncode=0,
                stdout=json.dumps(timeline_jq_result),
                stderr="",
            )
        return subprocess.CompletedProcess(
            args=cmd, returncode=0, stdout="", stderr=""
        )

    monkeypatch.setattr(subprocess, "run", fake_run_cmd)

    config_path = (
        Path(tmp_config.llm.api_key_path).parent / "config.toml"
    )
    rc = run.main(["--config", str(config_path)])

    assert rc in (0, 2)
    tick = json.loads(
        Path(tmp_config.paths.tick_signal_path).read_text(encoding="utf-8")
    )
    # Self-apply marker recorded
    assert any(
        "self-apply" in e.lower() for e in tick["errors"]
    )
    # Label removed (an edit --remove-label was issued for #7100)
    label_removals = [
        c for c in calls
        if len(c) >= 5 and c[1] == "issue" and c[2] == "edit"
        and c[3] == "7100" and "--remove-label" in c
    ]
    assert label_removals, f"expected label removal; got {calls!r}"
    # No close call for the pending-approval — the gate refused it.
    closes = [
        c for c in calls
        if len(c) >= 3 and c[1] == "issue" and c[2] == "close"
    ]
    assert not closes, f"unexpected close; got {closes!r}"


def test_pending_approval_human_approval_allowed_despite_bot_authored_issue(
    tmp_config: Any,
    monkeypatch: pytest.MonkeyPatch,
    mock_anthropic: Any,
):
    """Regression for the cycle-2 critical bug: the bot files every
    ``audit-pending-approval`` issue, so the AUTHOR is always the bot.
    The gate must NOT reject on author identity — it must inspect the
    timeline's most recent decision-label event's actor.

    This fixture mocks PRODUCTION conditions: the bot is the issue
    author, but the labeled-event actor is a human → must process.
    """
    pa = [
        {
            "number": 7101,
            "title": "Audit #6701: pending approval — 1 edit(s)",
            "body": "Refs #6701",
            # NOTE: the bot is the author — production reality.
            # The previous (buggy) gate would falsely reject here.
            "author": {"login": "kg-felix-bot"},
            "labels": [
                {"name": "audit-pending-approval"},
                {"name": "audit-approve"},
            ],
            "createdAt": "2026-05-20T11:00:00Z",
        }
    ]
    # The timeline's most recent decision-label event was applied by a
    # human (kentonium3) → gate allows processing.
    timeline_jq_result = {
        "label": "audit-approve",
        "actor": "kentonium3",
        "at": "2026-05-20T11:05:00Z",
    }

    calls: list[list[str]] = []

    def fake_run_cmd(cmd, *args, **kwargs):
        cmd = list(cmd)
        calls.append(cmd)
        if len(cmd) >= 3 and cmd[1] == "issue" and cmd[2] == "list":
            labels = [
                cmd[i + 1] for i, tok in enumerate(cmd)
                if tok == "--label" and i + 1 < len(cmd)
            ]
            if "audit-pending-approval" in labels:
                return subprocess.CompletedProcess(
                    args=cmd, returncode=0, stdout=json.dumps(pa), stderr=""
                )
            return subprocess.CompletedProcess(
                args=cmd, returncode=0, stdout="[]", stderr=""
            )
        if (
            len(cmd) >= 3 and cmd[1] == "api"
            and "/timeline" in (cmd[2] or "")
        ):
            return subprocess.CompletedProcess(
                args=cmd, returncode=0,
                stdout=json.dumps(timeline_jq_result),
                stderr="",
            )
        return subprocess.CompletedProcess(
            args=cmd, returncode=0, stdout="", stderr=""
        )

    monkeypatch.setattr(subprocess, "run", fake_run_cmd)

    config_path = (
        Path(tmp_config.llm.api_key_path).parent / "config.toml"
    )
    rc = run.main(["--config", str(config_path)])

    assert rc == 0
    tick = json.loads(
        Path(tmp_config.paths.tick_signal_path).read_text(encoding="utf-8")
    )
    # Self-apply gate did NOT trip (no self-apply error).
    assert not any(
        "self-apply" in e.lower() for e in tick["errors"]
    ), f"unexpected self-apply rejection: {tick['errors']!r}"
    # The pending-approval is recorded as applied.
    assert 7101 in tick["tick"]["pending_approvals_applied"]
    # Close calls were issued (PA + originating audit).
    closes = [
        c for c in calls
        if len(c) >= 3 and c[1] == "issue" and c[2] == "close"
    ]
    closed_numbers = {c[3] for c in closes}
    assert "7101" in closed_numbers


def test_pending_approval_actor_verification_uses_timeline(
    tmp_config: Any,
    monkeypatch: pytest.MonkeyPatch,
    mock_anthropic: Any,
):
    """The actor-verification check MUST call ``gh api .../timeline``,
    not ``gh issue view``. Explicit regression for the cycle-2 bug
    class: tests that mocked ``gh issue view --json author`` masked a
    production-only failure mode (bot is always the author).
    """
    pa = [
        {
            "number": 7102,
            "title": "Audit #6702: pending approval — 1 edit(s)",
            "body": "Refs #6702",
            "author": {"login": "kg-felix-bot"},
            "labels": [
                {"name": "audit-pending-approval"},
                {"name": "audit-approve"},
            ],
            "createdAt": "2026-05-20T12:00:00Z",
        }
    ]
    timeline_jq_result = {
        "label": "audit-approve",
        "actor": "kentonium3",
        "at": "2026-05-20T12:05:00Z",
    }

    calls: list[list[str]] = []

    def fake_run_cmd(cmd, *args, **kwargs):
        cmd = list(cmd)
        calls.append(cmd)
        if len(cmd) >= 3 and cmd[1] == "issue" and cmd[2] == "list":
            labels = [
                cmd[i + 1] for i, tok in enumerate(cmd)
                if tok == "--label" and i + 1 < len(cmd)
            ]
            if "audit-pending-approval" in labels:
                return subprocess.CompletedProcess(
                    args=cmd, returncode=0, stdout=json.dumps(pa), stderr=""
                )
            return subprocess.CompletedProcess(
                args=cmd, returncode=0, stdout="[]", stderr=""
            )
        if (
            len(cmd) >= 3 and cmd[1] == "api"
            and "/timeline" in (cmd[2] or "")
        ):
            return subprocess.CompletedProcess(
                args=cmd, returncode=0,
                stdout=json.dumps(timeline_jq_result),
                stderr="",
            )
        return subprocess.CompletedProcess(
            args=cmd, returncode=0, stdout="", stderr=""
        )

    monkeypatch.setattr(subprocess, "run", fake_run_cmd)

    config_path = (
        Path(tmp_config.llm.api_key_path).parent / "config.toml"
    )
    rc = run.main(["--config", str(config_path)])

    assert rc == 0
    # CRITICAL: the actor check went through `gh api .../timeline`.
    api_timeline_calls = [
        c for c in calls
        if len(c) >= 3 and c[0] == "gh" and c[1] == "api"
        and "/issues/7102/timeline" in (c[2] or "")
    ]
    assert api_timeline_calls, (
        f"expected gh api .../issues/7102/timeline call; got: {calls!r}"
    )
    # The jq filter selects labeled events with decision labels.
    last_call = api_timeline_calls[-1]
    assert "--jq" in last_call
    jq_idx = last_call.index("--jq")
    jq_expr = last_call[jq_idx + 1]
    assert '.event == "labeled"' in jq_expr
    assert '.label.name == "audit-approve"' in jq_expr
    assert '.label.name == "audit-reject"' in jq_expr
    assert '.label.name == "audit-skip"' in jq_expr
    # CRITICAL: the actor check did NOT use `gh issue view` for actor
    # lookup (the cycle-2 bug). Any `gh issue view` calls would be a
    # regression to the buggy author-based check.
    issue_view_calls = [
        c for c in calls
        if len(c) >= 4 and c[0] == "gh" and c[1] == "issue"
        and c[2] == "view" and c[3] == "7102"
    ]
    assert not issue_view_calls, (
        f"actor check must not use `gh issue view`; got: {issue_view_calls!r}"
    )


# ---------------------------------------------------------------------------
# Outcome rollup
# ---------------------------------------------------------------------------


def test_accumulate_routing_result_with_pending_approval():
    result = _empty_result()
    rr = RoutingResult(
        applied_count=2,
        gated=True,
        pending_approval_issue=8888,
        debt_issues=[111, 222],
        missing_issues=[],
        errors=["x"],
        exit_code=0,
    )
    run._accumulate_routing_result(rr, result)
    assert result.pending_approvals_filed == [8888]
    assert result.debt_filed == [111, 222]
    assert result.tier_a_commits == ["audit-applied:2"]
    assert any("routing: x" in e for e in result.errors)


def test_accumulate_routing_result_nonzero_exit_marks_partial():
    result = _empty_result()
    rr = RoutingResult(
        applied_count=0,
        gated=False,
        pending_approval_issue=None,
        debt_issues=[],
        missing_issues=[],
        errors=["routing leg X failed"],
        exit_code=3,
    )
    run._accumulate_routing_result(rr, result)
    assert result.status == "partial"


def test_outcome_from_routing_with_pending():
    rr = RoutingResult(
        applied_count=0, gated=True, pending_approval_issue=4321,
        debt_issues=[111], missing_issues=[], errors=[], exit_code=0,
    )
    out = run._outcome_from_routing(rr)
    assert out["pending_approval_issue"] == "#4321"
    assert out["debt_issue_refs"] == "#111"
    assert out["decision_applied"] == "none"


def test_outcome_from_routing_with_apply():
    rr = RoutingResult(
        applied_count=1, gated=False, pending_approval_issue=None,
        debt_issues=[], missing_issues=[], errors=[], exit_code=0,
    )
    out = run._outcome_from_routing(rr)
    assert out["pending_approval_issue"] == "none"
    assert out["decision_applied"] == "audit-approve"


# ---------------------------------------------------------------------------
# Resolve audit number from pending-approval payload
# ---------------------------------------------------------------------------


def test_resolve_audit_number_from_title():
    assert run._resolve_audit_number_from_pending(
        {"title": "Audit #1234: pending approval", "body": ""}
    ) == 1234


def test_resolve_audit_number_from_body():
    assert run._resolve_audit_number_from_pending(
        {"title": "Pending approval", "body": "Refs #5678 originating"}
    ) == 5678


def test_resolve_audit_number_missing():
    assert run._resolve_audit_number_from_pending(
        {"title": "no info", "body": "no refs"}
    ) is None


# ---------------------------------------------------------------------------
# Dry-run path: pending-approval
# ---------------------------------------------------------------------------


def test_dry_run_pending_approval_no_gh_close(
    tmp_config: Any,
    monkeypatch: pytest.MonkeyPatch,
    mock_anthropic: Any,
):
    """--dry-run pending-approval skips the gh-close + audit-close calls.

    Production conditions: the bot is the issue author (kg-felix-bot
    files every audit-pending-approval). The timeline's labeled-event
    actor is the human (kentonium3) so the gate proceeds (then dry-run
    short-circuits the close).
    """
    pa = [
        {
            "number": 7200,
            "title": "Audit #6800: pending approval — 1 edit(s)",
            "body": "Refs #6800",
            "author": {"login": "kg-felix-bot"},
            "labels": [
                {"name": "audit-pending-approval"},
                {"name": "audit-approve"},
            ],
            "createdAt": "2026-05-20T10:00:00Z",
        }
    ]
    timeline = {
        7200: {
            "label": "audit-approve",
            "actor": "kentonium3",
            "at": "2026-05-20T10:05:00Z",
        }
    }

    calls: list[list[str]] = []

    def fake_run_cmd(cmd, *args, **kwargs):
        cmd = list(cmd)
        calls.append(cmd)
        if len(cmd) >= 3 and cmd[1] == "issue" and cmd[2] == "list":
            labels = [
                cmd[i + 1] for i, tok in enumerate(cmd)
                if tok == "--label" and i + 1 < len(cmd)
            ]
            if "audit-pending-approval" in labels:
                return subprocess.CompletedProcess(
                    args=cmd, returncode=0, stdout=json.dumps(pa), stderr=""
                )
            return subprocess.CompletedProcess(
                args=cmd, returncode=0, stdout="[]", stderr=""
            )
        if (
            len(cmd) >= 3 and cmd[1] == "api"
            and "/timeline" in (cmd[2] or "")
        ):
            # Parse issue number from the path.
            parts = (cmd[2] or "").split("/")
            try:
                idx = parts.index("issues")
                n = int(parts[idx + 1])
            except (ValueError, IndexError):
                n = -1
            payload = timeline.get(n)
            return subprocess.CompletedProcess(
                args=cmd, returncode=0,
                stdout=("null" if payload is None else json.dumps(payload)),
                stderr="",
            )
        return subprocess.CompletedProcess(
            args=cmd, returncode=0, stdout="", stderr=""
        )

    monkeypatch.setattr(subprocess, "run", fake_run_cmd)

    config_path = (
        Path(tmp_config.llm.api_key_path).parent / "config.toml"
    )
    rc = run.main([
        "--config", str(config_path), "--dry-run",
    ])
    assert rc == 0
    # No gh issue close in dry-run.
    closes = [
        c for c in calls
        if len(c) >= 3 and c[1] == "issue" and c[2] == "close"
    ]
    assert not closes


# ---------------------------------------------------------------------------
# Drift-event flow with empty drift file (success path)
# ---------------------------------------------------------------------------


def test_drift_source_empty_file(
    tmp_config: Any,
    monkeypatch: pytest.MonkeyPatch,
    mock_anthropic: Any,
):
    """Empty drift-events.jsonl → drift_events_consumed=0; no error."""

    def fake_run_cmd(cmd, *args, **kwargs):
        return subprocess.CompletedProcess(
            args=list(cmd), returncode=0, stdout="[]", stderr=""
        )

    monkeypatch.setattr(subprocess, "run", fake_run_cmd)
    config_path = (
        Path(tmp_config.llm.api_key_path).parent / "config.toml"
    )
    rc = run.main(["--config", str(config_path)])
    assert rc == 0
    tick = json.loads(
        Path(tmp_config.paths.tick_signal_path).read_text(encoding="utf-8")
    )
    assert tick["tick"]["drift_events_consumed"] == 0


# ---------------------------------------------------------------------------
# Top-level: unhandled exception still writes a tick signal
# ---------------------------------------------------------------------------


def test_unhandled_exception_still_writes_signal(
    tmp_config: Any,
    monkeypatch: pytest.MonkeyPatch,
    mock_anthropic: Any,
):
    """An exception inside _run_tick is caught; tick signal is still written."""

    def boom(*args, **kwargs):
        raise RuntimeError("simulated crash deep in orchestration")

    monkeypatch.setattr(run, "_run_tick", boom)

    config_path = (
        Path(tmp_config.llm.api_key_path).parent / "config.toml"
    )
    rc = run.main(["--config", str(config_path)])
    assert rc == 1
    tick = json.loads(
        Path(tmp_config.paths.tick_signal_path).read_text(encoding="utf-8")
    )
    assert tick["status"] == "failure"
    assert any(
        "simulated crash" in e for e in tick["errors"]
    )


# ---------------------------------------------------------------------------
# Weekly doc audit dispatch
# ---------------------------------------------------------------------------


def test_weekly_audit_dispatches(
    tmp_config: Any,
    monkeypatch: pytest.MonkeyPatch,
    mock_anthropic: Any,
):
    """A ``Weekly doc audit —`` signal routes through _process_audit_signal."""
    weekly = [
        {
            "number": 4300,
            "title": "Weekly doc audit — 2026-05-19",
            "body": "",
            "labels": [{"name": "doc-audit"}, {"name": "weekly"}],
            "createdAt": "2026-05-19T07:00:00Z",
        }
    ]

    def fake_run_cmd(cmd, *args, **kwargs):
        cmd = list(cmd)
        if len(cmd) >= 3 and cmd[1] == "issue" and cmd[2] == "list":
            labels = [
                cmd[i + 1] for i, tok in enumerate(cmd)
                if tok == "--label" and i + 1 < len(cmd)
            ]
            if "doc-audit" in labels and "status:in-progress" not in labels:
                return subprocess.CompletedProcess(
                    args=cmd, returncode=0,
                    stdout=json.dumps(weekly), stderr="",
                )
        return subprocess.CompletedProcess(
            args=cmd, returncode=0, stdout="[]", stderr=""
        )

    monkeypatch.setattr(subprocess, "run", fake_run_cmd)

    def fake_apply(*args, **kwargs):
        return RoutingResult(
            applied_count=0, gated=False, pending_approval_issue=None,
            debt_issues=[], missing_issues=[], errors=[], exit_code=0,
        )

    monkeypatch.setattr(run, "apply_routing", fake_apply)

    config_path = (
        Path(tmp_config.llm.api_key_path).parent / "config.toml"
    )
    rc = run.main(["--config", str(config_path)])
    assert rc == 0
    tick = json.loads(
        Path(tmp_config.paths.tick_signal_path).read_text(encoding="utf-8")
    )
    assert tick["status"] == "success"
    assert tick["tick"]["audits_processed"] == [4300]


# ---------------------------------------------------------------------------
# Source restriction: --source drift_event only
# ---------------------------------------------------------------------------


def test_source_drift_only_skips_gh(
    tmp_config: Any,
    monkeypatch: pytest.MonkeyPatch,
    mock_anthropic: Any,
):
    """--source drift_event: gh_issue source is not built → no gh queries.

    The stuck-lock query AND the signal-source list query both run via
    subprocess.run; if --source drift_event excludes gh_issue we should
    see zero gh issue list calls.
    """
    calls: list[list[str]] = []

    def fake_run_cmd(cmd, *args, **kwargs):
        calls.append(list(cmd))
        return subprocess.CompletedProcess(
            args=list(cmd), returncode=0, stdout="[]", stderr=""
        )

    monkeypatch.setattr(subprocess, "run", fake_run_cmd)

    config_path = (
        Path(tmp_config.llm.api_key_path).parent / "config.toml"
    )
    rc = run.main([
        "--config", str(config_path), "--source", "drift_event",
    ])
    assert rc == 0
    # No `gh issue list` calls — the GH source is excluded entirely.
    gh_lists = [
        c for c in calls
        if len(c) >= 3 and c[0] == "gh" and c[1] == "issue" and c[2] == "list"
    ]
    assert not gh_lists, f"expected no gh issue list; got {gh_lists!r}"


# ---------------------------------------------------------------------------
# Activity-log failure path
# ---------------------------------------------------------------------------


def test_log_audit_outcome_swallows_error(
    tmp_config: Any, monkeypatch: pytest.MonkeyPatch
):
    """A log-write failure appends to errors but doesn't raise."""

    def boom(*args, **kwargs):
        raise OSError("disk full")

    monkeypatch.setattr(run, "append_audit_entry", boom)
    result = _empty_result()
    audit = AuditIssue(
        issue_number=9001, title="Doc audit: x", is_weekly=False,
        triggering_sha="x", area_labels=[], in_scope_docs=[],
    )
    # Should not raise.
    run._log_audit_outcome(tmp_config, result, audit, outcome={})
    assert any("activity log append failed" in e for e in result.errors)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _empty_result() -> TickResult:
    return TickResult(
        started_utc="2026-05-20T12:00:00Z",
        ended_utc="2026-05-20T12:00:01Z",
        status="success",
        signals_seen=0,
        signals_processed=0,
        tier_a_commits=[],
        pending_approvals_filed=[],
        pending_approvals_applied=[],
        debt_filed=[],
        drift_events_consumed=0,
        errors=[],
        judgment_calls={},
        token_usage={},
    )


# ---------------------------------------------------------------------------
# Additional coverage: error branches
# ---------------------------------------------------------------------------


def test_drift_event_commit_failure_records_partial(
    tmp_config: Any, monkeypatch: pytest.MonkeyPatch,
):
    """A drift commit() that raises is recorded as partial."""
    # Synthesize a drift-event line so pending() returns a signal.
    drift_path = Path(tmp_config.paths.drift_events)
    signal_map = Path(tmp_config.paths.signal_to_doc_map)
    # Provide a mapping table that matches our event so commit attempts
    # to file_doc_audit_issue.
    signal_map.write_text(
        json.dumps(
            {
                "mappings": [
                    {
                        "id": "test-mapping",
                        "match": {"baseline_name": "test-baseline"},
                        "doc_targets": ["docs/x.md"],
                        "rationale": "test fixture",
                        "issue_title_prefix": "Test:",
                        "issue_labels": ["doc-audit"],
                    }
                ]
            }
        ),
        encoding="utf-8",
    )
    drift_path.write_text(
        json.dumps(
            {
                "timestamp": "2026-05-20T12:00:00Z",
                "source": "audit.sh",
                "event_type": "baseline_drift",
                "baseline_name": "test-baseline",
                "diff_b64": "",
            }
        )
        + "\n",
        encoding="utf-8",
    )

    # Make file_doc_audit_issue fail to simulate the commit error.
    from doc_audit.signals import drift_event as drift_mod

    def failing_file(*args, **kwargs):
        return (False, "simulated filing failure")

    monkeypatch.setattr(drift_mod, "file_doc_audit_issue", failing_file)

    # Stub gh issue list calls (empty), so the GH source returns no
    # signals.
    def fake_run_cmd(cmd, *args, **kwargs):
        return subprocess.CompletedProcess(
            args=list(cmd), returncode=0, stdout="[]", stderr=""
        )

    monkeypatch.setattr(subprocess, "run", fake_run_cmd)

    config_path = (
        Path(tmp_config.llm.api_key_path).parent / "config.toml"
    )
    rc = run.main(["--config", str(config_path)])
    # drift commit failure → partial
    tick = json.loads(
        Path(tmp_config.paths.tick_signal_path).read_text(encoding="utf-8")
    )
    assert tick["status"] == "partial"
    assert any("drift_event.commit failed" in e for e in tick["errors"])
    # exit code aligns with status="partial" → 2
    assert rc == 2


def test_dry_run_doc_audit(
    tmp_config: Any, monkeypatch: pytest.MonkeyPatch, mock_anthropic: Any,
):
    """--dry-run on a doc audit: routing is NOT invoked, log entry is."""
    audits = [
        {
            "number": 5200,
            "title": "Doc audit: dddry111 (felix-core)",
            "body": "",
            "labels": [{"name": "doc-audit"}, {"name": "area/felix-core"}],
            "createdAt": "2026-05-20T11:00:00Z",
        }
    ]

    def fake_run_cmd(cmd, *args, **kwargs):
        cmd = list(cmd)
        if len(cmd) >= 3 and cmd[1] == "issue" and cmd[2] == "list":
            labels = [
                cmd[i + 1] for i, tok in enumerate(cmd)
                if tok == "--label" and i + 1 < len(cmd)
            ]
            if "doc-audit" in labels and "status:in-progress" not in labels:
                return subprocess.CompletedProcess(
                    args=cmd, returncode=0,
                    stdout=json.dumps(audits), stderr="",
                )
        return subprocess.CompletedProcess(
            args=cmd, returncode=0, stdout="[]", stderr=""
        )

    monkeypatch.setattr(subprocess, "run", fake_run_cmd)

    apply_called = {"count": 0}

    def fake_apply(*args, **kwargs):
        apply_called["count"] += 1
        return RoutingResult(exit_code=0)

    monkeypatch.setattr(run, "apply_routing", fake_apply)

    config_path = (
        Path(tmp_config.llm.api_key_path).parent / "config.toml"
    )
    rc = run.main(["--config", str(config_path), "--dry-run"])
    assert rc == 0
    # Routing was NOT invoked in dry-run.
    assert apply_called["count"] == 0
    # Activity log was still written (dry-run marker).
    log_dir = Path(tmp_config.paths.activity_log_dir)
    assert list(log_dir.glob("doc-auditor-*.md"))


def test_gh_pending_non_rate_limit_error_is_failure(
    tmp_config: Any, monkeypatch: pytest.MonkeyPatch, mock_anthropic: Any,
):
    """A non-rate-limit gh failure on pending() → result.status=failure."""

    def fake_run_cmd(cmd, *args, **kwargs):
        if (
            len(cmd) >= 3 and cmd[1] == "issue" and cmd[2] == "list"
            and "--state" in cmd
        ):
            raise subprocess.CalledProcessError(
                returncode=1, cmd=list(cmd), output="", stderr="500 server error"
            )
        return subprocess.CompletedProcess(
            args=list(cmd), returncode=0, stdout="[]", stderr=""
        )

    monkeypatch.setattr(subprocess, "run", fake_run_cmd)
    config_path = (
        Path(tmp_config.llm.api_key_path).parent / "config.toml"
    )
    rc = run.main(["--config", str(config_path)])
    assert rc == 1
    tick = json.loads(
        Path(tmp_config.paths.tick_signal_path).read_text(encoding="utf-8")
    )
    assert tick["status"] == "failure"
    assert any(
        "gh_issue.pending failed" in e or "500" in e for e in tick["errors"]
    )


def test_routing_called_process_error_non_rate_limit_marks_partial(
    tmp_config: Any, monkeypatch: pytest.MonkeyPatch, mock_anthropic: Any,
):
    """A non-rate-limit subprocess error from apply_routing → partial."""
    audits = [
        {
            "number": 5300,
            "title": "Doc audit: errcase (felix-core)",
            "body": "",
            "labels": [{"name": "doc-audit"}, {"name": "area/felix-core"}],
            "createdAt": "2026-05-20T11:00:00Z",
        }
    ]

    def fake_run_cmd(cmd, *args, **kwargs):
        cmd = list(cmd)
        if len(cmd) >= 3 and cmd[1] == "issue" and cmd[2] == "list":
            labels = [
                cmd[i + 1] for i, tok in enumerate(cmd)
                if tok == "--label" and i + 1 < len(cmd)
            ]
            if "doc-audit" in labels and "status:in-progress" not in labels:
                return subprocess.CompletedProcess(
                    args=cmd, returncode=0,
                    stdout=json.dumps(audits), stderr="",
                )
        return subprocess.CompletedProcess(
            args=cmd, returncode=0, stdout="[]", stderr=""
        )

    monkeypatch.setattr(subprocess, "run", fake_run_cmd)

    def fake_apply(*args, **kwargs):
        raise subprocess.CalledProcessError(
            returncode=1, cmd=["gh"], output="", stderr="some other gh error"
        )

    monkeypatch.setattr(run, "apply_routing", fake_apply)
    config_path = (
        Path(tmp_config.llm.api_key_path).parent / "config.toml"
    )
    rc = run.main(["--config", str(config_path)])
    assert rc in (1, 2)
    tick = json.loads(
        Path(tmp_config.paths.tick_signal_path).read_text(encoding="utf-8")
    )
    assert tick["status"] in ("partial", "failure")


def test_tick_signal_write_failure_swallowed(
    tmp_config: Any, monkeypatch: pytest.MonkeyPatch, mock_anthropic: Any,
    capsys: pytest.CaptureFixture,
):
    """If write_tick_signal raises, main returns sanely with FATAL on stderr."""

    def fake_run_cmd(cmd, *args, **kwargs):
        return subprocess.CompletedProcess(
            args=list(cmd), returncode=0, stdout="[]", stderr=""
        )

    monkeypatch.setattr(subprocess, "run", fake_run_cmd)

    def boom(*args, **kwargs):
        raise OSError("disk full writing last-tick.json")

    monkeypatch.setattr(run, "write_tick_signal", boom)

    config_path = (
        Path(tmp_config.llm.api_key_path).parent / "config.toml"
    )
    rc = run.main(["--config", str(config_path)])
    # Empty queue + sentinel write failure: empty queue status=success → rc 0
    assert rc == 0
    err = capsys.readouterr().err
    assert "tick signal write failed" in err


def test_in_progress_query_rate_limited_raises(
    tmp_config: Any, monkeypatch: pytest.MonkeyPatch, mock_anthropic: Any,
):
    """The in-progress query raising rate-limit propagates → status=failure.

    Exercises the ``raise RateLimitError`` branch inside
    :func:`_fetch_in_progress_audits` and the outer handler in
    :func:`_run_tick`.
    """
    call_count = {"i": 0}

    def fake_run_cmd(cmd, *args, **kwargs):
        cmd = list(cmd)
        call_count["i"] += 1
        # The 4th `gh issue list` call is the in-progress query (3
        # prior calls are pending-approvals, doc-audits, weekly).
        if (
            len(cmd) >= 3 and cmd[1] == "issue" and cmd[2] == "list"
            and "status:in-progress" in cmd
        ):
            raise subprocess.CalledProcessError(
                returncode=1, cmd=cmd, output="",
                stderr="HTTP 403: API rate limit exceeded",
            )
        return subprocess.CompletedProcess(
            args=cmd, returncode=0, stdout="[]", stderr=""
        )

    monkeypatch.setattr(subprocess, "run", fake_run_cmd)
    config_path = (
        Path(tmp_config.llm.api_key_path).parent / "config.toml"
    )
    rc = run.main(["--config", str(config_path)])
    assert rc == 1
    tick = json.loads(
        Path(tmp_config.paths.tick_signal_path).read_text(encoding="utf-8")
    )
    assert tick["status"] == "failure"
    assert any(
        "rate" in e.lower() for e in tick["errors"]
    )


# ---------------------------------------------------------------------------
# Cycle-2: audit workflow helpers
# ---------------------------------------------------------------------------


def test_guardrailed_path_constitution():
    """The constitution file is always guardrailed regardless of prefix."""
    assert run._is_guardrailed_path(
        "docs/constitution/FELIX-CONSTITUTION.md"
    )
    # Even when nested under a worktree-style prefix it still matches.
    assert run._is_guardrailed_path(
        "/.worktrees/x/docs/constitution/FELIX-CONSTITUTION.md"
    )


def test_guardrailed_path_claude_md_basename():
    """``CLAUDE.md`` at any path is guardrailed."""
    assert run._is_guardrailed_path("CLAUDE.md")
    assert run._is_guardrailed_path("scripts/CLAUDE.md")


def test_guardrailed_path_credentials():
    """``.env`` and ``credentials.json`` are guardrailed."""
    assert run._is_guardrailed_path(".env")
    assert run._is_guardrailed_path("services/foo/.env.production")
    assert run._is_guardrailed_path("path/credentials.json")


def test_guardrailed_path_speckitty_dirs():
    """``kitty-specs/`` and ``.kittify/`` are guardrailed."""
    assert run._is_guardrailed_path("kitty-specs/foo/spec.md")
    assert run._is_guardrailed_path(".kittify/runtime/state.json")
    assert run._is_guardrailed_path("repo/kitty-specs/abc.md")


def test_guardrailed_path_safe():
    """Ordinary doc paths are not guardrailed."""
    assert not run._is_guardrailed_path("docs/INDEX.md")
    assert not run._is_guardrailed_path("docs/runbooks/foo.md")
    assert not run._is_guardrailed_path("")


def test_load_doc_domain_map_missing(tmp_config: Any):
    """Missing doc-domain-map yields empty dict (graceful degrade)."""
    # The tmp_config fixture writes a stub doc-domain-map "{}"; unlink it.
    Path(tmp_config.paths.doc_domain_map).unlink()
    assert run._load_doc_domain_map(tmp_config) == {}


def test_load_doc_domain_map_malformed(tmp_config: Any):
    """Malformed JSON yields empty dict."""
    Path(tmp_config.paths.doc_domain_map).write_text(
        "{ not valid json", encoding="utf-8"
    )
    assert run._load_doc_domain_map(tmp_config) == {}


def test_load_doc_domain_map_not_dict(tmp_config: Any):
    """Non-object JSON yields empty dict."""
    Path(tmp_config.paths.doc_domain_map).write_text(
        "[1,2,3]", encoding="utf-8"
    )
    assert run._load_doc_domain_map(tmp_config) == {}


def test_load_doc_domain_map_missing_domains(tmp_config: Any):
    """JSON without 'domains' key yields empty dict."""
    Path(tmp_config.paths.doc_domain_map).write_text(
        '{"version": "1.0"}', encoding="utf-8"
    )
    assert run._load_doc_domain_map(tmp_config) == {}


def test_load_doc_domain_map_valid(tmp_config: Any):
    """A well-formed map returns the normalized domains dict."""
    Path(tmp_config.paths.doc_domain_map).write_text(
        json.dumps({
            "domains": {
                "area/felix-core": ["docs/constitution/foo.md", "x.md"],
                "area/security": ["sec.md"],
                # Invalid entries are dropped.
                "area/bad": "not a list",
                42: ["wrong-key"],
            }
        }),
        encoding="utf-8",
    )
    out = run._load_doc_domain_map(tmp_config)
    assert "area/felix-core" in out
    assert out["area/felix-core"] == ["docs/constitution/foo.md", "x.md"]
    assert out["area/security"] == ["sec.md"]
    assert "area/bad" not in out


def test_resolve_in_scope_docs_empty_map(sample_audit_issue):
    """Empty domain map yields empty in-scope list."""
    assert run._resolve_in_scope_docs(sample_audit_issue, {}) == []


def test_resolve_in_scope_docs_per_label(sample_audit_issue):
    """Audit area labels intersect the map (with dedup, order-preserving)."""
    domain_map = {
        "area/felix-core": ["a.md", "b.md", "shared.md"],
        "area/security": ["sec.md", "shared.md"],
    }
    out = run._resolve_in_scope_docs(sample_audit_issue, domain_map)
    # sample_audit_issue is area/felix-core only.
    assert out == ["a.md", "b.md", "shared.md"]


def test_resolve_in_scope_docs_full_scope():
    """Empty area_labels yields the union of all values (weekly behavior)."""
    audit = run.AuditIssue(
        issue_number=1, title="Weekly doc audit — 2026-05-20",
        is_weekly=True, triggering_sha=None,
        area_labels=[], in_scope_docs=[],
    )
    domain_map = {
        "area/a": ["a1.md", "a2.md"],
        "area/b": ["b1.md", "a1.md"],  # dedup
    }
    out = run._resolve_in_scope_docs(audit, domain_map)
    assert out == ["a1.md", "a2.md", "b1.md"]


def test_fetch_diff_for_sha_empty():
    """Empty SHA returns empty string without invoking git."""
    assert run._fetch_diff_for_sha("") == ""


def test_fetch_diff_for_sha_subprocess_failure(monkeypatch):
    """All exceptions from git show are swallowed → empty diff."""

    def boom(*args, **kwargs):
        raise RuntimeError("unexpected non-gh subprocess")

    monkeypatch.setattr(subprocess, "run", boom)
    assert run._fetch_diff_for_sha("abc123") == ""


def test_fetch_diff_for_sha_success(monkeypatch):
    """Successful git show returns stdout."""

    def ok(*args, **kwargs):
        return subprocess.CompletedProcess(
            args=args[0], returncode=0,
            stdout="diff --git a/x b/x\n+++ b/x\n",
            stderr="",
        )

    monkeypatch.setattr(subprocess, "run", ok)
    out = run._fetch_diff_for_sha("abc123")
    assert "+++ b/x" in out


def test_parse_touched_files_empty():
    assert run._parse_touched_files("") == []


def test_parse_touched_files_multi():
    diff = (
        "diff --git a/x.md b/x.md\n"
        "--- a/x.md\n"
        "+++ b/x.md\n"
        "diff --git a/y.md b/y.md\n"
        "+++ b/y.md\n"
        "+++ b/y.md\n"  # duplicate dropped
    )
    assert run._parse_touched_files(diff) == ["x.md", "y.md"]


def test_parse_touched_files_skips_devnull():
    diff = "+++ b//dev/null\n+++ b/real.md\n"
    assert run._parse_touched_files(diff) == ["real.md"]


def test_derive_candidate_edits_empty_diff():
    audit = run.AuditIssue(
        issue_number=1, title="t", is_weekly=False, triggering_sha="abc",
        area_labels=[], in_scope_docs=[],
    )
    assert run._derive_candidate_edits("", audit, []) == []


def test_derive_candidate_edits_frontmatter_bump():
    audit = run.AuditIssue(
        issue_number=42, title="Doc audit: abc123 (felix-core)",
        is_weekly=False, triggering_sha="abc123",
        area_labels=["area/felix-core"],
        in_scope_docs=["docs/runbooks/foo.md"],
    )
    diff = (
        "diff --git a/docs/runbooks/foo.md b/docs/runbooks/foo.md\n"
        "--- a/docs/runbooks/foo.md\n"
        "+++ b/docs/runbooks/foo.md\n"
        "@@ -1,3 +1,3 @@\n"
        " ---\n"
        "-last_validated: 2026-04-01\n"
        "+last_validated: 2026-05-20\n"
        " ---\n"
    )
    edits = run._derive_candidate_edits(
        diff, audit, ["docs/runbooks/foo.md"]
    )
    assert len(edits) == 1
    assert edits[0].doc_path == "docs/runbooks/foo.md"
    assert edits[0].change_type == "frontmatter_field_bump"
    assert edits[0].current_value == "2026-04-01"
    assert edits[0].proposed_value == "2026-05-20"


def test_derive_candidate_edits_skips_out_of_scope():
    audit = run.AuditIssue(
        issue_number=42, title="x", is_weekly=False, triggering_sha="abc",
        area_labels=["area/felix-core"],
        in_scope_docs=["docs/runbooks/foo.md"],
    )
    diff = (
        "diff --git a/docs/runbooks/bar.md b/docs/runbooks/bar.md\n"
        "--- a/docs/runbooks/bar.md\n"
        "+++ b/docs/runbooks/bar.md\n"
        "-last_validated: 2026-04-01\n"
        "+last_validated: 2026-05-20\n"
    )
    # bar.md is not in scope → no edits.
    edits = run._derive_candidate_edits(
        diff, audit, ["docs/runbooks/foo.md"]
    )
    assert edits == []


def test_frontmatter_excerpt_missing_file(tmp_path):
    """A missing doc returns the unavailable marker."""
    out = run._frontmatter_excerpt("never.md", tmp_path)
    assert out == "(unavailable)"


def test_frontmatter_excerpt_with_frontmatter(tmp_path):
    """A doc with frontmatter returns the front block."""
    d = tmp_path / "docs"
    d.mkdir()
    (d / "x.md").write_text(
        "---\ntitle: foo\nlast_validated: 2026-04-01\n---\n\nbody\n",
        encoding="utf-8",
    )
    out = run._frontmatter_excerpt("docs/x.md", tmp_path)
    assert "title: foo" in out
    assert out.startswith("---")


def test_frontmatter_excerpt_no_frontmatter(tmp_path):
    """A doc without frontmatter returns the first 10 lines verbatim."""
    (tmp_path / "x.md").write_text("# Title\nbody\n", encoding="utf-8")
    out = run._frontmatter_excerpt("x.md", tmp_path)
    assert "# Title" in out


def test_acquire_lock_dry_run(tmp_config: Any):
    """Dry-run skips the gh call entirely."""
    result = _empty_result()
    args_ns = type("A", (), {"dry_run": True})()
    assert (
        run._acquire_lock(tmp_config, 100, result, dry_run=True) is True
    )


def test_acquire_lock_success(tmp_config: Any, monkeypatch):
    """A successful gh edit returns True."""

    def ok(*args, **kwargs):
        return subprocess.CompletedProcess(
            args=args[0] if args else ["gh"], returncode=0, stdout="", stderr=""
        )

    monkeypatch.setattr(subprocess, "run", ok)
    result = _empty_result()
    assert run._acquire_lock(tmp_config, 100, result, dry_run=False) is True


def test_acquire_lock_rate_limited(tmp_config: Any, monkeypatch):
    """A 403 rate-limit becomes a RateLimitError (propagates to BREAK)."""

    def boom(*args, **kwargs):
        raise subprocess.CalledProcessError(
            returncode=1, cmd=args[0] if args else ["gh"],
            output="", stderr="HTTP 403: API rate limit exceeded",
        )

    monkeypatch.setattr(subprocess, "run", boom)
    result = _empty_result()
    with pytest.raises(run.RateLimitError):
        run._acquire_lock(tmp_config, 100, result, dry_run=False)


def test_acquire_lock_non_rate_failure(tmp_config: Any, monkeypatch):
    """A non-rate-limit failure logs + returns False (best-effort)."""

    def boom(*args, **kwargs):
        raise subprocess.CalledProcessError(
            returncode=1, cmd=args[0] if args else ["gh"],
            output="", stderr="label not found",
        )

    monkeypatch.setattr(subprocess, "run", boom)
    result = _empty_result()
    assert (
        run._acquire_lock(tmp_config, 100, result, dry_run=False) is False
    )
    assert any("lock acquisition failed" in e for e in result.errors)


def test_accumulate_token_usage_none_response():
    """Passing None response is a no-op."""
    result = _empty_result()
    run._accumulate_token_usage(result, None)
    assert result.token_usage == {}


def test_accumulate_token_usage_basic():
    """Token counts accumulate across multiple responses."""
    result = _empty_result()
    result.token_usage = {
        "input_tokens": 0,
        "cache_hit_input_tokens": 0,
        "output_tokens": 0,
    }
    from doc_audit.judgment.client import JudgmentResponse
    resp = JudgmentResponse(
        content="x", input_tokens=100, cache_hit_input_tokens=50,
        output_tokens=20, stop_reason="end_turn",
    )
    run._accumulate_token_usage(result, resp)
    run._accumulate_token_usage(result, resp)
    assert result.token_usage["input_tokens"] == 200
    assert result.token_usage["cache_hit_input_tokens"] == 100
    assert result.token_usage["output_tokens"] == 40


def test_detect_missing_artifacts_skipped_for_other_area(tmp_path):
    """Audit not in area/felix-core skips the missing-artifact scan."""
    audit = run.AuditIssue(
        issue_number=1, title="x", is_weekly=False,
        triggering_sha="abc", area_labels=["area/security"],
        in_scope_docs=[],
    )
    # Even with no agent-registry.json, the function returns [] (skipped).
    out = run._detect_missing_artifacts(None, audit, tmp_path)
    assert out == []


def test_detect_missing_artifacts_missing_registry(tmp_path):
    """Missing agent-registry.json returns empty list."""
    audit = run.AuditIssue(
        issue_number=1, title="x", is_weekly=False,
        triggering_sha="abc", area_labels=["area/felix-core"],
        in_scope_docs=[],
    )
    out = run._detect_missing_artifacts(None, audit, tmp_path)
    assert out == []


def test_detect_missing_artifacts_finds_gap(tmp_path):
    """A registered agent without a runbook becomes a missing-artifact debt."""
    constitution_dir = tmp_path / "docs" / "constitution"
    constitution_dir.mkdir(parents=True)
    (constitution_dir / "agent-registry.json").write_text(
        json.dumps({
            "agents": {
                "felix-doc-auditor": {"team": "X"},
                "felix-admin-foo": {"team": "Y"},
            }
        }),
        encoding="utf-8",
    )
    # Create the runbook only for felix-admin-foo (foo-ops.md).
    runbooks = tmp_path / "docs" / "runbooks"
    runbooks.mkdir(parents=True)
    (runbooks / "admin-foo-ops.md").write_text("# admin foo", encoding="utf-8")

    audit = run.AuditIssue(
        issue_number=42, title="Weekly", is_weekly=True,
        triggering_sha=None, area_labels=[], in_scope_docs=[],
    )
    out = run._detect_missing_artifacts(None, audit, tmp_path)
    # Only felix-doc-auditor has no matching runbook → 1 gap.
    assert len(out) == 1
    assert "felix-doc-auditor" in out[0].artifact_path


def test_classify_proposed_edits_tier_a(
    tmp_config: Any, mock_anthropic, sample_audit_issue
):
    """tier_classification returning TIER_A retains the edit."""
    mock_anthropic.messages.next_fixture = "tier_classification_tier_a"
    edit = run.ProposedEdit(
        doc_path="docs/runbooks/foo.md",
        change_type="frontmatter_field_bump",
        current_value="2026-04-01", proposed_value="2026-05-20",
        evidence_source="git show abc", tier="", confidence="high",
    )
    from doc_audit.judgment.client import JudgmentClient
    client = JudgmentClient(tmp_config)
    result = _empty_result()
    result.judgment_calls = {
        "tier_classification": 0,
        "debt_body_generation": 0,
        "cross_file_implication": 0,
    }
    result.token_usage = {
        "input_tokens": 0,
        "cache_hit_input_tokens": 0,
        "output_tokens": 0,
    }
    proposed, judgment = run._classify_proposed_edits(
        client, sample_audit_issue, [edit], Path("/tmp"), result,
    )
    assert len(proposed) == 1
    assert proposed[0].tier == "tier_a"
    assert judgment == []
    assert result.judgment_calls["tier_classification"] == 1
    assert result.token_usage["input_tokens"] > 0
    assert mock_anthropic.messages.calls, "LLM was actually called"


def test_classify_proposed_edits_judgment_demotion(
    tmp_config: Any, mock_anthropic, sample_audit_issue
):
    """tier_classification returning JUDGMENT demotes to debt finding."""
    mock_anthropic.messages.next_fixture = "tier_classification_judgment"
    edit = run.ProposedEdit(
        doc_path="docs/runbooks/foo.md",
        change_type="frontmatter_field_bump",
        current_value="x", proposed_value="y",
        evidence_source="git show abc", tier="", confidence="high",
    )
    from doc_audit.judgment.client import JudgmentClient
    client = JudgmentClient(tmp_config)
    result = _empty_result()
    result.judgment_calls = {"tier_classification": 0}
    result.token_usage = {
        "input_tokens": 0,
        "cache_hit_input_tokens": 0,
        "output_tokens": 0,
    }
    proposed, judgment = run._classify_proposed_edits(
        client, sample_audit_issue, [edit], Path("/tmp"), result,
    )
    assert proposed == []
    assert len(judgment) == 1
    assert "Author intent unclear" in judgment[0]["rationale"]


def test_classify_proposed_edits_classifier_error(
    tmp_config: Any, monkeypatch, sample_audit_issue
):
    """A classifier exception demotes to judgment with error info."""
    edit = run.ProposedEdit(
        doc_path="x.md", change_type="frontmatter_field_bump",
        current_value="x", proposed_value="y",
        evidence_source="z", tier="", confidence="high",
    )

    from doc_audit.judgment import tier_classification as tc

    def boom(*args, **kwargs):
        raise RuntimeError("simulated classifier crash")

    monkeypatch.setattr(tc, "classify", boom)
    result = _empty_result()
    result.judgment_calls = {"tier_classification": 0}
    result.token_usage = {
        "input_tokens": 0,
        "cache_hit_input_tokens": 0,
        "output_tokens": 0,
    }
    proposed, judgment = run._classify_proposed_edits(
        None, sample_audit_issue, [edit], Path("/tmp"), result,
    )
    assert proposed == []
    assert len(judgment) == 1
    assert "classifier error" in judgment[0]["rationale"]
    assert any("tier_classification failed" in e for e in result.errors)


def test_run_cross_file_implication_empty_scope(tmp_config: Any, sample_audit_issue):
    """Empty in_scope_docs short-circuits to []."""
    result = _empty_result()
    out = run._run_cross_file_implication(
        None, sample_audit_issue, "", [], [], result,
    )
    assert out == []


def test_run_cross_file_implication_all_touched(tmp_config: Any, sample_audit_issue):
    """When every in-scope doc is also touched, short-circuit to []."""
    result = _empty_result()
    out = run._run_cross_file_implication(
        None, sample_audit_issue, "", ["x.md"], ["x.md"], result,
    )
    assert out == []


def test_run_cross_file_implication_calls_llm(
    tmp_config: Any, mock_anthropic, sample_audit_issue
):
    """A valid scope triggers the LLM call and accumulates telemetry."""
    payload = {
        "text": json.dumps({
            "implications": [
                {
                    "untouched_file": "docs/runbooks/foo.md",
                    "implication": "may be stale",
                    "evidence": "commit abc",
                    "suggested_action": "judgment",
                }
            ]
        }),
        "usage": {
            "input_tokens": 100,
            "cache_read_input_tokens": 40,
            "output_tokens": 20,
        },
    }
    # Inline-stub the anthropic loader.
    mock_anthropic.messages._loader = lambda _name: payload
    mock_anthropic.messages.next_fixture = "stub"

    from doc_audit.judgment.client import JudgmentClient
    client = JudgmentClient(tmp_config)
    result = _empty_result()
    result.judgment_calls = {"cross_file_implication": 0}
    result.token_usage = {
        "input_tokens": 0,
        "cache_hit_input_tokens": 0,
        "output_tokens": 0,
    }
    out = run._run_cross_file_implication(
        client, sample_audit_issue, "diff data",
        touched_files=["x.md"],
        in_scope_docs=["x.md", "docs/runbooks/foo.md"],
        result=result,
    )
    assert len(out) == 1
    assert result.judgment_calls["cross_file_implication"] == 1
    assert result.token_usage["input_tokens"] == 100


def test_run_cross_file_implication_failure(
    tmp_config: Any, monkeypatch, sample_audit_issue
):
    """LLM error logs + returns []; tick continues."""
    from doc_audit.judgment import cross_file_implication as cfi

    def boom(*args, **kwargs):
        raise RuntimeError("anthropic blew up")

    monkeypatch.setattr(cfi, "detect", boom)
    result = _empty_result()
    out = run._run_cross_file_implication(
        None, sample_audit_issue, "diff",
        touched_files=["x.md"], in_scope_docs=["x.md", "y.md"],
        result=result,
    )
    assert out == []
    assert any("cross_file_implication failed" in e for e in result.errors)


def test_generate_debt_bodies_success(
    tmp_config: Any, mock_anthropic, sample_audit_issue
):
    """Each finding produces a DebtIssue with a generated body."""
    body_md = (
        "## Artifact\nfoo.md\n\n"
        "## Gap description\nstale\n\n"
        "## Area\narea/felix-core\n\n"
        "## Cross-references\n- Refs #4242 (originating audit)\n\n"
        "## Draft outline\n- step one\n\n"
        "## Success criteria\n- done\n"
    )
    mock_anthropic.messages._loader = lambda _name: {
        "text": body_md,
        "usage": {
            "input_tokens": 50,
            "cache_read_input_tokens": 30,
            "output_tokens": 80,
        },
    }
    mock_anthropic.messages.next_fixture = "stub"

    from doc_audit.judgment.client import JudgmentClient
    client = JudgmentClient(tmp_config)
    result = _empty_result()
    result.judgment_calls = {"debt_body_generation": 0}
    result.token_usage = {
        "input_tokens": 0, "cache_hit_input_tokens": 0, "output_tokens": 0,
    }
    findings = [{
        "doc_path": "docs/runbooks/foo.md",
        "gap_description": "stale frontmatter",
        "evidence_source": "git show abc",
        "rationale": "x",
    }]
    out = run._generate_debt_bodies(client, sample_audit_issue, findings, result)
    assert len(out) == 1
    assert out[0].draft_outline.startswith("## Artifact")
    assert result.judgment_calls["debt_body_generation"] == 1


def test_generate_debt_bodies_failure(
    tmp_config: Any, monkeypatch, sample_audit_issue
):
    """A debt_body_generation crash still produces a stub DebtIssue."""
    from doc_audit.judgment import debt_body_generation as dbg

    def boom(*args, **kwargs):
        raise RuntimeError("model error")

    monkeypatch.setattr(dbg, "generate", boom)
    result = _empty_result()
    findings = [{
        "doc_path": "x.md", "gap_description": "g",
        "evidence_source": "e", "rationale": "r",
    }]
    out = run._generate_debt_bodies(None, sample_audit_issue, findings, result)
    assert len(out) == 1
    assert "## Gap description" in out[0].draft_outline
    assert any("debt_body_generation failed" in e for e in result.errors)


def test_recover_stuck_locks_synthesizes_signal(
    tmp_config: Any, monkeypatch
):
    """A stuck audit (in-progress, no PA) is synthesized as a fresh signal."""
    stuck = [
        {
            "number": 1234,
            "title": "Doc audit: abc1234 (felix-core)",
            "body": "...",
            "labels": [
                {"name": "doc-audit"},
                {"name": "status:in-progress"},
                {"name": "area/felix-core"},
            ],
            "createdAt": "2026-05-20T08:00:00Z",
        }
    ]

    calls: list[list[str]] = []

    def fake_run_cmd(cmd, *args, **kwargs):
        cmd = list(cmd)
        calls.append(cmd)
        if (
            len(cmd) >= 3 and cmd[1] == "issue" and cmd[2] == "list"
            and "status:in-progress" in cmd
        ):
            return subprocess.CompletedProcess(
                args=cmd, returncode=0, stdout=json.dumps(stuck), stderr="",
            )
        return subprocess.CompletedProcess(
            args=cmd, returncode=0, stdout="", stderr="",
        )

    monkeypatch.setattr(subprocess, "run", fake_run_cmd)
    args_ns = type("A", (), {"dry_run": False})()
    result = _empty_result()
    recovered = run._recover_stuck_locks(tmp_config, {}, args_ns, result)
    assert len(recovered) == 1
    assert recovered[0].payload["stale_lock"] is True
    assert recovered[0].payload["issue_number"] == 1234
    assert recovered[0].kind == "doc_audit"
    # Lock release was attempted.
    label_removals = [
        c for c in calls
        if len(c) >= 5 and c[1] == "issue" and c[2] == "edit"
        and "--remove-label" in c
    ]
    assert label_removals


def test_recover_stuck_locks_skips_without_label(
    tmp_config: Any, monkeypatch
):
    """An in-progress query result lacking the actual label is not stuck."""
    fake_issue = [
        {
            "number": 5,
            "title": "Doc audit: x",
            "body": "",
            "labels": [{"name": "doc-audit"}],  # no status:in-progress!
            "createdAt": "2026-05-20T08:00:00Z",
        }
    ]

    def fake_run_cmd(cmd, *args, **kwargs):
        cmd = list(cmd)
        if (
            len(cmd) >= 3 and cmd[1] == "issue" and cmd[2] == "list"
            and "status:in-progress" in cmd
        ):
            return subprocess.CompletedProcess(
                args=cmd, returncode=0, stdout=json.dumps(fake_issue), stderr="",
            )
        return subprocess.CompletedProcess(
            args=cmd, returncode=0, stdout="", stderr="",
        )

    monkeypatch.setattr(subprocess, "run", fake_run_cmd)
    args_ns = type("A", (), {"dry_run": False})()
    result = _empty_result()
    out = run._recover_stuck_locks(tmp_config, {}, args_ns, result)
    assert out == []


def test_recover_stuck_locks_skipped_with_pending_approval(
    tmp_config: Any, monkeypatch
):
    """An in-progress audit with a matching PA is not flagged as stuck."""
    stuck = [
        {
            "number": 1234,
            "title": "Doc audit: x",
            "body": "",
            "labels": [
                {"name": "doc-audit"},
                {"name": "status:in-progress"},
            ],
            "createdAt": "2026-05-20T08:00:00Z",
        }
    ]

    def fake_run_cmd(cmd, *args, **kwargs):
        cmd = list(cmd)
        if (
            len(cmd) >= 3 and cmd[1] == "issue" and cmd[2] == "list"
            and "status:in-progress" in cmd
        ):
            return subprocess.CompletedProcess(
                args=cmd, returncode=0, stdout=json.dumps(stuck), stderr="",
            )
        return subprocess.CompletedProcess(
            args=cmd, returncode=0, stdout="", stderr="",
        )

    monkeypatch.setattr(subprocess, "run", fake_run_cmd)
    args_ns = type("A", (), {"dry_run": False})()
    result = _empty_result()
    # PA index maps audit 1234 → PA 5678.
    out = run._recover_stuck_locks(tmp_config, {1234: 5678}, args_ns, result)
    assert out == []  # expected wait state — not stuck.


def test_recover_stuck_locks_weekly_priority(
    tmp_config: Any, monkeypatch
):
    """A weekly stuck audit synthesizes a weekly signal at priority 30."""
    stuck = [
        {
            "number": 99,
            "title": "Weekly doc audit — 2026-05-20",
            "body": "",
            "labels": [
                {"name": "doc-audit"},
                {"name": "status:in-progress"},
            ],
            "createdAt": "2026-05-20T08:00:00Z",
        }
    ]

    def fake_run_cmd(cmd, *args, **kwargs):
        cmd = list(cmd)
        if (
            len(cmd) >= 3 and cmd[1] == "issue" and cmd[2] == "list"
            and "status:in-progress" in cmd
        ):
            return subprocess.CompletedProcess(
                args=cmd, returncode=0, stdout=json.dumps(stuck), stderr="",
            )
        return subprocess.CompletedProcess(
            args=cmd, returncode=0, stdout="", stderr="",
        )

    monkeypatch.setattr(subprocess, "run", fake_run_cmd)
    args_ns = type("A", (), {"dry_run": False})()
    result = _empty_result()
    out = run._recover_stuck_locks(tmp_config, {}, args_ns, result)
    assert len(out) == 1
    assert out[0].kind == "weekly_doc_audit"
    assert out[0].priority == 30


# ---------------------------------------------------------------------------
# Cycle-4 Finding 1: stale-lock cross-reference query must include
# awaiting-decision pending-approvals (not just decided ones).
# ---------------------------------------------------------------------------


def test_in_progress_audit_with_undecided_pending_approval_is_not_reprocessed(
    tmp_config: Any,
    monkeypatch: pytest.MonkeyPatch,
    mock_anthropic: Any,
):
    """An open pending-approval WITHOUT a decision label is an
    EXPECTED wait state — the in-progress audit it references must
    NOT be flagged as a stuck lock and must NOT be reprocessed.

    Cycle-4 Finding 1 regression: the prior implementation built the
    cross-reference index from ``gh_source.pending()`` which filtered
    pending-approvals to only those with a decision label applied.
    An awaiting-decision PA would therefore be missing from the
    index → the in-progress audit got flagged as stuck and the lock
    was incorrectly cleared mid-decision.

    Production scenario this reproduces: audit #6500 was processed,
    filed pending-approval #7000 with no decision label, and the
    audit kept ``status:in-progress``. On the next tick the driver
    must recognize this as the expected wait state.
    """
    # Stuck-lock query result: one in-progress audit (#6500).
    in_progress = [
        {
            "number": 6500,
            "title": "Doc audit: abc1234 (felix-core)",
            "body": "Triggered by commit abc1234 on main.",
            "labels": [
                {"name": "doc-audit"},
                {"name": "status:in-progress"},
                {"name": "area/felix-core"},
            ],
            "createdAt": "2026-05-20T08:00:00Z",
        }
    ]
    # PA cross-ref query result: PA #7000 exists, references audit
    # #6500, but has NO decision label applied yet (operator hasn't
    # decided). ``gh_source.pending()`` would have filtered this out
    # because it only emits PAs with a decision label.
    pa_cross_ref = [
        {
            "number": 7000,
            "title": "Audit #6500: pending approval — 1 edit(s)",
            "body": "Refs #6500",
        }
    ]

    calls: list[list[str]] = []

    def fake_run_cmd(cmd, *args, **kwargs):
        cmd = list(cmd)
        calls.append(cmd)
        if len(cmd) >= 3 and cmd[1] == "issue" and cmd[2] == "list":
            labels = [
                cmd[i + 1] for i, tok in enumerate(cmd)
                if tok == "--label" and i + 1 < len(cmd)
            ]
            # The signal-source's pending-approval query (filters to
            # decided PAs) — return empty so the gh-source emits no
            # pending-approval signal for this fixture.
            if (
                "audit-pending-approval" in labels
                and "audit-approve" in labels
            ):
                return subprocess.CompletedProcess(
                    args=cmd, returncode=0, stdout="[]", stderr="",
                )
            # The pa-cross-ref query (cycle-4 dedicated query) —
            # enumerates ALL open audit-pending-approval, regardless
            # of decision label.
            if (
                "audit-pending-approval" in labels
                and "audit-approve" not in labels
                and "audit-reject" not in labels
                and "audit-skip" not in labels
            ):
                return subprocess.CompletedProcess(
                    args=cmd, returncode=0,
                    stdout=json.dumps(pa_cross_ref), stderr="",
                )
            # The stuck-lock query (in-progress audits).
            if "status:in-progress" in cmd:
                return subprocess.CompletedProcess(
                    args=cmd, returncode=0,
                    stdout=json.dumps(in_progress), stderr="",
                )
            # All other gh issue list calls return empty.
            return subprocess.CompletedProcess(
                args=cmd, returncode=0, stdout="[]", stderr="",
            )
        return subprocess.CompletedProcess(
            args=cmd, returncode=0, stdout="", stderr="",
        )

    monkeypatch.setattr(subprocess, "run", fake_run_cmd)

    # If the cross-ref index were built from gh_source.pending()
    # (cycle-3 behavior), the cross-ref index would be empty because
    # the undecided PA is filtered out → audit #6500 would be flagged
    # as stuck → the lock removal call would be issued and a
    # synthesized fresh signal would be processed. Either side-effect
    # would constitute the regression we're guarding against.
    config_path = (
        Path(tmp_config.llm.api_key_path).parent / "config.toml"
    )
    rc = run.main(["--config", str(config_path)])

    # The tick should succeed (no stuck lock detected, expected wait
    # state honored).
    assert rc == 0
    tick = json.loads(
        Path(tmp_config.paths.tick_signal_path).read_text(encoding="utf-8")
    )
    # No stale-lock recovery marker — the cycle-3 bug would have
    # surfaced one here.
    assert not any(
        "recovered-stale-lock" in e.lower() for e in tick["errors"]
    ), (
        f"audit #6500 was incorrectly flagged as a stuck lock; "
        f"errors={tick['errors']!r}"
    )
    # No lock-removal call was issued for #6500. The cycle-3 bug
    # would have invoked `gh issue edit 6500 ... --remove-label
    # status:in-progress` here.
    label_removals = [
        c for c in calls
        if len(c) >= 5 and c[1] == "issue" and c[2] == "edit"
        and c[3] == "6500" and "--remove-label" in c
    ]
    assert not label_removals, (
        f"unexpected lock-removal on #6500 (expected wait state was "
        f"misclassified as stuck); calls={calls!r}"
    )
    # And nothing about audit #6500 was reprocessed.
    assert tick["tick"]["audits_processed"] == []


# ---------------------------------------------------------------------------
# Cycle-4 Finding 3: judgment-helper exceptions must bump tick status
# from "success" to "partial".
# ---------------------------------------------------------------------------


def test_tier_classification_exception_routes_partial(
    tmp_config: Any,
    monkeypatch: pytest.MonkeyPatch,
    mock_anthropic: Any,
):
    """When ``tier_classification.classify`` raises, the audit workflow
    continues (filing a debt issue for the gap) but the tick must
    report ``status="partial"`` and exit code 2.

    Cycle-4 Finding 3 regression: the prior implementation appended
    to ``result.errors`` but left ``result.status`` at ``"success"``,
    so an operator running the driver via systemd never saw the
    partial-failure exit code that should have triggered an alert.

    This test reproduces the bug end-to-end via ``run.main()``:
    a doc audit with a triggering commit whose diff contains a
    frontmatter date bump → tier_classification crashes → routing
    still runs → tick exit code 2, status="partial".
    """
    audits = [
        {
            "number": 6600,
            "title": "Doc audit: cyclefour (felix-core)",
            "body": "Triggered by commit cyclefour on main.",
            "labels": [
                {"name": "doc-audit"},
                {"name": "area/felix-core"},
            ],
            "createdAt": "2026-05-20T08:00:00Z",
        }
    ]
    # A diff with a frontmatter date bump so _derive_candidate_edits
    # produces a candidate edit (without it, tier_classification is
    # never called).
    fake_diff = (
        "diff --git a/docs/runbooks/foo.md b/docs/runbooks/foo.md\n"
        "--- a/docs/runbooks/foo.md\n"
        "+++ b/docs/runbooks/foo.md\n"
        "@@ -1,3 +1,3 @@\n"
        " ---\n"
        "-last_validated: 2026-04-01\n"
        "+last_validated: 2026-05-20\n"
        " ---\n"
    )

    # Configure a domain map that puts docs/runbooks/foo.md in scope.
    Path(tmp_config.paths.doc_domain_map).write_text(
        json.dumps({
            "domains": {
                "area/felix-core": ["docs/runbooks/foo.md"],
            }
        }),
        encoding="utf-8",
    )

    def fake_run_cmd(cmd, *args, **kwargs):
        cmd = list(cmd)
        if cmd and cmd[0] == "git" and len(cmd) >= 2 and cmd[1] == "show":
            return subprocess.CompletedProcess(
                args=cmd, returncode=0, stdout=fake_diff, stderr="",
            )
        if len(cmd) >= 3 and cmd[1] == "issue" and cmd[2] == "list":
            labels = [
                cmd[i + 1] for i, tok in enumerate(cmd)
                if tok == "--label" and i + 1 < len(cmd)
            ]
            if (
                "doc-audit" in labels
                and "status:in-progress" not in labels
                and "audit-pending-approval" not in labels
            ):
                return subprocess.CompletedProcess(
                    args=cmd, returncode=0,
                    stdout=json.dumps(audits), stderr="",
                )
            return subprocess.CompletedProcess(
                args=cmd, returncode=0, stdout="[]", stderr="",
            )
        return subprocess.CompletedProcess(
            args=cmd, returncode=0, stdout="", stderr="",
        )

    monkeypatch.setattr(subprocess, "run", fake_run_cmd)

    # tier_classification.classify raises — the regression target.
    from doc_audit.judgment import tier_classification as tc

    def boom(*args, **kwargs):
        raise RuntimeError("simulated tier_classification crash")

    monkeypatch.setattr(tc, "classify", boom)

    # Routing succeeds normally (returns 0).
    def fake_apply(*args, **kwargs):
        return RoutingResult(
            applied_count=0, gated=False, pending_approval_issue=None,
            debt_issues=[], missing_issues=[], errors=[], exit_code=0,
        )

    monkeypatch.setattr(run, "apply_routing", fake_apply)

    config_path = (
        Path(tmp_config.llm.api_key_path).parent / "config.toml"
    )
    rc = run.main(["--config", str(config_path)])

    # Cycle-4 expectation: exit code 2 (partial) and status="partial".
    assert rc == 2, (
        f"expected exit code 2 (partial) when tier_classification "
        f"raises; got rc={rc}"
    )
    tick = json.loads(
        Path(tmp_config.paths.tick_signal_path).read_text(encoding="utf-8")
    )
    assert tick["status"] == "partial", (
        f"expected status='partial' when tier_classification raises; "
        f"got status={tick['status']!r} errors={tick['errors']!r}"
    )
    # The actual error message is preserved.
    assert any(
        "tier_classification failed" in e for e in tick["errors"]
    ), tick["errors"]


# ---------------------------------------------------------------------------
# Cycle-4 Finding 4: main()'s finally block must write a per-tick
# entry to the activity log (in addition to writing last-tick.json).
# ---------------------------------------------------------------------------


def test_main_finally_writes_tick_signal_and_activity_log(
    tmp_config: Any,
    monkeypatch: pytest.MonkeyPatch,
    mock_anthropic: Any,
):
    """A single ``main()`` invocation must produce BOTH:

    - ``last-tick.json`` (structured tick signal, programmatic).
    - A per-tick ``## Tick`` entry in today's
      ``doc-auditor-<date>.md`` (operator-visible log).

    Both files must be present and non-empty:

    1. **Empty-queue path**: no audits to process → no
       ``## Audit run`` entries via ``append_audit_entry`` → without
       the cycle-4 fix the operator log would be empty for the day
       even though the tick fired.
    2. **Crashed-mid-tick path**: an exception escapes ``_run_tick``
       → no audit entries → same empty-log problem with a failure
       status that's not visible in the operator log.

    Both invariants are checked in this single test by running two
    ticks under different conditions and asserting the log file
    accumulates entries.
    """
    # --- Tick 1: empty queue (no audits, no PAs, no drift) ---
    def fake_run_cmd(cmd, *args, **kwargs):
        return subprocess.CompletedProcess(
            args=list(cmd), returncode=0, stdout="[]", stderr=""
        )

    monkeypatch.setattr(subprocess, "run", fake_run_cmd)
    config_path = (
        Path(tmp_config.llm.api_key_path).parent / "config.toml"
    )
    rc1 = run.main(["--config", str(config_path)])
    assert rc1 == 0

    # last-tick.json present + non-empty.
    tick_path = Path(tmp_config.paths.tick_signal_path)
    assert tick_path.is_file()
    assert tick_path.stat().st_size > 0
    tick1 = json.loads(tick_path.read_text(encoding="utf-8"))
    assert tick1["status"] == "success"

    # Per-tick activity log entry written even though the queue was
    # empty. The file name uses the local-tz date; we find it via
    # glob since the fixture date may vary by host.
    log_dir = Path(tmp_config.paths.activity_log_dir)
    log_files = list(log_dir.glob("doc-auditor-*.md"))
    assert log_files, (
        f"expected a per-tick activity log entry even for empty queue; "
        f"log_dir={log_dir!r} contents={list(log_dir.iterdir())!r}"
    )
    log_text_after_tick1 = log_files[0].read_text(encoding="utf-8")
    assert "## Tick" in log_text_after_tick1, (
        f"expected '## Tick' header in activity log; got "
        f"{log_text_after_tick1!r}"
    )
    assert "Status: success" in log_text_after_tick1
    assert "Signals seen: 0" in log_text_after_tick1

    # --- Tick 2: _run_tick raises → activity log STILL gets an entry ---
    def boom(*args, **kwargs):
        raise RuntimeError("simulated mid-tick crash")

    monkeypatch.setattr(run, "_run_tick", boom)
    rc2 = run.main(["--config", str(config_path)])
    assert rc2 == 1

    # last-tick.json was re-written with status=failure.
    tick2 = json.loads(tick_path.read_text(encoding="utf-8"))
    assert tick2["status"] == "failure"

    # Activity log gained a second per-tick entry reflecting the
    # failure — operators see crashes in the daily log too.
    log_text_after_tick2 = log_files[0].read_text(encoding="utf-8")
    # Count ## Tick headers — should be at least 2 by now.
    tick_header_count = log_text_after_tick2.count("## Tick")
    assert tick_header_count >= 2, (
        f"expected at least 2 '## Tick' headers after two ticks; "
        f"got {tick_header_count} in {log_text_after_tick2!r}"
    )
    assert "Status: failure" in log_text_after_tick2
