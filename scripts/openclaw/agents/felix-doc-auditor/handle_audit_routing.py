#!/usr/bin/env python3
"""Forward-path audit decision orchestrator for felix-doc-auditor.

Reads a serialized audit-state JSON file, partitions the included
proposals by `change_type` against an in-script allowlist of known
auto-applyable change types, and then:

  1. Atomically applies each auto-apply proposal (mode-preserving write).
  2. Commits all applied edits in a single git commit referencing the
     originating audit issue.
  3. If any proposals fall outside the allowlist (gated subset), files a
     `audit-pending-approval` GitHub issue listing exactly that subset.
  4. Posts an audit summary comment on the originating audit issue with
     the applied edits, gated edits (and pending-approval issue link if
     filed), and references to debt/missing-artifact issues already
     filed in § 7.8.
  5. Closes the originating audit issue when there were no gated edits.

The helper collapses what previously lived as prose in AGENTS.md
§ 7.9 / § 7.10 / § 7.11. See mission `auto-apply-audit-edits-01KRG1BG`
and issue #259 for context.

CLI:
    python3 handle_audit_routing.py @/path/to/audit-state.json

    The single positional argument is a path to a JSON file. The leading
    `@` is optional (accepted for ergonomic parity with `gh issue create
    --body-file @...`).

Input JSON shape (see kitty-specs/auto-apply-audit-edits-01KRG1BG/
data-model.md for the authoritative E-008 contract)::

    {
      "audit_issue_number": 258,
      "commit_sha": "7471fe7",
      "areas": ["area/biz-ops", "area/felix-core"],
      "proposals": [
        {
          "doc_path": "docs/INDEX.md",
          "change_type": "frontmatter_date",
          "current_value": "2026-05-10",
          "proposed_value": "2026-05-13",
          "evidence_source": "commit 7471fe7 (2026-05-13)",
          "confidence": "high"
        }
      ],
      "debt_issues_filed": [],
      "missing_artifact_issues_filed": []
    }

Exit codes::

    0  full success (including the empty-proposals case)
    1  input-validation failure (missing file, malformed JSON, missing
       required keys, wrong types)
    2  apply failure (one or more auto-apply edits could not be applied
       — `current_value` mismatch, missing file, etc.); rolls back any
       partial writes via `git checkout -- <files>`; no commit, no gate
    3  commit failure (`git commit` exited non-zero); no gate, no
       summary post — system is partially modified on disk but no commit
       landed; stderr identifies which leg
    4  gate-file failure (`gh issue create` for the pending-approval
       issue failed AFTER commit succeeded); summary still attempted on
       a best-effort basis but exit code reflects the gate failure
    5  summary-post failure (everything else succeeded but the final
       `gh issue comment` failed); non-fatal — the system is in the
       correct on-disk state, just under-reported

Invariants:
    * Subprocess sequencing on failure: if `git commit` fails, the
      gate-file leg MUST NOT be invoked. Don't half-do.
    * Atomic-write mode preservation: `_atomic_write` is a functional
      mirror of the helper in `scripts/inbox/inject_parse_error_marker.py`
      (mission #33, #254). Mode preservation is load-bearing because the
      auditor edits files that may be cross-user (e.g., kgale-owned docs
      edited by the claude-running agent); without it, ob (Obsidian Sync)
      loses read access.
"""
from __future__ import annotations

import argparse
import json
import os
import re
import stat
import subprocess
import sys
import tempfile
from pathlib import Path
from typing import Any

# C-001 / Decision 1 — the auto-apply allowlist. These are the
# change_types whose correct value is deterministically derivable from a
# system-state source. Cases requiring judgment go to § 7.8 debt
# issues (autonomous, no gate) and never reach this helper.
AUTO_APPLY_CHANGE_TYPES = frozenset({
    "frontmatter_date",
    "version_bump",
    "path_rename",
    "dead_ref_removal",
    "registry_entry_add",
    "registry_autonomy_update",
})

REQUIRED_TOP_KEYS = (
    "audit_issue_number",
    "commit_sha",
    "areas",
    "proposals",
    "debt_issues_filed",
    "missing_artifact_issues_filed",
)

REQUIRED_PROPOSAL_KEYS = (
    "doc_path",
    "change_type",
    "current_value",
    "proposed_value",
    "evidence_source",
    "confidence",
)


# ---------------------------------------------------------------------------
# Errors
# ---------------------------------------------------------------------------


class RouteApplyError(Exception):
    """Raised when a single proposal could not be applied to its doc."""

    def __init__(self, proposal: dict[str, Any], reason: str) -> None:
        super().__init__(f"{proposal.get('doc_path', '?')}: {reason}")
        self.proposal = proposal
        self.reason = reason


class InputValidationError(Exception):
    """Raised when the input JSON does not satisfy the contract."""


# ---------------------------------------------------------------------------
# Atomic mode-preserving write (mirror of mission #33 / #254 pattern)
# ---------------------------------------------------------------------------


def _atomic_write(path: Path, content: str) -> None:
    """Atomic write that preserves the original file's mode.

    Mirror of the pattern landed by mission #33 (#254) in
    `scripts/inbox/inject_parse_error_marker.py`. Mode preservation is
    load-bearing because the doc-auditor edits files that may be
    cross-user (e.g., kgale-owned docs edited by the claude-running
    agent); without it, ob (Obsidian Sync) loses read access.
    """
    parent = path.parent
    fd, tmp_name = tempfile.mkstemp(
        prefix=path.name + ".",
        suffix=".tmp",
        dir=str(parent),
    )
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as fh:
            fh.write(content)
        try:
            mode = stat.S_IMODE(os.stat(path).st_mode)
            kind = "preserved"
        except FileNotFoundError:
            mode = 0o664
            kind = "new"
        os.chmod(tmp_name, mode)
        os.replace(tmp_name, path)
        print(
            f"INFO: atomic_write {path} mode={oct(mode)} ({kind})",
            file=sys.stderr,
        )
    except Exception:
        try:
            os.unlink(tmp_name)
        except OSError:
            pass
        raise


# ---------------------------------------------------------------------------
# Per-change_type substitution helpers
# ---------------------------------------------------------------------------
#
# Each helper takes the current file content (`content`) and the
# proposal dict, and returns the new content. If the helper cannot
# perform the substitution — typically because `current_value` does not
# match what is actually present in the file (indicates concurrent
# drift) — it raises RouteApplyError so the main flow can roll back
# without committing partial work.


def _apply_frontmatter_date(content: str, proposal: dict[str, Any]) -> str:
    """Replace the value of a YAML frontmatter date-style field.

    The proposal carries `current_value` and `proposed_value`; the field
    is identified by exact value match within the frontmatter block.
    This is intentionally simple — the auditor's confidence in the edit
    means the (key, value) pair is unique in the frontmatter.
    """
    current = proposal["current_value"]
    proposed = proposal["proposed_value"]
    if current == proposed:
        # No-op edit; treat as drift (shouldn't reach this helper).
        raise RouteApplyError(proposal, "current and proposed values are identical")
    # Restrict the substitution to the frontmatter block so we don't
    # accidentally rewrite a body occurrence of the same date.
    lines = content.splitlines(keepends=True)
    if not lines or lines[0].rstrip("\n") != "---":
        raise RouteApplyError(proposal, "no leading YAML frontmatter found")
    close_idx = None
    for i, line in enumerate(lines[1:], start=1):
        if line.rstrip("\n") == "---":
            close_idx = i
            break
    if close_idx is None:
        raise RouteApplyError(proposal, "unterminated YAML frontmatter")
    # Look for the current_value within the frontmatter region.
    pre = "".join(lines[: close_idx + 1])
    post = "".join(lines[close_idx + 1 :])
    if current not in pre:
        raise RouteApplyError(
            proposal,
            f"current_value {current!r} not found in frontmatter",
        )
    new_pre = pre.replace(current, proposed, 1)
    return new_pre + post


def _apply_version_bump(content: str, proposal: dict[str, Any]) -> str:
    """Replace a single version-string occurrence.

    The substitution is bounded to the first occurrence of
    `current_value` in the document; if it is not present, raise.
    """
    current = proposal["current_value"]
    proposed = proposal["proposed_value"]
    if current == proposed:
        raise RouteApplyError(proposal, "current and proposed versions are identical")
    if current not in content:
        raise RouteApplyError(
            proposal,
            f"current_value {current!r} not found in document",
        )
    return content.replace(current, proposed, 1)


def _apply_path_rename(content: str, proposal: dict[str, Any]) -> str:
    """Replace path occurrences (all matches of `current_value`).

    Path renames are global within the touched file: every reference to
    the old path must be updated to the new path. Other change_types
    only replace a single occurrence.
    """
    current = proposal["current_value"]
    proposed = proposal["proposed_value"]
    if current == proposed:
        raise RouteApplyError(proposal, "current and proposed paths are identical")
    if current not in content:
        raise RouteApplyError(
            proposal,
            f"current_value {current!r} not found in document",
        )
    return content.replace(current, proposed)


def _apply_dead_ref_removal(content: str, proposal: dict[str, Any]) -> str:
    """Remove a dead reference line/snippet.

    The proposal's `current_value` is the snippet to remove;
    `proposed_value` is the empty string (or omitted). If the snippet is
    not present, raise.
    """
    current = proposal["current_value"]
    proposed = proposal.get("proposed_value", "") or ""
    if current not in content:
        raise RouteApplyError(
            proposal,
            f"dead reference {current!r} not found in document",
        )
    # If a whole line is being removed (current ends with a newline or
    # is a standalone match), drop the trailing newline too so we don't
    # leave a blank line where the dead ref was.
    if proposed == "":
        # Try to also consume one trailing newline if the snippet sits on
        # its own line. This is best-effort.
        pattern_with_nl = re.escape(current) + r"\n?"
        new_content, count = re.subn(pattern_with_nl, "", content, count=1)
        if count == 0:
            # Fallback: literal replace.
            new_content = content.replace(current, "", 1)
        return new_content
    return content.replace(current, proposed, 1)


def _apply_registry_entry_add(content: str, proposal: dict[str, Any]) -> str:
    """Add a new entry to a registry-style document.

    `proposed_value` is the new entry to add (e.g., a JSON snippet, a
    markdown row, a list item). `current_value` is the anchor line that
    immediately precedes the insertion point. If the anchor is absent,
    raise — the auditor's confidence in this edit assumes the anchor is
    stable.
    """
    current = proposal["current_value"]
    proposed = proposal["proposed_value"]
    if current not in content:
        raise RouteApplyError(
            proposal,
            f"anchor {current!r} not found in document",
        )
    # Insert the new entry on the line immediately after the anchor.
    # Preserve the anchor's trailing newline shape.
    if current.endswith("\n"):
        replacement = current + proposed
        if not proposed.endswith("\n"):
            replacement += "\n"
    else:
        replacement = current + "\n" + proposed
        if not proposed.endswith("\n"):
            replacement += "\n"
    return content.replace(current, replacement, 1)


def _apply_registry_autonomy_update(content: str, proposal: dict[str, Any]) -> str:
    """Update an autonomy designation within a registry doc.

    Functionally identical to `_apply_version_bump` (single-occurrence
    replacement) but kept as a distinct helper so the per-change_type
    dispatch table is explicit. Adding a future bespoke check (e.g.,
    "autonomy can only move forward one level") would land here.
    """
    current = proposal["current_value"]
    proposed = proposal["proposed_value"]
    if current == proposed:
        raise RouteApplyError(
            proposal,
            "current and proposed autonomy levels are identical",
        )
    if current not in content:
        raise RouteApplyError(
            proposal,
            f"current_value {current!r} not found in document",
        )
    return content.replace(current, proposed, 1)


APPLIERS: dict[str, Any] = {
    "frontmatter_date": _apply_frontmatter_date,
    "version_bump": _apply_version_bump,
    "path_rename": _apply_path_rename,
    "dead_ref_removal": _apply_dead_ref_removal,
    "registry_entry_add": _apply_registry_entry_add,
    "registry_autonomy_update": _apply_registry_autonomy_update,
}


# ---------------------------------------------------------------------------
# Input parsing & validation
# ---------------------------------------------------------------------------


def _resolve_state_path(raw: str) -> Path:
    """Strip the optional leading `@` and return a Path."""
    if raw.startswith("@"):
        raw = raw[1:]
    return Path(raw)


def _load_state(path: Path) -> dict[str, Any]:
    if not path.exists():
        raise InputValidationError(f"state file not found: {path}")
    try:
        text = path.read_text(encoding="utf-8")
    except OSError as exc:
        raise InputValidationError(f"state file unreadable: {exc}") from exc
    try:
        data = json.loads(text)
    except json.JSONDecodeError as exc:
        raise InputValidationError(f"state file is not valid JSON: {exc}") from exc
    if not isinstance(data, dict):
        raise InputValidationError("state file root must be a JSON object")
    missing = [k for k in REQUIRED_TOP_KEYS if k not in data]
    if missing:
        raise InputValidationError(
            f"state file missing required keys: {', '.join(missing)}"
        )
    if not isinstance(data["audit_issue_number"], int):
        raise InputValidationError("audit_issue_number must be an integer")
    if not isinstance(data["commit_sha"], str):
        raise InputValidationError("commit_sha must be a string")
    if not isinstance(data["areas"], list):
        raise InputValidationError("areas must be a list")
    if not isinstance(data["proposals"], list):
        raise InputValidationError("proposals must be a list")
    if not isinstance(data["debt_issues_filed"], list):
        raise InputValidationError("debt_issues_filed must be a list")
    if not isinstance(data["missing_artifact_issues_filed"], list):
        raise InputValidationError("missing_artifact_issues_filed must be a list")
    for idx, proposal in enumerate(data["proposals"]):
        if not isinstance(proposal, dict):
            raise InputValidationError(f"proposals[{idx}] must be an object")
        missing = [k for k in REQUIRED_PROPOSAL_KEYS if k not in proposal]
        if missing:
            raise InputValidationError(
                f"proposals[{idx}] missing keys: {', '.join(missing)}"
            )
    return data


# ---------------------------------------------------------------------------
# Partition + apply
# ---------------------------------------------------------------------------


def _partition(proposals: list[dict[str, Any]]) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    """Split proposals into (auto_apply, gated) by change_type."""
    auto_apply = [p for p in proposals if p["change_type"] in AUTO_APPLY_CHANGE_TYPES]
    gated = [p for p in proposals if p["change_type"] not in AUTO_APPLY_CHANGE_TYPES]
    return auto_apply, gated


def _apply_one(repo_root: Path, proposal: dict[str, Any]) -> Path:
    """Apply one proposal to its doc. Returns the absolute path written."""
    doc_path = repo_root / proposal["doc_path"]
    if not doc_path.exists():
        raise RouteApplyError(proposal, f"doc not found: {doc_path}")
    applier = APPLIERS.get(proposal["change_type"])
    if applier is None:  # pragma: no cover — partition filters first
        raise RouteApplyError(
            proposal,
            f"no applier registered for change_type {proposal['change_type']!r}",
        )
    content = doc_path.read_text(encoding="utf-8")
    new_content = applier(content, proposal)
    if new_content == content:
        raise RouteApplyError(proposal, "applier produced no change")
    _atomic_write(doc_path, new_content)
    return doc_path


def _rollback(repo_root: Path, paths: list[Path], git_bin: str) -> None:
    """Undo any partial writes via `git checkout -- <files>`. Best-effort."""
    if not paths:
        return
    rels = [str(p.relative_to(repo_root)) for p in paths]
    try:
        subprocess.run(
            [git_bin, "checkout", "--", *rels],
            cwd=str(repo_root),
            check=False,
        )
    except (OSError, subprocess.SubprocessError) as exc:
        print(
            f"WARN: rollback via git checkout failed: {exc}",
            file=sys.stderr,
        )


# ---------------------------------------------------------------------------
# Commit / gate-file / summary-post (subprocess legs)
# ---------------------------------------------------------------------------


def _build_commit_message(audit_issue: int, commit_sha: str, applied: list[dict[str, Any]]) -> str:
    n = len(applied)
    subject = f"docs(audit): apply {n} auto-resolved edit{'s' if n != 1 else ''} from audit #{audit_issue}"
    intro = (
        f"Triggered by commit {commit_sha}. Auto-applied per the felix-doc-auditor\n"
        "change_type allowlist (frontmatter_date, version_bump, etc.)."
    )
    bullets = "\n".join(
        f"- {p['doc_path']}: {p['change_type']} ({p['current_value']} -> {p['proposed_value']})"
        for p in applied
    )
    body = f"{intro}\n\nApplied edits:\n{bullets}"
    return f"{subject}\n\n{body}\n"


def _run_git_commit(
    repo_root: Path,
    git_bin: str,
    applied: list[dict[str, Any]],
    audit_issue: int,
    commit_sha: str,
) -> subprocess.CompletedProcess[str]:
    rels = sorted({p["doc_path"] for p in applied})
    add_result = subprocess.run(
        [git_bin, "add", "--", *rels],
        cwd=str(repo_root),
        capture_output=True,
        text=True,
    )
    if add_result.returncode != 0:
        return add_result
    message = _build_commit_message(audit_issue, commit_sha, applied)
    return subprocess.run(
        [git_bin, "commit", "-m", message],
        cwd=str(repo_root),
        capture_output=True,
        text=True,
    )


def _build_pending_approval_body(
    audit_issue: int,
    commit_sha: str,
    areas: list[str],
    gated: list[dict[str, Any]],
    debt_issues: list[int],
    missing_issues: list[int],
) -> str:
    """Render the pending-approval issue body.

    Preserves the contract defined by
    ``kitty-specs/felix-doc-auditor-agent-01KR7JK9/contracts/
    audit-pending-approval-issue.template.md`` so cron-tick decision
    handling and the human review workflow see a consistent surface.

    Fields not carried in the WP01 JSON contract are filled with
    explicit placeholders rather than dropped:
    - ``Docs reviewed`` → ``unknown`` (auditor doesn't pass a count here)
    - ``Items requiring human review`` → ``(none)`` (no field for this)
    """
    scope = ", ".join(areas) if areas else "full-scope"
    docs_reviewed = "unknown"
    items_requiring_review = "(none)"
    debt_str = (
        ", ".join(f"#{n}" for n in debt_issues) if debt_issues else "(none)"
    )
    missing_str = (
        ", ".join(f"#{n}" for n in missing_issues) if missing_issues else "(none)"
    )
    parts = [
        "## Audit pending approval",
        "",
        f"**Originating audit**: #{audit_issue}",
        f"**Triggering commit**: `{commit_sha}`",
        f"**Scope**: {scope}",
        f"**Docs reviewed**: {docs_reviewed}",
        "",
        "## Proposed edits",
        "",
        "Each numbered item is a high-confidence edit per the doc-audit skill's",
        "Section 4.1 confidence rules. Apply ALL of them on `audit-approve`.",
        "",
    ]
    for i, p in enumerate(gated, start=1):
        parts.extend([
            f"### {i}. `{p['doc_path']}`",
            "",
            f"**Change type**: {p['change_type']}",
            "",
            f"**Evidence**: {p['evidence_source']}",
            "",
            "**Diff**:",
            "```diff",
            f"- {p['current_value']}",
            f"+ {p['proposed_value']}",
            "```",
            "",
        ])
    parts.extend([
        "---",
        "",
        "## Already filed (autonomously, not part of this gate)",
        "",
        "These were filed in the same audit run without requiring approval —",
        "they're tracked-work artifacts that can be reviewed and closed",
        "individually post-hoc.",
        "",
        f"**Docs-debt issues filed**: {debt_str}",
        "",
        f"**Missing-artifact issues filed**: {missing_str}",
        "",
        f"**Items requiring human review** (could not classify): {items_requiring_review}",
        "",
        "---",
        "",
        "## Decision",
        "",
        "Apply ONE label to record your decision:",
        "",
        (
            f"- **`audit-approve`** — Apply all proposed edits, commit atomically "
            f"with the audit-issue reference, post the audit summary on "
            f"#{audit_issue}, close both this issue and #{audit_issue}."
        ),
        (
            "- **`audit-reject`** — Do NOT commit. Each proposed edit becomes its "
            "own `docs-debt` issue (with the proposed before/after preserved as "
            "evidence). Close both this issue and #" + str(audit_issue) + "."
        ),
        (
            "- **`audit-skip`** — Close both this issue and "
            f"#{audit_issue} with a skip note. No commit, no demotion, no "
            "further debt issues."
        ),
        "",
        "The agent picks up the decision on its next cron tick (every 60 minutes).",
        "No timeout — this issue stays open until you decide.",
        "",
        "---",
        "",
        "*Filed by `felix-doc-auditor:sonnet` (skill v1.2.0+).*",
    ])
    return "\n".join(parts) + "\n"


def _run_gh_issue_create(
    gh_bin: str,
    title: str,
    labels: list[str],
    body: str,
) -> subprocess.CompletedProcess[str]:
    cmd = [
        gh_bin,
        "issue",
        "create",
        "--repo",
        "kentonium3/kg-automation",
        "--title",
        title,
        "--label",
        ",".join(labels),
        "--body",
        body,
    ]
    return subprocess.run(cmd, capture_output=True, text=True)


_ISSUE_NUMBER_RE = re.compile(r"/issues/(\d+)")


def _parse_issue_number(stdout: str) -> int | None:
    match = _ISSUE_NUMBER_RE.search(stdout or "")
    if not match:
        return None
    try:
        return int(match.group(1))
    except ValueError:  # pragma: no cover
        return None


def _build_summary_body(
    applied: list[dict[str, Any]],
    gated: list[dict[str, Any]],
    pending_approval_issue: int | None,
    debt_issues: list[int],
    missing_issues: list[int],
) -> str:
    parts = ["## Audit summary (auto-routing)", ""]
    if applied:
        parts.append("**Applied edits (auto-routed):**")
        for p in applied:
            parts.append(
                f"- `{p['doc_path']}`: {p['change_type']} "
                f"({p['current_value']} -> {p['proposed_value']})"
            )
    else:
        parts.append("**Applied edits (auto-routed):** _(none)_")
    parts.append("")
    if gated:
        parts.append(
            f"**Gated edits (pending approval at "
            f"{('#' + str(pending_approval_issue)) if pending_approval_issue else '_unfiled_'}):**"
        )
        for p in gated:
            parts.append(
                f"- `{p['doc_path']}`: {p['change_type']} "
                f"({p['current_value']} -> {p['proposed_value']})"
            )
    else:
        parts.append("**Gated edits:** _(none)_")
    parts.append("")
    parts.append(
        "**Docs-debt issues filed**: "
        + (", ".join(f"#{n}" for n in debt_issues) if debt_issues else "_(none)_")
    )
    parts.append(
        "**Missing-artifact issues filed**: "
        + (", ".join(f"#{n}" for n in missing_issues) if missing_issues else "_(none)_")
    )
    parts.extend([
        "",
        "---",
        "*Posted by felix-doc-auditor:sonnet via `handle_audit_routing.py`.*",
    ])
    return "\n".join(parts) + "\n"


def _run_gh_issue_comment(
    gh_bin: str,
    issue_number: int,
    body: str,
) -> subprocess.CompletedProcess[str]:
    cmd = [
        gh_bin,
        "issue",
        "comment",
        str(issue_number),
        "--repo",
        "kentonium3/kg-automation",
        "--body",
        body,
    ]
    return subprocess.run(cmd, capture_output=True, text=True)


def _run_gh_issue_close(
    gh_bin: str,
    issue_number: int,
) -> subprocess.CompletedProcess[str]:
    cmd = [
        gh_bin,
        "issue",
        "close",
        str(issue_number),
        "--repo",
        "kentonium3/kg-automation",
    ]
    return subprocess.run(cmd, capture_output=True, text=True)


# ---------------------------------------------------------------------------
# Main flow
# ---------------------------------------------------------------------------


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Route felix-doc-auditor proposals: auto-apply known change_types, gate the rest.",
    )
    parser.add_argument(
        "state",
        help="Path to the audit-state JSON file. Optional leading `@` is accepted.",
    )
    parser.add_argument(
        "--git-bin",
        default=os.environ.get("GIT_BIN", "git"),
        help="git binary (override for tests). Defaults to GIT_BIN env or `git`.",
    )
    parser.add_argument(
        "--gh-bin",
        default=os.environ.get("GH_BIN", "gh"),
        help="gh binary (override for tests). Defaults to GH_BIN env or `gh`.",
    )
    parser.add_argument(
        "--repo-root",
        default=os.environ.get("REPO_ROOT"),
        help="Repository root (override for tests). Defaults to git rev-parse.",
    )
    args = parser.parse_args(argv)

    # ---------------- 1. Load + validate JSON --------------------------
    state_path = _resolve_state_path(args.state)
    try:
        state = _load_state(state_path)
    except InputValidationError as exc:
        print(f"ERROR: input validation: {exc}", file=sys.stderr)
        return 1

    audit_issue = state["audit_issue_number"]
    commit_sha = state["commit_sha"]
    areas = list(state["areas"])
    proposals = list(state["proposals"])
    debt_issues = [int(n) for n in state["debt_issues_filed"]]
    missing_issues = [int(n) for n in state["missing_artifact_issues_filed"]]

    # ---------------- 2. Empty short-circuit ---------------------------
    if not proposals:
        print("INFO: no proposals; exiting cleanly.", file=sys.stderr)
        return 0

    # ---------------- 3. Resolve repo root -----------------------------
    if args.repo_root:
        repo_root = Path(args.repo_root).resolve()
    else:
        try:
            res = subprocess.run(
                [args.git_bin, "rev-parse", "--show-toplevel"],
                capture_output=True,
                text=True,
                check=True,
            )
            repo_root = Path(res.stdout.strip()).resolve()
        except (OSError, subprocess.CalledProcessError) as exc:
            print(f"ERROR: could not resolve repo root: {exc}", file=sys.stderr)
            return 1

    # ---------------- 4. Partition -------------------------------------
    auto_apply, gated = _partition(proposals)
    print(
        f"INFO: partition: {len(auto_apply)} auto_apply, {len(gated)} gated",
        file=sys.stderr,
    )

    # ---------------- 5. Apply auto_apply edits ------------------------
    written: list[Path] = []
    apply_failed_proposal: dict[str, Any] | None = None
    apply_failure_reason: str | None = None
    for proposal in auto_apply:
        try:
            path = _apply_one(repo_root, proposal)
            written.append(path)
        except RouteApplyError as exc:
            apply_failed_proposal = exc.proposal
            apply_failure_reason = exc.reason
            break

    if apply_failed_proposal is not None:
        # Rollback any partial writes; do NOT commit; do NOT gate.
        _rollback(repo_root, written, args.git_bin)
        print(
            "ERROR: apply failure: "
            f"doc={apply_failed_proposal.get('doc_path')!r} "
            f"change_type={apply_failed_proposal.get('change_type')!r} "
            f"reason={apply_failure_reason!r}",
            file=sys.stderr,
        )
        return 2

    # ---------------- 6. Commit (only if anything applied) -------------
    if auto_apply:
        commit_result = _run_git_commit(
            repo_root,
            args.git_bin,
            auto_apply,
            audit_issue,
            commit_sha,
        )
        if commit_result.returncode != 0:
            # Subprocess sequencing invariant: gate-file MUST NOT run
            # after a commit failure. Don't half-do.
            print(
                "ERROR: git commit failed (rc="
                f"{commit_result.returncode}); "
                f"stdout={commit_result.stdout.strip()!r} "
                f"stderr={commit_result.stderr.strip()!r}",
                file=sys.stderr,
            )
            return 3

    # ---------------- 7. Gate-file pending-approval (if gated) ---------
    pending_approval_issue: int | None = None
    if gated:
        gate_labels = ["audit-pending-approval"]
        gate_labels.extend(a for a in areas if a.startswith("area/"))
        gate_title = (
            f"Audit #{audit_issue}: pending approval — "
            f"{len(gated)} proposed edit(s)"
        )
        gate_body = _build_pending_approval_body(
            audit_issue=audit_issue,
            commit_sha=commit_sha,
            areas=areas,
            gated=gated,
            debt_issues=debt_issues,
            missing_issues=missing_issues,
        )
        gate_result = _run_gh_issue_create(
            args.gh_bin,
            gate_title,
            gate_labels,
            gate_body,
        )
        if gate_result.returncode != 0:
            print(
                "ERROR: gate-file (gh issue create) failed (rc="
                f"{gate_result.returncode}); "
                f"stdout={gate_result.stdout.strip()!r} "
                f"stderr={gate_result.stderr.strip()!r}",
                file=sys.stderr,
            )
            # Best-effort summary so the system isn't completely silent.
            summary_body = _build_summary_body(
                applied=auto_apply,
                gated=gated,
                pending_approval_issue=None,
                debt_issues=debt_issues,
                missing_issues=missing_issues,
            )
            _run_gh_issue_comment(args.gh_bin, audit_issue, summary_body)
            return 4
        pending_approval_issue = _parse_issue_number(gate_result.stdout)
        if pending_approval_issue is None:
            print(
                "WARN: could not parse new issue number from gh output: "
                f"{gate_result.stdout.strip()!r}",
                file=sys.stderr,
            )

    # ---------------- 8. Post audit summary on originating issue -------
    summary_body = _build_summary_body(
        applied=auto_apply,
        gated=gated,
        pending_approval_issue=pending_approval_issue,
        debt_issues=debt_issues,
        missing_issues=missing_issues,
    )
    summary_result = _run_gh_issue_comment(
        args.gh_bin,
        audit_issue,
        summary_body,
    )
    if summary_result.returncode != 0:
        print(
            "ERROR: summary-post (gh issue comment) failed (rc="
            f"{summary_result.returncode}); "
            f"stdout={summary_result.stdout.strip()!r} "
            f"stderr={summary_result.stderr.strip()!r}",
            file=sys.stderr,
        )
        return 5

    # ---------------- 9. Close originating audit (only if no gate) ----
    if not gated:
        close_result = _run_gh_issue_close(args.gh_bin, audit_issue)
        if close_result.returncode != 0:
            # Closing the audit is best-effort; the gate-file path is
            # the load-bearing state-transition. Treat close failures
            # as a summary-post-style non-fatal but report.
            print(
                "WARN: closing the audit issue failed (rc="
                f"{close_result.returncode}); "
                f"stdout={close_result.stdout.strip()!r} "
                f"stderr={close_result.stderr.strip()!r}",
                file=sys.stderr,
            )

    return 0


if __name__ == "__main__":  # pragma: no cover
    sys.exit(main())
