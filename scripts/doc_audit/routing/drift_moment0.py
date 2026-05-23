"""Shared Moment 0 routing helper.

This module is the single source of truth for Moment 0 (LLM drift
interpretation) + verdict routing + ledger append. It is invoked from
both the cron entry point (``scripts/doc_audit/signals/drift_event.py
::DriftEventSignalSource.commit``) and the library/CLI entry point
(``scripts/doc_audit/helpers/handle_drift_events.py::process_events``).

Per mission ``moment0-integration-fix-01KS8XRM`` (FR-001, FR-004), the
logic that previously lived inline in ``handle_drift_events.py`` has
been promoted here so that both code paths execute identical behavior
without duplication.

The public surface is intentionally minimal:

- :class:`RoutingOutcome` — metadata returned to callers
- :func:`route_drift_event` — the orchestrating helper (keyword-only)

Side-effect ordering inside :func:`route_drift_event` (critical for
crash recovery — see ``contracts/routing-helper.md`` §"Side-effect
ordering"):

1. LLM call (retries internally per #362 D6)
2. Verdict routing side effects (commit / PR / issue) — visible to GitHub
3. Ledger append (last)

The caller (process_events / commit) catches :class:`DriftInterpretationError`
externally to drive the RETRY_EXHAUSTED fallback path (write a
``RETRY_EXHAUSTED`` ledger row, then file the pre-#362 ``[doc-audit]``
issue). This helper never catches that exception itself — letting it
propagate keeps the fallback semantics in one place.

The :class:`Mapping` dataclass remains owned by
``doc_audit.helpers.handle_drift_events``; importing it lazily inside
the function signature avoids a circular import (handle_drift_events
imports from this module).
"""

from __future__ import annotations

import logging
import re
import subprocess
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import TYPE_CHECKING, Any, Optional

if TYPE_CHECKING:  # pragma: no cover
    from doc_audit.helpers.handle_drift_events import Mapping


logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Public dataclass — RoutingOutcome (E1 promoted from WP04)
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class RoutingOutcome:
    """Metadata returned by :func:`route_drift_event` for caller diagnostics.

    All fields are populated; ``None`` where not applicable.

    Per ``data-model.md`` (promoted from WP04-local), the shape is::

        outcome                       str  -- canonical ledger enum value
        tier_classification_outcome   Optional[str]
        github_issue_number           Optional[int]
        retry_count                   int  -- 0..3 inclusive
        latency_ms                    int  -- end-to-end including retries

    The legacy ``success`` and ``error`` fields are preserved for
    backward compatibility with any caller that constructs a
    ``RoutingOutcome`` manually (e.g., process_events' RETRY_EXHAUSTED
    fallback that builds one synthetically). They default to ``True`` /
    ``None`` so post-#362 callers that only set the documented fields
    keep working unchanged.
    """

    outcome: str  # one of VALID_OUTCOMES in drift_ledger
    tier_classification_outcome: Optional[str] = None
    github_issue_number: Optional[int] = None
    success: bool = True
    error: Optional[str] = None
    retry_count: int = 0
    latency_ms: int = 0


# ---------------------------------------------------------------------------
# Module-private helpers (moved from handle_drift_events.py)
# ---------------------------------------------------------------------------


_ISSUE_NUMBER_RE = re.compile(r"/issues/(\d+)")


def _now_utc_iso() -> str:
    """Return the current UTC time as an ISO 8601 ``Z``-suffixed string."""
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _parse_issue_number(stdout: str) -> Optional[int]:
    """Extract an issue number from ``gh issue create`` stdout."""
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


def _decode_diff(event: dict[str, Any]) -> str:
    """Return the diff text from an event, decoding from base64 if needed.

    Local copy to avoid importing from ``handle_drift_events`` (which
    imports this module). Behaviorally identical to
    ``doc_audit.helpers.handle_drift_events.decode_diff``.
    """
    import base64

    if "diff_b64" in event:
        try:
            return base64.b64decode(event["diff_b64"]).decode("utf-8", errors="replace")
        except Exception:
            return "<diff decode failed>"
    return event.get("diff", "")


def _build_context_from_event(
    event: dict[str, Any],
    mapping: "Mapping",
    cursor_line: int,
    repo_root: Path,
) -> "Any":
    """Assemble a ``DriftInterpretationContext`` (E2) from one event.

    Loads each ``mapping.doc_targets`` file from the repo checkout,
    truncates per D2, and packages the event into the input shape
    Moment 0 (``drift_interpretation.interpret``) consumes.

    The return type is ``Any`` so this module does not require the
    judgment package to be importable at module-load time (the
    ``[drift_interpretation].enabled=false`` path must never need the
    LLM SDK to be installed — FR-013 / NFR-007 from #362).
    """
    from doc_audit.judgment.drift_interpretation import (
        DocTarget,
        DriftInterpretationContext,
    )

    timestamp = str(event.get("timestamp", _now_utc_iso()))
    if not timestamp.endswith("Z"):
        timestamp = timestamp + "Z" if "T" in timestamp else _now_utc_iso()

    diff_text = _decode_diff(event)

    targets: list[DocTarget] = []
    for rel_path in mapping.doc_targets:
        doc_path = repo_root / rel_path
        try:
            raw = doc_path.read_text(encoding="utf-8")
        except FileNotFoundError:
            raw = ""
            targets.append(
                DocTarget(
                    path=rel_path,
                    contents=raw,
                    truncated=True,
                    truncation_strategy="missing_file",
                )
            )
            continue
        except OSError as exc:
            logger.warning(
                "could not read doc_target %s for event: %s", rel_path, exc
            )
            targets.append(
                DocTarget(
                    path=rel_path,
                    contents="",
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
    mapping: "Mapping",
    question: str,
    rationale: str,
    repo: str,
    dry_run: bool = False,
) -> tuple[bool, str, Optional[int]]:
    """File a ``[doc-audit]`` issue carrying the LLM's specific question.

    Per FR-006 from #362, JUDGMENT_REQUIRED verdicts produce an
    operator-readable issue with the LLM's ``question`` prominently in
    the body (rather than the generic "review the diff" prompt of the
    pre-#362 path).

    Returns ``(success, gh_output_or_url, issue_number_or_None)``.
    """
    timestamp = event.get("timestamp", "unknown")
    baseline = event.get("baseline_name", "unknown")
    diff_text = _decode_diff(event)
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


def _route_verdict(
    verdict: "Any",
    context: "Any",
    event: dict[str, Any],
    mapping: "Mapping",
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
        # No GitHub action; ledger entry only (FR-007 from #362).
        return RoutingOutcome(
            outcome="auto_closed",
            tier_classification_outcome=None,
            github_issue_number=None,
            success=True,
        )

    if verdict_value == "JUDGMENT_REQUIRED":
        # FR-006 from #362: file an issue carrying the LLM's question.
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
    from doc_audit.routing.drift_to_proposed_edit import build as build_proposed_edit

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
    mapping: "Mapping",
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
    mapping: "Mapping",
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
    completed side-effect (FR-010 from #362 says exactly one row per
    processed event, but if the ledger write fails the side-effect
    already happened; we surface the failure to the operator via logs).
    """
    from doc_audit.output.drift_ledger import AuditLedgerEntry
    from doc_audit.output.drift_ledger import append as ledger_append

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


def _build_judgment_client(config: "Any") -> "Any":
    """Construct one :class:`JudgmentClient` per tick (cache stays warm).

    Wrapped in a helper so callers can monkeypatch a stub for tests
    without going through the real Anthropic SDK constructor.
    """
    from doc_audit.judgment.client import JudgmentClient

    return JudgmentClient(config)


# ---------------------------------------------------------------------------
# Public API — route_drift_event
# ---------------------------------------------------------------------------


def route_drift_event(
    *,
    event: dict[str, Any],
    mapping: "Mapping",
    config: "Any",
    client: "Any",
    ledger_path: Path,
    repo: str,
    event_id: str,
    timestamp_utc: str,
    cursor_line: int,
    repo_root: Path,
    dry_run: bool = False,
) -> RoutingOutcome:
    """Moment 0 LLM judgment + verdict routing + ledger append.

    Public Moment 0 helper called from both
    ``signals/drift_event.py::commit()`` (cron path) and
    ``helpers/handle_drift_events.py::process_events()`` (library/CLI
    path). See ``contracts/routing-helper.md`` for the full contract.

    Args (all keyword-only):
        event: parsed dict from drift-events.jsonl
        mapping: matching ``Mapping`` from signal-to-doc-map.json
            (must NOT be ``None``)
        config: full ``Config`` (for drift_interpretation block +
            repo settings)
        client: ``JudgmentClient`` (caller manages lifecycle; one
            per tick)
        ledger_path: path to drift-events-ledger.jsonl
        repo: GitHub repo slug for any issue/PR filings
            ("kentonium3/kg-automation")
        event_id: composite "cursor_line:timestamp_utc" string (the
            ``DriftInterpretationContext`` re-derives this from the
            ``cursor_line`` and event timestamp; the parameter is
            retained for caller traceability and ledger labelling)
        timestamp_utc: ISO 8601 Z-suffixed string from the drift event
        cursor_line: line number in drift-events.jsonl (for event_id
            construction)
        repo_root: local repo checkout path (for loading doc_targets)
        dry_run: when True, skip GitHub side effects and ledger writes

    Returns:
        :class:`RoutingOutcome` with ``retry_count`` and ``latency_ms``
        populated alongside ``outcome``, ``tier_classification_outcome``,
        and ``github_issue_number``.

    Raises:
        :class:`DriftInterpretationError`: after retry exhaustion or on
            a semantic violation (out-of-set ``doc_path``). Caller
            handles the pre-#362 fallback path; this helper does NOT
            catch the exception.
        ``OSError``: only via ``_append_ledger_entry`` if the ledger
            write fails AFTER side effects landed — the helper logs
            the error and continues; it does not raise.
    """
    # `event_id` and `timestamp_utc` are part of the documented contract
    # for caller traceability. The actual context object derives its
    # ``event_id`` from ``cursor_line`` + event timestamp so it remains
    # in sync with the on-disk drift-events.jsonl line number.
    del event_id, timestamp_utc  # part of the contract; not consumed here

    from doc_audit.judgment.drift_interpretation import interpret

    event_start = time.perf_counter()
    context = _build_context_from_event(event, mapping, cursor_line, repo_root)
    context_event_id = context.event_id
    baseline = context.baseline
    doc_paths = [t.path for t in context.doc_targets]

    # Let DriftInterpretationError propagate to the caller (per
    # contracts/routing-helper.md §"Failure modes"). The caller writes
    # the RETRY_EXHAUSTED ledger row + files the pre-#362 fallback
    # issue.
    verdict = interpret(
        client,
        context,
        model=config.drift_interpretation.model,
        timeout=config.drift_interpretation.timeout_seconds,
        confidence_threshold=config.drift_interpretation.confidence_threshold,
    )

    outcome = _route_verdict(
        verdict=verdict,
        context=context,
        event=event,
        mapping=mapping,
        repo=repo,
        repo_root=repo_root,
        judgment_client=client,
        dry_run=dry_run,
    )

    latency_ms = int((time.perf_counter() - event_start) * 1000)

    if not dry_run:
        _append_ledger_entry(
            ledger_path=ledger_path,
            event_id=context_event_id,
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

    # Augment the returned outcome with retry_count + latency_ms so the
    # caller can record diagnostics without re-deriving them.
    return RoutingOutcome(
        outcome=outcome.outcome,
        tier_classification_outcome=outcome.tier_classification_outcome,
        github_issue_number=outcome.github_issue_number,
        success=outcome.success,
        error=outcome.error,
        retry_count=0,
        latency_ms=latency_ms,
    )


__all__ = ["RoutingOutcome", "route_drift_event"]
