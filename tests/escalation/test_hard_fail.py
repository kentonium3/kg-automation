"""Tests for scripts/escalation/hard_fail.py (WP04 / T014).

Coverage matrix per work-package spec:

- ``render_bug_body`` -- title format, body sections, C-006 (no second-brain
  paths), each ``HardFailReason`` value.
- ``dedup_existing_open`` -- match / no-match, exact ``gh`` argv per
  research D9, ``--state open`` filter.
- ``file_hard_fail_bug`` -- dedup short-circuit, full filing path,
  double-fire prevention across two simulated ticks, re-fire after issue
  is closed, subprocess failure.

All ``subprocess.run`` calls are monkey-patched. No live ``gh`` invocations,
no live ``felix-file-issue.py`` invocations.
"""
from __future__ import annotations

import json
import subprocess
from typing import Any, Optional

import pytest

from scripts.escalation.hard_fail import (
    HARD_FAIL_LABELS,
    REPO,
    dedup_existing_open,
    file_hard_fail_bug,
    render_bug_body,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


class _FakeCompletedProcess:
    """Minimal stand-in for ``subprocess.CompletedProcess`` used in mocks."""

    def __init__(self, stdout: str = "", stderr: str = "", returncode: int = 0):
        self.stdout = stdout
        self.stderr = stderr
        self.returncode = returncode


def _default_vikunja_state() -> dict:
    """Canonical vikunja_state dict used across most rendering tests."""
    return {
        "done": False,
        "due_date": "2026-05-15T00:00:00Z",
    }


# ---------------------------------------------------------------------------
# render_bug_body
# ---------------------------------------------------------------------------


def test_render_title_format():
    """Title must match Entity 5: ``Escalation hard-fail: <title> (task #<id>) — <reason>``.

    The separator is U+2014 EM DASH (``—``), not two ASCII hyphens. When the
    title flows through ``felix-file-issue.py``, the helper prefixes
    ``Bug: ``, so the final filed title reads
    ``Bug: Escalation hard-fail: ... (task #N) — ...``.
    """
    title, _ = render_bug_body(
        task_id=1234,
        project_id=4,
        task_title="Email Q3 board summary",
        reason="malformed_jsonl_record",
        jsonl_path="/data/services/openclaw/state/escalation/inbox-escalation-history.jsonl",
        detection_snippet='{"domain":"escalation",...broken...}',
        vikunja_state=_default_vikunja_state(),
    )
    assert title == (
        "Escalation hard-fail: Email Q3 board summary "
        "(task #1234) — malformed JSONL"
    )
    # Explicit em dash check -- a future ASCII regression would fail here.
    assert " — " in title
    assert " -- " not in title


@pytest.mark.parametrize(
    "reason,short",
    [
        ("malformed_jsonl_record", "malformed JSONL"),
        ("derive_state_inconsistency", "derive_state error"),
    ],
)
def test_render_title_for_each_reason(reason: str, short: str):
    """Each ``HardFailReason`` value maps to the right short reason in the title."""
    title, _ = render_bug_body(
        task_id=42,
        project_id=4,
        task_title="Some task",
        reason=reason,  # type: ignore[arg-type]
        jsonl_path="/data/services/openclaw/state/escalation/x.jsonl",
        detection_snippet="snippet",
        vikunja_state=_default_vikunja_state(),
    )
    # U+2014 em dash separator per Entity 5.
    assert title.endswith(f" — {short}")
    assert f"(task #42)" in title


def test_render_title_uses_em_dash_not_ascii_hyphens():
    """Regression guard: the separator before the short reason MUST be U+2014.

    The dedup query is substring-anchored on ``(task #<id>)`` and the
    ``Escalation hard-fail`` marker so it tolerates either separator, but
    the data-model Entity 5 spec requires ``—`` verbatim. Pin the format.
    """
    title, _ = render_bug_body(
        task_id=99,
        project_id=4,
        task_title="Pin separator",
        reason="derive_state_inconsistency",
        jsonl_path="/data/x.jsonl",
        detection_snippet="no records found",
        vikunja_state=_default_vikunja_state(),
    )
    assert "—" in title  # U+2014 em dash present
    assert "--" not in title  # ASCII double-hyphen absent


def test_render_body_includes_jsonl_path():
    """Body must surface the absolute JSONL path in the Hard-fail context block."""
    path = "/data/services/openclaw/state/escalation/inbox-escalation-history.jsonl"
    _, body = render_bug_body(
        task_id=1234,
        project_id=4,
        task_title="Task",
        reason="malformed_jsonl_record",
        jsonl_path=path,
        detection_snippet="snippet",
        vikunja_state=_default_vikunja_state(),
    )
    assert path in body
    assert "## Hard-fail context" in body


def test_render_body_includes_detection_snippet():
    """Body must include the raw detection snippet inside the Detection block."""
    snippet = '{"domain":"escalation","task_id":1234,...corrupt...}'
    _, body = render_bug_body(
        task_id=1234,
        project_id=4,
        task_title="Task",
        reason="malformed_jsonl_record",
        jsonl_path="/data/x.jsonl",
        detection_snippet=snippet,
        vikunja_state=_default_vikunja_state(),
    )
    assert "## Detection snippet" in body
    assert snippet in body


def test_render_body_omits_derive_state_error_when_not_provided():
    """``derive_state_error_message=None`` -> body shows ``n/a`` placeholder."""
    _, body = render_bug_body(
        task_id=1234,
        project_id=4,
        task_title="Task",
        reason="malformed_jsonl_record",
        jsonl_path="/data/x.jsonl",
        detection_snippet="snippet",
        vikunja_state=_default_vikunja_state(),
        derive_state_error_message=None,
    )
    assert "## derive_state output" in body
    assert "n/a" in body


def test_render_body_includes_derive_state_error_when_provided():
    """``derive_state_error_message=<msg>`` -> body renders it inside a code block."""
    err = "EscalationStateError: level_sent record missing required 'level' param"
    _, body = render_bug_body(
        task_id=1234,
        project_id=4,
        task_title="Task",
        reason="derive_state_inconsistency",
        jsonl_path="/data/x.jsonl",
        detection_snippet="snippet",
        vikunja_state=_default_vikunja_state(),
        derive_state_error_message=err,
    )
    assert err in body


def test_render_body_no_second_brain_paths():
    """C-006: well-behaved caller -> body has zero second-brain substrings.

    Happy-path pin: when callers pass clean inputs, the rendered body
    contains no ``~/second-brain``, ``/second-brain``, or ``_private``
    substrings. The data-model Entity 5 template itself has zero
    second-brain references, so this test guards against accidental
    template additions in future refactors.
    """
    _, body = render_bug_body(
        task_id=1234,
        project_id=4,
        task_title="Email Q3 board summary",
        reason="malformed_jsonl_record",
        jsonl_path="/data/services/openclaw/state/escalation/inbox-escalation-history.jsonl",
        detection_snippet="snippet without second brain reference",
        vikunja_state=_default_vikunja_state(),
        derive_state_error_message=None,
    )
    assert "~/second-brain" not in body
    assert "second-brain" not in body
    assert "_private" not in body


def test_render_body_redacts_second_brain_in_jsonl_path():
    """Adversarial C-006: a tainted ``jsonl_path`` MUST be redacted.

    Enforcement is at the render boundary via ``_sanitize_for_body``.
    Even if a caller passes a path under ``~/second-brain/_private``,
    the body must replace the forbidden substrings with the
    ``[REDACTED:second-brain-path]`` placeholder.

    Note: ``"second-brain"`` appears inside the placeholder itself, so we
    assert on the forbidden path *fragments* (``~/second-brain``,
    ``/second-brain``, ``_private``) rather than the bare word.
    """
    tainted_path = (
        "/Users/kent/second-brain/notes/04-Growth/_private/escalation.jsonl"
    )
    _, body = render_bug_body(
        task_id=1234,
        project_id=4,
        task_title="Clean title",
        reason="malformed_jsonl_record",
        jsonl_path=tainted_path,
        detection_snippet="snippet",
        vikunja_state=_default_vikunja_state(),
    )
    # The tainted path fragments must NOT appear in the rendered body.
    assert "~/second-brain" not in body
    assert "/second-brain" not in body
    assert "_private" not in body
    # The original raw filename suffix that depends on the redacted root
    # must not appear either -- a successful redaction breaks the path.
    assert "04-Growth/_private/escalation.jsonl" not in body
    # The placeholder MUST appear in the JSONL file line.
    assert "[REDACTED:second-brain-path]" in body


def test_render_body_redacts_second_brain_in_detection_snippet():
    """Adversarial C-006: a tainted ``detection_snippet`` MUST be redacted."""
    tainted_snippet = (
        '{"domain":"escalation","leaked":"~/second-brain/notes/x.md",'
        '"task_id":1234}'
    )
    _, body = render_bug_body(
        task_id=1234,
        project_id=4,
        task_title="Clean title",
        reason="malformed_jsonl_record",
        jsonl_path="/data/x.jsonl",
        detection_snippet=tainted_snippet,
        vikunja_state=_default_vikunja_state(),
    )
    assert "~/second-brain" not in body
    assert "/second-brain" not in body
    assert "[REDACTED:second-brain-path]" in body


def test_render_body_redacts_second_brain_in_task_title():
    """Adversarial C-006: a tainted ``task_title`` MUST be redacted in body AND title.

    The task title appears in both the title literal AND the body
    (``vikunja_link`` line in the Hard-fail context block). Both must be
    sanitized so a malicious or accidentally-tainted title cannot leak.
    """
    tainted_title = "Review _private notes for Q3 plan"
    title, body = render_bug_body(
        task_id=1234,
        project_id=4,
        task_title=tainted_title,
        reason="malformed_jsonl_record",
        jsonl_path="/data/x.jsonl",
        detection_snippet="snippet",
        vikunja_state=_default_vikunja_state(),
    )
    # _private must not survive in either output.
    assert "_private" not in title
    assert "_private" not in body
    # Placeholder must appear in both (title and body include the task title).
    assert "[REDACTED:second-brain-path]" in title
    assert "[REDACTED:second-brain-path]" in body


def test_render_body_redacts_second_brain_in_derive_state_error():
    """Adversarial C-006: a tainted ``derive_state_error_message`` MUST be redacted."""
    tainted_error = (
        "EscalationStateError: malformed level_sent at "
        "/Users/kent/second-brain/notes/04-Growth/_private/escalation.jsonl line 42"
    )
    _, body = render_bug_body(
        task_id=1234,
        project_id=4,
        task_title="Clean title",
        reason="derive_state_inconsistency",
        jsonl_path="/data/x.jsonl",
        detection_snippet="snippet",
        vikunja_state=_default_vikunja_state(),
        derive_state_error_message=tainted_error,
    )
    assert "~/second-brain" not in body
    assert "/second-brain" not in body
    assert "_private" not in body
    assert "[REDACTED:second-brain-path]" in body


def test_render_body_redacts_second_brain_in_vikunja_url():
    """Adversarial C-006: a tainted ``vikunja_url`` MUST be redacted.

    ``vikunja_url`` is a caller-provided string interpolated into the
    Markdown link target in the Hard-fail context block. An adversarial
    caller smuggling ``~/second-brain``, ``/second-brain``, or ``_private``
    through this field must be redacted to ``[REDACTED:second-brain-path]``
    before the body is rendered.

    Real Vikunja URLs (e.g., ``https://office2.tail0f5f56.ts.net/tasks/1234``)
    contain none of the forbidden substrings, so well-behaved callers see
    no change in behaviour -- this test only guards the adversarial path.
    """
    tainted_url = "file:///Users/kent/second-brain/notes/04-Growth/_private/leak.md"
    _, body = render_bug_body(
        task_id=1234,
        project_id=4,
        task_title="Clean title",
        reason="malformed_jsonl_record",
        jsonl_path="/data/x.jsonl",
        detection_snippet="snippet",
        vikunja_state=_default_vikunja_state(),
        vikunja_url=tainted_url,
    )
    assert "~/second-brain" not in body
    assert "/second-brain" not in body
    assert "_private" not in body
    # The forbidden literal path fragment must not survive in the link target.
    assert "second-brain/notes/04-Growth/_private/leak.md" not in body
    assert "[REDACTED:second-brain-path]" in body


def test_render_body_preserves_real_vikunja_url():
    """Sanity check: a real Vikunja URL passes through ``_sanitize_for_body`` unchanged.

    Guards against an over-aggressive sanitizer regression -- the canonical
    office2 Tailscale URL must appear verbatim in the rendered link target.
    """
    real_url = "https://office2.tail0f5f56.ts.net/tasks/1234"
    _, body = render_bug_body(
        task_id=1234,
        project_id=4,
        task_title="Clean title",
        reason="malformed_jsonl_record",
        jsonl_path="/data/x.jsonl",
        detection_snippet="snippet",
        vikunja_state=_default_vikunja_state(),
        vikunja_url=real_url,
    )
    assert real_url in body
    assert "[REDACTED:second-brain-path]" not in body


def test_render_body_redacts_second_brain_in_detected_at():
    """Adversarial C-006: a tainted ``detected_at`` MUST be redacted.

    ``detected_at`` is typed as ``Optional[str]`` and interpolated raw into
    the body's Hard-fail context block. In normal usage it is a UTC ISO-8601
    timestamp (no forbidden substrings), but the function accepts any string,
    so an adversarial caller could smuggle ``~/second-brain``, ``/second-brain``,
    or ``_private`` through this field. Both forbidden fragments and the
    redaction placeholder must be detectable in the rendered body.
    """
    tainted_detected_at = (
        "2026-05-19T13:00:00Z (from ~/second-brain/notes/04-Growth/_private/log.md)"
    )
    _, body = render_bug_body(
        task_id=1234,
        project_id=4,
        task_title="Clean title",
        reason="malformed_jsonl_record",
        jsonl_path="/data/x.jsonl",
        detection_snippet="snippet",
        vikunja_state=_default_vikunja_state(),
        detected_at=tainted_detected_at,
    )
    assert "~/second-brain" not in body
    assert "/second-brain" not in body
    assert "_private" not in body
    assert "[REDACTED:second-brain-path]" in body


def test_render_rejects_unknown_reason():
    """``ValueError`` raised on a reason outside the ``HardFailReason`` set."""
    with pytest.raises(ValueError) as exc_info:
        render_bug_body(
            task_id=1,
            project_id=4,
            task_title="Task",
            reason="not_a_real_reason",  # type: ignore[arg-type]
            jsonl_path="/data/x.jsonl",
            detection_snippet="snippet",
            vikunja_state=_default_vikunja_state(),
        )
    assert "not_a_real_reason" in str(exc_info.value)


# ---------------------------------------------------------------------------
# dedup_existing_open
# ---------------------------------------------------------------------------


def test_dedup_returns_url_on_match(monkeypatch):
    """When gh returns one issue, dedup returns its URL."""
    captured: dict[str, Any] = {}

    def fake_run(argv, **kwargs):
        captured["argv"] = list(argv)
        captured["kwargs"] = kwargs
        return _FakeCompletedProcess(
            stdout=json.dumps(
                [
                    {
                        "number": 999,
                        "title": "Bug: Escalation hard-fail: ... (task #1234) — malformed JSONL",
                        "url": "https://github.com/kentonium3/kg-automation/issues/999",
                    }
                ]
            )
        )

    monkeypatch.setattr(subprocess, "run", fake_run)
    monkeypatch.setattr(
        "scripts.escalation.hard_fail.subprocess.run", fake_run
    )

    url = dedup_existing_open(1234)
    assert url == "https://github.com/kentonium3/kg-automation/issues/999"


def test_dedup_returns_none_on_empty(monkeypatch):
    """When gh returns ``[]``, dedup returns ``None`` (no open bug exists)."""
    monkeypatch.setattr(
        "scripts.escalation.hard_fail.subprocess.run",
        lambda *a, **kw: _FakeCompletedProcess(stdout="[]"),
    )
    assert dedup_existing_open(1234) is None


def test_dedup_uses_correct_search_query(monkeypatch):
    """Exact ``--search`` argv per research D9.

    Verbatim: ``'in:title "(task #<id>)" "Escalation hard-fail"'``.
    """
    captured: dict[str, Any] = {}

    def fake_run(argv, **kwargs):
        captured["argv"] = list(argv)
        return _FakeCompletedProcess(stdout="[]")

    monkeypatch.setattr(
        "scripts.escalation.hard_fail.subprocess.run", fake_run
    )

    dedup_existing_open(1234)
    argv = captured["argv"]

    # Spot-check the canonical shape per D9.
    assert argv[0] == "gh"
    assert argv[1] == "issue"
    assert argv[2] == "list"
    # --search value contains BOTH anchors per D9.
    assert "--search" in argv
    search_value = argv[argv.index("--search") + 1]
    assert search_value == 'in:title "(task #1234)" "Escalation hard-fail"'
    # Required JSON fields per the WP04 contract.
    assert "--json" in argv
    json_value = argv[argv.index("--json") + 1]
    assert "url" in json_value
    assert "number" in json_value
    assert "title" in json_value
    # --limit 5 per the contract.
    assert "--limit" in argv
    assert argv[argv.index("--limit") + 1] == "5"
    # Repo pinned via constant.
    assert "--repo" in argv
    assert argv[argv.index("--repo") + 1] == REPO


def test_dedup_uses_state_open_filter(monkeypatch):
    """``--state open`` MUST be in argv (per D9, enables re-fire after close)."""
    captured: dict[str, Any] = {}

    def fake_run(argv, **kwargs):
        captured["argv"] = list(argv)
        return _FakeCompletedProcess(stdout="[]")

    monkeypatch.setattr(
        "scripts.escalation.hard_fail.subprocess.run", fake_run
    )

    dedup_existing_open(1234)
    argv = captured["argv"]
    assert "--state" in argv
    assert argv[argv.index("--state") + 1] == "open"


def test_dedup_reraises_subprocess_failure(monkeypatch):
    """``gh`` non-zero exit re-raises ``CalledProcessError`` (no silent swallow)."""

    def fake_run(argv, **kwargs):
        raise subprocess.CalledProcessError(
            returncode=1,
            cmd=argv,
            output="",
            stderr="gh: HTTP 502 from github.com",
        )

    monkeypatch.setattr(
        "scripts.escalation.hard_fail.subprocess.run", fake_run
    )

    with pytest.raises(subprocess.CalledProcessError):
        dedup_existing_open(1234)


# ---------------------------------------------------------------------------
# file_hard_fail_bug -- dedup behavior
# ---------------------------------------------------------------------------


def test_file_skips_when_dedup_hit(monkeypatch):
    """When gh returns a matching issue, felix-file-issue is NOT invoked."""
    invocation_argvs: list[list[str]] = []

    def fake_run(argv, **kwargs):
        invocation_argvs.append(list(argv))
        # The first (and only) invocation should be the dedup gh query.
        if argv[:3] == ["gh", "issue", "list"]:
            return _FakeCompletedProcess(
                stdout=json.dumps(
                    [
                        {
                            "number": 42,
                            "title": "Bug: Escalation hard-fail: ... (task #1234) — malformed JSONL",
                            "url": "https://github.com/kentonium3/kg-automation/issues/42",
                        }
                    ]
                )
            )
        # If we reach here, the helper invoked felix-file-issue -- fail loudly.
        raise AssertionError(
            f"felix-file-issue invoked despite dedup hit: argv={argv}"
        )

    monkeypatch.setattr(
        "scripts.escalation.hard_fail.subprocess.run", fake_run
    )

    result = file_hard_fail_bug(
        task_id=1234,
        project_id=4,
        task_title="Task",
        reason="malformed_jsonl_record",
        jsonl_path="/data/x.jsonl",
        detection_snippet="snippet",
        vikunja_state=_default_vikunja_state(),
    )

    assert result == {
        "filed": False,
        "deduped": True,
        "existing_url": "https://github.com/kentonium3/kg-automation/issues/42",
    }
    # Confirm only the dedup gh call ran.
    assert len(invocation_argvs) == 1
    assert invocation_argvs[0][:3] == ["gh", "issue", "list"]


def test_file_invokes_when_no_dedup_match(monkeypatch):
    """When gh returns empty, felix-file-issue IS invoked with the right argv."""
    invocation_argvs: list[list[str]] = []

    def fake_run(argv, **kwargs):
        invocation_argvs.append(list(argv))
        if argv[:3] == ["gh", "issue", "list"]:
            return _FakeCompletedProcess(stdout="[]")
        # Second call: felix-file-issue. Return a plausible stdout.
        return _FakeCompletedProcess(
            stdout=(
                '{"issue_number": 555, '
                '"issue_url": "https://github.com/kentonium3/kg-automation/issues/555", '
                '"title": "Bug: Escalation hard-fail: Task (task #1234) — malformed JSONL", '
                '"labels": ["P2-bug", "area/escalation", "spec: ready"]}\n'
                "SUMMARY: type=bug priority=P2 area=escalation tier=3 spec=ready issue=#555"
            )
        )

    monkeypatch.setattr(
        "scripts.escalation.hard_fail.subprocess.run", fake_run
    )

    result = file_hard_fail_bug(
        task_id=1234,
        project_id=4,
        task_title="Task",
        reason="malformed_jsonl_record",
        jsonl_path="/data/x.jsonl",
        detection_snippet="snippet",
        vikunja_state=_default_vikunja_state(),
    )

    assert result["filed"] is True
    assert result["deduped"] is False
    assert (
        result["issue_url"]
        == "https://github.com/kentonium3/kg-automation/issues/555"
    )

    # Two subprocess invocations: dedup (gh) then file (felix-file-issue).
    assert len(invocation_argvs) == 2
    assert invocation_argvs[0][:3] == ["gh", "issue", "list"]

    # Verify the felix-file-issue argv shape.
    felix_argv = invocation_argvs[1]
    assert felix_argv[0] == "python3"
    assert "scripts/openclaw/agents/main/felix-file-issue.py" in felix_argv[1]
    assert "--type" in felix_argv
    assert felix_argv[felix_argv.index("--type") + 1] == "bug"
    assert "--priority" in felix_argv
    assert felix_argv[felix_argv.index("--priority") + 1] == "P2"
    assert "--area" in felix_argv
    assert felix_argv[felix_argv.index("--area") + 1] == "escalation"
    assert "--title" in felix_argv
    title_arg = felix_argv[felix_argv.index("--title") + 1]
    # Title MUST match the Entity 5 format (em dash, not ASCII hyphens).
    assert title_arg == (
        "Escalation hard-fail: Task (task #1234) — malformed JSONL"
    )
    # Body is passed via a tempfile path, not inline.
    assert "--problem-statement-file" in felix_argv


# ---------------------------------------------------------------------------
# Double-fire prevention (D9) -- two simulated ticks
# ---------------------------------------------------------------------------


def test_two_consecutive_ticks_file_only_once(monkeypatch):
    """First tick fires; second tick dedups (gh now returns the just-filed issue)."""
    # Track what each call sees. We sequence the dedup response: empty,
    # then populated. Filing happens once.
    call_log: list[str] = []
    state = {"dedup_returns": "empty"}

    def fake_run(argv, **kwargs):
        if argv[:3] == ["gh", "issue", "list"]:
            call_log.append("dedup")
            if state["dedup_returns"] == "empty":
                return _FakeCompletedProcess(stdout="[]")
            return _FakeCompletedProcess(
                stdout=json.dumps(
                    [
                        {
                            "number": 555,
                            "title": "Bug: Escalation hard-fail: Task (task #1234) — malformed JSONL",
                            "url": "https://github.com/kentonium3/kg-automation/issues/555",
                        }
                    ]
                )
            )
        # felix-file-issue.py invocation
        call_log.append("file")
        return _FakeCompletedProcess(
            stdout=(
                '{"issue_number": 555, '
                '"issue_url": "https://github.com/kentonium3/kg-automation/issues/555"}'
            )
        )

    monkeypatch.setattr(
        "scripts.escalation.hard_fail.subprocess.run", fake_run
    )

    common_kwargs = dict(
        task_id=1234,
        project_id=4,
        task_title="Task",
        reason="malformed_jsonl_record",
        jsonl_path="/data/x.jsonl",
        detection_snippet="snippet",
        vikunja_state=_default_vikunja_state(),
    )

    # Tick 1: empty dedup -> file the bug.
    result1 = file_hard_fail_bug(**common_kwargs)
    assert result1["filed"] is True
    assert result1["deduped"] is False
    assert (
        result1["issue_url"]
        == "https://github.com/kentonium3/kg-automation/issues/555"
    )

    # Tick 2: dedup now returns the just-filed issue -> skip filing.
    state["dedup_returns"] = "populated"
    result2 = file_hard_fail_bug(**common_kwargs)
    assert result2["filed"] is False
    assert result2["deduped"] is True
    assert (
        result2["existing_url"]
        == "https://github.com/kentonium3/kg-automation/issues/555"
    )

    # Total subprocess calls: 2 dedups + 1 file = 3.
    assert call_log == ["dedup", "file", "dedup"]


# ---------------------------------------------------------------------------
# Re-fire after close
# ---------------------------------------------------------------------------


def test_refire_after_issue_closed(monkeypatch):
    """After operator closes the bug w/o fix, next tick MUST re-file.

    The dedup query carries ``--state open`` per D9, so closed issues fall
    outside its scope. We simulate this by returning ``[]`` from gh even
    though a (closed) issue exists in the repo.
    """
    call_log: list[str] = []

    def fake_run(argv, **kwargs):
        if argv[:3] == ["gh", "issue", "list"]:
            call_log.append("dedup")
            # The closed issue is filtered out by --state open; gh returns [].
            return _FakeCompletedProcess(stdout="[]")
        call_log.append("file")
        return _FakeCompletedProcess(
            stdout=(
                '{"issue_number": 600, '
                '"issue_url": "https://github.com/kentonium3/kg-automation/issues/600"}'
            )
        )

    monkeypatch.setattr(
        "scripts.escalation.hard_fail.subprocess.run", fake_run
    )

    result = file_hard_fail_bug(
        task_id=1234,
        project_id=4,
        task_title="Task",
        reason="malformed_jsonl_record",
        jsonl_path="/data/x.jsonl",
        detection_snippet="snippet",
        vikunja_state=_default_vikunja_state(),
    )
    assert result["filed"] is True
    assert result["deduped"] is False
    assert (
        result["issue_url"]
        == "https://github.com/kentonium3/kg-automation/issues/600"
    )
    assert call_log == ["dedup", "file"]


# ---------------------------------------------------------------------------
# Subprocess failure paths
# ---------------------------------------------------------------------------


def test_file_returns_error_on_felix_file_issue_failure(monkeypatch):
    """felix-file-issue.py exit != 0 -> ``{filed: False, deduped: False, error: ...}``."""

    def fake_run(argv, **kwargs):
        if argv[:3] == ["gh", "issue", "list"]:
            return _FakeCompletedProcess(stdout="[]")
        raise subprocess.CalledProcessError(
            returncode=1,
            cmd=argv,
            output="",
            stderr="gh identity check failed: not kg-felix-bot",
        )

    monkeypatch.setattr(
        "scripts.escalation.hard_fail.subprocess.run", fake_run
    )

    result = file_hard_fail_bug(
        task_id=1234,
        project_id=4,
        task_title="Task",
        reason="malformed_jsonl_record",
        jsonl_path="/data/x.jsonl",
        detection_snippet="snippet",
        vikunja_state=_default_vikunja_state(),
    )
    assert result["filed"] is False
    assert result["deduped"] is False
    assert "felix-file-issue.py failed" in result["error"]
    assert "gh identity check failed" in result["error"]


def test_file_returns_error_on_dedup_failure(monkeypatch):
    """Dedup gh failure -> ``{filed: False, deduped: False, error: ...}``."""

    def fake_run(argv, **kwargs):
        raise subprocess.CalledProcessError(
            returncode=1,
            cmd=argv,
            output="",
            stderr="gh: HTTP 502",
        )

    monkeypatch.setattr(
        "scripts.escalation.hard_fail.subprocess.run", fake_run
    )

    result = file_hard_fail_bug(
        task_id=1234,
        project_id=4,
        task_title="Task",
        reason="malformed_jsonl_record",
        jsonl_path="/data/x.jsonl",
        detection_snippet="snippet",
        vikunja_state=_default_vikunja_state(),
    )
    assert result["filed"] is False
    assert result["deduped"] is False
    assert "dedup query failed" in result["error"]
    assert "HTTP 502" in result["error"]


# ---------------------------------------------------------------------------
# Module constants
# ---------------------------------------------------------------------------


def test_hard_fail_labels_constant():
    """``HARD_FAIL_LABELS`` is the canonical label list."""
    assert HARD_FAIL_LABELS == ["P2-bug", "area/escalation"]


def test_repo_constant():
    """``REPO`` pins to the kg-automation repository."""
    assert REPO == "kentonium3/kg-automation"
