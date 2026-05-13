"""Tests for `handle_audit_routing.py` (felix-doc-auditor orchestrator).

The handler is exercised end-to-end via `subprocess.run` so the CLI
surface (argument parsing, exit codes, stderr) is covered. The
handler's internal subprocess calls (`git` and `gh`) are stubbed by
passing `--git-bin` / `--gh-bin` pointing at small shell scripts that
record their invocations and emit canned outputs.

This mirrors the regression-guard role of mission #33's
`tests/inbox/test_atomic_write_perms.py` for the doc-auditor's new
edit-application surface.
"""
from __future__ import annotations

import json
import os
import stat
import subprocess
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[4]
HANDLER_PATH = (
    REPO_ROOT
    / "scripts"
    / "openclaw"
    / "agents"
    / "felix-doc-auditor"
    / "handle_audit_routing.py"
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _write_stub(
    path: Path,
    log_path: Path,
    exit_code: int = 0,
    stdout: str = "",
    stderr: str = "",
) -> None:
    """Create a stub Python script that logs its args and emits canned output.

    Each invocation appends one line of JSON (`{"argv": [...]}`) to
    `log_path`, then prints `stdout`/`stderr` and exits with
    `exit_code`. Using JSON sidesteps the multi-line --body problem
    that a shell stub would have.
    """
    py = (
        "#!/usr/bin/env python3\n"
        "import json, sys\n"
        f"with open({repr(str(log_path))}, 'a', encoding='utf-8') as fh:\n"
        "    fh.write(json.dumps({'argv': sys.argv[1:]}) + '\\n')\n"
    )
    if stdout:
        py += f"sys.stdout.write({stdout!r})\n"
    if stderr:
        py += f"sys.stderr.write({stderr!r})\n"
    py += f"sys.exit({exit_code})\n"
    path.write_text(py, encoding="utf-8")
    path.chmod(0o755)


def _read_stub_log(log_path: Path) -> list[list[str]]:
    """Return a list of argv lists, one per invocation recorded."""
    if not log_path.exists():
        return []
    invocations: list[list[str]] = []
    for line in log_path.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        rec = json.loads(line)
        invocations.append(rec["argv"])
    return invocations


def _run_handler(
    state_file: Path,
    git_bin: Path,
    gh_bin: Path,
    repo_root: Path,
) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [
            sys.executable,
            str(HANDLER_PATH),
            f"@{state_file}",
            "--git-bin",
            str(git_bin),
            "--gh-bin",
            str(gh_bin),
            "--repo-root",
            str(repo_root),
        ],
        capture_output=True,
        text=True,
    )


def _write_doc(path: Path, body: str, mode: int) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(body, encoding="utf-8")
    os.chmod(path, mode)


def _mode(path: Path) -> int:
    return stat.S_IMODE(path.stat().st_mode)


@pytest.fixture
def fake_repo(tmp_path: Path) -> Path:
    """A scratch directory used as --repo-root for the handler."""
    repo = tmp_path / "repo"
    repo.mkdir()
    return repo


@pytest.fixture
def state_file(tmp_path: Path):
    """Factory: serialize an audit-state dict to a JSON file in tmp_path."""

    def _make(state: dict) -> Path:
        path = tmp_path / "state.json"
        path.write_text(json.dumps(state), encoding="utf-8")
        return path

    return _make


@pytest.fixture
def stubs(tmp_path: Path):
    """Factory: returns (git_bin, gh_bin, git_log, gh_log) with optional canned outputs."""
    git_log = tmp_path / "git.log"
    gh_log = tmp_path / "gh.log"
    git_bin = tmp_path / "git-stub.sh"
    gh_bin = tmp_path / "gh-stub.sh"

    def _make(
        git_exit: int = 0,
        gh_create_stdout: str = "https://github.com/kentonium3/kg-automation/issues/999\n",
        gh_exit: int = 0,
    ) -> tuple[Path, Path, Path, Path]:
        _write_stub(git_bin, git_log, exit_code=git_exit)
        # gh stub: handles `issue create` (emits URL on stdout), `issue
        # comment`, and `issue close`. The same canned stdout is fine
        # for all — only the `create` path parses it.
        _write_stub(gh_bin, gh_log, exit_code=gh_exit, stdout=gh_create_stdout)
        return git_bin, gh_bin, git_log, gh_log

    return _make


def _baseline_state(**overrides) -> dict:
    state = {
        "audit_issue_number": 258,
        "commit_sha": "7471fe7",
        "areas": ["area/felix-core"],
        "proposals": [],
        "debt_issues_filed": [],
        "missing_artifact_issues_filed": [],
    }
    state.update(overrides)
    return state


def _frontmatter_doc(date: str = "2026-05-10") -> str:
    return (
        "---\n"
        "id: docs-index\n"
        "doc_type: index\n"
        f"last_validated: {date}\n"
        "---\n"
        "\n"
        "# Doc\n"
        f"\nBody mentions {date} but the canonical value is the frontmatter line.\n"
    )


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


def test_all_auto_apply_no_gate(fake_repo, state_file, stubs):
    """Single frontmatter_date proposal: file edited, git commit run, no gate, summary posted."""
    doc_rel = "docs/INDEX.md"
    doc_abs = fake_repo / doc_rel
    _write_doc(doc_abs, _frontmatter_doc("2026-05-10"), mode=0o644)

    state = _baseline_state(
        proposals=[
            {
                "doc_path": doc_rel,
                "change_type": "frontmatter_date",
                "current_value": "2026-05-10",
                "proposed_value": "2026-05-13",
                "evidence_source": "commit 7471fe7 (2026-05-13)",
                "confidence": "high",
            }
        ],
    )
    sf = state_file(state)
    git_bin, gh_bin, git_log, gh_log = stubs()

    result = _run_handler(sf, git_bin, gh_bin, fake_repo)

    assert result.returncode == 0, result.stderr

    # Frontmatter date was updated; body occurrence untouched (single-occurrence sub within fm region).
    new_text = doc_abs.read_text(encoding="utf-8")
    assert "last_validated: 2026-05-13" in new_text
    # Mode preserved.
    assert _mode(doc_abs) == 0o644

    # git stub recorded `add` + `commit`.
    git_invocations = _read_stub_log(git_log)
    assert any(inv[:1] == ["add"] for inv in git_invocations), git_invocations
    assert any(inv[:1] == ["commit"] for inv in git_invocations), git_invocations

    # gh stub recorded a comment (summary) and a close — but NO create.
    gh_invocations = _read_stub_log(gh_log)
    created = [inv for inv in gh_invocations if inv[:2] == ["issue", "create"]]
    commented = [inv for inv in gh_invocations if inv[:2] == ["issue", "comment"]]
    closed = [inv for inv in gh_invocations if inv[:2] == ["issue", "close"]]
    assert created == [], "gate-file should not be invoked when nothing is gated"
    assert len(commented) == 1, gh_invocations
    assert len(closed) == 1, gh_invocations


def test_all_gated(fake_repo, state_file, stubs):
    """Single prose_replacement proposal (unknown type): no edit, no commit, gate filed, summary posted."""
    doc_rel = "docs/INDEX.md"
    doc_abs = fake_repo / doc_rel
    original = _frontmatter_doc("2026-05-10")
    _write_doc(doc_abs, original, mode=0o644)

    state = _baseline_state(
        proposals=[
            {
                "doc_path": doc_rel,
                "change_type": "prose_replacement",
                "current_value": "old prose",
                "proposed_value": "new prose",
                "evidence_source": "author judgment",
                "confidence": "judgment",
            }
        ],
    )
    sf = state_file(state)
    git_bin, gh_bin, git_log, gh_log = stubs()

    result = _run_handler(sf, git_bin, gh_bin, fake_repo)

    assert result.returncode == 0, result.stderr

    # Doc unchanged.
    assert doc_abs.read_text(encoding="utf-8") == original

    # git stub never called.
    assert _read_stub_log(git_log) == []

    # gh stub: one create (gate) and one comment (summary). No close — gate is now open thread.
    gh_invocations = _read_stub_log(gh_log)
    created = [inv for inv in gh_invocations if inv[:2] == ["issue", "create"]]
    commented = [inv for inv in gh_invocations if inv[:2] == ["issue", "comment"]]
    closed = [inv for inv in gh_invocations if inv[:2] == ["issue", "close"]]
    assert len(created) == 1, gh_invocations
    assert len(commented) == 1, gh_invocations
    assert closed == [], gh_invocations


def test_gated_body_preserves_template_contract(fake_repo, state_file, stubs):
    """Regression guard: pending-approval body must preserve the template contract.

    The template at
    ``kitty-specs/felix-doc-auditor-agent-01KR7JK9/contracts/
    audit-pending-approval-issue.template.md`` is the canonical surface
    consumed by the cron-tick decision handler and the human review
    workflow. The body produced by the helper must include every
    contract-required heading and marker so downstream consumers don't
    drift.
    """
    doc_rel = "docs/INDEX.md"
    doc_abs = fake_repo / doc_rel
    _write_doc(doc_abs, _frontmatter_doc("2026-05-10"), mode=0o644)

    state = _baseline_state(
        proposals=[
            {
                "doc_path": doc_rel,
                "change_type": "prose_replacement",
                "current_value": "old prose",
                "proposed_value": "new prose",
                "evidence_source": "author judgment",
                "confidence": "judgment",
            }
        ],
        debt_issues_filed=[401, 402],
        missing_artifact_issues_filed=[501],
    )
    sf = state_file(state)
    git_bin, gh_bin, _, gh_log = stubs()

    result = _run_handler(sf, git_bin, gh_bin, fake_repo)
    assert result.returncode == 0, result.stderr

    gh_invocations = _read_stub_log(gh_log)
    created = [inv for inv in gh_invocations if inv[:2] == ["issue", "create"]]
    assert len(created) == 1, gh_invocations
    body_idx = created[0].index("--body") + 1
    body = created[0][body_idx]

    # Template-required headings and labelled fields.
    required_markers = [
        "## Audit pending approval",
        "**Originating audit**: #",
        "**Triggering commit**: `",
        "**Scope**: ",
        "**Docs reviewed**",
        "## Proposed edits",
        "**Change type**:",
        "**Evidence**:",
        "**Diff**:",
        "```diff",
        "## Already filed (autonomously, not part of this gate)",
        "**Docs-debt issues filed**:",
        "**Missing-artifact issues filed**:",
        "**Items requiring human review**",
        "## Decision",
        "`audit-approve`",
        "`audit-reject`",
        "`audit-skip`",
        "No timeout",
        "Filed by `felix-doc-auditor:",
    ]
    for marker in required_markers:
        assert marker in body, (
            f"pending-approval body missing template marker {marker!r}; "
            f"body=\n{body}"
        )

    # Debt/missing-artifact references should be wired through from JSON.
    assert "#401" in body and "#402" in body, body
    assert "#501" in body, body


def test_mixed_partition(fake_repo, state_file, stubs):
    """1 known + 1 unknown: known applied + committed; unknown filed as gate; summary names both."""
    doc_rel = "docs/INDEX.md"
    doc_abs = fake_repo / doc_rel
    _write_doc(doc_abs, _frontmatter_doc("2026-05-10"), mode=0o644)

    state = _baseline_state(
        proposals=[
            {
                "doc_path": doc_rel,
                "change_type": "frontmatter_date",
                "current_value": "2026-05-10",
                "proposed_value": "2026-05-13",
                "evidence_source": "commit 7471fe7 (2026-05-13)",
                "confidence": "high",
            },
            {
                "doc_path": doc_rel,
                "change_type": "prose_replacement",
                "current_value": "Body mentions 2026-05-13",
                "proposed_value": "Body now references 2026-05-13",
                "evidence_source": "judgment",
                "confidence": "judgment",
            },
        ],
    )
    sf = state_file(state)
    git_bin, gh_bin, git_log, gh_log = stubs()

    result = _run_handler(sf, git_bin, gh_bin, fake_repo)
    assert result.returncode == 0, result.stderr

    # Known change applied.
    assert "last_validated: 2026-05-13" in doc_abs.read_text(encoding="utf-8")

    git_invocations = _read_stub_log(git_log)
    assert any(inv[:1] == ["commit"] for inv in git_invocations)

    gh_invocations = _read_stub_log(gh_log)
    created = [inv for inv in gh_invocations if inv[:2] == ["issue", "create"]]
    commented = [inv for inv in gh_invocations if inv[:2] == ["issue", "comment"]]
    closed = [inv for inv in gh_invocations if inv[:2] == ["issue", "close"]]
    assert len(created) == 1
    # The gate-file body lists only the gated subset.
    # `--body` arg lives after `--body` flag in the argv; locate it.
    create_inv = created[0]
    body_idx = create_inv.index("--body") + 1
    gate_body = create_inv[body_idx]
    assert "prose_replacement" in gate_body
    assert "frontmatter_date" not in gate_body, "gate body should not list auto-applied edit"

    # Summary names both partitions.
    summary_inv = commented[0]
    body_idx = summary_inv.index("--body") + 1
    summary_body = summary_inv[body_idx]
    assert "frontmatter_date" in summary_body
    assert "prose_replacement" in summary_body

    # No close (gate is the new open thread).
    assert closed == []


def test_empty_proposals(fake_repo, state_file, stubs):
    """Empty proposals: exit 0 immediately, no git/gh activity."""
    state = _baseline_state(proposals=[])
    sf = state_file(state)
    git_bin, gh_bin, git_log, gh_log = stubs()

    result = _run_handler(sf, git_bin, gh_bin, fake_repo)
    assert result.returncode == 0, result.stderr
    assert _read_stub_log(git_log) == []
    assert _read_stub_log(gh_log) == []


def test_invalid_json(tmp_path, fake_repo, stubs):
    """Malformed JSON input: exit 1, structured stderr, no subprocess activity."""
    bad = tmp_path / "bad.json"
    bad.write_text("{not valid json", encoding="utf-8")
    git_bin, gh_bin, git_log, gh_log = stubs()

    result = _run_handler(bad, git_bin, gh_bin, fake_repo)
    assert result.returncode == 1, result.stdout + "\n" + result.stderr
    assert "ERROR" in result.stderr
    assert _read_stub_log(git_log) == []
    assert _read_stub_log(gh_log) == []


def test_commit_failure_propagates(fake_repo, state_file, stubs):
    """git commit non-zero: exit 3, gate-file NOT invoked even if gated subset exists, no summary."""
    doc_rel = "docs/INDEX.md"
    doc_abs = fake_repo / doc_rel
    _write_doc(doc_abs, _frontmatter_doc("2026-05-10"), mode=0o644)

    state = _baseline_state(
        proposals=[
            {
                "doc_path": doc_rel,
                "change_type": "frontmatter_date",
                "current_value": "2026-05-10",
                "proposed_value": "2026-05-13",
                "evidence_source": "commit",
                "confidence": "high",
            },
            {
                # gated; should NOT be filed because commit fails first.
                "doc_path": doc_rel,
                "change_type": "prose_replacement",
                "current_value": "Body",
                "proposed_value": "Body!",
                "evidence_source": "judgment",
                "confidence": "judgment",
            },
        ],
    )
    sf = state_file(state)
    # git stub fails (exit 7 for visibility).
    git_bin, gh_bin, git_log, gh_log = stubs(git_exit=7)

    result = _run_handler(sf, git_bin, gh_bin, fake_repo)
    assert result.returncode == 3, result.stdout + "\n" + result.stderr
    assert "git commit failed" in result.stderr or "git" in result.stderr.lower()

    # No gate-file or summary should have been attempted.
    gh_invocations = _read_stub_log(gh_log)
    assert gh_invocations == [], (
        f"after commit failure, gate-file and summary must not run; got {gh_invocations}"
    )


def test_atomic_write_preserves_mode(fake_repo, state_file, stubs):
    """Regression guard against re-introducing #254: mode preserved across atomic write."""
    doc_rel = "docs/INDEX.md"
    doc_abs = fake_repo / doc_rel

    for mode in (0o600, 0o644, 0o664):
        # Re-create the doc fresh for each mode iteration.
        _write_doc(doc_abs, _frontmatter_doc("2026-05-10"), mode=mode)

        state = _baseline_state(
            proposals=[
                {
                    "doc_path": doc_rel,
                    "change_type": "frontmatter_date",
                    "current_value": "2026-05-10",
                    "proposed_value": "2026-05-13",
                    "evidence_source": "commit",
                    "confidence": "high",
                }
            ],
        )
        sf = state_file(state)
        git_bin, gh_bin, _, _ = stubs()

        result = _run_handler(sf, git_bin, gh_bin, fake_repo)
        assert result.returncode == 0, result.stderr
        assert _mode(doc_abs) == mode, f"mode {oct(mode)} not preserved"
        # And content was actually updated.
        assert "last_validated: 2026-05-13" in doc_abs.read_text(encoding="utf-8")


def test_apply_mismatch_aborts(fake_repo, state_file, stubs):
    """current_value mismatch: exit 2 with proposal identified; no commit, no gate."""
    doc_rel = "docs/INDEX.md"
    doc_abs = fake_repo / doc_rel
    _write_doc(doc_abs, _frontmatter_doc("2026-05-10"), mode=0o644)

    state = _baseline_state(
        proposals=[
            {
                "doc_path": doc_rel,
                "change_type": "frontmatter_date",
                # NOTE: this value isn't in the file (concurrent drift).
                "current_value": "1999-12-31",
                "proposed_value": "2026-05-13",
                "evidence_source": "commit",
                "confidence": "high",
            },
        ],
    )
    sf = state_file(state)
    git_bin, gh_bin, git_log, gh_log = stubs()

    result = _run_handler(sf, git_bin, gh_bin, fake_repo)
    assert result.returncode == 2, result.stdout + "\n" + result.stderr
    # The failing proposal should be named in stderr.
    assert "docs/INDEX.md" in result.stderr
    assert "frontmatter_date" in result.stderr

    # No commit was invoked (rollback's `git checkout` is allowed since
    # nothing was written, but `git commit` must not appear).
    git_invocations = _read_stub_log(git_log)
    commits = [inv for inv in git_invocations if inv[:1] == ["commit"]]
    assert commits == []

    # No gate-file or summary.
    gh_invocations = _read_stub_log(gh_log)
    assert gh_invocations == []
