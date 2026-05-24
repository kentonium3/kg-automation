#!/usr/bin/env python3
"""Forward-path audit decision orchestrator for felix-doc-auditor.

Importable surface (per mission #343 WP01 lift):
    from doc_audit.helpers.handle_audit_routing import (
        route_audit_decision,   # library entry point — see RoutingResult
        RoutingResult,
        InputValidationError,
        RouteApplyError,
        AUTO_APPLY_CHANGE_TYPES,
    )

    Set ``PYTHONPATH=scripts/`` so the ``doc_audit`` package is on the
    import path. The CLI ``main()`` is now a thin argparse wrapper that
    delegates to ``route_audit_decision`` — both surfaces share the
    same code.

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
import logging
import os
import re
import stat
import subprocess
import sys
import tempfile
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional


logger = logging.getLogger(__name__)

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
# Library result type
# ---------------------------------------------------------------------------


@dataclass
class RoutingResult:
    """Structured result from :func:`route_audit_decision`.

    Mirrors the side-effects the CLI orchestration produces so library
    callers can act on the outcome without re-parsing stderr. The
    ``exit_code`` field carries the same exit-code semantics the CLI
    documents (0=success, 1=input-validation, 2=apply, 3=commit,
    4=gate-file, 5=summary-post).
    """

    applied_count: int = 0
    gated: bool = False
    pending_approval_issue: int | None = None
    debt_issues: list[int] = field(default_factory=list)
    missing_issues: list[int] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)
    exit_code: int = 0


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


def _run_gh_issue_remove_label(
    gh_bin: str,
    issue_number: int,
    label: str,
) -> subprocess.CompletedProcess[str]:
    cmd = [
        gh_bin,
        "issue",
        "edit",
        str(issue_number),
        "--repo",
        "kentonium3/kg-automation",
        "--remove-label",
        label,
    ]
    return subprocess.run(cmd, capture_output=True, text=True)


_NO_PROPOSALS_COMMENT = (
    "**Driver: no automatable edits found.**\n\n"
    "The post-#343 doc-audit driver scanned this commit's diff and found "
    "no deterministically-classifiable edits (frontmatter date bumps, "
    "service version bumps, file path renames, etc.). The `status:in-progress` "
    "lock has been released.\n\n"
    "This audit's checklist items in the issue body still require "
    "**manual operator review**. Close this issue once the checklist is "
    "verified (or apply `audit-skip` to acknowledge no docs need updates).\n"
)


# ---------------------------------------------------------------------------
# audit_interpretation Moment 0 wiring (mission #400)
# ---------------------------------------------------------------------------
#
# When ``[audit_interpretation].enabled`` is True AND the audit carries a
# ``commit_sha``, the no-proposals branch builds an
# ``AuditInterpretationContext`` (audit + diff + in-scope docs) and calls
# ``interpret_audit``. Each per-doc verdict routes per spec:
#   - PROPOSED_EDIT (conf ≥0.80)  → tier_classification → auto-commit /
#                                   PR / DebtIssue (existing helpers)
#   - JUDGMENT_REQUIRED           → accumulate into a SINGLE consolidated
#                                   comment per audit (research D3)
#   - NO_CHANGE_NEEDED            → ledger entry only; if ALL clean, the
#                                   audit auto-closes with a summary
# DriftInterpretationError (retry exhausted) and the disabled-config /
# weekly-audit case fall through to the existing fallback path (release
# the status:in-progress lock + post the generic "no automatable edits"
# comment) so today's behavior is preserved.


def _audit_interpretation_enabled(config: Optional[Any]) -> bool:
    """Return True when the audit_interpretation Moment 0 path is enabled.

    The config object is read defensively via ``getattr`` so callers
    that haven't yet added the ``[audit_interpretation]`` block to
    ``Config`` (WP03 ships it) keep the disabled-by-default behavior.
    """
    if config is None:
        return False
    block = getattr(config, "audit_interpretation", None)
    if block is None:
        return False
    return bool(getattr(block, "enabled", False))


def _load_config_lazy() -> Optional[Any]:
    """Best-effort load of the driver Config.

    Returns ``None`` on any failure — callers fall through to the
    fallback path when the config can't be loaded. Never raises.
    """
    try:
        from doc_audit.config import load_config
    except Exception as exc:  # pragma: no cover - defensive
        logger.info(
            "audit_interpretation: could not import doc_audit.config (%s); "
            "falling back",
            type(exc).__name__,
        )
        return None
    try:
        return load_config()
    except Exception as exc:
        logger.info(
            "audit_interpretation: load_config failed (%s); falling back",
            type(exc).__name__,
        )
        return None


def _fetch_diff_for_commit(
    commit_sha: str,
    repo_root: Path,
    git_bin: str,
) -> str:
    """Best-effort ``git show <sha>`` for the audit's triggering commit.

    Mirror of ``doc_audit.run._fetch_diff_for_sha`` so the routing
    helper can re-derive the diff without coupling to ``run``.
    Returns ``""`` on any failure — callers treat that as "no diff"
    and fall through to the fallback path (the diff is load-bearing
    for the LLM judgment).
    """
    if not commit_sha:
        return ""
    try:
        completed = subprocess.run(
            [git_bin, "show", "--stat", "--patch", commit_sha],
            cwd=str(repo_root),
            capture_output=True,
            text=True,
            check=True,
            timeout=10,
        )
    except Exception as exc:  # noqa: BLE001 — non-essential enrichment
        logger.info(
            "audit_interpretation: git show %s unavailable (%s); "
            "proceeding with empty diff",
            commit_sha,
            type(exc).__name__,
        )
        return ""
    return completed.stdout or ""


def _load_doc_domain_map_path(map_path: Path) -> dict[str, list[str]]:
    """Load ``doc-domain-map.json`` from an absolute path.

    Mirror of ``doc_audit.run._load_doc_domain_map`` but keyed off an
    explicit path so the routing helper does not need to thread the
    full :class:`Config` through every call. Returns the ``domains``
    sub-dict (label → list[doc-path]). Missing or malformed file
    yields an empty dict.
    """
    try:
        raw = map_path.read_text(encoding="utf-8")
    except FileNotFoundError:
        logger.info(
            "audit_interpretation: doc-domain-map not found at %s; "
            "in-scope docs empty",
            map_path,
        )
        return {}
    except OSError as exc:
        logger.info(
            "audit_interpretation: doc-domain-map at %s unreadable (%s); "
            "in-scope docs empty",
            map_path,
            exc,
        )
        return {}
    try:
        parsed = json.loads(raw or "{}")
    except json.JSONDecodeError as exc:
        logger.info(
            "audit_interpretation: doc-domain-map at %s is not valid "
            "JSON (%s); in-scope docs empty",
            map_path,
            exc,
        )
        return {}
    if not isinstance(parsed, dict):
        return {}
    domains = parsed.get("domains")
    if not isinstance(domains, dict):
        return {}
    normalized: dict[str, list[str]] = {}
    for label, paths in domains.items():
        if isinstance(label, str) and isinstance(paths, list):
            normalized[label] = [p for p in paths if isinstance(p, str) and p]
    return normalized


def _resolve_in_scope_docs_from_areas(
    areas: list[str],
    domain_map: dict[str, list[str]],
) -> list[str]:
    """Intersect ``areas`` with the doc-domain map (order-preserving).

    Mirror of ``doc_audit.run._resolve_in_scope_docs`` but takes the
    raw areas list rather than an ``AuditIssue``.
    """
    if not domain_map:
        return []
    seen: set[str] = set()
    out: list[str] = []
    if not areas:
        for label_paths in domain_map.values():
            for path in label_paths:
                if path not in seen:
                    seen.add(path)
                    out.append(path)
        return out
    for label in areas:
        for path in domain_map.get(label, []):
            if path not in seen:
                seen.add(path)
                out.append(path)
    return out


def _build_doc_targets(
    in_scope_docs: list[str],
    diff: str,
    repo_root: Path,
) -> list[Any]:
    """Build a list of ``DocTarget`` from in-scope doc paths.

    Reads each doc's current contents from ``repo_root``, applies the
    D2 truncation strategy from :mod:`doc_audit.judgment.drift_interpretation`,
    and returns a parallel list of ``DocTarget`` dataclasses. Missing
    or unreadable docs are skipped with a warning (the LLM has nothing
    useful to evaluate without contents).
    """
    from doc_audit.judgment.drift_interpretation import (
        DocTarget,
        _truncate_doc_state,
    )

    targets: list[Any] = []
    for rel_path in in_scope_docs:
        abs_path = repo_root / rel_path
        try:
            raw = abs_path.read_text(encoding="utf-8")
        except FileNotFoundError:
            logger.info(
                "audit_interpretation: in-scope doc %s not found; "
                "skipping from LLM evaluation",
                rel_path,
            )
            continue
        except OSError as exc:
            logger.info(
                "audit_interpretation: in-scope doc %s unreadable (%s); "
                "skipping from LLM evaluation",
                rel_path,
                exc,
            )
            continue
        contents, was_truncated, strategy = _truncate_doc_state(raw, diff)
        targets.append(
            DocTarget(
                path=rel_path,
                contents=contents,
                truncated=was_truncated,
                truncation_strategy=strategy,
            )
        )
    return targets


def _now_utc_iso() -> str:
    """Return the current UTC time as an ISO 8601 ``Z``-suffixed string."""
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _append_audit_ledger_entry_safe(
    *,
    audit_issue: int,
    doc_path: str,
    commit_sha: str,
    verdict: str,
    confidence: Optional[float],
    outcome: str,
    ledger_path: Optional[Path] = None,
) -> None:
    """Append one ``AuditLedgerEntry`` (best-effort, never raises).

    Mirrors ``drift_moment0._append_ledger_entry``'s failure
    semantics: a ledger-write failure does NOT undo a completed side
    effect; the error is logged to stderr but execution continues.
    """
    from doc_audit.output.audit_ledger import (
        AuditLedgerEntry,
        DEFAULT_LEDGER_PATH,
        append as audit_ledger_append,
    )

    entry = AuditLedgerEntry(
        audit_issue=audit_issue,
        doc_path=doc_path,
        timestamp_utc=_now_utc_iso(),
        commit_sha=commit_sha or "unknown",
        verdict=verdict,
        confidence=confidence,
        outcome=outcome,
    )
    try:
        audit_ledger_append(
            entry, ledger_path=ledger_path or DEFAULT_LEDGER_PATH
        )
    except (OSError, ValueError) as exc:
        logger.error(
            "audit_interpretation: ledger append failed for audit #%d "
            "doc=%s (%s); side-effect already completed, continuing",
            audit_issue,
            doc_path,
            exc,
        )


def _build_audit_derived_proposed_edit(
    verdict: Any,
    commit_sha: str,
) -> Any:
    """Translate a PROPOSED_EDIT verdict into a ``ProposedEdit`` dataclass.

    Mirrors :func:`doc_audit.routing.drift_to_proposed_edit.build` but
    inlined here because the audit path has its own ``evidence_source``
    string and uses ``change_type="audit_derived"`` (per data_model.py
    docstring).
    """
    from doc_audit.data_model import ProposedEdit

    proposed = verdict.proposed_edit or {}
    return ProposedEdit(
        doc_path=verdict.doc_path,
        change_type="audit_derived",
        current_value=str(proposed.get("current_value", "")),
        proposed_value=str(proposed.get("proposed_value", "")),
        evidence_source=f"audit-commit:{commit_sha}",
        tier="tier_b",  # placeholder; tier_classification reassigns
        confidence="high",
    )


def _apply_audit_derived_tier_a(
    proposed_edit: Any,
    repo_root: Path,
    audit_issue: int,
    commit_sha: str,
    git_bin: str,
) -> tuple[bool, str]:
    """Apply a Tier A audit-derived edit and commit it.

    Mirror of ``drift_moment0._apply_tier_a_edit`` but commits with an
    audit-aware message. Tries the sequence of safe appliers
    (version_bump, frontmatter_date, path_rename) — whichever produces
    a successful substitution wins. Returns ``(success, message)``.
    """
    doc_path = repo_root / proposed_edit.doc_path
    if not doc_path.exists():
        return False, f"doc not found: {doc_path}"
    try:
        content = doc_path.read_text(encoding="utf-8")
    except OSError as exc:
        return False, f"doc unreadable: {exc}"

    proposal_dict = {
        "doc_path": proposed_edit.doc_path,
        "change_type": proposed_edit.change_type,
        "current_value": proposed_edit.current_value,
        "proposed_value": proposed_edit.proposed_value,
        "evidence_source": proposed_edit.evidence_source,
        "confidence": proposed_edit.confidence,
    }

    last_error: Optional[str] = None
    new_content: Optional[str] = None
    for applier_name in ("version_bump", "frontmatter_date", "path_rename"):
        applier = APPLIERS.get(applier_name)
        if applier is None:  # pragma: no cover
            continue
        try:
            new_content = applier(content, proposal_dict)
            break
        except RouteApplyError as exc:
            last_error = exc.reason
            continue

    if new_content is None or new_content == content:
        return (
            False,
            f"no applier produced a change: {last_error or 'unknown'}",
        )

    try:
        _atomic_write(doc_path, new_content)
    except OSError as exc:
        return False, f"atomic write failed: {exc}"

    subject = (
        f"docs(audit): apply audit_derived edit from audit #{audit_issue}"
    )
    body = (
        f"\nTriggered by audit #{audit_issue} (commit {commit_sha}).\n"
        f"Auto-applied via Moment 0 (audit_interpretation) Tier A.\n\n"
        f"- {proposed_edit.doc_path}: "
        f"{proposed_edit.current_value!r} -> {proposed_edit.proposed_value!r}\n\n"
        f"Evidence: {proposed_edit.evidence_source}\n"
    )
    commit_message = subject + "\n" + body
    try:
        add_res = subprocess.run(
            [git_bin, "add", "--", proposed_edit.doc_path],
            cwd=str(repo_root),
            capture_output=True,
            text=True,
        )
        if add_res.returncode != 0:
            return False, f"git add failed: {(add_res.stderr or '').strip()}"
        commit_res = subprocess.run(
            [git_bin, "commit", "-m", commit_message],
            cwd=str(repo_root),
            capture_output=True,
            text=True,
        )
        if commit_res.returncode != 0:
            return False, (
                f"git commit failed: {(commit_res.stderr or '').strip()}"
            )
    except OSError as exc:
        return False, f"git invocation failed: {exc}"

    return True, f"applied + committed {proposed_edit.doc_path}"


def _file_audit_derived_tier_b_pending_approval(
    proposed_edit: Any,
    audit_issue: int,
    commit_sha: str,
    areas: list[str],
    gh_bin: str,
) -> tuple[bool, Optional[int], str]:
    """File a Tier B pending-approval issue for an audit-derived edit.

    Reuses :func:`_run_gh_issue_create` so the gh-bin override path is
    consistent with the rest of the helper. Returns
    ``(success, issue_number_or_None, message)``.
    """
    title = (
        f"Audit #{audit_issue}: pending approval — audit_derived "
        f"edit to {proposed_edit.doc_path}"
    )
    labels = ["audit-pending-approval"]
    labels.extend(a for a in areas if a.startswith("area/"))
    body = (
        "## Tier B pending approval (audit_interpretation Moment 0)\n\n"
        "An audit-derived proposed edit reached Tier B and needs "
        "operator approval before landing.\n\n"
        f"**Originating audit**: #{audit_issue}\n"
        f"**Triggering commit**: `{commit_sha}`\n"
        f"**Doc target**: `{proposed_edit.doc_path}`\n"
        f"**Change type**: `{proposed_edit.change_type}`\n"
        f"**Evidence**: {proposed_edit.evidence_source}\n\n"
        "### Diff\n\n"
        "```diff\n"
        f"- {proposed_edit.current_value}\n"
        f"+ {proposed_edit.proposed_value}\n"
        "```\n\n"
        "## Auto-generated\n\n"
        "Filed by `handle_audit_routing.py` (mission #400 Moment 0).\n"
    )
    result = _run_gh_issue_create(gh_bin, title, labels, body)
    if result.returncode != 0:
        return False, None, f"gh issue create failed: {(result.stderr or '').strip()}"
    return True, _parse_issue_number(result.stdout or ""), "filed"


def _file_audit_derived_debt_issue(
    proposed_edit: Any,
    audit_issue: int,
    commit_sha: str,
    rationale: str,
    areas: list[str],
    gh_bin: str,
) -> tuple[bool, Optional[int], str]:
    """File a docs-debt issue for a judgment-routed audit_derived edit."""
    title = (
        f"Docs: audit-derived judgment for {proposed_edit.doc_path} "
        f"(audit #{audit_issue})"
    )
    labels = ["docs-debt"]
    labels.extend(a for a in areas if a.startswith("area/"))
    body = (
        "## Audit-derived edit needs judgment\n\n"
        "Moment 1 ``tier_classification`` routed this audit-derived "
        "proposed edit to ``JUDGMENT`` — the operator should review the "
        "proposed diff and decide.\n\n"
        f"**Originating audit**: #{audit_issue}\n"
        f"**Triggering commit**: `{commit_sha}`\n"
        f"**Doc target**: `{proposed_edit.doc_path}`\n"
        f"**Evidence**: {proposed_edit.evidence_source}\n\n"
        "### Proposed diff\n\n"
        "```diff\n"
        f"- {proposed_edit.current_value}\n"
        f"+ {proposed_edit.proposed_value}\n"
        "```\n\n"
        "### Moment 1 rationale\n\n"
        f"{rationale}\n\n"
        "## Auto-generated\n\n"
        "Filed by `handle_audit_routing.py` (mission #400 Moment 0).\n"
    )
    result = _run_gh_issue_create(gh_bin, title, labels, body)
    if result.returncode != 0:
        return False, None, f"gh issue create failed: {(result.stderr or '').strip()}"
    return True, _parse_issue_number(result.stdout or ""), "filed"


def _build_consolidated_judgment_comment(
    judgment_items: list[tuple[str, str]],
    clean_docs: list[str],
) -> str:
    """Render the single consolidated JUDGMENT_REQUIRED comment (D3).

    ``judgment_items`` is a list of ``(doc_path, question)`` tuples.
    ``clean_docs`` is the parallel list of NO_CHANGE_NEEDED docs (may
    be empty). Format mirrors research.md D3.
    """
    total = len(judgment_items) + len(clean_docs)
    header = (
        f"**Driver: {len(judgment_items)} of {total} doc(s) need your "
        "judgment**"
        if total
        else "**Driver: judgment required**"
    )
    parts = [header, ""]
    for doc_path, question in judgment_items:
        parts.append(f"- `{doc_path}`: {question}")
    if clean_docs:
        joined = ", ".join(f"`{p}`" for p in clean_docs)
        parts.extend(
            [
                "",
                f"Other docs evaluated as no change needed: {joined}.",
            ]
        )
    parts.extend(
        [
            "",
            "---",
            "*Posted by `handle_audit_routing.py` "
            "(mission #400 Moment 0).*",
        ]
    )
    return "\n".join(parts) + "\n"


def _build_audit_auto_close_comment(clean_docs: list[str]) -> str:
    """Render the auto-close summary comment (all docs NO_CHANGE_NEEDED)."""
    if clean_docs:
        bullets = "\n".join(f"- `{p}`" for p in clean_docs)
    else:
        bullets = "_(no in-scope docs evaluated)_"
    return (
        "**Driver: audit auto-closed — no doc updates needed.**\n\n"
        "The audit_interpretation Moment 0 LLM evaluated each in-scope "
        "doc against the commit diff and returned NO_CHANGE_NEEDED for "
        "all of them. Closing the audit.\n\n"
        "Docs evaluated as clean:\n"
        f"{bullets}\n\n"
        "---\n"
        "*Posted by `handle_audit_routing.py` "
        "(mission #400 Moment 0).*\n"
    )


def _release_in_progress_lock(gh_bin: str, audit_issue: int) -> None:
    """Best-effort release of the ``status:in-progress`` label."""
    proc = _run_gh_issue_remove_label(gh_bin, audit_issue, "status:in-progress")
    if proc.returncode != 0:
        print(
            f"WARN: audit_interpretation label removal failed for "
            f"#{audit_issue}: rc={proc.returncode} "
            f"stderr={(proc.stderr or '').strip()!r}",
            file=sys.stderr,
        )


def _post_fallback_no_proposals(
    gh_bin: str,
    audit_issue: int,
) -> None:
    """Run today's no-proposals behavior: comment + lock release.

    Preserved verbatim from the pre-#400 commit ``bf17c3cf`` so the
    fallback path stays operator-visibly identical when
    audit_interpretation is disabled or retries exhaust.
    """
    comment_proc = _run_gh_issue_comment(
        gh_bin, audit_issue, _NO_PROPOSALS_COMMENT,
    )
    if comment_proc.returncode != 0:
        print(
            f"WARN: no-proposals comment post failed for #{audit_issue}: "
            f"rc={comment_proc.returncode} "
            f"stderr={(comment_proc.stderr or '').strip()!r}",
            file=sys.stderr,
        )
    _release_in_progress_lock(gh_bin, audit_issue)


def _audit_interpretation_ledger_path(config: Optional[Any]) -> Optional[Path]:
    """Resolve the audit-events ledger path from config (if available).

    WP03 may add an explicit ``[audit_interpretation].ledger_path``
    field. Until then we use the dataclass default. ``None`` lets the
    ledger module pick :data:`DEFAULT_LEDGER_PATH`.
    """
    if config is None:
        return None
    block = getattr(config, "audit_interpretation", None)
    if block is None:
        return None
    raw = getattr(block, "ledger_path", None)
    if isinstance(raw, str) and raw:
        return Path(raw)
    return None


def _run_audit_interpretation_flow(
    *,
    audit_issue: int,
    commit_sha: str,
    areas: list[str],
    repo_root: Path,
    git_bin: str,
    gh_bin: str,
    config: Any,
    client_factory: Optional[Any] = None,
    interpret_audit_fn: Optional[Any] = None,
    tier_classify_fn: Optional[Any] = None,
) -> bool:
    """Run the audit_interpretation Moment 0 path for one audit.

    Returns ``True`` when the flow handled the audit (verdicts
    dispatched + ledger written + side effects posted + lock released).
    Returns ``False`` when the caller should fall through to the
    today-merged fallback path (retry exhausted, missing diff, no
    in-scope docs after resolution, or any internal error that means
    we couldn't produce verdicts).

    Args (all keyword-only):
        audit_issue: GH issue number for the originating audit.
        commit_sha: triggering commit SHA (non-empty — weekly audits
            skip Moment 0 per C-006 BEFORE this is invoked).
        areas: ``area/*`` labels from the audit state.
        repo_root: repository checkout root.
        git_bin / gh_bin: subprocess binary overrides.
        config: driver :class:`Config` (must have
            ``audit_interpretation.enabled = True`` — caller gates).
        client_factory: callable returning a ``JudgmentClient`` (for
            test injection). Defaults to constructing one from config.
        interpret_audit_fn: callable matching
            :func:`doc_audit.judgment.audit_interpretation.interpret_audit`
            (for test injection).
        tier_classify_fn: callable matching
            :func:`doc_audit.judgment.tier_classification.classify`
            (for test injection).
    """
    # Lazy imports so the disabled-config path never needs the
    # anthropic SDK (NFR-007 mirror of #362's contract).
    from doc_audit.judgment.audit_interpretation import (
        AuditInterpretationContext,
        interpret_audit as _default_interpret_audit,
    )
    from doc_audit.judgment.drift_interpretation import DriftInterpretationError
    from doc_audit.judgment import tier_classification as _tier_classification_module

    interpret_audit_fn = interpret_audit_fn or _default_interpret_audit
    tier_classify_fn = tier_classify_fn or _tier_classification_module.classify

    diff = _fetch_diff_for_commit(commit_sha, repo_root, git_bin)
    if not diff:
        logger.info(
            "audit_interpretation: empty diff for commit %s; falling back",
            commit_sha,
        )
        return False

    domain_map_path = Path(config.paths.doc_domain_map)
    domain_map = _load_doc_domain_map_path(domain_map_path)
    in_scope_docs = _resolve_in_scope_docs_from_areas(areas, domain_map)
    if not in_scope_docs:
        logger.info(
            "audit_interpretation: no in-scope docs for areas=%s; falling back",
            areas,
        )
        return False

    doc_targets = _build_doc_targets(in_scope_docs, diff, repo_root)
    if not doc_targets:
        logger.info(
            "audit_interpretation: no readable in-scope docs; falling back",
        )
        return False

    context = AuditInterpretationContext(
        audit_issue=audit_issue,
        commit_sha=commit_sha,
        diff=diff,
        in_scope_docs=doc_targets,
    )

    # Build a JudgmentClient lazily (mirror drift_moment0._build_judgment_client).
    if client_factory is None:
        def _default_client_factory() -> Any:
            from doc_audit.judgment.client import JudgmentClient
            return JudgmentClient(config)
        client_factory = _default_client_factory
    try:
        client = client_factory()
    except Exception as exc:
        logger.warning(
            "audit_interpretation: JudgmentClient construction failed "
            "(%s); falling back",
            exc,
        )
        return False

    ledger_path = _audit_interpretation_ledger_path(config)

    try:
        verdicts = interpret_audit_fn(client, context)
    except DriftInterpretationError as exc:
        # Retry exhausted for at least one doc (interpret_audit catches
        # per-doc internally, so reaching here means a non-recoverable
        # error). Record RETRY_EXHAUSTED ledger row PER doc, then fall
        # back to the today's no-proposals path.
        logger.warning(
            "audit_interpretation: interpret_audit raised "
            "DriftInterpretationError (%s); recording RETRY_EXHAUSTED "
            "per doc and falling back",
            exc,
        )
        for target in doc_targets:
            _append_audit_ledger_entry_safe(
                audit_issue=audit_issue,
                doc_path=target.path,
                commit_sha=commit_sha,
                verdict="RETRY_EXHAUSTED",
                confidence=None,
                outcome="retry_exhausted",
                ledger_path=ledger_path,
            )
        return False
    except Exception as exc:  # pragma: no cover - defensive
        logger.warning(
            "audit_interpretation: interpret_audit raised unexpected %s "
            "(%s); falling back",
            type(exc).__name__,
            exc,
        )
        return False

    # ------------------------------------------------------------------
    # Verdict dispatch (per spec FR-004/006/007/008)
    # ------------------------------------------------------------------
    judgment_items: list[tuple[str, str]] = []
    clean_docs: list[str] = []
    any_proposed_edit = False

    for verdict in verdicts:
        if verdict.verdict == "NO_CHANGE_NEEDED":
            clean_docs.append(verdict.doc_path)
            _append_audit_ledger_entry_safe(
                audit_issue=audit_issue,
                doc_path=verdict.doc_path,
                commit_sha=commit_sha,
                verdict="NO_CHANGE_NEEDED",
                confidence=float(verdict.confidence),
                outcome="auto_closed",
                ledger_path=ledger_path,
            )
            continue

        if verdict.verdict == "JUDGMENT_REQUIRED":
            question = verdict.question or "Please review this doc."
            judgment_items.append((verdict.doc_path, question))
            _append_audit_ledger_entry_safe(
                audit_issue=audit_issue,
                doc_path=verdict.doc_path,
                commit_sha=commit_sha,
                verdict="JUDGMENT_REQUIRED",
                confidence=float(verdict.confidence),
                outcome="judgment_required_posted",
                ledger_path=ledger_path,
            )
            continue

        # verdict.verdict == "PROPOSED_EDIT"
        any_proposed_edit = True
        proposed_edit = _build_audit_derived_proposed_edit(verdict, commit_sha)
        try:
            tier, tier_rationale, _resp = tier_classify_fn(
                client,
                proposed_edit,
                audit_area_labels=list(areas),
                doc_frontmatter_excerpt="",
                guardrail_check_result="not_guardrailed",
            )
        except Exception as exc:
            logger.warning(
                "audit_interpretation: tier_classification raised %s for "
                "%s; demoting to judgment debt issue",
                type(exc).__name__,
                verdict.doc_path,
            )
            _file_audit_derived_debt_issue(
                proposed_edit=proposed_edit,
                audit_issue=audit_issue,
                commit_sha=commit_sha,
                rationale=f"tier_classification error: {exc}",
                areas=areas,
                gh_bin=gh_bin,
            )
            _append_audit_ledger_entry_safe(
                audit_issue=audit_issue,
                doc_path=verdict.doc_path,
                commit_sha=commit_sha,
                verdict="PROPOSED_EDIT",
                confidence=float(verdict.confidence),
                outcome="issue_filed",
                ledger_path=ledger_path,
            )
            continue

        tier_value = getattr(tier, "value", None) or str(tier)
        if tier_value == "tier_a":
            ok, message = _apply_audit_derived_tier_a(
                proposed_edit=proposed_edit,
                repo_root=repo_root,
                audit_issue=audit_issue,
                commit_sha=commit_sha,
                git_bin=git_bin,
            )
            if ok:
                _append_audit_ledger_entry_safe(
                    audit_issue=audit_issue,
                    doc_path=verdict.doc_path,
                    commit_sha=commit_sha,
                    verdict="PROPOSED_EDIT",
                    confidence=float(verdict.confidence),
                    outcome="auto_committed",
                    ledger_path=ledger_path,
                )
            else:
                # Tier A apply failed → demote to a judgment debt issue
                # so the operator sees the proposed edit + the apply
                # error. Mirror of drift_moment0's same-leg behavior.
                logger.warning(
                    "audit_interpretation: Tier A apply failed for %s "
                    "(%s); demoting to debt issue",
                    verdict.doc_path,
                    message,
                )
                _file_audit_derived_debt_issue(
                    proposed_edit=proposed_edit,
                    audit_issue=audit_issue,
                    commit_sha=commit_sha,
                    rationale=(
                        f"Tier A auto-apply failed: {message}.\n\n"
                        f"tier_classification rationale: {tier_rationale}"
                    ),
                    areas=areas,
                    gh_bin=gh_bin,
                )
                _append_audit_ledger_entry_safe(
                    audit_issue=audit_issue,
                    doc_path=verdict.doc_path,
                    commit_sha=commit_sha,
                    verdict="PROPOSED_EDIT",
                    confidence=float(verdict.confidence),
                    outcome="issue_filed",
                    ledger_path=ledger_path,
                )
        elif tier_value == "tier_b":
            ok, issue_number, message = _file_audit_derived_tier_b_pending_approval(
                proposed_edit=proposed_edit,
                audit_issue=audit_issue,
                commit_sha=commit_sha,
                areas=areas,
                gh_bin=gh_bin,
            )
            _append_audit_ledger_entry_safe(
                audit_issue=audit_issue,
                doc_path=verdict.doc_path,
                commit_sha=commit_sha,
                verdict="PROPOSED_EDIT",
                confidence=float(verdict.confidence),
                outcome="pr_filed",
                ledger_path=ledger_path,
            )
            if not ok:
                logger.warning(
                    "audit_interpretation: Tier B pending-approval "
                    "file failed for %s: %s",
                    verdict.doc_path,
                    message,
                )
        else:
            # judgment (or anything unexpected) → debt issue
            _file_audit_derived_debt_issue(
                proposed_edit=proposed_edit,
                audit_issue=audit_issue,
                commit_sha=commit_sha,
                rationale=tier_rationale,
                areas=areas,
                gh_bin=gh_bin,
            )
            _append_audit_ledger_entry_safe(
                audit_issue=audit_issue,
                doc_path=verdict.doc_path,
                commit_sha=commit_sha,
                verdict="PROPOSED_EDIT",
                confidence=float(verdict.confidence),
                outcome="issue_filed",
                ledger_path=ledger_path,
            )

    # ------------------------------------------------------------------
    # Post-dispatch: consolidated comment + auto-close
    # ------------------------------------------------------------------
    if judgment_items:
        comment_body = _build_consolidated_judgment_comment(
            judgment_items, clean_docs
        )
        comment_proc = _run_gh_issue_comment(
            gh_bin, audit_issue, comment_body
        )
        if comment_proc.returncode != 0:
            print(
                "WARN: audit_interpretation consolidated judgment "
                f"comment post failed for #{audit_issue}: "
                f"rc={comment_proc.returncode} "
                f"stderr={(comment_proc.stderr or '').strip()!r}",
                file=sys.stderr,
            )

    all_no_change = (
        bool(clean_docs)
        and not judgment_items
        and not any_proposed_edit
    )
    if all_no_change:
        comment_proc = _run_gh_issue_comment(
            gh_bin, audit_issue, _build_audit_auto_close_comment(clean_docs)
        )
        if comment_proc.returncode != 0:
            print(
                "WARN: audit_interpretation auto-close summary comment "
                f"post failed for #{audit_issue}: "
                f"rc={comment_proc.returncode} "
                f"stderr={(comment_proc.stderr or '').strip()!r}",
                file=sys.stderr,
            )
        close_proc = _run_gh_issue_close(gh_bin, audit_issue)
        if close_proc.returncode != 0:
            print(
                "WARN: audit_interpretation auto-close failed for "
                f"#{audit_issue}: rc={close_proc.returncode} "
                f"stderr={(close_proc.stderr or '').strip()!r}",
                file=sys.stderr,
            )

    # Always release the lock at the end (mirror the existing best-effort
    # behavior). When the audit was auto-closed the close already removes
    # state from the operator queue, but releasing the lock is idempotent
    # and matches today's contract.
    _release_in_progress_lock(gh_bin, audit_issue)
    return True


# ---------------------------------------------------------------------------
# Main flow
# ---------------------------------------------------------------------------


def route_audit_decision(
    state_path: Path,
    git_bin: str = "git",
    gh_bin: str = "gh",
    repo_root: Path | None = None,
    config: Optional[Any] = None,
) -> RoutingResult:
    """Library entry point for the audit-decision routing pipeline.

    Pure-Python orchestration of the CLI behavior. Reads the audit-state
    JSON file, partitions proposals into auto-apply vs gated, applies
    + commits the auto-apply set, files an ``audit-pending-approval``
    issue for the gated set (if any), and posts an audit summary on the
    originating audit issue.

    The :class:`RoutingResult` returned mirrors the side-effects the
    CLI orchestration produces so library callers can act on the
    outcome without re-parsing stderr. The ``exit_code`` field carries
    the same exit-code semantics the CLI documents (0=success,
    1=input-validation, 2=apply, 3=commit, 4=gate-file,
    5=summary-post).

    Args:
        state_path: Path to the audit-state JSON file. The optional
            leading ``@`` accepted on the CLI must be stripped by the
            caller before invoking this function.
        git_bin: ``git`` binary to use (override for tests).
        gh_bin: ``gh`` binary to use (override for tests).
        repo_root: Repository root (override for tests). When ``None``,
            resolved via ``git rev-parse --show-toplevel``.

    Returns:
        :class:`RoutingResult` carrying applied/gated/issue counts and
        the suggested CLI ``exit_code``.
    """
    result = RoutingResult()

    # ---------------- 1. Load + validate JSON --------------------------
    try:
        state = _load_state(state_path)
    except InputValidationError as exc:
        print(f"ERROR: input validation: {exc}", file=sys.stderr)
        result.errors.append(f"input validation: {exc}")
        result.exit_code = 1
        return result

    audit_issue = state["audit_issue_number"]
    commit_sha = state["commit_sha"]
    areas = list(state["areas"])
    proposals = list(state["proposals"])
    debt_issues = [int(n) for n in state["debt_issues_filed"]]
    missing_issues = [int(n) for n in state["missing_artifact_issues_filed"]]
    result.debt_issues = list(debt_issues)
    result.missing_issues = list(missing_issues)

    # ---------------- 2. Empty short-circuit ---------------------------
    if not proposals:
        # Try the audit_interpretation Moment 0 path (mission #400) when
        # the config flag is on AND the audit carries a commit_sha
        # (weekly audits skip per C-006). When that path either:
        #   - declines to run (gate off, no commit_sha, no config), or
        #   - exhausts retries / hits an internal error,
        # fall through to the today-merged fallback (preserved verbatim
        # from commit bf17c3cf): release the status:in-progress lock +
        # post the generic "no automatable edits" comment.
        handled = False
        if commit_sha:
            effective_config = config
            if effective_config is None:
                effective_config = _load_config_lazy()
            if _audit_interpretation_enabled(effective_config):
                try:
                    # Resolve a usable repo_root for the LLM doc reads.
                    if repo_root is not None:
                        ai_repo_root = Path(repo_root).resolve()
                    else:
                        try:
                            res = subprocess.run(
                                [git_bin, "rev-parse", "--show-toplevel"],
                                capture_output=True,
                                text=True,
                                check=True,
                            )
                            ai_repo_root = Path(res.stdout.strip()).resolve()
                        except (OSError, subprocess.CalledProcessError) as exc:
                            logger.info(
                                "audit_interpretation: could not resolve "
                                "repo_root (%s); falling back",
                                exc,
                            )
                            ai_repo_root = None
                    if ai_repo_root is not None:
                        handled = _run_audit_interpretation_flow(
                            audit_issue=audit_issue,
                            commit_sha=commit_sha,
                            areas=areas,
                            repo_root=ai_repo_root,
                            git_bin=git_bin,
                            gh_bin=gh_bin,
                            config=effective_config,
                        )
                except Exception as exc:  # pragma: no cover - defensive
                    logger.warning(
                        "audit_interpretation: flow raised unexpected %s "
                        "(%s); falling back",
                        type(exc).__name__,
                        exc,
                    )
                    handled = False

        if not handled:
            # FALLBACK — today-merged behavior preserved verbatim
            # (commit bf17c3cf). Both operations are best-effort:
            # failures are logged but don't change the exit code —
            # the no-proposals path is fundamentally a no-op for the
            # driver.
            _post_fallback_no_proposals(gh_bin, audit_issue)
        print("INFO: no proposals; exiting cleanly.", file=sys.stderr)
        return result

    # ---------------- 3. Resolve repo root -----------------------------
    if repo_root is not None:
        repo_root_resolved = Path(repo_root).resolve()
    else:
        try:
            res = subprocess.run(
                [git_bin, "rev-parse", "--show-toplevel"],
                capture_output=True,
                text=True,
                check=True,
            )
            repo_root_resolved = Path(res.stdout.strip()).resolve()
        except (OSError, subprocess.CalledProcessError) as exc:
            print(f"ERROR: could not resolve repo root: {exc}", file=sys.stderr)
            result.errors.append(f"could not resolve repo root: {exc}")
            result.exit_code = 1
            return result

    # ---------------- 4. Partition -------------------------------------
    auto_apply, gated = _partition(proposals)
    result.gated = bool(gated)
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
            path = _apply_one(repo_root_resolved, proposal)
            written.append(path)
        except RouteApplyError as exc:
            apply_failed_proposal = exc.proposal
            apply_failure_reason = exc.reason
            break

    if apply_failed_proposal is not None:
        # Rollback any partial writes; do NOT commit; do NOT gate.
        _rollback(repo_root_resolved, written, git_bin)
        print(
            "ERROR: apply failure: "
            f"doc={apply_failed_proposal.get('doc_path')!r} "
            f"change_type={apply_failed_proposal.get('change_type')!r} "
            f"reason={apply_failure_reason!r}",
            file=sys.stderr,
        )
        result.errors.append(
            f"apply failure: doc={apply_failed_proposal.get('doc_path')!r} "
            f"change_type={apply_failed_proposal.get('change_type')!r} "
            f"reason={apply_failure_reason!r}"
        )
        result.exit_code = 2
        return result

    result.applied_count = len(auto_apply)

    # ---------------- 6. Commit (only if anything applied) -------------
    if auto_apply:
        commit_result = _run_git_commit(
            repo_root_resolved,
            git_bin,
            auto_apply,
            audit_issue,
            commit_sha,
        )
        if commit_result.returncode != 0:
            # Subprocess sequencing invariant: gate-file MUST NOT run
            # after a commit failure. Don't half-do.
            msg = (
                f"git commit failed (rc={commit_result.returncode}); "
                f"stdout={commit_result.stdout.strip()!r} "
                f"stderr={commit_result.stderr.strip()!r}"
            )
            print(f"ERROR: {msg}", file=sys.stderr)
            result.errors.append(msg)
            result.exit_code = 3
            return result

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
            gh_bin,
            gate_title,
            gate_labels,
            gate_body,
        )
        if gate_result.returncode != 0:
            msg = (
                f"gate-file (gh issue create) failed (rc={gate_result.returncode}); "
                f"stdout={gate_result.stdout.strip()!r} "
                f"stderr={gate_result.stderr.strip()!r}"
            )
            print(f"ERROR: {msg}", file=sys.stderr)
            result.errors.append(msg)
            # Best-effort summary so the system isn't completely silent.
            summary_body = _build_summary_body(
                applied=auto_apply,
                gated=gated,
                pending_approval_issue=None,
                debt_issues=debt_issues,
                missing_issues=missing_issues,
            )
            _run_gh_issue_comment(gh_bin, audit_issue, summary_body)
            result.exit_code = 4
            return result
        pending_approval_issue = _parse_issue_number(gate_result.stdout)
        if pending_approval_issue is None:
            print(
                "WARN: could not parse new issue number from gh output: "
                f"{gate_result.stdout.strip()!r}",
                file=sys.stderr,
            )
        result.pending_approval_issue = pending_approval_issue

    # ---------------- 8. Post audit summary on originating issue -------
    summary_body = _build_summary_body(
        applied=auto_apply,
        gated=gated,
        pending_approval_issue=pending_approval_issue,
        debt_issues=debt_issues,
        missing_issues=missing_issues,
    )
    summary_result = _run_gh_issue_comment(
        gh_bin,
        audit_issue,
        summary_body,
    )
    if summary_result.returncode != 0:
        msg = (
            f"summary-post (gh issue comment) failed (rc={summary_result.returncode}); "
            f"stdout={summary_result.stdout.strip()!r} "
            f"stderr={summary_result.stderr.strip()!r}"
        )
        print(f"ERROR: {msg}", file=sys.stderr)
        result.errors.append(msg)
        result.exit_code = 5
        return result

    # ---------------- 9. Close originating audit (only if no gate) ----
    if not gated:
        close_result = _run_gh_issue_close(gh_bin, audit_issue)
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

    return result


def main(argv: list[str] | None = None) -> int:
    """Thin CLI wrapper around :func:`route_audit_decision`."""
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

    state_path = _resolve_state_path(args.state)
    repo_root = Path(args.repo_root) if args.repo_root else None

    result = route_audit_decision(
        state_path=state_path,
        git_bin=args.git_bin,
        gh_bin=args.gh_bin,
        repo_root=repo_root,
    )
    return result.exit_code


if __name__ == "__main__":  # pragma: no cover
    sys.exit(main())
