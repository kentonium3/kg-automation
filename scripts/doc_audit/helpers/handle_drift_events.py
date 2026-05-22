#!/usr/bin/env python3
"""Consume audit.sh drift-events.jsonl and route to doc-audit issue filing.

Implements the signal-driven doc-audit pipeline (#278). Deterministic
detection of system state changes (by audit.sh) → deterministic mapping
to documentation surfaces (via signal-to-doc-map.json) → either an
auto-filed [doc-audit] issue (matched signals) or routing to
unmapped-events.jsonl for AI review (unmatched signals).

Extended by mission ``drift-event-auto-resolution-01KS8J32`` (#362) to
wire Moment 0 (LLM drift interpretation) into the loop. When
``[drift_interpretation].enabled = true`` in config.toml, each mapped
event is passed through ``drift_interpretation.interpret`` and routed
per verdict (PROPOSED_EDIT → tier_classification dispatch,
JUDGMENT_REQUIRED → file issue with LLM's question, NO_CHANGE_NEEDED →
no GitHub artifact). Every event produces exactly one ledger row (FR-010).
Retry exhaustion falls back to the pre-#362 issue path (FR-009).

The pre-#362 CLI surface is preserved verbatim (per C-002). New flags:
- ``--reset-cursor`` writes the cursor to 0 and exits (FR-014, used by
  the cutover script in WP05).
- ``--config-path`` accepts an override path for the driver config.toml.

Invocation (CLI):
    python3 handle_drift_events.py \\
        --events /data/services/security-monitor/logs/drift-events.jsonl \\
        --cursor /data/services/security-monitor/.drift-events.cursor \\
        --mapping /home/claude/kg-automation/docs/design/architecture/data/signal-to-doc-map.json \\
        --unmapped /data/services/security-monitor/logs/unmapped-events.jsonl \\
        --repo kentonium3/kg-automation

Importable surface (per mission #343 WP01 lift):
    from doc_audit.helpers.handle_drift_events import (
        process_events,         # library entry point — see ProcessResult
        ProcessResult,
        Mapping,
        load_mappings,
        read_cursor,
        write_cursor_atomic,
        find_mapping,
        decode_diff,
        file_doc_audit_issue,
        append_unmapped,
    )

    Set ``PYTHONPATH=scripts/`` so the ``doc_audit`` package is on the
    import path. The CLI ``main()`` is now a thin argparse wrapper that
    delegates to ``process_events`` — both surfaces share the same code.

Exit codes:
    0 — success (events processed, cursor advanced)
    1 — operational error (file unreadable, gh failure, etc.)
    2 — invalid arguments or config

Idempotency: cursor stores the last-processed line number. Re-running
without new events is a no-op. Cursor is written atomically (tempfile +
rename) to avoid partial state on crash.

No de-duplication of repeat-drift across cron runs is performed in v1.
If a baseline keeps drifting day-over-day, multiple issues will be
filed — that's intentional (continued drift is itself a signal worth
surfacing). De-dup can be layered on later if churn becomes a problem.
"""
from __future__ import annotations

import argparse
import base64
import json
import logging
import os
import re
import subprocess
import sys
import tempfile
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional


logger = logging.getLogger(__name__)


@dataclass
class Mapping:
    id: str
    match: dict[str, Any]
    doc_targets: list[str]
    rationale: str
    issue_title_prefix: str
    issue_labels: list[str]


@dataclass
class ProcessResult:
    """Structured result from :func:`process_events`.

    Mirrors the values reported in the CLI ``SUMMARY:`` line so library
    callers receive the same outcome counts the CLI prints without
    having to re-parse stdout.

    Mission #362 adds aggregate verdict counters so callers (and the
    SUMMARY line) can see how the pipeline classified each event:
    ``proposed_edit_routed``, ``judgment_required_filed``,
    ``no_change_needed_closed``, ``retry_exhausted``. The pre-existing
    fields are preserved (per C-002, the CLI surface stays stable).
    """

    processed: int
    matched_filed: int
    unmapped: int
    errors: int
    new_cursor: int
    exit_code: int = 0
    proposed_edit_routed: int = 0
    judgment_required_filed: int = 0
    no_change_needed_closed: int = 0
    retry_exhausted: int = 0


@dataclass
class RoutingOutcome:
    """Internal — captures the side-effect outcome of one verdict's routing.

    Used by ``_route_verdict`` to feed the ledger writer (E3
    ``AuditLedgerEntry``). ``outcome`` is the canonical ledger enum
    value (per ``contracts/ledger-schema.md``).
    """

    outcome: str  # one of VALID_OUTCOMES in drift_ledger
    tier_classification_outcome: Optional[str] = None
    github_issue_number: Optional[int] = None
    success: bool = True
    error: Optional[str] = None


def load_mappings(path: Path) -> list[Mapping]:
    data = json.loads(path.read_text())
    mappings = []
    for m in data.get("mappings", []):
        mappings.append(
            Mapping(
                id=m["id"],
                match=m["match"],
                doc_targets=m["doc_targets"],
                rationale=m["rationale"],
                issue_title_prefix=m["issue_title_prefix"],
                issue_labels=m.get("issue_labels", ["spec: brief"]),
            )
        )
    return mappings


def read_cursor(cursor_path: Path) -> int:
    try:
        return int(cursor_path.read_text().strip())
    except (FileNotFoundError, ValueError):
        return 0


def write_cursor_atomic(cursor_path: Path, value: int) -> None:
    parent = cursor_path.parent
    parent.mkdir(parents=True, exist_ok=True)
    fd, tmp_name = tempfile.mkstemp(
        prefix=cursor_path.name + ".", suffix=".tmp", dir=str(parent)
    )
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as fh:
            fh.write(str(value))
        os.replace(tmp_name, cursor_path)
    except Exception:
        try:
            os.unlink(tmp_name)
        except OSError:
            pass
        raise


def find_mapping(event: dict[str, Any], mappings: list[Mapping]) -> Mapping | None:
    """Return the first mapping whose `match` is a subset of the event."""
    for m in mappings:
        if all(event.get(k) == v for k, v in m.match.items()):
            return m
    return None


def decode_diff(event: dict[str, Any]) -> str:
    """Return the diff text from an event, decoding from base64 if needed."""
    if "diff_b64" in event:
        try:
            return base64.b64decode(event["diff_b64"]).decode("utf-8", errors="replace")
        except Exception:
            return "<diff decode failed>"
    return event.get("diff", "")


def file_doc_audit_issue(
    event: dict[str, Any],
    mapping: Mapping,
    repo: str,
    dry_run: bool = False,
    extra_body: str = "",
) -> tuple[bool, str]:
    """File a [doc-audit] issue. Returns (success, output_or_url).

    ``extra_body`` is appended verbatim to the issue body before the
    "Auto-generated" footer. Used by the Moment 0 ``RETRY_EXHAUSTED``
    fallback to embed the ``DriftInterpretationError.to_diagnostic_block``
    payload (FR-009).
    """
    timestamp = event.get("timestamp", "unknown")
    baseline = event.get("baseline_name", "unknown")
    diff_text = decode_diff(event)
    diff_excerpt = diff_text if len(diff_text) <= 4000 else diff_text[:4000] + "\n...(truncated)"

    title = f"{mapping.issue_title_prefix} — {timestamp}"
    doc_target_lines = "\n".join(f"- `{t}`" for t in mapping.doc_targets)
    label_arg = ",".join(mapping.issue_labels)

    body = f"""## Auto-detected drift via signal-driven doc-audit (#278)

**Signal source**: `{event.get('source', 'unknown')}`
**Baseline**: `{baseline}`
**Event timestamp**: `{timestamp}`
**Mapping id**: `{mapping.id}`

## Likely doc targets

The signal-to-doc-map.json mapping identifies these documents as candidates for review:

{doc_target_lines}

## Rationale

{mapping.rationale}

## Drift diff

```
{diff_excerpt}
```

## Next steps

1. Review the diff above against the listed doc target(s)
2. If the change is intentional and the docs need updating: open a PR with the doc updates and reference this issue
3. If the change is intentional and the docs are already correct: close this issue with a note
4. If the change is unintentional: investigate and remediate before resetting the audit baseline
"""

    if extra_body:
        body = body + "\n" + extra_body + "\n"

    body += """
## Auto-generated

This issue was filed automatically by `handle_drift_events.py` based on `signal-to-doc-map.json`. To suppress this class of auto-filed issue, edit the mapping (or remove it) in `docs/design/architecture/data/signal-to-doc-map.json`.
"""

    if dry_run:
        return True, f"[dry-run] would file: {title}"

    try:
        result = subprocess.run(
            [
                "gh",
                "issue",
                "create",
                "--repo",
                repo,
                "--title",
                title,
                "--label",
                label_arg,
                "--body",
                body,
            ],
            capture_output=True,
            text=True,
            check=True,
            timeout=60,
        )
        return True, result.stdout.strip()
    except subprocess.CalledProcessError as e:
        return False, f"gh issue create failed: {e.stderr.strip()}"
    except subprocess.TimeoutExpired:
        return False, "gh issue create timed out after 60s"


def append_unmapped(unmapped_path: Path, event: dict[str, Any]) -> None:
    unmapped_path.parent.mkdir(parents=True, exist_ok=True)
    with open(unmapped_path, "a", encoding="utf-8") as fh:
        fh.write(json.dumps(event) + "\n")


# ---------------------------------------------------------------------------
# Moment 0 helpers (mission #362)
# ---------------------------------------------------------------------------


def _now_utc_iso() -> str:
    """Return the current UTC time as an ISO 8601 `Z`-suffixed string."""
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


# Truncation logic (D2 tiered strategy) lives in
# doc_audit.judgment.drift_interpretation as the single source of truth.
# We import it lazily inside _build_context_from_event to avoid a top-level
# circular-import risk (drift_interpretation may eventually import helpers).


def _build_context_from_event(
    event: dict[str, Any],
    mapping: Mapping,
    cursor_line: int,
    repo_root: Path,
) -> "Any":
    """Assemble a :class:`DriftInterpretationContext` (E2) from one event.

    Loads each ``mapping.doc_targets`` file from the repo checkout,
    truncates per D2, and packages the event into the input shape
    Moment 0 (``drift_interpretation.interpret``) consumes.

    The return type is ``Any`` so this module does not require the
    judgment package to be importable at module-load time (the
    ``[drift_interpretation].enabled=false`` path must never need the
    LLM SDK to be installed — FR-013 / NFR-007).
    """
    from doc_audit.judgment.drift_interpretation import (
        DocTarget,
        DriftInterpretationContext,
    )

    timestamp = str(event.get("timestamp", _now_utc_iso()))
    if not timestamp.endswith("Z"):
        timestamp = timestamp + "Z" if "T" in timestamp else _now_utc_iso()

    diff_text = decode_diff(event)

    targets: list[DocTarget] = []
    for rel_path in mapping.doc_targets:
        doc_path = repo_root / rel_path
        try:
            raw = doc_path.read_text(encoding="utf-8")
        except FileNotFoundError:
            # Missing doc target — pass an empty body marked truncated so
            # the LLM can still produce a JUDGMENT_REQUIRED if needed.
            raw = ""
            truncated, strategy = True, "missing_file"
            targets.append(
                DocTarget(
                    path=rel_path,
                    contents=raw,
                    truncated=truncated,
                    truncation_strategy=strategy,
                )
            )
            continue
        except OSError as exc:
            logger.warning(
                "could not read doc_target %s for event: %s", rel_path, exc
            )
            raw = ""
            targets.append(
                DocTarget(
                    path=rel_path,
                    contents=raw,
                    truncated=True,
                    truncation_strategy="read_error",
                )
            )
            continue

        from doc_audit.judgment.drift_interpretation import (
            _truncate_doc_state as _drift_truncate_doc_state,
        )

        truncated_contents, was_truncated, strategy = _drift_truncate_doc_state(
            raw, diff_text
        )
        targets.append(
            DocTarget(
                path=rel_path,
                contents=truncated_contents,
                truncated=was_truncated,
                truncation_strategy=strategy,
            )
        )

    baseline = str(event.get("baseline_name", event.get("baseline", "unknown")))

    return DriftInterpretationContext(
        event_id=f"{cursor_line}:{timestamp}",
        timestamp_utc=timestamp,
        baseline=baseline,
        mapping_id=mapping.id,
        mapping_rationale=mapping.rationale,
        diff=diff_text,
        doc_targets=targets,
    )


def _file_judgment_issue(
    event: dict[str, Any],
    mapping: Mapping,
    question: str,
    rationale: str,
    repo: str,
    dry_run: bool = False,
) -> tuple[bool, str, Optional[int]]:
    """File a `[doc-audit]` issue carrying the LLM's specific question.

    Per FR-006, JUDGMENT_REQUIRED verdicts produce an operator-readable
    issue with the LLM's `question` prominently in the body (rather
    than the generic "review the diff" prompt of the pre-#362 path).

    Returns ``(success, gh_output_or_url, issue_number_or_None)``.
    """
    timestamp = event.get("timestamp", "unknown")
    baseline = event.get("baseline_name", "unknown")
    diff_text = decode_diff(event)
    diff_excerpt = (
        diff_text if len(diff_text) <= 4000 else diff_text[:4000] + "\n...(truncated)"
    )

    title = f"{mapping.issue_title_prefix} — judgment required — {timestamp}"
    doc_target_lines = "\n".join(f"- `{t}`" for t in mapping.doc_targets)
    label_arg = ",".join(mapping.issue_labels)

    body = f"""## Drift event needs judgment (#362 Moment 0)

The Moment 0 LLM judgment classified this drift event as **JUDGMENT_REQUIRED**. The
question below is the specific operator decision the LLM could not make
autonomously.

### Question

{question}

### LLM rationale

{rationale}

---

**Signal source**: `{event.get('source', 'unknown')}`
**Baseline**: `{baseline}`
**Event timestamp**: `{timestamp}`
**Mapping id**: `{mapping.id}`

## Likely doc targets

{doc_target_lines}

## Drift diff

```
{diff_excerpt}
```

## Auto-generated

Filed by `handle_drift_events.py` (mission #362). See `docs/design/architecture/data/signal-to-doc-map.json` for the mapping.
"""

    if dry_run:
        return True, f"[dry-run] would file judgment issue: {title}", None

    try:
        result = subprocess.run(
            [
                "gh",
                "issue",
                "create",
                "--repo",
                repo,
                "--title",
                title,
                "--label",
                label_arg,
                "--body",
                body,
            ],
            capture_output=True,
            text=True,
            check=True,
            timeout=60,
        )
        stdout = result.stdout.strip()
        return True, stdout, _parse_issue_number(stdout)
    except subprocess.CalledProcessError as e:
        return False, f"gh issue create failed: {e.stderr.strip()}", None
    except subprocess.TimeoutExpired:
        return False, "gh issue create timed out after 60s", None


_ISSUE_NUMBER_RE = re.compile(r"/issues/(\d+)")


def _parse_issue_number(stdout: str) -> Optional[int]:
    """Extract an issue number from `gh issue create` stdout."""
    match = _ISSUE_NUMBER_RE.search(stdout or "")
    if not match:
        return None
    try:
        return int(match.group(1))
    except ValueError:
        return None


def _resolve_repo_root() -> Path:
    """Return the git repo root for the current working directory."""
    try:
        res = subprocess.run(
            ["git", "rev-parse", "--show-toplevel"],
            capture_output=True,
            text=True,
            check=True,
        )
        return Path(res.stdout.strip()).resolve()
    except (OSError, subprocess.CalledProcessError):
        return Path.cwd().resolve()


def _route_verdict(
    verdict: "Any",
    context: "Any",
    event: dict[str, Any],
    mapping: Mapping,
    repo: str,
    repo_root: Path,
    judgment_client: "Any",
    dry_run: bool = False,
) -> RoutingOutcome:
    """Dispatch a :class:`DriftVerdict` to the correct side-effect.

    Verdict → side-effect → ledger ``outcome`` mapping (per
    ``contracts/ledger-schema.md``):

    - PROPOSED_EDIT  → translator + tier_classification:
        - TIER_A    → auto-commit       → ``outcome="auto_committed"``
        - TIER_B    → file PR/pending   → ``outcome="pr_filed"``
        - JUDGMENT  → file DebtIssue    → ``outcome="issue_filed"``
    - JUDGMENT_REQUIRED → file [doc-audit] issue → ``outcome="issue_filed"``
    - NO_CHANGE_NEEDED → no GitHub action       → ``outcome="auto_closed"``

    Reuses the per-change_type appliers and gh helpers from
    :mod:`doc_audit.helpers.handle_audit_routing` so we don't
    re-implement that surface here.
    """
    verdict_value = getattr(verdict, "verdict", None)

    if verdict_value == "NO_CHANGE_NEEDED":
        # No GitHub action; ledger entry only (FR-007).
        return RoutingOutcome(
            outcome="auto_closed",
            tier_classification_outcome=None,
            github_issue_number=None,
            success=True,
        )

    if verdict_value == "JUDGMENT_REQUIRED":
        # FR-006: file an issue carrying the LLM's question.
        question = getattr(verdict, "question", "") or ""
        rationale = getattr(verdict, "rationale", "") or ""
        ok, output, issue_number = _file_judgment_issue(
            event=event,
            mapping=mapping,
            question=question,
            rationale=rationale,
            repo=repo,
            dry_run=dry_run,
        )
        return RoutingOutcome(
            outcome="issue_filed",
            tier_classification_outcome=None,
            github_issue_number=issue_number,
            success=ok,
            error=None if ok else output,
        )

    if verdict_value != "PROPOSED_EDIT":
        # Defense-in-depth: drift_interpretation guarantees one of the
        # three verdicts. Anything else demotes to JUDGMENT_REQUIRED-like
        # behavior so the operator sees something.
        ok, output, issue_number = _file_judgment_issue(
            event=event,
            mapping=mapping,
            question=f"Unexpected verdict value: {verdict_value!r}",
            rationale=getattr(verdict, "rationale", "") or "",
            repo=repo,
            dry_run=dry_run,
        )
        return RoutingOutcome(
            outcome="issue_filed",
            tier_classification_outcome=None,
            github_issue_number=issue_number,
            success=ok,
        )

    # ------------------- PROPOSED_EDIT path -------------------------------
    from doc_audit.judgment import tier_classification
    from doc_audit.routing import build as build_proposed_edit

    try:
        proposed_edit = build_proposed_edit(verdict, context)
    except ValueError as exc:
        # Translator rejected — defense-in-depth. Demote to JUDGMENT_REQUIRED.
        logger.warning(
            "drift_to_proposed_edit.build rejected verdict: %s; demoting", exc
        )
        ok, output, issue_number = _file_judgment_issue(
            event=event,
            mapping=mapping,
            question=(
                "drift_to_proposed_edit.build rejected the LLM verdict; "
                "the proposed edit was out-of-set or malformed."
            ),
            rationale=str(exc),
            repo=repo,
            dry_run=dry_run,
        )
        return RoutingOutcome(
            outcome="issue_filed",
            tier_classification_outcome="judgment",
            github_issue_number=issue_number,
            success=ok,
        )

    # ----- Moment 1 tier_classification -----
    # Pass an empty frontmatter excerpt + the mapping's labels (the most
    # specific scope we have at this layer). guardrail_check_result is
    # left as "not_guardrailed"; tier_classification's own SKILL.md
    # short-circuit catches guardrailed paths regardless.
    try:
        tier, tier_rationale, _resp = tier_classification.classify(
            judgment_client,
            proposed_edit,
            audit_area_labels=list(mapping.issue_labels),
            doc_frontmatter_excerpt="",
            guardrail_check_result="not_guardrailed",
        )
    except Exception as exc:  # pragma: no cover - defensive
        # Any tier_classification failure → file an issue rather than
        # auto-applying. Operator surface preserved.
        logger.warning(
            "tier_classification raised %s; demoting to JUDGMENT", exc
        )
        ok, output, issue_number = _file_judgment_issue(
            event=event,
            mapping=mapping,
            question=(
                "Moment 1 tier_classification failed; the proposed edit "
                "needs operator review."
            ),
            rationale=f"tier_classification error: {exc}",
            repo=repo,
            dry_run=dry_run,
        )
        return RoutingOutcome(
            outcome="issue_filed",
            tier_classification_outcome="judgment",
            github_issue_number=issue_number,
            success=ok,
        )

    tier_value = getattr(tier, "value", None) or str(tier)

    if tier_value == "tier_a":
        ok, output, applied_path = _apply_tier_a_edit(
            proposed_edit=proposed_edit,
            repo_root=repo_root,
            event=event,
            mapping=mapping,
            dry_run=dry_run,
        )
        if ok:
            return RoutingOutcome(
                outcome="auto_committed",
                tier_classification_outcome="tier_a",
                github_issue_number=None,
                success=True,
            )
        # Tier A apply failed — fall back to filing a judgment issue.
        logger.warning("Tier A auto-commit failed: %s; demoting to judgment", output)
        ok, output, issue_number = _file_judgment_issue(
            event=event,
            mapping=mapping,
            question=(
                "Tier A auto-commit failed; the proposed edit needs "
                "operator review (likely current_value mismatch)."
            ),
            rationale=f"{tier_rationale}\n\nApply error: {output}",
            repo=repo,
            dry_run=dry_run,
        )
        return RoutingOutcome(
            outcome="issue_filed",
            tier_classification_outcome="tier_a",
            github_issue_number=issue_number,
            success=ok,
        )

    if tier_value == "tier_b":
        ok, output, issue_number = _file_tier_b_pending_approval(
            proposed_edit=proposed_edit,
            event=event,
            mapping=mapping,
            rationale=tier_rationale,
            repo=repo,
            dry_run=dry_run,
        )
        return RoutingOutcome(
            outcome="pr_filed",
            tier_classification_outcome="tier_b",
            github_issue_number=issue_number,
            success=ok,
            error=None if ok else output,
        )

    # tier_value == "judgment" — file a DebtIssue-style issue.
    ok, output, issue_number = _file_judgment_issue(
        event=event,
        mapping=mapping,
        question=(
            "Moment 1 tier_classification routed this proposed edit to "
            "JUDGMENT; please review the diff and decide."
        ),
        rationale=tier_rationale,
        repo=repo,
        dry_run=dry_run,
    )
    return RoutingOutcome(
        outcome="issue_filed",
        tier_classification_outcome="judgment",
        github_issue_number=issue_number,
        success=ok,
        error=None if ok else output,
    )


def _apply_tier_a_edit(
    proposed_edit: "Any",
    repo_root: Path,
    event: dict[str, Any],
    mapping: Mapping,
    dry_run: bool = False,
) -> tuple[bool, str, Optional[Path]]:
    """Apply a Tier A proposed edit and commit it.

    Reuses :func:`doc_audit.helpers.handle_audit_routing._apply_one` for
    the substitution + atomic write so we don't reimplement the
    per-change_type applier table. The commit is constructed inline
    because the audit-decision routing's commit message references an
    audit issue we don't have for drift-derived edits.
    """
    from doc_audit.helpers.handle_audit_routing import (
        APPLIERS,
        RouteApplyError,
        _atomic_write,
    )

    # `proposed_edit` has change_type="drift_derived" — translate to an
    # applier key by inspecting the edit shape. We try the common
    # appliers in order; whichever performs a successful substitution
    # wins. If none of them match, fall back to judgment.
    proposal_dict = {
        "doc_path": proposed_edit.doc_path,
        "change_type": proposed_edit.change_type,
        "current_value": proposed_edit.current_value,
        "proposed_value": proposed_edit.proposed_value,
        "evidence_source": proposed_edit.evidence_source,
        "confidence": proposed_edit.confidence,
    }

    doc_path = repo_root / proposed_edit.doc_path
    if not doc_path.exists():
        return False, f"doc not found: {doc_path}", None

    try:
        content = doc_path.read_text(encoding="utf-8")
    except OSError as exc:
        return False, f"doc unreadable: {exc}", None

    # Try a sequence of safe appliers. ``version_bump`` is the most
    # permissive single-occurrence substitution and is the right default
    # for drift_derived edits whose change_type doesn't match a more
    # specific applier.
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
            None,
        )

    if dry_run:
        return True, f"[dry-run] would apply Tier A edit to {proposed_edit.doc_path}", doc_path

    try:
        _atomic_write(doc_path, new_content)
    except OSError as exc:
        return False, f"atomic write failed: {exc}", None

    # Build a commit referencing the drift event so the operator can
    # trace it back to the originating signal.
    timestamp = event.get("timestamp", "unknown")
    subject = (
        f"docs(drift): auto-apply drift_derived edit for {mapping.id}"
    )
    body_lines = [
        "",
        f"Triggered by drift event timestamp={timestamp} mapping={mapping.id}.",
        f"Auto-applied via Moment 0 (drift_interpretation) Tier A.",
        "",
        f"- {proposed_edit.doc_path}: "
        f"{proposed_edit.current_value!r} -> {proposed_edit.proposed_value!r}",
        "",
        f"Evidence: {proposed_edit.evidence_source}",
    ]
    commit_message = subject + "\n" + "\n".join(body_lines) + "\n"

    try:
        add_res = subprocess.run(
            ["git", "add", "--", proposed_edit.doc_path],
            cwd=str(repo_root),
            capture_output=True,
            text=True,
        )
        if add_res.returncode != 0:
            return False, f"git add failed: {add_res.stderr.strip()}", None
        commit_res = subprocess.run(
            ["git", "commit", "-m", commit_message],
            cwd=str(repo_root),
            capture_output=True,
            text=True,
        )
        if commit_res.returncode != 0:
            return False, f"git commit failed: {commit_res.stderr.strip()}", None
    except OSError as exc:
        return False, f"git invocation failed: {exc}", None

    return True, "applied + committed", doc_path


def _file_tier_b_pending_approval(
    proposed_edit: "Any",
    event: dict[str, Any],
    mapping: Mapping,
    rationale: str,
    repo: str,
    dry_run: bool = False,
) -> tuple[bool, str, Optional[int]]:
    """File a Tier B pending-approval issue for the proposed edit."""
    timestamp = event.get("timestamp", "unknown")
    title = (
        f"{mapping.issue_title_prefix} — pending approval — {timestamp}"
    )
    label_arg = ",".join(["audit-pending-approval"] + list(mapping.issue_labels))

    body = f"""## Tier B pending approval (#362 Moment 0)

A drift-derived proposed edit reached Tier B and needs operator approval before
landing.

**Doc target**: `{proposed_edit.doc_path}`
**Change type**: `{proposed_edit.change_type}`
**Evidence**: {proposed_edit.evidence_source}

### Diff

```diff
- {proposed_edit.current_value}
+ {proposed_edit.proposed_value}
```

### LLM rationale (Moment 1)

{rationale}

### Drift event

- baseline: `{event.get('baseline_name', 'unknown')}`
- mapping: `{mapping.id}`
- timestamp: `{timestamp}`

## Auto-generated

Filed by `handle_drift_events.py` (mission #362).
"""

    if dry_run:
        return True, f"[dry-run] would file Tier B issue: {title}", None

    try:
        result = subprocess.run(
            [
                "gh",
                "issue",
                "create",
                "--repo",
                repo,
                "--title",
                title,
                "--label",
                label_arg,
                "--body",
                body,
            ],
            capture_output=True,
            text=True,
            check=True,
            timeout=60,
        )
        stdout = result.stdout.strip()
        return True, stdout, _parse_issue_number(stdout)
    except subprocess.CalledProcessError as e:
        return False, f"gh issue create failed: {e.stderr.strip()}", None
    except subprocess.TimeoutExpired:
        return False, "gh issue create timed out after 60s", None


def _append_ledger_entry(
    *,
    ledger_path: Path,
    event_id: str,
    baseline: str,
    mapping_id: str,
    verdict_value: str,
    confidence: Optional[float],
    outcome: str,
    doc_paths: list[str],
    retry_count: int,
    latency_ms: int,
    tier_classification_outcome: Optional[str],
    github_issue_number: Optional[int],
) -> None:
    """Append one row to the drift-events ledger (E3).

    Wraps :func:`doc_audit.output.drift_ledger.append` so all the
    schema-required field plumbing lives in one place. Errors are
    logged but never raised — a ledger-write failure must NOT undo a
    completed side-effect (FR-010 says exactly one row per processed
    event, but if the ledger write fails the side-effect already
    happened; we surface the failure to the operator via logs).
    """
    from doc_audit.output.drift_ledger import AuditLedgerEntry, append as ledger_append

    entry = AuditLedgerEntry(
        event_id=event_id,
        timestamp_utc=_now_utc_iso(),
        baseline=baseline or "unknown",
        mapping_id=mapping_id,
        verdict=verdict_value,
        confidence=confidence,
        outcome=outcome,
        doc_paths=list(doc_paths),
        retry_count=retry_count,
        latency_ms=max(0, int(latency_ms)),
        tier_classification_outcome=tier_classification_outcome,
        github_issue_number=github_issue_number,
    )
    try:
        ledger_append(entry, ledger_path=ledger_path)
    except (OSError, ValueError) as exc:
        logger.error(
            "ledger append failed for event_id=%s: %s; side-effect already "
            "completed, continuing",
            event_id,
            exc,
        )


def _handle_moment0_event(
    *,
    event: dict[str, Any],
    mapping: Mapping,
    cursor_line: int,
    config: "Any",
    judgment_client: "Any",
    repo: str,
    repo_root: Path,
    ledger_path: Path,
    dry_run: bool,
) -> RoutingOutcome:
    """Drive Moment 0 for a single mapped event end-to-end.

    Returns the :class:`RoutingOutcome` produced by ``_route_verdict``
    (or a synthetic ``retry_exhausted`` outcome if Moment 0 raises
    after retries exhausted).
    """
    from doc_audit.judgment.drift_interpretation import (
        DriftInterpretationError,
        interpret,
    )

    event_start = time.monotonic()
    context = _build_context_from_event(event, mapping, cursor_line, repo_root)
    event_id = context.event_id
    baseline = context.baseline
    doc_paths = [t.path for t in context.doc_targets]

    try:
        verdict = interpret(
            judgment_client,
            context,
            model=config.drift_interpretation.model,
            timeout=config.drift_interpretation.timeout_seconds,
            confidence_threshold=config.drift_interpretation.confidence_threshold,
        )
    except DriftInterpretationError as exc:
        # FR-009: retry exhausted — fall back to the pre-#362 issue path.
        logger.error(
            "Moment 0 retry exhausted for event %s: %s", event_id, exc
        )
        if not dry_run:
            ok, output = file_doc_audit_issue(
                event=event,
                mapping=mapping,
                repo=repo,
                dry_run=False,
                extra_body=exc.to_diagnostic_block(),
            )
            issue_number = _parse_issue_number(output) if ok else None
        else:
            ok = True
            issue_number = None
        latency_ms = int((time.monotonic() - event_start) * 1000)
        if not dry_run:
            _append_ledger_entry(
                ledger_path=ledger_path,
                event_id=event_id,
                baseline=baseline,
                mapping_id=mapping.id,
                verdict_value="RETRY_EXHAUSTED",
                confidence=None,
                outcome="retry_exhausted",
                doc_paths=doc_paths,
                retry_count=getattr(exc, "attempts", 3),
                latency_ms=latency_ms,
                tier_classification_outcome=None,
                github_issue_number=issue_number,
            )
        return RoutingOutcome(
            outcome="retry_exhausted",
            tier_classification_outcome=None,
            github_issue_number=issue_number,
            success=True,
        )

    # Normal verdict routing
    outcome = _route_verdict(
        verdict=verdict,
        context=context,
        event=event,
        mapping=mapping,
        repo=repo,
        repo_root=repo_root,
        judgment_client=judgment_client,
        dry_run=dry_run,
    )

    latency_ms = int((time.monotonic() - event_start) * 1000)
    if not dry_run:
        _append_ledger_entry(
            ledger_path=ledger_path,
            event_id=event_id,
            baseline=baseline,
            mapping_id=mapping.id,
            verdict_value=verdict.verdict,
            confidence=float(verdict.confidence),
            outcome=outcome.outcome,
            doc_paths=doc_paths,
            retry_count=0,
            latency_ms=latency_ms,
            tier_classification_outcome=outcome.tier_classification_outcome,
            github_issue_number=outcome.github_issue_number,
        )
    return outcome


def _build_judgment_client(config: "Any") -> "Any":
    """Construct one :class:`JudgmentClient` per tick (cache stays warm).

    Wrapped in a helper so callers can monkeypatch a stub for tests
    without going through the real Anthropic SDK constructor.
    """
    from doc_audit.judgment.client import JudgmentClient

    return JudgmentClient(config)


# ---------------------------------------------------------------------------
# Core loop
# ---------------------------------------------------------------------------


def process_events(
    events_path: Path,
    cursor_path: Path,
    mapping_path: Path,
    unmapped_path: Path,
    repo: str = "kentonium3/kg-automation",
    limit: int = 20,
    dry_run: bool = False,
    *,
    config: "Any" = None,
    judgment_client: "Any" = None,
    repo_root: Optional[Path] = None,
) -> ProcessResult:
    """Library entry point for the drift-events pipeline.

    Pure-Python orchestration of the CLI behavior. Reads the cursor +
    mapping + events files, classifies each event against the mapping
    table, files a ``[doc-audit]`` issue (matched) or appends to the
    unmapped log (unmatched), and advances the cursor atomically.

    Mission #362 extension: when ``config.drift_interpretation.enabled
    == True`` and a mapping matched, each event is passed through
    Moment 0 (``drift_interpretation.interpret``) and routed per
    verdict. Every processed event produces exactly one ledger row
    (FR-010). The pre-#362 CLI shape (positional + keyword args
    ``events_path`` through ``dry_run``) is preserved verbatim (C-002).

    The :class:`ProcessResult` returned mirrors the values reported in
    the CLI ``SUMMARY:`` line so library callers receive the same
    outcome counts the CLI prints without having to re-parse stdout.

    Args:
        events_path: Path to ``drift-events.jsonl``.
        cursor_path: Path to the cursor file (one integer line number).
        mapping_path: Path to ``signal-to-doc-map.json``.
        unmapped_path: Path to ``unmapped-events.jsonl`` for unmatched
            events.
        repo: GitHub repo slug used by ``gh issue create``.
        limit: Maximum events to process per invocation.
        dry_run: If True, don't actually file issues and don't advance
            the on-disk cursor.
        config: Optional :class:`doc_audit.config.Config`. When
            provided AND ``config.drift_interpretation.enabled``, the
            Moment 0 path is exercised. When ``None`` or disabled, the
            pipeline runs in pre-#362 mode (FR-013 / NFR-007).
        judgment_client: Optional pre-built :class:`JudgmentClient`.
            When ``None`` and Moment 0 is enabled, one is constructed
            per tick.
        repo_root: Override for the repo root used by Tier A applier
            and Moment 0 doc-target reads. Defaults to
            ``git rev-parse --show-toplevel``.

    Returns:
        :class:`ProcessResult` carrying the per-invocation counters and
        the suggested CLI ``exit_code`` (0 on success, 1 on error, 2 on
        invalid config).
    """
    if not mapping_path.exists():
        print(f"ERROR: mapping file not found: {mapping_path}", file=sys.stderr)
        return ProcessResult(
            processed=0,
            matched_filed=0,
            unmapped=0,
            errors=0,
            new_cursor=read_cursor(cursor_path),
            exit_code=2,
        )

    mappings = load_mappings(mapping_path)
    cursor = read_cursor(cursor_path)

    if not events_path.exists():
        # No events file yet — nothing to do; not an error
        print(f"INFO: no events file at {events_path}; nothing to process")
        return ProcessResult(
            processed=0,
            matched_filed=0,
            unmapped=0,
            errors=0,
            new_cursor=cursor,
            exit_code=0,
        )

    with open(events_path, encoding="utf-8") as fh:
        lines = fh.readlines()

    new_lines = lines[cursor:]
    if not new_lines:
        print(f"INFO: no new events since cursor={cursor}")
        return ProcessResult(
            processed=0,
            matched_filed=0,
            unmapped=0,
            errors=0,
            new_cursor=cursor,
            exit_code=0,
        )

    if len(new_lines) > limit:
        print(
            f"WARN: {len(new_lines)} new events exceeds --limit={limit}; "
            f"processing first {limit}, cursor will advance only that far",
            file=sys.stderr,
        )
        new_lines = new_lines[:limit]

    # Moment 0 enablement gate. ``moment0_on`` is True iff the operator
    # has explicitly turned on the drift_interpretation feature AND we
    # have a config to drive it. When False, the loop runs in pre-#362
    # mode (file_doc_audit_issue for every matched event).
    moment0_on = (
        config is not None
        and getattr(config, "drift_interpretation", None) is not None
        and config.drift_interpretation.enabled
    )

    judgment_client_local = judgment_client
    if moment0_on and judgment_client_local is None:
        try:
            judgment_client_local = _build_judgment_client(config)
        except Exception as exc:
            logger.error(
                "Could not build JudgmentClient; falling back to pre-#362 "
                "path: %s",
                exc,
            )
            moment0_on = False

    ledger_path = (
        Path(config.drift_interpretation.ledger_path)
        if moment0_on
        else None
    )
    # Only resolve the repo root when Moment 0 is on. The pre-#362 path
    # never reads doc-target contents or invokes git, so a repo-root
    # lookup would just add an unnecessary subprocess.run call.
    if moment0_on:
        resolved_repo_root = (
            Path(repo_root) if repo_root is not None else _resolve_repo_root()
        )
    else:
        resolved_repo_root = None

    matched = 0
    unmapped = 0
    errors = 0
    processed = 0
    proposed_edit_routed = 0
    judgment_required_filed = 0
    no_change_needed_closed = 0
    retry_exhausted_count = 0

    for offset, line in enumerate(new_lines):
        cursor_line = cursor + offset
        line = line.strip()
        if not line:
            processed += 1
            continue

        try:
            event = json.loads(line)
        except json.JSONDecodeError as e:
            print(f"WARN: skipping malformed event line: {e}", file=sys.stderr)
            processed += 1
            continue

        mapping = find_mapping(event, mappings)
        if mapping is None:
            append_unmapped(unmapped_path, event)
            unmapped += 1
            print(
                f"INFO: no mapping for event source={event.get('source')} "
                f"baseline={event.get('baseline_name')}; routed to unmapped log"
            )
            processed += 1
            continue

        if moment0_on:
            outcome = _handle_moment0_event(
                event=event,
                mapping=mapping,
                cursor_line=cursor_line,
                config=config,
                judgment_client=judgment_client_local,
                repo=repo,
                repo_root=resolved_repo_root,
                ledger_path=ledger_path,
                dry_run=dry_run,
            )

            if outcome.outcome == "retry_exhausted":
                retry_exhausted_count += 1
                # Pre-#362 fallback already filed an issue inside the
                # handler; count as a matched-filed for backward-compat
                # SUMMARY semantics.
                matched += 1
            elif outcome.outcome == "auto_closed":
                no_change_needed_closed += 1
            elif outcome.outcome in ("auto_committed", "pr_filed"):
                proposed_edit_routed += 1
                matched += 1
            elif outcome.outcome == "issue_filed":
                # Either JUDGMENT_REQUIRED or PROPOSED_EDIT routed to
                # tier_classification's JUDGMENT bucket — both surface
                # via a filed issue.
                judgment_required_filed += 1
                matched += 1
            print(
                f"INFO: moment0 mapping={mapping.id} → outcome={outcome.outcome}"
                + (f" issue=#{outcome.github_issue_number}"
                   if outcome.github_issue_number else "")
            )
            processed += 1
            continue

        # Pre-#362 path (flag disabled OR no config supplied)
        ok, output = file_doc_audit_issue(event, mapping, repo, dry_run=dry_run)
        if ok:
            matched += 1
            print(f"INFO: mapping={mapping.id} → {output}")
            processed += 1
        else:
            errors += 1
            print(f"ERROR: mapping={mapping.id} → {output}", file=sys.stderr)
            # Don't advance cursor past failed events so they retry next run
            break

    new_cursor = cursor + processed
    if dry_run:
        print(
            f"SUMMARY: processed={processed} matched_filed={matched} "
            f"unmapped={unmapped} errors={errors} "
            f"cursor={cursor}→{new_cursor} (DRY-RUN — cursor NOT written)"
        )
    else:
        write_cursor_atomic(cursor_path, new_cursor)
        print(
            f"SUMMARY: processed={processed} matched_filed={matched} "
            f"unmapped={unmapped} errors={errors} cursor={cursor}→{new_cursor}"
        )

    return ProcessResult(
        processed=processed,
        matched_filed=matched,
        unmapped=unmapped,
        errors=errors,
        new_cursor=new_cursor,
        exit_code=1 if errors > 0 else 0,
        proposed_edit_routed=proposed_edit_routed,
        judgment_required_filed=judgment_required_filed,
        no_change_needed_closed=no_change_needed_closed,
        retry_exhausted=retry_exhausted_count,
    )


def main(argv: list[str] | None = None) -> int:
    """Thin CLI wrapper around :func:`process_events`."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--events", type=Path, help="Path to drift-events.jsonl")
    parser.add_argument("--cursor", type=Path, help="Path to cursor file")
    parser.add_argument(
        "--mapping",
        type=Path,
        help="Path to signal-to-doc-map.json",
    )
    parser.add_argument(
        "--unmapped",
        type=Path,
        help="Path to unmapped-events.jsonl (events without a mapping)",
    )
    parser.add_argument(
        "--repo",
        default="kentonium3/kg-automation",
        help="GitHub repo for issue filing",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Don't actually file issues; print what would happen",
    )
    parser.add_argument(
        "--limit",
        type=int,
        default=20,
        help="Maximum events to process per invocation (safety against runaway)",
    )
    parser.add_argument(
        "--reset-cursor",
        action="store_true",
        default=False,
        help=(
            "Write cursor=0 and exit 0 (FR-014, used by the #362 cutover "
            "script). Idempotent. Requires --cursor."
        ),
    )
    parser.add_argument(
        "--config-path",
        type=Path,
        default=None,
        help=(
            "Path to the driver config.toml (default: scripts/doc_audit/"
            "config.toml). Used only to load the [drift_interpretation] block."
        ),
    )
    args = parser.parse_args(argv)

    # --reset-cursor short-circuits before anything else (FR-014). It only
    # requires --cursor; the other arguments are not consulted.
    if args.reset_cursor:
        if args.cursor is None:
            parser.error("--reset-cursor requires --cursor")
        write_cursor_atomic(args.cursor, 0)
        print(
            f"INFO: cursor reset to 0 by operator request at {args.cursor}"
        )
        return 0

    for required in ("events", "cursor", "mapping", "unmapped"):
        if getattr(args, required) is None:
            parser.error(f"--{required} is required")

    # Load config if available; absence is OK (falls back to pre-#362).
    config = None
    try:
        from doc_audit.config import load_config

        config = load_config(args.config_path) if args.config_path else load_config()
    except (FileNotFoundError, ValueError) as exc:
        logger.info(
            "config.toml unavailable (%s); running in pre-#362 mode", exc
        )
        config = None

    result = process_events(
        events_path=args.events,
        cursor_path=args.cursor,
        mapping_path=args.mapping,
        unmapped_path=args.unmapped,
        repo=args.repo,
        limit=args.limit,
        dry_run=args.dry_run,
        config=config,
    )
    return result.exit_code


if __name__ == "__main__":
    sys.exit(main())
