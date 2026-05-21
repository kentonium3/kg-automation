"""Integration tests for the 5 documented tick outcomes (T030).

These tests exercise the FULL driver end-to-end:
``run.main()`` → signal sources → audit/pending-approval processing →
routing layer → tick signal + activity log.

Mocked surfaces (per ``conftest.py`` design):
- ``subprocess.run`` is patched per-test to route by the ``gh ...``
  command shape (label / subcommand / state). Both the signal-source
  ``gh issue list`` queries and the routing-layer commit/comment/close
  calls flow through the same patch.
- ``anthropic.Anthropic`` is patched via ``mock_anthropic`` so
  judgment calls don't escape to the network.
- The routing layer is monkeypatched at
  ``doc_audit.run.apply_routing`` so we can return a deterministic
  :class:`RoutingResult` per outcome.

The five outcomes (per WP06 prompt + spec):
1. **Empty queue** — no signals; exit 0; status=success.
2. **Debt-only audit** — audit produces no Tier A/B edits; only debt;
   no commit; no pending-approval.
3. **Tier-A auto-commit** — audit produces one Tier-A edit that the
   routing layer applies + commits.
4. **Pending-approval-apply** — a labeled pending-approval issue is
   applied (close issue + audit).
5. **Pending-approval-reject** — same but reject path; gated edits
   demoted to debt instead of applied.
"""
from __future__ import annotations

import json
import subprocess
from pathlib import Path
from typing import Any, Callable

import pytest

# Ensure scripts/ is on sys.path (conftest also does this; defensive)
import sys
SCRIPTS = Path(__file__).resolve().parent.parent.parent / "scripts"
if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))

from doc_audit import run  # noqa: E402
from doc_audit.helpers.handle_audit_routing import RoutingResult  # noqa: E402


# ---------------------------------------------------------------------------
# Test-local helpers — flexible gh routing
# ---------------------------------------------------------------------------


def _completed(stdout: str = "", stderr: str = "", rc: int = 0):
    return subprocess.CompletedProcess(
        args=["gh"], returncode=rc, stdout=stdout, stderr=stderr
    )


def _make_gh_router(
    monkeypatch: pytest.MonkeyPatch,
    *,
    list_by_label: dict[str, list[dict]] | None = None,
    view_by_number: dict[int, dict] | None = None,
    timeline_by_number: dict[int, dict] | None = None,
    default_list: list[dict] | None = None,
    raise_on: Callable[[list[str]], BaseException | None] | None = None,
) -> list[list[str]]:
    """Return a calls log; patch ``subprocess.run`` to route gh commands.

    Routing:
    - ``gh issue list ... --label <L>`` → ``list_by_label[L]`` if present,
      else ``default_list`` (default ``[]``).
    - ``gh issue view <N>`` → ``view_by_number[N]`` if present, else ``{}``.
    - ``gh api repos/<repo>/issues/<N>/timeline --jq ...`` →
      ``timeline_by_number[N]`` if present, else ``null`` (the jq
      filter returns ``null`` when no decision-label event exists).
      The value is rendered as a JSON object representing the jq's
      ``{label, actor, at}`` result.
    - All other gh subcommands return rc=0 stdout="" — they're side
      effects the driver doesn't read back from.
    - When ``raise_on(cmd)`` returns an exception, the patch raises it
      instead of returning a CompletedProcess.
    """
    list_by_label = list_by_label or {}
    view_by_number = view_by_number or {}
    timeline_by_number = timeline_by_number or {}
    default_list = default_list if default_list is not None else []

    calls: list[list[str]] = []

    def fake_run(cmd, *args, **kwargs):  # type: ignore[no-untyped-def]
        if not (isinstance(cmd, (list, tuple)) and cmd and cmd[0] == "gh"):
            raise RuntimeError(f"unexpected non-gh subprocess: {cmd!r}")
        cmd = list(cmd)
        calls.append(cmd)
        if raise_on is not None:
            exc = raise_on(cmd)
            if exc is not None:
                raise exc
        if len(cmd) >= 3 and cmd[1] == "issue" and cmd[2] == "list":
            # Extract --label values
            label_values: list[str] = []
            for i, tok in enumerate(cmd):
                if tok == "--label" and i + 1 < len(cmd):
                    label_values.append(cmd[i + 1])
            # Route by the FIRST recognized label
            for lbl in label_values:
                if lbl in list_by_label:
                    return _completed(json.dumps(list_by_label[lbl]))
            return _completed(json.dumps(default_list))
        if len(cmd) >= 4 and cmd[1] == "issue" and cmd[2] == "view":
            try:
                number = int(cmd[3])
            except ValueError:
                number = -1
            payload = view_by_number.get(number, {})
            return _completed(json.dumps(payload))
        # `gh api repos/<repo>/issues/<N>/timeline ...` — actor lookup
        # via the timeline labeled-event sequence (SKILL.md §8.6).
        if (
            len(cmd) >= 3 and cmd[1] == "api"
            and "/timeline" in (cmd[2] or "")
        ):
            # Extract the issue number from the path.
            path = cmd[2] or ""
            number = -1
            try:
                # path looks like: repos/<owner>/<repo>/issues/<N>/timeline
                parts = path.split("/")
                idx = parts.index("issues")
                number = int(parts[idx + 1])
            except (ValueError, IndexError):
                pass
            payload = timeline_by_number.get(number)
            if payload is None:
                return _completed("null")
            return _completed(json.dumps(payload))
        # Default: success with no output (close/comment/edit/create).
        return _completed("")

    monkeypatch.setattr(subprocess, "run", fake_run)
    return calls


def _read_tick_signal(tmp_config: Any) -> dict[str, Any]:
    path = Path(tmp_config.paths.tick_signal_path)
    assert path.exists(), "tick signal was not written"
    return json.loads(path.read_text(encoding="utf-8"))


# ---------------------------------------------------------------------------
# Outcome 1: Empty queue
# ---------------------------------------------------------------------------


def test_empty_queue_exits_success(
    tmp_config: Any,
    monkeypatch: pytest.MonkeyPatch,
    mock_anthropic: Any,
) -> None:
    """No pending signals → exit 0, status=success, counts all zero."""
    _make_gh_router(monkeypatch, default_list=[])

    exit_code = run.main(["--config", str(_config_path(tmp_config))])

    assert exit_code == 0
    signal = _read_tick_signal(tmp_config)
    assert signal["status"] == "success"
    assert signal["exit_code"] == 0
    assert signal["tick"]["signals_seen"] == 0
    assert signal["tick"]["signals_processed"] == 0
    assert signal["tick"]["audits_processed"] == []
    assert signal["tick"]["tier_a_commits"] == []
    assert signal["tick"]["debt_filed"] == []


# ---------------------------------------------------------------------------
# Outcome 2: Debt-only audit
# ---------------------------------------------------------------------------


def test_debt_only_audit(
    tmp_config: Any,
    monkeypatch: pytest.MonkeyPatch,
    mock_anthropic: Any,
) -> None:
    """One doc audit yields zero edits but debt issues filed (per routing)."""
    audits = [
        {
            "number": 5000,
            "title": "Doc audit: aaa1111 (felix-core)",
            "body": "Triggered by commit aaa1111.",
            "labels": [
                {"name": "doc-audit"},
                {"name": "area/felix-core"},
            ],
            "createdAt": "2026-05-20T10:00:00Z",
        }
    ]
    _make_gh_router(
        monkeypatch,
        list_by_label={"doc-audit": audits},
    )

    def fake_apply(config, audit, proposed_edits, debt_issues, missing_artifacts):
        return RoutingResult(
            applied_count=0,
            gated=False,
            pending_approval_issue=None,
            debt_issues=[6001, 6002],
            missing_issues=[],
            errors=[],
            exit_code=0,
        )

    monkeypatch.setattr(run, "apply_routing", fake_apply)

    exit_code = run.main(["--config", str(_config_path(tmp_config))])

    assert exit_code == 0
    signal = _read_tick_signal(tmp_config)
    assert signal["status"] == "success"
    assert signal["tick"]["signals_seen"] == 1
    assert signal["tick"]["signals_processed"] == 1
    assert signal["tick"]["audits_processed"] == [5000]
    assert signal["tick"]["tier_a_commits"] == []
    assert signal["tick"]["debt_filed"] == [6001, 6002]
    # Activity log entry should exist
    log_dir = Path(tmp_config.paths.activity_log_dir)
    log_files = list(log_dir.glob("doc-auditor-*.md"))
    assert log_files, "no activity log file written"


# ---------------------------------------------------------------------------
# Outcome 3: Tier-A auto-commit
# ---------------------------------------------------------------------------


def test_tier_a_auto_commit(
    tmp_config: Any,
    monkeypatch: pytest.MonkeyPatch,
    mock_anthropic: Any,
) -> None:
    """Audit produces one Tier-A edit that routing commits."""
    audits = [
        {
            "number": 5100,
            "title": "Doc audit: bbb2222 (felix-core)",
            "body": "",
            "labels": [
                {"name": "doc-audit"},
                {"name": "area/felix-core"},
            ],
            "createdAt": "2026-05-20T10:30:00Z",
        }
    ]
    _make_gh_router(monkeypatch, list_by_label={"doc-audit": audits})

    def fake_apply(config, audit, proposed_edits, debt_issues, missing_artifacts):
        return RoutingResult(
            applied_count=1,
            gated=False,
            pending_approval_issue=None,
            debt_issues=[],
            missing_issues=[],
            errors=[],
            exit_code=0,
        )

    monkeypatch.setattr(run, "apply_routing", fake_apply)

    exit_code = run.main(["--config", str(_config_path(tmp_config))])

    assert exit_code == 0
    signal = _read_tick_signal(tmp_config)
    assert signal["status"] == "success"
    assert signal["tick"]["signals_processed"] == 1
    # tier_a_commits has the placeholder marker for 1 applied edit
    assert len(signal["tick"]["tier_a_commits"]) == 1
    assert "audit-applied:1" in signal["tick"]["tier_a_commits"][0]
    assert signal["tick"]["debt_filed"] == []
    assert signal["tick"]["pending_approvals_filed"] == []


# ---------------------------------------------------------------------------
# Outcome 4: Pending-approval-apply
# ---------------------------------------------------------------------------


def test_pending_approval_apply(
    tmp_config: Any,
    monkeypatch: pytest.MonkeyPatch,
    mock_anthropic: Any,
) -> None:
    """A labeled pending-approval is applied (closed) by the driver.

    Production conditions: the bot is the AUTHOR of every
    ``audit-pending-approval`` issue (because the bot files them). The
    actor-verification gate (SKILL.md §8.6) inspects the TIMELINE's
    most recent decision-label event — its actor must be a human.
    """
    pa = [
        {
            "number": 7001,
            "title": "Audit #6500: pending approval — 1 proposed edit(s)",
            "body": "Refs #6500\n\n...",
            # The bot files the pending-approval issues in production.
            "author": {"login": "kg-felix-bot"},
            "labels": [
                {"name": "audit-pending-approval"},
                {"name": "audit-approve"},
                {"name": "area/felix-core"},
            ],
            "createdAt": "2026-05-19T18:00:00Z",
        }
    ]
    # Timeline's most recent decision-label event was applied by a human
    # → gate proceeds with apply.
    timeline = {
        7001: {
            "label": "audit-approve",
            "actor": "kentonium3",
            "at": "2026-05-19T18:30:00Z",
        }
    }
    calls = _make_gh_router(
        monkeypatch,
        list_by_label={"audit-pending-approval": pa},
        timeline_by_number=timeline,
    )

    exit_code = run.main(["--config", str(_config_path(tmp_config))])

    assert exit_code == 0
    signal = _read_tick_signal(tmp_config)
    assert signal["status"] == "success"
    assert signal["tick"]["pending_approvals_applied"] == [7001]
    # We expect at least one close call (the pending-approval) and one
    # for the audit (6500). Both are issued by _apply_pending_decision.
    closes = [c for c in calls if len(c) >= 3 and c[1] == "issue" and c[2] == "close"]
    closed_numbers = {c[3] for c in closes}
    assert "7001" in closed_numbers
    assert "6500" in closed_numbers


# ---------------------------------------------------------------------------
# Outcome 5: Pending-approval-reject
# ---------------------------------------------------------------------------


def test_pending_approval_reject(
    tmp_config: Any,
    monkeypatch: pytest.MonkeyPatch,
    mock_anthropic: Any,
) -> None:
    """Reject path: same close flow, decision label = audit-reject.

    Same production conditions as the apply test: the bot is the issue
    author, but the timeline's labeled-event actor is a human.
    """
    pa = [
        {
            "number": 7050,
            "title": "Audit #6550: pending approval — 2 proposed edit(s)",
            "body": "Refs #6550\n\n...",
            "author": {"login": "kg-felix-bot"},
            "labels": [
                {"name": "audit-pending-approval"},
                {"name": "audit-reject"},
                {"name": "area/felix-core"},
            ],
            "createdAt": "2026-05-19T19:00:00Z",
        }
    ]
    timeline = {
        7050: {
            "label": "audit-reject",
            "actor": "kentonium3",
            "at": "2026-05-19T19:30:00Z",
        }
    }
    calls = _make_gh_router(
        monkeypatch,
        list_by_label={"audit-pending-approval": pa},
        timeline_by_number=timeline,
    )

    exit_code = run.main(["--config", str(_config_path(tmp_config))])

    assert exit_code == 0
    signal = _read_tick_signal(tmp_config)
    assert signal["status"] == "success"
    assert signal["tick"]["pending_approvals_applied"] == [7050]
    # Verify reject comment text on the close.
    closes = [c for c in calls if len(c) >= 3 and c[1] == "issue" and c[2] == "close"]
    assert any(
        "audit-reject" in (c[c.index("--comment") + 1] if "--comment" in c else "")
        for c in closes
    )


# ---------------------------------------------------------------------------
# Cycle-5 finding 1: PA approve/reject/skip wire through routing layer
# ---------------------------------------------------------------------------


# Representative PA body that mirrors the format emitted by
# ``handle_audit_routing._build_pending_approval_body`` for one
# proposed edit. The parser
# (:func:`doc_audit.run._parse_proposals_from_pa_body`) extracts the
# doc_path, change_type, evidence_source, and the current/proposed
# values from the diff block.
_PA_BODY_WITH_ONE_EDIT = """## Audit pending approval

**Originating audit**: #6500
**Triggering commit**: `deadbeef`
**Scope**: area/felix-core
**Docs reviewed**: 1

## Proposed edits

Each numbered item is a high-confidence edit per the doc-audit skill's
Section 4.1 confidence rules. Apply ALL of them on `audit-approve`.

### 1. `docs/runbooks/openclaw-ops.md`

**Change type**: frontmatter_date

**Evidence**: Triggered by commit deadbeef on main.

**Diff**:
```diff
- last_validated: 2026-04-10
+ last_validated: 2026-05-20
```

---

Refs #6500
"""


_PA_BODY_WITH_TWO_EDITS = """## Audit pending approval

**Originating audit**: #6550

## Proposed edits

### 1. `docs/a.md`

**Change type**: frontmatter_date

**Evidence**: commit aaa on main.

**Diff**:
```diff
- last_validated: 2026-04-01
+ last_validated: 2026-05-20
```

### 2. `docs/b.md`

**Change type**: version_bump

**Evidence**: commit bbb on main.

**Diff**:
```diff
- vikunja: 0.24.0
+ vikunja: 0.24.1
```

---

Refs #6550
"""


def test_pending_approval_approve_calls_routing_apply_with_edits(
    tmp_config: Any,
    monkeypatch: pytest.MonkeyPatch,
    mock_anthropic: Any,
) -> None:
    """Cycle-5 finding 1 — audit-approve passes parsed edits into routing.

    Asserts that the driver:
    - Parses the PA body into one or more :class:`ProposedEdit`.
    - Invokes the routing layer (``apply_routing``) with that
      non-empty list of proposals.
    - Records the PA in ``pending_approvals_applied``.
    - Closes both the PA and the originating audit.

    Previously (cycle 4) the handler closed both issues but never
    handed the edits to the routing layer, so no commit was ever made
    in production. This test pins the wire-up.
    """
    pa = [
        {
            "number": 7301,
            "title": "Audit #6500: pending approval — 1 proposed edit(s)",
            "body": _PA_BODY_WITH_ONE_EDIT,
            "author": {"login": "kg-felix-bot"},
            "labels": [
                {"name": "audit-pending-approval"},
                {"name": "audit-approve"},
                {"name": "area/felix-core"},
            ],
            "createdAt": "2026-05-19T18:00:00Z",
        }
    ]
    timeline = {
        7301: {
            "label": "audit-approve",
            "actor": "kentonium3",
            "at": "2026-05-19T18:30:00Z",
        }
    }
    # Provide the originating audit (#6500) on `gh issue view 6500`
    # so the driver can reconstruct an AuditIssue with proper title
    # + area labels for the routing call.
    view_by_number = {
        6500: {
            "number": 6500,
            "title": "Doc audit: deadbeef (felix-core)",
            "body": "Triggered by commit deadbeef on main.",
            "labels": [
                {"name": "doc-audit"},
                {"name": "area/felix-core"},
            ],
        }
    }
    _make_gh_router(
        monkeypatch,
        list_by_label={"audit-pending-approval": pa},
        view_by_number=view_by_number,
        timeline_by_number=timeline,
    )

    # Intercept the routing layer so we can inspect the arguments.
    captured: dict[str, Any] = {}

    def fake_apply(config, audit, proposed_edits, debt_issues, missing_artifacts):
        captured["proposed_edits"] = list(proposed_edits)
        captured["debt_issues"] = list(debt_issues)
        captured["missing_artifacts"] = list(missing_artifacts)
        captured["audit_number"] = audit.issue_number
        return RoutingResult(
            applied_count=len(proposed_edits),
            gated=False,
            pending_approval_issue=None,
            debt_issues=[],
            missing_issues=[],
            errors=[],
            exit_code=0,
        )

    monkeypatch.setattr(run, "apply_routing", fake_apply)

    exit_code = run.main(["--config", str(_config_path(tmp_config))])

    assert exit_code == 0
    signal = _read_tick_signal(tmp_config)
    assert signal["status"] == "success"

    # Routing was called with a non-empty proposed_edits list
    # (cycle-5 finding 1 — previously NO routing call was made).
    assert "proposed_edits" in captured, (
        "apply_routing was never invoked for audit-approve"
    )
    assert len(captured["proposed_edits"]) == 1, (
        f"expected 1 parsed edit; got {captured['proposed_edits']}"
    )
    edit = captured["proposed_edits"][0]
    assert edit.doc_path == "docs/runbooks/openclaw-ops.md"
    assert edit.change_type == "frontmatter_date"
    assert edit.current_value == "last_validated: 2026-04-10"
    assert edit.proposed_value == "last_validated: 2026-05-20"

    # Routing receives the originating audit (#6500), not the PA (#7301).
    assert captured["audit_number"] == 6500

    # PA was recorded as applied + tick signal reflects the apply.
    assert signal["tick"]["pending_approvals_applied"] == [7301]


def test_pending_approval_reject_files_debt_per_edit(
    tmp_config: Any,
    monkeypatch: pytest.MonkeyPatch,
    mock_anthropic: Any,
) -> None:
    """Cycle-5 finding 1 — audit-reject demotes each edit to docs-debt.

    Asserts that the driver:
    - Parses the PA body into multiple :class:`ProposedEdit` (2 here).
    - Files one ``gh issue create`` call per rejected edit.
    - Invokes the routing layer with EMPTY ``proposed_edits`` (no
      apply) but ``missing_artifacts`` carrying the new debt-issue
      numbers (so the helper's summary cross-references them).
    - Closes both the PA and the originating audit.

    Previously (cycle 4) the handler closed both issues but never
    filed debt for the rejected edits — the operator's intent
    ("preserve as evidence") was silently dropped.
    """
    pa = [
        {
            "number": 7302,
            "title": "Audit #6550: pending approval — 2 proposed edit(s)",
            "body": _PA_BODY_WITH_TWO_EDITS,
            "author": {"login": "kg-felix-bot"},
            "labels": [
                {"name": "audit-pending-approval"},
                {"name": "audit-reject"},
                {"name": "area/felix-core"},
            ],
            "createdAt": "2026-05-19T19:00:00Z",
        }
    ]
    timeline = {
        7302: {
            "label": "audit-reject",
            "actor": "kentonium3",
            "at": "2026-05-19T19:30:00Z",
        }
    }
    view_by_number = {
        6550: {
            "number": 6550,
            "title": "Doc audit: bbbcccc (felix-core)",
            "body": "Triggered by commit bbbcccc on main.",
            "labels": [
                {"name": "doc-audit"},
                {"name": "area/felix-core"},
            ],
        }
    }

    # Track `gh issue create` calls so we can assert one debt issue
    # was filed per rejected proposed edit. The default _make_gh_router
    # returns stdout="" for issue create, which our parser treats as
    # "could not parse issue number"; we need to return a URL so the
    # numbers land in debt_filed. Build a richer router for this test.
    create_counter = {"n": 0}

    def fake_run_cmd(cmd, *args, **kwargs):  # type: ignore[no-untyped-def]
        cmd = list(cmd)
        if not (isinstance(cmd, list) and cmd and cmd[0] == "gh"):
            raise RuntimeError(f"unexpected non-gh subprocess: {cmd!r}")
        if len(cmd) >= 3 and cmd[1] == "issue" and cmd[2] == "list":
            label_values = [
                cmd[i + 1] for i, tok in enumerate(cmd)
                if tok == "--label" and i + 1 < len(cmd)
            ]
            for lbl in label_values:
                if lbl == "audit-pending-approval":
                    return _completed(json.dumps(pa))
            return _completed("[]")
        if len(cmd) >= 4 and cmd[1] == "issue" and cmd[2] == "view":
            try:
                n = int(cmd[3])
            except ValueError:
                n = -1
            return _completed(json.dumps(view_by_number.get(n, {})))
        if (
            len(cmd) >= 3 and cmd[1] == "api"
            and "/timeline" in (cmd[2] or "")
        ):
            parts = (cmd[2] or "").split("/")
            try:
                idx = parts.index("issues")
                n = int(parts[idx + 1])
            except (ValueError, IndexError):
                n = -1
            payload = timeline.get(n)
            return _completed(
                "null" if payload is None else json.dumps(payload)
            )
        if len(cmd) >= 3 and cmd[1] == "issue" and cmd[2] == "create":
            create_counter["n"] += 1
            # gh issue create echoes the issue URL on stdout.
            new_num = 8000 + create_counter["n"]
            return _completed(
                f"https://github.com/kentonium3/kg-automation/issues/{new_num}\n"
            )
        return _completed("")

    monkeypatch.setattr(subprocess, "run", fake_run_cmd)

    captured: dict[str, Any] = {}

    def fake_apply(config, audit, proposed_edits, debt_issues, missing_artifacts):
        captured["proposed_edits"] = list(proposed_edits)
        captured["debt_issues"] = list(debt_issues)
        captured["missing_artifacts"] = list(missing_artifacts)
        return RoutingResult(
            applied_count=0,
            gated=False,
            pending_approval_issue=None,
            debt_issues=[],
            missing_issues=[],
            errors=[],
            exit_code=0,
        )

    monkeypatch.setattr(run, "apply_routing", fake_apply)

    exit_code = run.main(["--config", str(_config_path(tmp_config))])

    assert exit_code == 0
    signal = _read_tick_signal(tmp_config)
    assert signal["status"] == "success"

    # Both edits were demoted → two `gh issue create` calls.
    assert create_counter["n"] == 2, (
        f"expected 2 debt-issue create calls; got {create_counter['n']}"
    )

    # Routing was invoked with EMPTY proposed_edits (reject = no apply)
    # but with a non-empty missing_artifacts list referencing the
    # newly-filed debt issues.
    assert "proposed_edits" in captured, (
        "apply_routing was never invoked for audit-reject"
    )
    assert captured["proposed_edits"] == [], (
        f"expected empty proposed_edits on reject; got "
        f"{captured['proposed_edits']}"
    )
    assert len(captured["missing_artifacts"]) == 2, (
        f"expected 2 missing_artifacts entries (one per debt issue); "
        f"got {captured['missing_artifacts']}"
    )
    for entry in captured["missing_artifacts"]:
        assert entry["kind"] == "debt"
        assert isinstance(entry["issue_number"], int)

    # The tick signal carries the new debt-issue numbers in
    # ``debt_filed`` — operator-visible evidence of the demotion.
    assert sorted(signal["tick"]["debt_filed"]) == [8001, 8002]
    assert signal["tick"]["pending_approvals_applied"] == [7302]


def test_pending_approval_skip_closes_both_no_routing_call(
    tmp_config: Any,
    monkeypatch: pytest.MonkeyPatch,
    mock_anthropic: Any,
) -> None:
    """Cycle-5 finding 1 — audit-skip closes both issues; no routing call.

    Per SKILL.md §8.5 audit-skip semantics: no commit, no demotion,
    no further debt issues. The handler MUST close both the PA and
    the originating audit but MUST NOT invoke the routing layer (no
    summary post; the audit is closed with a plain skip note).
    """
    pa = [
        {
            "number": 7303,
            "title": "Audit #6575: pending approval — 1 proposed edit(s)",
            "body": _PA_BODY_WITH_ONE_EDIT,
            "author": {"login": "kg-felix-bot"},
            "labels": [
                {"name": "audit-pending-approval"},
                {"name": "audit-skip"},
                {"name": "area/felix-core"},
            ],
            "createdAt": "2026-05-19T20:00:00Z",
        }
    ]
    timeline = {
        7303: {
            "label": "audit-skip",
            "actor": "kentonium3",
            "at": "2026-05-19T20:30:00Z",
        }
    }
    view_by_number = {
        6575: {
            "number": 6575,
            "title": "Doc audit: cafebabe (felix-core)",
            "body": "",
            "labels": [
                {"name": "doc-audit"},
                {"name": "area/felix-core"},
            ],
        }
    }
    calls = _make_gh_router(
        monkeypatch,
        list_by_label={"audit-pending-approval": pa},
        view_by_number=view_by_number,
        timeline_by_number=timeline,
    )

    apply_calls: list[Any] = []

    def fake_apply(config, audit, proposed_edits, debt_issues, missing_artifacts):
        apply_calls.append((audit.issue_number, list(proposed_edits)))
        return RoutingResult(exit_code=0)

    monkeypatch.setattr(run, "apply_routing", fake_apply)

    exit_code = run.main(["--config", str(_config_path(tmp_config))])

    assert exit_code == 0
    signal = _read_tick_signal(tmp_config)
    assert signal["status"] == "success"

    # Routing was NOT invoked on the skip path (no commit, no
    # summary, no demotion).
    assert apply_calls == [], (
        f"audit-skip MUST NOT call routing layer; got: {apply_calls}"
    )

    # Both issues were closed.
    closes = [
        c for c in calls
        if len(c) >= 3 and c[1] == "issue" and c[2] == "close"
    ]
    closed_numbers = {c[3] for c in closes}
    assert "7303" in closed_numbers, (
        f"expected PA #7303 close; got: {closes!r}"
    )
    assert "6575" in closed_numbers, (
        f"expected originating audit #6575 close; got: {closes!r}"
    )

    # Debt-filed list is empty (no demotion on skip).
    assert signal["tick"]["debt_filed"] == []
    # PA recorded as applied.
    assert signal["tick"]["pending_approvals_applied"] == [7303]


# ---------------------------------------------------------------------------
# Cycle-5 finding 2: all-signals-failed promotes status to failure
# ---------------------------------------------------------------------------


def test_all_signals_fail_promotes_to_failure(
    tmp_config: Any,
    monkeypatch: pytest.MonkeyPatch,
    mock_anthropic: Any,
) -> None:
    """Cycle-5 finding 2 — every signal fails → status="failure", rc=1.

    Per FR-007 status semantics: ``partial`` means "made some
    progress"; if NO signal succeeded, the tick is a failure for
    operator alerting (not a partial outcome). Previously the
    per-signal except handlers always set ``status="partial"`` on the
    first failure, which left an all-fail tick incorrectly classified
    as partial.
    """
    audits = [
        {
            "number": 9001,
            "title": "Doc audit: aaa1 (felix-core)",
            "body": "",
            "labels": [
                {"name": "doc-audit"},
                {"name": "area/felix-core"},
            ],
            "createdAt": "2026-05-20T10:00:00Z",
        },
        {
            "number": 9002,
            "title": "Doc audit: aaa2 (felix-core)",
            "body": "",
            "labels": [
                {"name": "doc-audit"},
                {"name": "area/felix-core"},
            ],
            "createdAt": "2026-05-20T10:10:00Z",
        },
        {
            "number": 9003,
            "title": "Doc audit: aaa3 (felix-core)",
            "body": "",
            "labels": [
                {"name": "doc-audit"},
                {"name": "area/felix-core"},
            ],
            "createdAt": "2026-05-20T10:20:00Z",
        },
    ]
    _make_gh_router(
        monkeypatch,
        list_by_label={"doc-audit": audits},
    )

    # Force every audit to raise during processing — they all fail.
    def boom_process_audit(*args, **kwargs):
        raise RuntimeError("simulated processing failure")

    monkeypatch.setattr(run, "_process_audit_signal", boom_process_audit)

    exit_code = run.main(["--config", str(_config_path(tmp_config))])

    # All 3 signals failed → status=failure, exit code=1.
    assert exit_code == 1, (
        f"expected exit_code=1 (failure) when all signals fail; got {exit_code}"
    )
    signal = _read_tick_signal(tmp_config)
    assert signal["status"] == "failure", (
        f"expected status='failure' when all signals fail; "
        f"got {signal['status']!r}"
    )
    # Saw 3 signals, processed 0.
    assert signal["tick"]["signals_seen"] == 3
    assert signal["tick"]["signals_processed"] == 0
    # All 3 failures were recorded.
    assert len(signal["errors"]) >= 3


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _config_path(tmp_config: Any) -> Path:
    """Return the on-disk config path used to build ``tmp_config``.

    ``tmp_config`` is the loaded ``Config`` dataclass; the original
    TOML lives at ``<tmp_path>/config.toml`` per conftest.
    """
    # The tmp_path is the parent of the API key file (per conftest).
    api_key_path = Path(tmp_config.llm.api_key_path)
    return api_key_path.parent / "config.toml"


# ---------------------------------------------------------------------------
# Outcome 6 (cycle-2 expansion): Full pipeline end-to-end — verify the
# judgment modules ARE called and the routing layer receives non-empty
# proposed_edits / debt_issues lists.
# ---------------------------------------------------------------------------


def _make_full_pipeline_router(
    monkeypatch: pytest.MonkeyPatch,
    *,
    audits_by_label: dict[str, list[dict]],
    git_diff_stdout: str,
) -> tuple[list[list[str]], dict[str, int]]:
    """Patch subprocess.run to handle gh + git show calls.

    Routes:
    - ``gh issue list ... --label X`` → audits_by_label[X] (or []).
    - ``gh issue view`` → empty author.
    - ``git show <sha>`` → ``git_diff_stdout``.
    - Any other gh call → empty success.

    Returns the call-log + a per-binary call-counter for assertions.
    """
    calls: list[list[str]] = []
    counters = {"gh": 0, "git": 0, "other": 0}

    def fake_run(cmd, *args, **kwargs):  # type: ignore[no-untyped-def]
        cmd = list(cmd)
        calls.append(cmd)
        bin_name = cmd[0] if cmd else ""
        if bin_name == "git":
            counters["git"] += 1
            if len(cmd) >= 3 and cmd[1] == "show":
                return _completed(git_diff_stdout)
            return _completed("")
        if bin_name == "gh":
            counters["gh"] += 1
            if len(cmd) >= 3 and cmd[1] == "issue" and cmd[2] == "list":
                label_values = [
                    cmd[i + 1] for i, tok in enumerate(cmd)
                    if tok == "--label" and i + 1 < len(cmd)
                ]
                for lbl in label_values:
                    if lbl in audits_by_label:
                        return _completed(json.dumps(audits_by_label[lbl]))
                return _completed("[]")
            if len(cmd) >= 4 and cmd[1] == "issue" and cmd[2] == "view":
                return _completed("{}")
            return _completed("")
        counters["other"] += 1
        return _completed("")

    monkeypatch.setattr(subprocess, "run", fake_run)
    return calls, counters


def test_full_pipeline_tier_a_classify_then_route(
    tmp_config: Any,
    monkeypatch: pytest.MonkeyPatch,
    mock_anthropic: Any,
) -> None:
    """Cycle-2 end-to-end: diff yields candidate, LLM classifies tier_a, routing applies.

    Verifies that:
    1. The driver fetches the diff via git show (call recorded).
    2. The candidate frontmatter date bump is derived from the diff.
    3. ``tier_classification.classify`` is invoked through the LLM
       (``mock_anthropic.messages.calls`` is non-empty).
    4. The routing layer receives a NON-EMPTY ``proposed_edits`` list
       (intercept via monkeypatched ``apply_routing``).
    5. The tick signal reflects the applied count + judgment-call total.
    """
    audits = [
        {
            "number": 6100,
            "title": "Doc audit: deadbee (felix-core)",
            "body": "Triggered by commit deadbee on main.",
            "labels": [
                {"name": "doc-audit"},
                {"name": "area/felix-core"},
            ],
            "createdAt": "2026-05-20T12:00:00Z",
        }
    ]
    # Real-ish diff: one frontmatter date bump in an in-scope doc.
    git_diff = (
        "diff --git a/docs/runbooks/openclaw-ops.md b/docs/runbooks/openclaw-ops.md\n"
        "--- a/docs/runbooks/openclaw-ops.md\n"
        "+++ b/docs/runbooks/openclaw-ops.md\n"
        "@@ -1,5 +1,5 @@\n"
        " ---\n"
        " title: openclaw ops\n"
        "-last_validated: 2026-04-10\n"
        "+last_validated: 2026-05-20\n"
        " ---\n"
    )
    _make_full_pipeline_router(
        monkeypatch,
        audits_by_label={"doc-audit": audits},
        git_diff_stdout=git_diff,
    )

    # Provide a doc-domain-map that puts the modified file in scope.
    Path(tmp_config.paths.doc_domain_map).write_text(
        json.dumps({
            "domains": {
                "area/felix-core": ["docs/runbooks/openclaw-ops.md"],
            }
        }),
        encoding="utf-8",
    )

    # Mock anthropic to return tier_a verdict.
    mock_anthropic.messages.next_fixture = "tier_classification_tier_a"

    # Intercept routing to verify non-empty proposed_edits.
    captured_args: dict[str, Any] = {}

    def fake_apply(config, audit, proposed_edits, debt_issues, missing_artifacts):
        captured_args["proposed_edits"] = list(proposed_edits)
        captured_args["debt_issues"] = list(debt_issues)
        captured_args["missing_artifacts"] = list(missing_artifacts)
        return RoutingResult(
            applied_count=len(proposed_edits),
            gated=False,
            pending_approval_issue=None,
            debt_issues=[],
            missing_issues=[],
            errors=[],
            exit_code=0,
        )

    monkeypatch.setattr(run, "apply_routing", fake_apply)

    exit_code = run.main(["--config", str(_config_path(tmp_config))])

    # 1. Tick completed cleanly.
    assert exit_code == 0
    signal = _read_tick_signal(tmp_config)
    assert signal["status"] == "success"

    # 2. The LLM was actually called (not bypassed).
    assert len(mock_anthropic.messages.calls) >= 1, (
        "mock_anthropic.messages.create should have been called for "
        "tier_classification"
    )

    # 3. Routing received a non-empty proposed_edits list.
    assert "proposed_edits" in captured_args, (
        "apply_routing was never invoked"
    )
    assert len(captured_args["proposed_edits"]) == 1, (
        f"expected 1 proposed edit; got {captured_args['proposed_edits']}"
    )
    edit = captured_args["proposed_edits"][0]
    assert edit.doc_path == "docs/runbooks/openclaw-ops.md"
    assert edit.tier == "tier_a"

    # 4. Tick signal reflects the judgment-call telemetry.
    assert signal["judgment"]["tier_classification_calls"] == 1
    assert signal["judgment"]["input_tokens"] > 0
    assert signal["tick"]["tier_a_commits"], (
        "expected at least one tier_a_commits marker; got "
        f"{signal['tick']['tier_a_commits']}"
    )


def test_full_pipeline_judgment_demotes_to_debt(
    tmp_config: Any,
    monkeypatch: pytest.MonkeyPatch,
    mock_anthropic: Any,
) -> None:
    """End-to-end: diff yields candidate, LLM says judgment, debt body generated.

    Verifies the JUDGMENT branch of the workflow: the candidate edit is
    demoted to a debt finding, ``debt_body_generation`` is invoked, and
    the routing layer receives a non-empty ``debt_issues`` list.
    """
    audits = [
        {
            "number": 6200,
            "title": "Doc audit: feeded5 (felix-core)",
            "body": "",
            "labels": [
                {"name": "doc-audit"},
                {"name": "area/felix-core"},
            ],
            "createdAt": "2026-05-20T12:30:00Z",
        }
    ]
    git_diff = (
        "diff --git a/docs/runbooks/x.md b/docs/runbooks/x.md\n"
        "--- a/docs/runbooks/x.md\n"
        "+++ b/docs/runbooks/x.md\n"
        "-last_validated: 2026-04-10\n"
        "+last_validated: 2026-05-20\n"
    )
    _make_full_pipeline_router(
        monkeypatch,
        audits_by_label={"doc-audit": audits},
        git_diff_stdout=git_diff,
    )

    Path(tmp_config.paths.doc_domain_map).write_text(
        json.dumps({
            "domains": {
                # Two in-scope docs so cross_file_implication has an
                # untouched file to reason about (x.md is touched by
                # the diff; y.md is not).
                "area/felix-core": [
                    "docs/runbooks/x.md",
                    "docs/runbooks/y.md",
                ],
            }
        }),
        encoding="utf-8",
    )

    # Sequence: first call (tier_classification) → judgment; second
    # call (cross_file_implication) → empty implications; third call
    # (debt_body_generation) → full body markdown. We swap loaders.
    call_sequence = iter([
        # tier_classification: judgment
        {
            "text": json.dumps({
                "tier": "judgment",
                "rationale": "needs human eyes",
            }),
            "usage": {
                "input_tokens": 100,
                "cache_read_input_tokens": 30,
                "output_tokens": 20,
            },
        },
        # cross_file_implication: no implications
        {
            "text": json.dumps({"implications": []}),
            "usage": {
                "input_tokens": 80,
                "cache_read_input_tokens": 30,
                "output_tokens": 5,
            },
        },
        # debt_body_generation: full markdown
        {
            "text": (
                "## Artifact\ndocs/runbooks/x.md\n\n"
                "## Gap description\nframewmatter bumped\n\n"
                "## Area\narea/felix-core\n\n"
                "## Cross-references\n- Refs #6200 (originating audit)\n\n"
                "## Draft outline\n- step\n\n"
                "## Success criteria\n- done\n"
            ),
            "usage": {
                "input_tokens": 200,
                "cache_read_input_tokens": 60,
                "output_tokens": 80,
            },
        },
    ])

    def cycling_loader(_name):
        try:
            return next(call_sequence)
        except StopIteration:
            return {
                "text": "{}",
                "usage": {
                    "input_tokens": 0,
                    "cache_read_input_tokens": 0,
                    "output_tokens": 0,
                },
            }

    mock_anthropic.messages._loader = cycling_loader
    mock_anthropic.messages.next_fixture = "stub"

    captured: dict[str, Any] = {}

    def fake_apply(config, audit, proposed_edits, debt_issues, missing_artifacts):
        captured["proposed_edits"] = list(proposed_edits)
        captured["debt_issues"] = list(debt_issues)
        return RoutingResult(
            applied_count=0,
            gated=False,
            pending_approval_issue=None,
            debt_issues=[7777],  # mock routing files one debt issue
            missing_issues=[],
            errors=[],
            exit_code=0,
        )

    monkeypatch.setattr(run, "apply_routing", fake_apply)

    exit_code = run.main(["--config", str(_config_path(tmp_config))])

    assert exit_code == 0
    signal = _read_tick_signal(tmp_config)
    assert signal["status"] == "success"
    # 3 LLM calls (tier_classification + cross_file_implication + debt_body_generation)
    assert len(mock_anthropic.messages.calls) >= 3, (
        f"expected ≥3 LLM calls; got {len(mock_anthropic.messages.calls)}"
    )
    # Routing received empty proposed_edits and a non-empty debt_issues
    # (the demoted finding + its generated body). The missing-artifact
    # scan may add additional entries — we filter to the LLM-generated
    # ones (is_missing_artifact=False) for the body-content assertion.
    assert captured["proposed_edits"] == []
    assert len(captured["debt_issues"]) >= 1, (
        f"expected ≥1 DebtIssue passed to routing; got {captured['debt_issues']}"
    )
    llm_debts = [
        d for d in captured["debt_issues"] if not d.is_missing_artifact
    ]
    assert llm_debts, (
        f"expected an LLM-generated DebtIssue; got {captured['debt_issues']}"
    )
    debt = llm_debts[0]
    assert (
        "Gap description" in debt.draft_outline
        or debt.draft_outline.startswith("## Artifact")
    )
    # All three judgment-call counters were incremented.
    assert signal["judgment"]["tier_classification_calls"] == 1
    assert signal["judgment"]["debt_body_generation_calls"] == 1
    assert signal["judgment"]["cross_file_implication_calls"] == 1


def test_full_pipeline_no_sha_skips_llm(
    tmp_config: Any,
    monkeypatch: pytest.MonkeyPatch,
    mock_anthropic: Any,
) -> None:
    """Weekly audit with no SHA → no diff → no candidate edits → no LLM call.

    Verifies the empty-pipeline graceful-degrade path: when there's no
    triggering commit we don't waste LLM tokens. Routing still runs.
    """
    audits = [
        {
            "number": 6300,
            "title": "Weekly doc audit — 2026-05-20",
            "body": "",
            "labels": [{"name": "doc-audit"}, {"name": "weekly"}],
            "createdAt": "2026-05-20T07:00:00Z",
        }
    ]
    _make_full_pipeline_router(
        monkeypatch,
        audits_by_label={"doc-audit": audits},
        git_diff_stdout="",
    )

    captured: dict[str, Any] = {}

    def fake_apply(config, audit, proposed_edits, debt_issues, missing_artifacts):
        captured["proposed_edits"] = list(proposed_edits)
        return RoutingResult(exit_code=0)

    monkeypatch.setattr(run, "apply_routing", fake_apply)

    exit_code = run.main(["--config", str(_config_path(tmp_config))])

    assert exit_code == 0
    # No LLM calls: there were no candidate edits and no in-scope docs
    # to cross-reference.
    assert mock_anthropic.messages.calls == [], (
        f"expected zero LLM calls; got {len(mock_anthropic.messages.calls)}"
    )
    assert captured["proposed_edits"] == []


def test_full_pipeline_acquires_lock(
    tmp_config: Any,
    monkeypatch: pytest.MonkeyPatch,
    mock_anthropic: Any,
) -> None:
    """Driver issues ``gh issue edit ... --add-label status:in-progress`` per audit."""
    audits = [
        {
            "number": 6400,
            "title": "Doc audit: locktest (felix-core)",
            "body": "",
            "labels": [{"name": "doc-audit"}, {"name": "area/felix-core"}],
            "createdAt": "2026-05-20T13:00:00Z",
        }
    ]
    calls, _ = _make_full_pipeline_router(
        monkeypatch,
        audits_by_label={"doc-audit": audits},
        git_diff_stdout="",
    )

    monkeypatch.setattr(
        run, "apply_routing",
        lambda *a, **kw: RoutingResult(exit_code=0),
    )

    exit_code = run.main(["--config", str(_config_path(tmp_config))])
    assert exit_code == 0

    # Exactly one lock-acquisition gh edit call for #6400.
    locks = [
        c for c in calls
        if len(c) >= 5
        and c[1] == "issue" and c[2] == "edit" and c[3] == "6400"
        and "--add-label" in c
        and "status:in-progress" in c
    ]
    assert locks, f"expected lock acquisition for #6400; got calls={calls!r}"


def test_stuck_lock_processed_in_tick(
    tmp_config: Any,
    monkeypatch: pytest.MonkeyPatch,
    mock_anthropic: Any,
) -> None:
    """Cycle-2 finding #3: stuck lock is processed THIS tick, not deferred.

    A stuck audit (status:in-progress with no matching PA) is synthesized
    into the signal queue and dispatched through the normal workflow.
    The tick signal's ``audits_processed`` should INCLUDE the recovered
    audit number — proving it ran in-tick rather than being deferred.
    """
    stuck = [
        {
            "number": 8800,
            "title": "Doc audit: stalecase (felix-core)",
            "body": "",
            "labels": [
                {"name": "doc-audit"},
                {"name": "status:in-progress"},
                {"name": "area/felix-core"},
            ],
            "createdAt": "2026-05-20T07:00:00Z",
        }
    ]

    def fake_run(cmd, *args, **kwargs):
        cmd = list(cmd)
        if cmd[0] == "git":
            return _completed("")
        if (
            len(cmd) >= 3 and cmd[1] == "issue" and cmd[2] == "list"
            and "status:in-progress" in cmd
        ):
            return _completed(json.dumps(stuck))
        # Normal list scan returns nothing (the only audit is stuck).
        return _completed("[]" if "list" in cmd else "")

    monkeypatch.setattr(subprocess, "run", fake_run)
    monkeypatch.setattr(
        run, "apply_routing",
        lambda *a, **kw: RoutingResult(exit_code=0),
    )

    exit_code = run.main(["--config", str(_config_path(tmp_config))])
    assert exit_code == 0
    signal = _read_tick_signal(tmp_config)
    # The stuck audit was processed in THIS tick (not deferred).
    assert 8800 in signal["tick"]["audits_processed"], (
        f"expected #8800 processed in-tick; got "
        f"{signal['tick']['audits_processed']}"
    )
    # Recovery marker still present in errors.
    assert any(
        "recovered-stale-lock" in e for e in signal["errors"]
    )
