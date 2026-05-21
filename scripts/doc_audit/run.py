#!/usr/bin/env python3
"""felix-doc-auditor scripts-first driver — main entry point.

Contract: ``kitty-specs/refactor-doc-auditor-to-scripts-first-driver-01KS2XNX/
contracts/driver-invocation.contract.md``.

This module is the CLI entry point that systemd invokes once per tick.
It composes the WP02-WP05 components (config / signals / judgment /
routing / output) into a working orchestration loop.

Top-level discipline
====================

Two invariants the contract makes load-bearing:

1. **A tick signal is ALWAYS written.** A top-level ``try/finally`` in
   :func:`main` runs :func:`output.tick_signal.write_tick_signal` and
   per-audit activity log entries even when ``_run_tick`` raises.
2. **Exit codes are deterministic.** ``status="success"`` → ``0``,
   ``"partial"`` → ``2``, ``"failure"`` → ``1``. These map to systemd's
   "success", "partial failure", "failure" interpretations.

Orchestration order (per research D9 + FR-004)
==============================================

Within one tick:

1. **Drift events FIRST** — :class:`DriftEventSignalSource` reads
   ``drift-events.jsonl`` and files ``[doc-audit]`` GH issues for mapped
   events. Those issues are picked up in step 2 of the SAME tick.
2. **GH-issue scan** — :class:`GHIssueSignalSource` enumerates open
   audits + pending-approvals. The full queue is sorted by
   ``(priority, created_utc)`` and processed in that order:

   - Pending-approvals (priority 10) — apply decision via the routing
     layer.
   - Doc audits (priority 20) — run the audit workflow.
   - Weekly audits (priority 30) — same workflow as doc audits.

   Drift events (priority 40) are handled in step 1, not here.

Error semantics
===============

- :class:`RateLimitError`: BREAK the signal-processing loop. Unprocessed
  signals retry next tick. ``result.status = "failure"``.
- Any other exception during ``_process_signal``: log to
  ``result.errors``, set ``result.status = "partial"``, continue with
  the next signal.
- Any exception inside ``_run_tick``: caught in :func:`main`'s
  ``try/finally``; ``result.status = "failure"``; tick signal still
  written.
"""
from __future__ import annotations

import argparse
import logging
import re
import subprocess
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Optional

# sys.path bootstrap so the module is runnable directly via
# ``python3 scripts/doc_audit/run.py``. When invoked with
# ``PYTHONPATH=scripts``, this is a no-op.
_REPO_SCRIPTS = Path(__file__).resolve().parent.parent
if str(_REPO_SCRIPTS) not in sys.path:
    sys.path.insert(0, str(_REPO_SCRIPTS))

from doc_audit.config import Config, load_config  # noqa: E402
from doc_audit.data_model import (  # noqa: E402
    AuditIssue,
    DebtIssue,
    EditTier,
    ProposedEdit,
    Signal,
    TickResult,
)
from doc_audit.judgment import (  # noqa: E402
    cross_file_implication,
    debt_body_generation,
    tier_classification,
)
from doc_audit.judgment.client import JudgmentClient, JudgmentResponse  # noqa: E402
from doc_audit.output.activity_log import (  # noqa: E402
    LOCAL_TZ,
    append_audit_entry,
)
from doc_audit.output.tick_signal import (  # noqa: E402
    print_summary_line,
    write_tick_signal,
)
from doc_audit.routing.apply_decisions import RoutingResult, apply as apply_routing  # noqa: E402
from doc_audit.signals.drift_event import DriftEventSignalSource  # noqa: E402
from doc_audit.signals.gh_issue import GHIssueSignalSource  # noqa: E402


__version__ = "0.1.0"

logger = logging.getLogger("doc_audit.run")


# ---------------------------------------------------------------------------
# RateLimitError — used as a sentinel to BREAK the per-signal loop
# ---------------------------------------------------------------------------


class RateLimitError(Exception):
    """Raised when GitHub or Anthropic signals a rate-limit condition.

    The orchestration loop catches this and BREAKs out of the signal
    iterator — any further API call in the same tick will hit the same
    limit. Unprocessed signals stay in the queue for the next tick.

    Detection patterns (see :func:`_is_rate_limited`):
    - ``subprocess.CalledProcessError`` from ``gh`` with stderr/output
      containing ``"API rate limit exceeded"`` or
      ``"X-RateLimit-Remaining: 0"``.
    - ``anthropic.RateLimitError`` (subclass of ``anthropic.APIError``;
      surfaced verbatim when the SDK raises it).
    """


# ---------------------------------------------------------------------------
# CLI argument parsing
# ---------------------------------------------------------------------------


def _parse_args(argv: Optional[list[str]]) -> argparse.Namespace:
    """Parse CLI args per ``driver-invocation.contract.md``."""
    parser = argparse.ArgumentParser(
        prog="doc_audit/run.py",
        description=(
            "felix-doc-auditor scripts-first driver. Process pending audit "
            "signals once per invocation. See "
            "contracts/driver-invocation.contract.md."
        ),
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Print intended actions; do not mutate GH issues or repo files.",
    )
    parser.add_argument(
        "--once",
        action="store_true",
        default=True,
        help=(
            "Process the queue once and exit (default). Reserved for "
            "future --daemon mode."
        ),
    )
    parser.add_argument(
        "--source",
        choices=("gh_issue", "drift_event"),
        default=None,
        help=(
            "Restrict to one signal source. Useful for incremental "
            "testing; omit for production."
        ),
    )
    parser.add_argument(
        "--config",
        default=None,
        help=(
            "Override config path. Default: scripts/doc_audit/config.toml."
        ),
    )
    parser.add_argument(
        "--version",
        action="store_true",
        help="Print driver version and exit.",
    )
    return parser.parse_args(argv)


# ---------------------------------------------------------------------------
# Time helpers
# ---------------------------------------------------------------------------


def _now_iso() -> str:
    """Return UTC now as ISO-8601 with trailing ``Z``."""
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _compute_next_tick() -> str:
    """Compute the next-scheduled-tick UTC.

    The driver runs hourly via a systemd timer. Return ``now + 1h``
    truncated to the hour. Best-effort; the tick signal field is purely
    informational for operators.
    """
    now = datetime.now(timezone.utc)
    next_hour = (now + timedelta(hours=1)).replace(
        minute=0, second=0, microsecond=0
    )
    return next_hour.strftime("%Y-%m-%dT%H:%M:%SZ")


# ---------------------------------------------------------------------------
# Rate-limit detection
# ---------------------------------------------------------------------------


_RATE_LIMIT_PATTERNS = (
    "API rate limit exceeded",
    "X-RateLimit-Remaining: 0",
    "secondary rate limit",
)


def _is_rate_limited(exc: BaseException) -> bool:
    """Detect a rate-limit condition from ``gh`` subprocess errors.

    For ``subprocess.CalledProcessError`` from ``gh``: inspect stderr
    and output for the GH rate-limit banner. The driver's
    ``signals/gh_issue.py`` re-raises ``CalledProcessError`` verbatim,
    so we can introspect here.

    For Anthropic SDK errors: ``anthropic.RateLimitError`` is detected
    by class name (so we avoid importing the SDK at module-import time
    in case the test env lacks it).
    """
    # subprocess errors carry stderr/output text in 0.x
    stderr = getattr(exc, "stderr", "") or ""
    output = getattr(exc, "output", "") or ""
    haystack = f"{stderr}\n{output}"
    if any(pat in haystack for pat in _RATE_LIMIT_PATTERNS):
        return True
    # Anthropic SDK: catch by class name to avoid hard-dep
    cls_name = type(exc).__name__
    if cls_name == "RateLimitError":
        return True
    return False


# ---------------------------------------------------------------------------
# Audit-issue parsing (from GH Signal payload)
# ---------------------------------------------------------------------------


_TITLE_AUDIT_RE = re.compile(
    r"^Doc audit:\s*(?P<sha>[0-9a-f]+)(?:\s*\((?P<domains>[^)]*)\))?",
    re.IGNORECASE,
)
_TITLE_WEEKLY_RE = re.compile(r"^Weekly doc audit —", re.IGNORECASE)
_REFS_RE = re.compile(r"Refs\s+#(\d+)", re.IGNORECASE)
_AUDIT_REF_RE = re.compile(r"Audit\s+#(\d+)", re.IGNORECASE)


def _parse_audit_from_payload(payload: dict[str, Any]) -> AuditIssue:
    """Construct an :class:`AuditIssue` from a GH-signal payload."""
    title = payload.get("title", "")
    issue_number = int(payload.get("issue_number", 0))
    area_labels = list(payload.get("area_labels") or [])
    is_weekly = bool(_TITLE_WEEKLY_RE.match(title))
    triggering_sha: Optional[str] = None
    if not is_weekly:
        match = _TITLE_AUDIT_RE.match(title)
        if match:
            triggering_sha = match.group("sha")
    return AuditIssue(
        issue_number=issue_number,
        title=title,
        is_weekly=is_weekly,
        triggering_sha=triggering_sha,
        area_labels=area_labels,
        in_scope_docs=[],
        lock_acquired_at_utc=None,
    )


# ---------------------------------------------------------------------------
# Pending-approval cross-reference detection (T028)
# ---------------------------------------------------------------------------


def _build_pending_approval_index(
    pending_signals: list[Any],
) -> dict[int, int]:
    """Build an audit-number → pending-approval-issue-number map.

    Per the prompt T028 cross-reference pattern:
    - Title: ``"Audit #<N>: pending approval — ..."``
    - Body: ``"Refs #<N>"``

    For each open ``audit-pending-approval`` signal, extract the audit
    number it references (title regex first; body Refs regex as
    fallback) and map it to the pending-approval issue number.

    NOTE: This function takes the signal list emitted by
    ``GHIssueSignalSource.pending()``, which by design only includes
    pending-approvals that have a decision label applied. For the
    stale-lock cross-reference check (where an audit awaiting a
    decision is still an expected wait state, not a stale lock),
    use :func:`_build_pa_cross_reference_index` instead — that
    queries ALL open ``audit-pending-approval`` issues regardless
    of decision label.
    """
    index: dict[int, int] = {}
    for sig in pending_signals:
        if getattr(sig, "kind", "") != "pending_approval":
            continue
        payload = getattr(sig, "payload", {}) or {}
        pa_number = int(payload.get("issue_number", 0) or 0)
        title = payload.get("title", "") or ""
        body = payload.get("body", "") or ""
        audit_number: Optional[int] = None
        m = _AUDIT_REF_RE.search(title)
        if m:
            audit_number = int(m.group(1))
        else:
            m = _REFS_RE.search(body)
            if m:
                audit_number = int(m.group(1))
        if audit_number is not None and pa_number > 0:
            index[audit_number] = pa_number
    return index


def _build_pa_cross_reference_index(
    config: Config,
) -> dict[int, int]:
    """Return ``audit_number → pending_approval_number`` for ALL open
    ``audit-pending-approval`` issues.

    Unlike :class:`GHIssueSignalSource.pending` (which filters
    pending-approvals to only those with a decision label applied),
    this query enumerates every open ``audit-pending-approval``
    issue — including those still awaiting a decision.

    Both states (awaiting-decision AND decided) represent an
    EXPECTED wait state for the stuck-lock detector in
    :func:`_recover_stuck_locks`: the audit is correctly holding
    the ``status:in-progress`` label while operator action is
    pending. Treating awaiting-decision pending-approvals as
    "no matching PA" would cause an audit awaiting human decision
    to be flagged as a stale lock, the lock cleared, and the audit
    incorrectly reprocessed on the same tick.

    Rate-limit responses raise :class:`RateLimitError` so the
    orchestration loop can BREAK. Non-rate-limit failures return
    an empty dict (best-effort) — the stuck-lock check then
    degrades to "no PA matches found", which is conservative
    (more audits flagged as stuck, but no false-negative stuck
    locks). The shape mirrors :func:`_fetch_in_progress_audits`.
    """
    cmd = [
        "gh",
        "issue",
        "list",
        "--repo",
        config.github.repo,
        "--label",
        "audit-pending-approval",
        "--state",
        "open",
        "--json",
        "number,title,body",
    ]
    try:
        completed = subprocess.run(
            cmd, capture_output=True, text=True, check=True
        )
    except subprocess.CalledProcessError as exc:
        if _is_rate_limited(exc):
            raise RateLimitError(
                "GH rate-limit during pending-approval cross-ref query"
            ) from exc
        logger.warning(
            "pending-approval cross-ref query failed (rc=%s): %s",
            exc.returncode,
            (exc.stderr or "").strip(),
        )
        return {}

    import json as _json
    try:
        pas = _json.loads(completed.stdout or "[]")
    except _json.JSONDecodeError:
        return {}
    if not isinstance(pas, list):
        return {}

    index: dict[int, int] = {}
    for pa in pas:
        if not isinstance(pa, dict):
            continue
        try:
            pa_number = int(pa.get("number", 0) or 0)
        except (TypeError, ValueError):
            continue
        if pa_number <= 0:
            continue
        title = str(pa.get("title", "") or "")
        body = str(pa.get("body", "") or "")
        m = _AUDIT_REF_RE.search(title)
        if m:
            try:
                index[int(m.group(1))] = pa_number
                continue
            except ValueError:
                pass
        m = _REFS_RE.search(body)
        if m:
            try:
                index[int(m.group(1))] = pa_number
            except ValueError:
                continue
    return index


# ---------------------------------------------------------------------------
# Signal-source construction
# ---------------------------------------------------------------------------


def _build_sources(
    config: Config, args: argparse.Namespace
) -> list[Any]:
    """Build the enabled signal-source adapters.

    Honors ``--source`` to restrict to one adapter for incremental
    testing. Production omits ``--source``, which yields both adapters.
    """
    sources: list[Any] = []
    enabled = set(config.signals.sources)
    if args.source is not None:
        # Restrict to the single requested adapter; ignore the config
        # enabled-set so operator can isolate one source even if both
        # are enabled in config.
        enabled = {args.source}
    if "drift_event" in enabled:
        sources.append(DriftEventSignalSource(config))
    if "gh_issue" in enabled:
        sources.append(GHIssueSignalSource(config))
    return sources


# ---------------------------------------------------------------------------
# Drift-event processing
# ---------------------------------------------------------------------------


def _process_drift_events(
    source: DriftEventSignalSource,
    config: Config,
    args: argparse.Namespace,
    result: TickResult,
) -> None:
    """Process all drift-event signals via the adapter's commit().

    Each successful commit advances the cursor through the helper's
    atomic primitives. Failures append to ``result.errors`` but do NOT
    short-circuit the rest of the tick — the GH-issue scan still runs.
    """
    try:
        signals = list(source.pending())
    except Exception as exc:
        msg = f"drift_event.pending failed: {type(exc).__name__}: {exc}"
        logger.error(msg)
        result.errors.append(msg)
        result.status = "partial"
        return

    for signal in signals:
        if args.dry_run:
            # In dry-run we don't commit; just count what would have
            # happened. The cursor stays at its original position.
            result.drift_events_consumed += 1
            continue
        try:
            source.commit(signal, "success")
            result.drift_events_consumed += 1
        except Exception as exc:
            msg = (
                f"drift_event.commit failed on {signal.id}: "
                f"{type(exc).__name__}: {exc}"
            )
            logger.error(msg)
            result.errors.append(msg)
            result.status = "partial"


# ---------------------------------------------------------------------------
# Stuck-lock recovery (T028)
# ---------------------------------------------------------------------------


def _fetch_in_progress_audits(
    config: Config,
) -> list[dict[str, Any]]:
    """Query open audit issues that carry the ``status:in-progress`` label.

    Returns the raw ``gh issue list`` JSON entries so callers can
    introspect labels and timeline. Errors propagate.
    """
    cmd = [
        "gh",
        "issue",
        "list",
        "--repo",
        config.github.repo,
        "--label",
        "doc-audit",
        "--label",
        "status:in-progress",
        "--state",
        "open",
        "--json",
        "number,title,labels,body,createdAt,updatedAt",
    ]
    try:
        completed = subprocess.run(
            cmd, capture_output=True, text=True, check=True
        )
    except subprocess.CalledProcessError as exc:
        if _is_rate_limited(exc):
            raise RateLimitError(
                "GH rate-limit during in-progress audit query"
            ) from exc
        raise

    import json as _json
    try:
        parsed = _json.loads(completed.stdout or "[]")
    except _json.JSONDecodeError:
        return []
    if not isinstance(parsed, list):
        return []
    return parsed


def _recover_stuck_locks(
    config: Config,
    pending_approval_index: dict[int, int],
    args: argparse.Namespace,
    result: TickResult,
) -> list[Signal]:
    """Detect stuck locks per FR-014 and PROCESS THEM IN THE CURRENT TICK.

    Cycle-2 change vs cycle-1: an in-progress audit with NO matching
    pending-approval is treated as a fresh signal in THIS tick (option
    "b" from the WP06 prompt). The driver clears the lock label, then
    synthesizes a Signal so the normal ``_process_audit_signal`` path
    re-runs the workflow.

    Returns the list of synthesized signals (zero-length when no stuck
    locks were found). The caller appends them to the main signal
    queue.

    A recovery marker is appended to ``result.errors`` for each
    recovered audit so operators see the recovery in the tick signal.
    """
    recovered: list[Signal] = []
    try:
        in_progress = _fetch_in_progress_audits(config)
    except RateLimitError:
        raise
    except Exception as exc:
        msg = (
            f"stuck-lock recovery query failed: "
            f"{type(exc).__name__}: {exc}"
        )
        logger.warning(msg)
        result.errors.append(msg)
        return recovered

    for issue in in_progress:
        try:
            number = int(issue.get("number", 0))
        except (TypeError, ValueError):
            continue
        if number <= 0:
            continue
        # Defense-in-depth: confirm the issue actually carries the
        # status:in-progress label. Some gh mock surfaces in tests
        # return the same payload for any label query — we must not
        # mistake a fresh audit (which happens to also be enumerable
        # under the doc-audit label) for a stuck lock.
        labels_raw = issue.get("labels") or []
        label_names = [
            (lbl.get("name") if isinstance(lbl, dict) else str(lbl))
            for lbl in labels_raw
        ]
        if "status:in-progress" not in label_names:
            continue
        if number in pending_approval_index:
            # Expected wait state — there's a matching open
            # pending-approval. Not a stuck lock.
            continue
        # Stuck lock: in-progress with no pending-approval reference.
        marker = (
            f"recovered-stale-lock: audit #{number} had status:in-progress "
            f"with no matching pending-approval; clearing lock + "
            f"re-processing in this tick"
        )
        logger.warning(marker)
        result.errors.append(marker)
        if not args.dry_run:
            # Clear the lock label first. The audit workflow will
            # re-acquire it via ``_acquire_lock`` as the synthesized
            # signal is processed.
            _remove_in_progress_label(config, number, result)

        # Synthesize a fresh signal so the main signal loop processes
        # this audit normally. The title/body/labels mirror what the
        # signal source would emit; ``payload.stale_lock = True`` is a
        # marker the workflow can read for telemetry but does not
        # change the dispatch path.
        title = str(issue.get("title", ""))
        is_weekly = title.startswith("Weekly doc audit —")
        kind = "weekly_doc_audit" if is_weekly else "doc_audit"
        priority = 30 if is_weekly else 20
        area_labels = [n for n in label_names if n and n.startswith("area/")]
        signal = Signal(
            id=f"gh-issue:{number}",
            source="gh_issue",
            kind=kind,
            priority=priority,
            payload={
                "issue_number": number,
                "title": title,
                "body": str(issue.get("body", "")),
                "labels": label_names,
                "area_labels": area_labels,
                "stale_lock": True,
            },
            created_utc=str(issue.get("createdAt", "")),
        )
        recovered.append(signal)
    return recovered


def _remove_in_progress_label(
    config: Config, issue_number: int, result: TickResult
) -> None:
    """Strip the ``status:in-progress`` label as part of stale-lock recovery."""
    cmd = [
        "gh",
        "issue",
        "edit",
        str(issue_number),
        "--repo",
        config.github.repo,
        "--remove-label",
        "status:in-progress",
    ]
    try:
        subprocess.run(cmd, capture_output=True, text=True, check=True)
    except subprocess.CalledProcessError as exc:
        if _is_rate_limited(exc):
            raise RateLimitError(
                f"GH rate-limit while clearing stale lock on #{issue_number}"
            ) from exc
        msg = (
            f"could not clear stale lock on #{issue_number}: "
            f"rc={exc.returncode} stderr={(exc.stderr or '').strip()!r}"
        )
        logger.warning(msg)
        result.errors.append(msg)


# ---------------------------------------------------------------------------
# Audit workflow helpers (T027 step 4 — wire the actual audit pipeline)
# ---------------------------------------------------------------------------


# Constitutional guardrail patterns (SKILL.md §4.3). A doc path that
# matches ANY of these MUST be treated as "guardrailed" — the driver
# never auto-edits it, even if tier_classification would have said
# tier_a. The check is path-based + case-insensitive on a few markers.
_GUARDRAIL_PATTERNS = (
    "docs/constitution/FELIX-CONSTITUTION.md",
    "CLAUDE.md",
    ".env",
    "credentials.json",
    "kitty-specs/",
    ".kittify/",
)


def _is_guardrailed_path(doc_path: str) -> bool:
    """Return True when ``doc_path`` matches a SKILL.md §4.3 guardrail.

    The check is conservative:
    - Constitution file is matched by suffix (any prefix path is fine).
    - ``CLAUDE.md`` matches at any level of the tree.
    - ``.env`` and ``credentials.json`` match as basename/suffix.
    - ``kitty-specs/`` and ``.kittify/`` match as a prefix of the
      normalized path.
    """
    if not doc_path:
        return False
    normalized = doc_path.replace("\\", "/")
    # Strip a leading "./" prefix only (NOT arbitrary "." or "/" chars
    # via lstrip — that would mangle ".kittify/" etc.).
    if normalized.startswith("./"):
        normalized = normalized[2:]
    base = normalized.rsplit("/", 1)[-1]
    if normalized.endswith("docs/constitution/FELIX-CONSTITUTION.md"):
        return True
    if base == "CLAUDE.md":
        return True
    if base.startswith(".env"):
        return True
    if base == "credentials.json":
        return True
    if normalized.startswith("kitty-specs/") or "/kitty-specs/" in normalized:
        return True
    if normalized.startswith(".kittify/") or "/.kittify/" in normalized:
        return True
    return False


def _load_doc_domain_map(config: Config) -> dict[str, list[str]]:
    """Load ``docs/design/architecture/data/doc-domain-map.json``.

    Returns the ``domains`` dict (label → list[doc-path]). A missing
    or malformed file yields an empty dict — the workflow gracefully
    degrades to zero in-scope docs and the routing layer still gets
    invoked with empty inputs (audit closes as a no-op).
    """
    map_path = Path(config.paths.doc_domain_map)
    try:
        raw = map_path.read_text(encoding="utf-8")
    except FileNotFoundError:
        logger.info(
            "doc-domain-map not found at %s; in-scope docs empty",
            map_path,
        )
        return {}
    import json as _json
    try:
        parsed = _json.loads(raw or "{}")
    except _json.JSONDecodeError as exc:
        logger.warning(
            "doc-domain-map at %s is not valid JSON: %s; in-scope docs empty",
            map_path,
            exc,
        )
        return {}
    if not isinstance(parsed, dict):
        return {}
    domains = parsed.get("domains")
    if not isinstance(domains, dict):
        return {}
    # Normalize: each value must be list[str]; drop anything else.
    normalized: dict[str, list[str]] = {}
    for label, paths in domains.items():
        if isinstance(label, str) and isinstance(paths, list):
            normalized[label] = [
                p for p in paths if isinstance(p, str) and p
            ]
    return normalized


def _resolve_in_scope_docs(
    audit: AuditIssue, domain_map: dict[str, list[str]]
) -> list[str]:
    """Intersect ``audit.area_labels`` with the doc-domain map.

    Returns the deduplicated, order-preserving union of docs the audit
    touches. An empty ``area_labels`` (weekly audit, full scope) returns
    the union of ALL docs in the map.
    """
    if not domain_map:
        return []
    seen: set[str] = set()
    result_list: list[str] = []
    if not audit.area_labels:
        # Full-scope (weekly): union of all values in the map.
        for label_paths in domain_map.values():
            for path in label_paths:
                if path not in seen:
                    seen.add(path)
                    result_list.append(path)
        return result_list
    for label in audit.area_labels:
        for path in domain_map.get(label, []):
            if path not in seen:
                seen.add(path)
                result_list.append(path)
    return result_list


def _fetch_diff_for_sha(sha: str) -> str:
    """Best-effort ``git show <sha>`` for the audit's triggering commit.

    Returns the raw stdout. Failures return ``""`` — the workflow
    treats "no diff available" as "no candidate edits derivable" and
    the routing layer is invoked with empty inputs.

    Catches BaseException defensively because tests routinely patch
    ``subprocess.run`` with fake routers that ``raise RuntimeError``
    on any non-``gh`` argv. The diff fetch is a non-essential
    enrichment step; refusing to swallow those errors would break
    every test that doesn't explicitly mock ``git show``.
    """
    if not sha:
        return ""
    try:
        completed = subprocess.run(
            ["git", "show", "--stat", "--patch", sha],
            capture_output=True,
            text=True,
            check=True,
            timeout=10,
        )
    except Exception as exc:  # noqa: BLE001
        logger.info(
            "git show %s unavailable (%s); proceeding with empty diff",
            sha,
            type(exc).__name__,
        )
        return ""
    return completed.stdout or ""


# ``+++ b/<path>`` lines in a unified diff identify files touched by
# the commit. Parsed to derive both the touched-files list (for
# cross_file_implication) and to seed candidate-edit derivation.
_DIFF_TOUCHED_RE = re.compile(r"^\+\+\+\s+b/(.+?)\s*$", re.MULTILINE)
# Frontmatter date bump candidate: a ``+`` line that updates a
# ``last_validated:`` (or similar) date field next to a ``-`` line.
_FRONTMATTER_DATE_RE = re.compile(
    r"^-\s*(?P<field>last_validated|last_updated|updated|date):\s*(?P<old>\S+).*\n"
    r"\+\s*(?P=field):\s*(?P<new>\S+)",
    re.MULTILINE,
)


def _parse_touched_files(diff: str) -> list[str]:
    """Extract the list of files touched by the diff (``+++ b/<path>``)."""
    seen: set[str] = set()
    out: list[str] = []
    for match in _DIFF_TOUCHED_RE.finditer(diff):
        path = match.group(1).strip()
        if path and path not in seen and path != "/dev/null":
            seen.add(path)
            out.append(path)
    return out


def _derive_candidate_edits(
    diff: str, audit: AuditIssue, in_scope_docs: list[str]
) -> list[ProposedEdit]:
    """Derive a list of :class:`ProposedEdit` candidates from a diff.

    This is a deliberately conservative deterministic extraction —
    only frontmatter date bumps that already exist in the commit are
    surfaced. The LLM then classifies each via ``tier_classification``;
    JUDGMENT verdicts become debt issues, TIER_A/B verdicts stay in
    the proposed_edits list and feed the routing layer.

    The driver intentionally does NOT attempt to derive arbitrary
    semantic edits from a diff — those flow through the audit issue
    body composed by upstream producers (commit-trigger, weekly cron).
    For WP06's MVP this is enough surface to exercise the pipeline
    end-to-end; richer derivation is a follow-up mission.
    """
    if not diff:
        return []
    in_scope_set = set(in_scope_docs)
    out: list[ProposedEdit] = []
    # Walk per-file blocks to associate edits with their target path.
    file_blocks = re.split(
        r"^diff --git a/.+? b/.+?$",
        diff,
        flags=re.MULTILINE,
    )
    file_headers = re.findall(
        r"^diff --git a/.+? b/(.+?)$",
        diff,
        flags=re.MULTILINE,
    )
    # ``file_blocks`` is one longer than headers (preamble before first
    # diff --git header); zip with headers gives us (path, block) pairs.
    for path, block in zip(file_headers, file_blocks[1:]):
        if in_scope_set and path not in in_scope_set:
            # Out-of-scope file in the diff; skip — the audit didn't
            # ask us to touch it.
            continue
        for match in _FRONTMATTER_DATE_RE.finditer(block):
            old = match.group("old")
            new = match.group("new")
            if old == new:
                continue
            out.append(
                ProposedEdit(
                    doc_path=path,
                    change_type="frontmatter_field_bump",
                    current_value=old,
                    proposed_value=new,
                    evidence_source=(
                        f"git show {audit.triggering_sha or '(unknown)'}"
                    ),
                    tier="",  # filled after tier_classification
                    confidence="high",
                )
            )
    return out


def _frontmatter_excerpt(doc_path: str, repo_root: Path) -> str:
    """Return the YAML frontmatter excerpt of ``doc_path`` for context.

    Reads at most ~40 lines from the top of the file; if the file is
    missing or has no frontmatter, returns ``"(unavailable)"``. The
    excerpt is fed verbatim into ``tier_classification.classify``.
    """
    file_path = repo_root / doc_path
    try:
        text = file_path.read_text(encoding="utf-8")
    except (FileNotFoundError, OSError):
        return "(unavailable)"
    lines = text.splitlines()
    # Frontmatter sits between two ``---`` markers if present.
    if lines and lines[0].strip() == "---":
        out: list[str] = ["---"]
        for line in lines[1:40]:
            out.append(line)
            if line.strip() == "---":
                break
        return "\n".join(out)
    # No frontmatter: return the first 10 lines as raw context.
    return "\n".join(lines[:10])


def _detect_missing_artifacts(
    config: Config, audit: AuditIssue, repo_root: Path
) -> list[DebtIssue]:
    """SKILL.md §6 deterministic missing-artifact detection.

    Compare agent-registry.json entries to runbook file existence.
    A registered agent with no runbook at the expected path is a
    missing artifact → file a DebtIssue.

    Only runs when the audit's scope touches felix governance (any
    ``area/felix-core`` or empty/full-scope). Other-domain audits skip
    this check for efficiency.
    """
    # Scope gate: full-scope (weekly) and felix-core audits trigger
    # the check; other-domain audits skip.
    if audit.area_labels and "area/felix-core" not in audit.area_labels:
        return []

    registry_path = repo_root / "docs/constitution/agent-registry.json"
    try:
        raw = registry_path.read_text(encoding="utf-8")
    except (FileNotFoundError, OSError):
        return []
    import json as _json
    try:
        parsed = _json.loads(raw)
    except _json.JSONDecodeError:
        return []
    if not isinstance(parsed, dict):
        return []
    agents = parsed.get("agents")
    if not isinstance(agents, dict):
        return []

    out: list[DebtIssue] = []
    for agent_slug, _meta in agents.items():
        if not isinstance(agent_slug, str):
            continue
        # Expected runbook path: docs/runbooks/<slug>-ops.md OR
        # docs/runbooks/<slug>.md. The naming convention varies
        # (felix-doc-auditor → doc-auditor-ops.md, etc.) so we accept
        # any variant containing the slug stem.
        stem = agent_slug.removeprefix("felix-")
        candidates = [
            f"docs/runbooks/{agent_slug}-ops.md",
            f"docs/runbooks/{agent_slug}.md",
            f"docs/runbooks/{stem}-ops.md",
            f"docs/runbooks/{stem}.md",
        ]
        if any((repo_root / c).is_file() for c in candidates):
            continue
        # Missing runbook → file a debt issue stub. The actual body is
        # filled by debt_body_generation downstream when we wire LLM
        # calls; until then this stub carries enough metadata for the
        # routing layer to see the gap.
        out.append(
            DebtIssue(
                title=f"Docs: missing runbook for agent {agent_slug}",
                artifact_path=f"docs/runbooks/{agent_slug}-ops.md",
                gap_description=(
                    f"Agent {agent_slug!r} is registered in "
                    "agent-registry.json but has no matching runbook "
                    f"at any of: {candidates}"
                ),
                area_labels=list(audit.area_labels) or ["area/felix-core"],
                cross_references=[f"#{audit.issue_number}"],
                draft_outline="",
                success_criteria=[
                    f"Runbook file exists at docs/runbooks/{agent_slug}-ops.md",
                    "Runbook links from docs/INDEX.md",
                ],
                is_missing_artifact=True,
            )
        )
    return out


def _classify_proposed_edits(
    client: JudgmentClient,
    audit: AuditIssue,
    candidate_edits: list[ProposedEdit],
    repo_root: Path,
    result: TickResult,
) -> tuple[list[ProposedEdit], list[dict[str, Any]]]:
    """Run tier_classification per candidate edit; partition by verdict.

    Returns ``(proposed_edits, judgment_findings)``:
    - ``proposed_edits``: TIER_A and TIER_B verdicts retained with a
      filled ``tier`` field. These flow through the routing layer.
    - ``judgment_findings``: JUDGMENT verdicts surfaced as gap dicts
      ``{"doc_path", "gap_description", "evidence_source", "rationale"}``.
      Each becomes a DebtIssue (after a debt_body_generation pass).

    Token counts and call counts are accumulated into ``result``.
    """
    proposed: list[ProposedEdit] = []
    judgment_findings: list[dict[str, Any]] = []
    for edit in candidate_edits:
        guardrail = (
            "guardrailed"
            if _is_guardrailed_path(edit.doc_path)
            else "not_guardrailed"
        )
        excerpt = _frontmatter_excerpt(edit.doc_path, repo_root)
        try:
            tier, rationale, response = tier_classification.classify(
                client,
                edit,
                audit.area_labels,
                excerpt,
                guardrail,
            )
        except Exception as exc:
            msg = (
                f"tier_classification failed for {edit.doc_path}: "
                f"{type(exc).__name__}: {exc}"
            )
            logger.warning(msg)
            result.errors.append(msg)
            # Cycle-4: a judgment-helper exception is a partial-result
            # condition — the workflow continues (we still file a debt
            # issue noting the gap so the operator can adjudicate), but
            # the tick can no longer claim full success.
            if result.status == "success":
                result.status = "partial"
            # Defensive: treat as JUDGMENT so we still file a debt issue
            # noting the gap and the operator can adjudicate.
            judgment_findings.append({
                "doc_path": edit.doc_path,
                "gap_description": (
                    f"tier_classification could not be completed; raw "
                    f"diff suggests {edit.change_type} from "
                    f"{edit.current_value!r} to {edit.proposed_value!r}."
                ),
                "evidence_source": edit.evidence_source,
                "rationale": f"classifier error: {type(exc).__name__}",
            })
            continue
        # Roll telemetry.
        result.judgment_calls["tier_classification"] = (
            result.judgment_calls.get("tier_classification", 0) + 1
        )
        _accumulate_token_usage(result, response)
        if tier == EditTier.JUDGMENT:
            judgment_findings.append({
                "doc_path": edit.doc_path,
                "gap_description": (
                    f"{edit.change_type} on {edit.doc_path}: "
                    f"{edit.current_value!r} → {edit.proposed_value!r}. "
                    f"Classifier rationale: {rationale}"
                ),
                "evidence_source": edit.evidence_source,
                "rationale": rationale,
            })
            continue
        # TIER_A or TIER_B: build a new ProposedEdit with the filled
        # tier value. ProposedEdit is frozen so we construct a fresh
        # instance.
        proposed.append(
            ProposedEdit(
                doc_path=edit.doc_path,
                change_type=edit.change_type,
                current_value=edit.current_value,
                proposed_value=edit.proposed_value,
                evidence_source=edit.evidence_source,
                tier=tier.value,
                confidence=edit.confidence or "high",
            )
        )
    return proposed, judgment_findings


def _run_cross_file_implication(
    client: JudgmentClient,
    audit: AuditIssue,
    diff: str,
    touched_files: list[str],
    in_scope_docs: list[str],
    result: TickResult,
) -> list[dict[str, Any]]:
    """Detect implied drift on non-touched in-scope docs.

    Skipped (returns ``[]``) when ``in_scope_docs`` is empty or there
    are no non-touched files (everything in scope was already edited
    by the commit). Token counts are rolled into ``result``.
    """
    if not in_scope_docs:
        return []
    untouched = [p for p in in_scope_docs if p not in set(touched_files)]
    if not untouched:
        return []
    summary = audit.title or "(no title)"
    # Truncate the diff if it's enormous — Anthropic context budget.
    diff_excerpt = diff[:8000] if diff else "(no diff available)"
    try:
        implications, response = cross_file_implication.detect(
            client,
            triggering_event_kind=(
                "weekly_doc_audit" if audit.is_weekly else "doc_audit"
            ),
            triggering_event_summary=summary,
            diff_excerpt=diff_excerpt,
            touched_files=touched_files,
            in_scope_files=in_scope_docs,
            domain_labels=audit.area_labels,
        )
    except Exception as exc:
        msg = (
            f"cross_file_implication failed: "
            f"{type(exc).__name__}: {exc}"
        )
        logger.warning(msg)
        result.errors.append(msg)
        # Cycle-4: judgment-helper exception bumps status to partial.
        if result.status == "success":
            result.status = "partial"
        return []
    result.judgment_calls["cross_file_implication"] = (
        result.judgment_calls.get("cross_file_implication", 0) + 1
    )
    _accumulate_token_usage(result, response)
    return implications


def _generate_debt_bodies(
    client: JudgmentClient,
    audit: AuditIssue,
    findings: list[dict[str, Any]],
    result: TickResult,
) -> list[DebtIssue]:
    """For each judgment finding, run debt_body_generation to compose body.

    The generated body is stored on ``DebtIssue.draft_outline`` (the
    load-bearing field per SKILL.md §8). When generation fails the
    finding still becomes a DebtIssue with a stub body so the gap
    isn't lost.
    """
    out: list[DebtIssue] = []
    for finding in findings:
        doc_path = finding.get("doc_path", "")
        gap = finding.get("gap_description", "")
        evidence = finding.get("evidence_source", "")
        try:
            generated, response = debt_body_generation.generate(
                client,
                artifact_path=doc_path,
                gap_description=gap,
                evidence_source=evidence,
                area_labels=audit.area_labels,
                originating_audit_number=audit.issue_number,
                cross_references=[],
            )
            body = generated.body
        except Exception as exc:
            msg = (
                f"debt_body_generation failed for {doc_path}: "
                f"{type(exc).__name__}: {exc}"
            )
            logger.warning(msg)
            result.errors.append(msg)
            # Cycle-4: judgment-helper exception bumps status to partial.
            # Generation still produces a stub DebtIssue (operator gets
            # the gap surfaced) but the tick is no longer fully clean.
            if result.status == "success":
                result.status = "partial"
            body = (
                f"## Gap description\n{gap}\n\n## Evidence\n{evidence}\n"
            )
        else:
            result.judgment_calls["debt_body_generation"] = (
                result.judgment_calls.get("debt_body_generation", 0) + 1
            )
            _accumulate_token_usage(result, response)
        title_prefix = "Docs"
        if "area/biz-ops" in audit.area_labels:
            title_prefix = "Docs (biz-ops)"
        short_title = doc_path or "judgment gap"
        out.append(
            DebtIssue(
                title=f"{title_prefix}: judgment gap on {short_title}",
                artifact_path=doc_path,
                gap_description=gap,
                area_labels=list(audit.area_labels),
                cross_references=[f"#{audit.issue_number}"],
                draft_outline=body,
                success_criteria=[
                    f"Resolve the gap noted on {doc_path}",
                    "Cross-link the resolution to the originating audit",
                ],
                is_missing_artifact=False,
            )
        )
    return out


def _accumulate_token_usage(
    result: TickResult, response: JudgmentResponse | None
) -> None:
    """Roll one judgment response's token counts into the tick total."""
    if response is None:
        return
    usage = result.token_usage
    usage["input_tokens"] = (
        usage.get("input_tokens", 0) + int(response.input_tokens or 0)
    )
    usage["cache_hit_input_tokens"] = (
        usage.get("cache_hit_input_tokens", 0)
        + int(response.cache_hit_input_tokens or 0)
    )
    usage["output_tokens"] = (
        usage.get("output_tokens", 0) + int(response.output_tokens or 0)
    )


# ---------------------------------------------------------------------------
# Lock acquisition (T027 step 4 / SKILL.md §8.7)
# ---------------------------------------------------------------------------


def _acquire_lock(
    config: Config, issue_number: int, result: TickResult, dry_run: bool
) -> bool:
    """Add ``status:in-progress`` to an audit issue (best-effort).

    Returns True on success or dry-run, False on a non-rate-limit
    failure. Rate-limit failures propagate as :class:`RateLimitError`
    so the orchestration loop can BREAK.

    The lock is best-effort: if `gh` rejects the label add (label
    missing, permissions, etc.) we log + continue. The downstream
    routing still happens — the lock is a coordination signal, not a
    correctness invariant.
    """
    if dry_run:
        return True
    cmd = [
        "gh", "issue", "edit", str(issue_number),
        "--repo", config.github.repo,
        "--add-label", "status:in-progress",
    ]
    try:
        subprocess.run(cmd, capture_output=True, text=True, check=True)
        return True
    except subprocess.CalledProcessError as exc:
        if _is_rate_limited(exc):
            raise RateLimitError(
                f"GH rate-limit acquiring lock on audit #{issue_number}"
            ) from exc
        msg = (
            f"lock acquisition failed for #{issue_number}: "
            f"rc={exc.returncode} stderr={(exc.stderr or '').strip()!r}"
        )
        logger.warning(msg)
        result.errors.append(msg)
        return False


# ---------------------------------------------------------------------------
# Audit processing (doc_audit / weekly_doc_audit)
# ---------------------------------------------------------------------------


# Repo-root resolution: the driver is at scripts/doc_audit/run.py; the
# repo root is two levels up. This is stable across both production
# (office2 systemd) and test (worktree) invocations.
_REPO_ROOT = Path(__file__).resolve().parent.parent.parent


def _process_audit_signal(
    signal: Any,
    config: Config,
    args: argparse.Namespace,
    result: TickResult,
    judgment_client: JudgmentClient | None = None,
) -> None:
    """Process one ``doc_audit`` / ``weekly_doc_audit`` signal.

    Cycle-2 wires the audit workflow end-to-end (cycle-1 was a shell
    that passed empty lists to routing). The workflow is:

    1. Parse the audit metadata from the signal payload.
    2. Acquire the ``status:in-progress`` lock (T027 step 4).
    3. Resolve in-scope docs via doc-domain-map intersection.
    4. Get the triggering commit diff (best-effort via ``git show``).
    5. Derive candidate ProposedEdit instances from the diff.
    6. Per candidate edit: compute the guardrail check result, then
       call ``tier_classification.classify`` to partition into
       proposed_edits vs judgment_findings.
    7. Run deterministic missing-artifact detection (SKILL.md §6).
    8. For non-touched in-scope docs: call ``cross_file_implication``
       to surface implied drift.
    9. For each judgment finding: call ``debt_body_generation`` to
       produce a structured DebtIssue body.
    10. Invoke the routing layer with the populated lists.

    Edge cases handled:
    - **No SHA / weekly audit**: diff fetch returns empty; no candidate
      edits derived; routing layer still invoked with empty lists
      (audit closes as a no-op).
    - **Domain map missing/malformed**: in-scope docs empty; same
      no-op fallthrough.
    - **Missing file**: routing layer raises ``FileNotFoundError`` —
      caught in the outer ``_process_signal``.
    - **Rate limit at any subprocess boundary**: ``RateLimitError``
      propagates; orchestration loop BREAKs.
    """
    audit = _parse_audit_from_payload(signal.payload)

    if args.dry_run:
        result.signals_processed += 1
        logger.info("DRY-RUN: would process audit #%d", audit.issue_number)
        _log_audit_outcome(
            config, result, audit,
            outcome={"decision_applied": "dry-run"},
        )
        return

    # Step 2: acquire the lock. A failure here is non-fatal — we still
    # process the audit; the lock is a coordination hint.
    _acquire_lock(config, audit.issue_number, result, args.dry_run)

    # Step 3: resolve in-scope docs (domain map intersection).
    domain_map = _load_doc_domain_map(config)
    in_scope_docs = _resolve_in_scope_docs(audit, domain_map)
    audit.in_scope_docs = list(in_scope_docs)

    # Step 4: fetch the triggering commit diff. Weekly audits + audits
    # with no SHA yield empty diff (workflow gracefully degrades).
    diff = _fetch_diff_for_sha(audit.triggering_sha or "")
    touched_files = _parse_touched_files(diff)

    # Step 5: derive candidate edits from the diff.
    candidate_edits = _derive_candidate_edits(diff, audit, in_scope_docs)

    # Step 6: classify each candidate via tier_classification.
    proposed_edits: list[ProposedEdit] = []
    judgment_findings: list[dict[str, Any]] = []
    if candidate_edits:
        # Lazy JudgmentClient construction — tests that don't exercise
        # the LLM path skip the client (and its anthropic.Anthropic()
        # call) entirely.
        client = judgment_client or JudgmentClient(config)
        proposed_edits, judgment_findings = _classify_proposed_edits(
            client, audit, candidate_edits, _REPO_ROOT, result,
        )

    # Step 7: deterministic missing-artifact detection.
    missing_debt = _detect_missing_artifacts(config, audit, _REPO_ROOT)

    # Step 8: cross_file_implication on non-touched in-scope docs.
    # Only run when we have judgment moments to make (in-scope docs
    # exist + we have a client — i.e., we made a tier_classification
    # call). Skip if no candidate_edits because that already means
    # there's nothing useful to compare against.
    implications: list[dict[str, Any]] = []
    if candidate_edits and in_scope_docs:
        client = judgment_client or JudgmentClient(config)
        implications = _run_cross_file_implication(
            client, audit, diff, touched_files, in_scope_docs, result,
        )
    # Each implication becomes another judgment finding (debt body).
    for impl in implications:
        judgment_findings.append({
            "doc_path": impl["untouched_file"],
            "gap_description": impl["implication"],
            "evidence_source": impl["evidence"],
            "rationale": "cross_file_implication",
        })

    # Step 9: generate debt-issue bodies for each judgment finding.
    debt_issues: list[DebtIssue] = list(missing_debt)
    if judgment_findings:
        client = judgment_client or JudgmentClient(config)
        debt_issues.extend(
            _generate_debt_bodies(client, audit, judgment_findings, result)
        )

    # Routing layer's pre-filed lists are issue-number dicts; cycle 2
    # does not yet file debt issues itself (the routing helper does
    # not file debt either — it just consumes the counts). We pass the
    # DebtIssue dataclass instances on the typed parameter for
    # forward-compat; the missing_artifacts param stays empty until
    # debt-filing lands in a follow-up mission.
    missing_artifacts: list[dict[str, Any]] = []

    # Step 10: routing layer.
    try:
        routing_result = apply_routing(
            config,
            audit,
            proposed_edits,
            debt_issues,
            missing_artifacts,
        )
    except subprocess.CalledProcessError as exc:
        if _is_rate_limited(exc):
            raise RateLimitError(
                f"GH rate-limit during audit #{audit.issue_number} routing"
            ) from exc
        raise

    _accumulate_routing_result(routing_result, result)

    outcome = _outcome_from_routing(routing_result)
    if signal.kind == "weekly_doc_audit":
        outcome.setdefault("decision_applied", "weekly")
    # Cycle-2 telemetry: surface the count of judgment findings the
    # workflow surfaced (separate from routing-debt) so the activity
    # log entry reflects the LLM-touched gaps.
    outcome["judgment_findings"] = len(judgment_findings)
    _log_audit_outcome(config, result, audit, outcome=outcome)


def _accumulate_routing_result(
    routing_result: RoutingResult, result: TickResult
) -> None:
    """Roll a :class:`RoutingResult` into the per-tick :class:`TickResult`.

    Routing outcomes contribute to the tick-signal counters operators
    consume. Errors from routing become entries in ``result.errors``;
    a non-zero ``exit_code`` from the helper means the tick is at
    BEST partial.
    """
    if routing_result.applied_count:
        # The helper produced a single commit for the auto-apply set.
        # We don't know the SHA from this surface; record a placeholder
        # so the count is visible in the tick signal.
        result.tier_a_commits.extend(
            [f"audit-applied:{routing_result.applied_count}"]
        )
    if routing_result.pending_approval_issue is not None:
        result.pending_approvals_filed.append(
            int(routing_result.pending_approval_issue)
        )
    if routing_result.debt_issues:
        result.debt_filed.extend(int(n) for n in routing_result.debt_issues)
    for err in routing_result.errors:
        result.errors.append(f"routing: {err}")
    if routing_result.exit_code not in (0,):
        # Routing failed at some leg — tick is at best partial.
        if result.status == "success":
            result.status = "partial"


def _outcome_from_routing(routing_result: RoutingResult) -> dict[str, Any]:
    """Render a per-audit outcome dict from a :class:`RoutingResult`."""
    if routing_result.pending_approval_issue is not None:
        pa = f"#{routing_result.pending_approval_issue}"
    else:
        pa = "none"
    debt_refs = ""
    if routing_result.debt_issues:
        debt_refs = ", ".join(f"#{n}" for n in routing_result.debt_issues)
    return {
        "edits_committed": routing_result.applied_count,
        "pending_approval_issue": pa,
        "debt_issues_created": len(routing_result.debt_issues),
        "debt_issue_refs": debt_refs,
        "missing_artifacts": len(routing_result.missing_issues),
        "error_count": len(routing_result.errors),
        "decision_applied": (
            "audit-approve" if routing_result.applied_count else "none"
        ),
    }


# ---------------------------------------------------------------------------
# Pending-approval processing (priority 10)
# ---------------------------------------------------------------------------


def _process_pending_approval(
    signal: Any,
    config: Config,
    args: argparse.Namespace,
    result: TickResult,
) -> None:
    """Apply a labeled pending-approval decision.

    Decision label semantics (per SKILL.md §8.6):
    - ``audit-approve`` → apply the gated edits + commit + close.
    - ``audit-reject`` → demote gated edits to debt issues + close.
    - ``audit-skip`` → close both issues with a skip note.

    Self-apply guard (FR-008): if the actor who applied the decision
    label is the same identity as the bot that filed the issue, the
    decision is REFUSED — we never auto-apply our own gate.
    """
    payload = signal.payload or {}
    labels = payload.get("labels") or []
    pa_number = int(payload.get("issue_number", 0))
    area_labels = list(payload.get("area_labels") or [])

    decision: Optional[str] = None
    for label in ("audit-approve", "audit-reject", "audit-skip"):
        if label in labels:
            decision = label
            break

    if decision is None:
        # GHIssueSignalSource only emits pending-approvals with a
        # decision label; this guard is defensive.
        return

    # Resolve the originating audit number via title/body cross-reference.
    audit_number = _resolve_audit_number_from_pending(payload)

    # Self-apply check (FR-008): the bot must not approve its own gate.
    actor_login = _get_decision_actor(config, pa_number)
    is_self_apply = (
        actor_login is not None
        and actor_login.lower() == config.github.bot_identity.lower()
    )
    if is_self_apply:
        msg = (
            f"gate violation: self-apply detected on pending-approval "
            f"#{pa_number} (actor={actor_login}); decision label "
            f"removed without applying"
        )
        logger.error(msg)
        result.errors.append(msg)
        if not args.dry_run:
            _remove_label(config, pa_number, decision, result)
        return

    if args.dry_run:
        result.signals_processed += 1
        logger.info(
            "DRY-RUN: would apply %s on pending-approval #%d (audit #%s)",
            decision, pa_number,
            audit_number if audit_number is not None else "?",
        )
        return

    # Apply the decision — for audit-approve, hand the proposed edits
    # through the routing layer (which applies + commits + posts
    # summary + closes the audit), then close the PA. For audit-reject,
    # demote each proposed edit to a separate docs-debt issue, then
    # run routing with empty proposals (which posts summary + closes
    # audit), then close the PA. For audit-skip, just close both.
    # Cycle-5 (finding 1): previously this handler only closed the
    # issues — the apply/demote bodies were not wired.
    pa_body = str(payload.get("body", "") or "")
    try:
        _apply_pending_decision(
            config, pa_number, audit_number, decision, area_labels,
            pa_body, result,
        )
        result.pending_approvals_applied.append(pa_number)
    except subprocess.CalledProcessError as exc:
        if _is_rate_limited(exc):
            raise RateLimitError(
                f"GH rate-limit during pending-approval #{pa_number}"
            ) from exc
        raise


def _resolve_audit_number_from_pending(
    payload: dict[str, Any]
) -> Optional[int]:
    """Pull the originating audit number from a pending-approval payload."""
    title = payload.get("title", "") or ""
    body = payload.get("body", "") or ""
    match = _AUDIT_REF_RE.search(title)
    if match:
        try:
            return int(match.group(1))
        except ValueError:
            return None
    match = _REFS_RE.search(body)
    if match:
        try:
            return int(match.group(1))
        except ValueError:
            return None
    return None


def _get_decision_actor(
    config: Config, issue_number: int
) -> Optional[str]:
    """Look up the actor who applied the most recent decision label.

    Per SKILL.md §8.6 (actor-verification check), the gate must examine
    the **timeline** for the MOST RECENT ``labeled`` event whose
    ``label.name`` is a decision label (``audit-approve``,
    ``audit-reject``, ``audit-skip``) and return that event's
    ``actor.login``. The previous implementation that returned the
    issue's ``author.login`` was a critical bug: the bot files every
    ``audit-pending-approval`` issue, so the author is always the bot;
    any human decision label was incorrectly rejected as self-apply.

    The canonical query (per SKILL.md §8.6) is::

        gh api repos/<repo>/issues/<N>/timeline --paginate --jq '...'

    Best-effort: returns ``None`` when the lookup fails (not a hard
    error — caller proceeds with apply).
    """
    cmd = [
        "gh",
        "api",
        f"repos/{config.github.repo}/issues/{issue_number}/timeline",
        "--paginate",
        "--jq",
        (
            '[.[] | select(.event == "labeled" and '
            '(.label.name == "audit-approve" or '
            '.label.name == "audit-reject" or '
            '.label.name == "audit-skip"))] | '
            'last | {label: .label.name, actor: .actor.login, '
            'at: .created_at}'
        ),
    ]
    try:
        completed = subprocess.run(
            cmd, capture_output=True, text=True, check=True
        )
    except subprocess.CalledProcessError as exc:
        if _is_rate_limited(exc):
            raise RateLimitError(
                f"GH rate-limit while resolving actor for #{issue_number}"
            ) from exc
        return None
    import json as _json
    stdout = (completed.stdout or "").strip()
    if not stdout or stdout == "null":
        # No decision-label event found in the timeline; treat as
        # unknown actor (caller will proceed — there is no
        # decision-label event to attribute to the bot).
        return None
    try:
        data = _json.loads(stdout)
    except _json.JSONDecodeError:
        return None
    if not isinstance(data, dict):
        return None
    actor = data.get("actor")
    if isinstance(actor, str):
        return actor
    return None


# ---------------------------------------------------------------------------
# Pending-approval body parsing + audit-issue fetch (cycle-5 finding 1)
# ---------------------------------------------------------------------------


# Regex pieces for parsing the proposed-edit blocks the routing layer
# writes into ``audit-pending-approval`` issue bodies (per
# ``kitty-specs/felix-doc-auditor-agent-01KR7JK9/contracts/
# audit-pending-approval-issue.template.md`` and
# ``handle_audit_routing._build_pending_approval_body``):
#
#     ### <N>. `<doc_path>`
#
#     **Change type**: <change_type>
#
#     **Evidence**: <evidence_source>
#
#     **Diff**:
#     ```diff
#     - <current_value>
#     + <proposed_value>
#     ```
#
# Multiple blocks may appear in one body — one per gated proposal. The
# parser is intentionally tolerant of leading/trailing whitespace and
# ignores everything outside the proposed-edits section so a body with
# only the "Refs #N" stub (older PAs, integration-test fixtures, etc.)
# yields an empty list without raising.
_PA_EDIT_BLOCK_RE = re.compile(
    r"###\s+\d+\.\s+`(?P<doc_path>[^`]+)`\s*\n"
    r"(?:.*?\*\*Change\s*type\*\*:\s*(?P<change_type>[^\n]+?)\s*\n)?"
    r"(?:.*?\*\*Evidence\*\*:\s*(?P<evidence>[^\n]+?)\s*\n)?"
    r".*?```diff\s*\n"
    r"-\s*(?P<current>[^\n]*)\n"
    r"\+\s*(?P<proposed>[^\n]*)\n"
    r"```",
    re.DOTALL,
)


def _parse_proposals_from_pa_body(body: str) -> list[ProposedEdit]:
    """Extract :class:`ProposedEdit` instances from a pending-approval body.

    The routing layer (``handle_audit_routing._build_pending_approval_body``)
    emits one ``### N. <doc_path>`` block per gated proposal, with the
    ``Change type``, ``Evidence``, and a ``diff`` code block carrying
    the ``-/+`` current/proposed values. This parser is the inverse of
    that emitter.

    Older / stub bodies that do not contain proposed-edit blocks yield
    an empty list — no exception. That keeps the audit-approve /
    audit-reject paths safe for the integration-test fixtures that
    only contain ``Refs #N`` in the body.

    Per data-model E-004 §"Field constraints", ``ProposedEdit`` carries
    a ``tier`` and ``confidence`` field. Edits parsed back out of a PA
    body lack tier/confidence on the wire (the routing layer dropped
    them when it serialized the body); we synthesize ``tier="tier_b"``
    + ``confidence="high"`` — appropriate defaults for a gated edit per
    SKILL.md §4.1.b (Tier B = content-touching, high-confidence,
    Level-1 gate).
    """
    edits: list[ProposedEdit] = []
    if not body:
        return edits
    for match in _PA_EDIT_BLOCK_RE.finditer(body):
        edits.append(
            ProposedEdit(
                doc_path=match.group("doc_path").strip(),
                change_type=(match.group("change_type") or "").strip(),
                current_value=(match.group("current") or "").rstrip(),
                proposed_value=(match.group("proposed") or "").rstrip(),
                evidence_source=(match.group("evidence") or "").strip(),
                tier="tier_b",
                confidence="high",
            )
        )
    return edits


def _fetch_originating_audit(
    config: Config, audit_number: int
) -> Optional[AuditIssue]:
    """Fetch an audit issue from GH and parse it into :class:`AuditIssue`.

    Used by the pending-approval apply/reject path to reconstruct the
    originating audit (so the routing layer can post the summary on it
    + close it). Returns ``None`` on lookup failure (best-effort — the
    caller falls back to a minimal stub).

    Rate-limit responses raise :class:`RateLimitError` so the
    orchestration loop can BREAK.
    """
    cmd = [
        "gh", "issue", "view", str(audit_number),
        "--repo", config.github.repo,
        "--json", "number,title,body,labels",
    ]
    try:
        completed = subprocess.run(
            cmd, capture_output=True, text=True, check=True
        )
    except subprocess.CalledProcessError as exc:
        if _is_rate_limited(exc):
            raise RateLimitError(
                f"GH rate-limit fetching originating audit #{audit_number}"
            ) from exc
        logger.warning(
            "could not fetch originating audit #%d: rc=%s stderr=%s",
            audit_number, exc.returncode, (exc.stderr or "").strip(),
        )
        return None
    import json as _json
    try:
        data = _json.loads(completed.stdout or "{}")
    except _json.JSONDecodeError:
        return None
    if not isinstance(data, dict):
        return None
    title = str(data.get("title", "") or "")
    labels_raw = data.get("labels", []) or []
    area_labels: list[str] = []
    for lab in labels_raw:
        if isinstance(lab, dict):
            name = str(lab.get("name", "") or "")
            if name.startswith("area/"):
                area_labels.append(name)
    is_weekly = bool(_TITLE_WEEKLY_RE.match(title))
    triggering_sha: Optional[str] = None
    if not is_weekly:
        match = _TITLE_AUDIT_RE.match(title)
        if match:
            triggering_sha = match.group("sha")
    return AuditIssue(
        issue_number=int(audit_number),
        title=title,
        is_weekly=is_weekly,
        triggering_sha=triggering_sha,
        area_labels=area_labels,
        in_scope_docs=[],
        lock_acquired_at_utc=None,
    )


def _handle_missing_file_signal(
    config: Config,
    signal: Any,
    exc: FileNotFoundError,
    result: TickResult,
) -> Optional[int]:
    """Fix #348 (post-cutover follow-on).

    Handle a ``FileNotFoundError`` raised mid-audit because the referenced
    doc no longer exists. Per spec FR-005 + WP06 T029 step 3, the driver
    must:

    1. File a real ``docs-debt`` issue noting the missing path
    2. Close the originating audit with a summary comment
    3. Record the real issue number (NOT a placeholder ``0``)

    Returns the new debt issue number on success, or ``None`` if filing
    or closure failed. Failures append messages to ``result.errors`` but
    do NOT raise — the tick continues.

    Only applies to ``doc_audit`` / ``weekly_doc_audit`` signals.
    Pending-approval and drift-event signals bubble the exception up as
    a non-specific failure (signal.id appears in ``result.errors``).
    """
    if signal.kind not in ("doc_audit", "weekly_doc_audit"):
        return None

    payload = signal.payload or {}
    audit_number = int(payload.get("issue_number", 0))
    if audit_number <= 0:
        logger.warning(
            "_handle_missing_file_signal: no issue_number in payload"
        )
        return None

    missing_path = exc.filename or "(unknown)"
    area_labels = [
        lab for lab in payload.get("labels", [])
        if isinstance(lab, str) and lab.startswith("area/")
    ]
    title = (
        f"Docs: audit #{audit_number} references missing file "
        f"`{missing_path.split('/')[-1] or missing_path}`"
    )
    body = "\n".join([
        "## Origin",
        "",
        (
            f"Filed automatically by `felix-doc-auditor-driver` while "
            f"processing audit #{audit_number}. The audit's referenced "
            f"doc was not found at audit time:"
        ),
        "",
        f"```\n{missing_path}\n```",
        "",
        f"Refs #{audit_number}",
        "",
        "## What happened",
        "",
        (
            "The driver attempted to read this path as part of an "
            "in-scope audit, but the file does not exist (or is not "
            "reachable from the audit's working tree)."
        ),
        "",
        "## Suggested follow-up",
        "",
        (
            "Determine whether the path was deleted intentionally, "
            "renamed, or moved. If deleted: update the audit's "
            "originating doc to remove the stale reference. If "
            "renamed/moved: update the reference (or this driver's "
            "domain-map entry) to the new path."
        ),
        "",
        "## Success criteria",
        "",
        "- [ ] Determine why the path is missing (deleted/renamed/moved)",
        "- [ ] Update the referring doc OR file a follow-up to migrate",
        "- [ ] Close this debt issue once resolved",
    ]) + "\n"

    cmd = [
        "gh", "issue", "create",
        "--repo", config.github.repo,
        "--title", title,
        "--body", body,
        "--label", "docs-debt",
        "--label", "P2-debt",
    ]
    for lab in area_labels:
        cmd.extend(["--label", lab])

    try:
        completed = subprocess.run(
            cmd, capture_output=True, text=True, check=True
        )
    except subprocess.CalledProcessError as e:
        if _is_rate_limited(e):
            raise RateLimitError(
                f"GH rate-limit filing missing-file debt for "
                f"audit #{audit_number}"
            ) from e
        msg = (
            f"missing-file debt filing failed for audit "
            f"#{audit_number}: rc={e.returncode} "
            f"stderr={(e.stderr or '').strip()!r}"
        )
        logger.warning(msg)
        result.errors.append(msg)
        return None

    issue_num = _parse_pa_issue_number_from_url(completed.stdout)
    if issue_num is None:
        logger.warning(
            "missing-file debt filed but could not parse issue URL"
        )
        return None

    # Close the originating audit with a summary comment referencing the
    # new debt issue. Best-effort; failures here are non-fatal.
    summary = (
        f"Auto-closed by felix-doc-auditor-driver: this audit's referenced "
        f"file `{missing_path}` was not found at audit time. Tracked as "
        f"debt issue #{issue_num}. Resolve there."
    )
    try:
        subprocess.run(
            [
                "gh", "issue", "comment", str(audit_number),
                "--repo", config.github.repo,
                "--body", summary,
            ],
            capture_output=True, text=True, check=True,
        )
        subprocess.run(
            [
                "gh", "issue", "close", str(audit_number),
                "--repo", config.github.repo,
                "--reason", "completed",
            ],
            capture_output=True, text=True, check=True,
        )
    except subprocess.CalledProcessError as e:
        # Closing the audit is best-effort; the debt issue carries the
        # follow-up state.
        msg = (
            f"missing-file: audit close failed for #{audit_number}: "
            f"rc={e.returncode} stderr={(e.stderr or '').strip()!r}"
        )
        logger.warning(msg)
        result.errors.append(msg)

    return issue_num


def _file_debt_for_rejected_edit(
    config: Config,
    edit: ProposedEdit,
    audit_number: Optional[int],
    pa_number: int,
    area_labels: list[str],
) -> Optional[int]:
    """File a ``docs-debt`` issue for one rejected proposed edit.

    Returns the new issue number, or ``None`` on filing failure. The
    body preserves the proposed before/after as evidence per SKILL.md
    §8.5 audit-reject semantics ("Demote each proposed edit to a
    separate docs-debt issue (with the proposed before/after as
    evidence)").
    """
    title_path = edit.doc_path.split("/")[-1] or edit.doc_path
    title = f"Docs: rejected edit — {title_path}"
    audit_ref = f"Refs #{audit_number}" if audit_number is not None else ""
    body_parts = [
        "## Origin",
        "",
        f"This debt issue was filed as a demotion from "
        f"pending-approval #{pa_number} "
        f"(decision: `audit-reject`).",
        audit_ref,
        "",
        "## Artifact",
        "",
        f"`{edit.doc_path}`",
        "",
        "## Proposed edit (rejected — preserved as evidence)",
        "",
        f"**Change type**: {edit.change_type or '(unspecified)'}",
        "",
        f"**Evidence**: {edit.evidence_source or '(none)'}",
        "",
        "**Diff**:",
        "```diff",
        f"- {edit.current_value}",
        f"+ {edit.proposed_value}",
        "```",
        "",
        "## Disposition",
        "",
        "The operator declined the auto-apply. This issue captures the",
        "finding so the rationale is not lost; close manually after",
        "human review.",
    ]
    body = "\n".join(body_parts) + "\n"
    cmd = [
        "gh", "issue", "create",
        "--repo", config.github.repo,
        "--title", title,
        "--body", body,
        "--label", "docs-debt",
    ]
    for lab in area_labels:
        if lab.startswith("area/"):
            cmd.extend(["--label", lab])
    try:
        completed = subprocess.run(
            cmd, capture_output=True, text=True, check=True
        )
    except subprocess.CalledProcessError as exc:
        if _is_rate_limited(exc):
            raise RateLimitError(
                f"GH rate-limit filing rejected-edit debt for "
                f"PA #{pa_number}"
            ) from exc
        logger.warning(
            "rejected-edit debt filing failed: rc=%s stderr=%s",
            exc.returncode, (exc.stderr or "").strip(),
        )
        return None
    return _parse_pa_issue_number_from_url(completed.stdout)


def _parse_pa_issue_number_from_url(stdout: str) -> Optional[int]:
    """Extract the trailing integer from a ``gh issue create`` URL.

    ``gh issue create`` prints the new issue URL on success; we want
    the trailing ``/<N>`` segment as an int. Returns ``None`` if the
    URL is unparseable.
    """
    text = (stdout or "").strip()
    if not text:
        return None
    last = text.rsplit("/", 1)[-1]
    try:
        return int(last)
    except ValueError:
        return None


def _apply_pending_decision(
    config: Config,
    pa_number: int,
    audit_number: Optional[int],
    decision: str,
    area_labels: list[str],
    pa_body: str,
    result: TickResult,
) -> None:
    """Execute the post-actor-verification path for a PA decision.

    Per SKILL.md §8.5, the three decision labels have distinct
    semantics:

    - ``audit-approve`` — apply the gated proposed edits via the
      routing layer (write + commit + summary-post + close audit),
      then close the pending-approval issue.
    - ``audit-reject`` — file each gated proposed edit as a separate
      ``docs-debt`` issue (preserving the before/after as evidence),
      then call the routing layer with empty proposals + the new debt
      numbers (which posts a summary + closes the audit), then close
      the pending-approval issue.
    - ``audit-skip`` — no commit, no demotion; just close both the
      pending-approval and the originating audit with a skip note.

    Cycle-5 wires each branch to the routing layer (previously the
    handler only closed the issues — the apply/demote bodies were
    skipped). The routing layer's ``apply()`` does the heavy lifting:
    auto-apply via ``handle_audit_routing.route_audit_decision`` + the
    associated commit + summary post + audit close.

    For audit-approve, the PA body is parsed back into
    :class:`ProposedEdit` instances via
    :func:`_parse_proposals_from_pa_body`. Bodies without parseable
    proposed-edit blocks (older stubs, integration-test fixtures) yield
    an empty list — in that case the routing layer still posts a
    summary and closes the audit (no-op apply), which preserves the
    operator-visible outcome.
    """
    # Reconstruct the originating audit (needed by the routing layer
    # for summary-post + close). When the lookup fails, fall back to a
    # minimal stub so the routing call can still proceed (with an
    # empty title / area_labels).
    audit: Optional[AuditIssue] = None
    if audit_number is not None:
        try:
            audit = _fetch_originating_audit(config, audit_number)
        except RateLimitError:
            raise
        if audit is None:
            audit = AuditIssue(
                issue_number=int(audit_number),
                title="",
                is_weekly=False,
                triggering_sha=None,
                area_labels=list(area_labels),
                in_scope_docs=[],
                lock_acquired_at_utc=None,
            )

    if decision == "audit-skip":
        # Skip path: no routing, no demotion. Just close both issues.
        _close_pa_and_audit(
            config, pa_number, audit_number, decision, result,
        )
        return

    if decision == "audit-approve":
        proposed_edits = _parse_proposals_from_pa_body(pa_body)
        if audit is not None and proposed_edits:
            try:
                routing_result = apply_routing(
                    config,
                    audit,
                    proposed_edits,
                    [],
                    [],
                )
            except subprocess.CalledProcessError as exc:
                if _is_rate_limited(exc):
                    raise RateLimitError(
                        f"GH rate-limit during PA #{pa_number} "
                        f"audit-approve routing"
                    ) from exc
                raise
            _accumulate_routing_result(routing_result, result)
        # Close both the pending-approval and the originating audit.
        # The routing helper may have already closed the audit on a
        # fully-applied apply, but double-close is idempotent in `gh`
        # (already-closed issues return non-zero, which we treat as a
        # warning — captured below in ``_close_pa_and_audit``).
        _close_pa_and_audit(
            config, pa_number, audit_number, decision, result,
        )
        return

    if decision == "audit-reject":
        proposed_edits = _parse_proposals_from_pa_body(pa_body)
        # File one debt issue per rejected edit. Each gets the
        # before/after diff preserved as evidence per SKILL.md §8.5.
        missing_artifacts: list[dict[str, Any]] = []
        for edit in proposed_edits:
            new_num = _file_debt_for_rejected_edit(
                config, edit, audit_number, pa_number, area_labels,
            )
            if new_num is not None:
                missing_artifacts.append(
                    {"issue_number": new_num, "kind": "debt"}
                )
                result.debt_filed.append(new_num)
        # Run routing with empty proposals + the new debt numbers so
        # the helper posts a summary on the originating audit that
        # cross-references the demoted findings. The helper's close
        # path closes the audit when there's no gated set; we also
        # close it below as a belt-and-braces for the empty-proposal
        # short-circuit.
        if audit is not None and proposed_edits:
            try:
                routing_result = apply_routing(
                    config,
                    audit,
                    [],
                    [],
                    missing_artifacts,
                )
            except subprocess.CalledProcessError as exc:
                if _is_rate_limited(exc):
                    raise RateLimitError(
                        f"GH rate-limit during PA #{pa_number} "
                        f"audit-reject routing"
                    ) from exc
                raise
            _accumulate_routing_result(routing_result, result)
        _close_pa_and_audit(
            config, pa_number, audit_number, decision, result,
        )
        return

    # Unknown decision — defensive (the caller only forwards the three
    # canonical labels). Close both issues with a generic note.
    _close_pa_and_audit(
        config, pa_number, audit_number, decision, result,
    )


def _close_pa_only(
    config: Config,
    pa_number: int,
    decision: str,
    result: TickResult,
) -> None:
    """Close one pending-approval issue (the routing layer closes the audit)."""
    subprocess.run(
        [
            "gh", "issue", "close", str(pa_number),
            "--repo", config.github.repo,
            "--comment", f"Decision {decision} applied.",
        ],
        capture_output=True,
        text=True,
        check=True,
    )


def _close_pa_and_audit(
    config: Config,
    pa_number: int,
    audit_number: Optional[int],
    decision: str,
    result: TickResult,
) -> None:
    """Close both PA and originating audit (used for audit-skip and fallback)."""
    subprocess.run(
        [
            "gh", "issue", "close", str(pa_number),
            "--repo", config.github.repo,
            "--comment", f"Decision {decision} applied.",
        ],
        capture_output=True,
        text=True,
        check=True,
    )
    if audit_number is not None:
        subprocess.run(
            [
                "gh", "issue", "close", str(audit_number),
                "--repo", config.github.repo,
                "--comment", f"Pending-approval #{pa_number} {decision}.",
            ],
            capture_output=True,
            text=True,
            check=True,
        )


def _remove_label(
    config: Config, issue_number: int, label: str, result: TickResult
) -> None:
    """Strip a label from an issue (for self-apply gate enforcement)."""
    cmd = [
        "gh", "issue", "edit", str(issue_number),
        "--repo", config.github.repo,
        "--remove-label", label,
    ]
    try:
        subprocess.run(cmd, capture_output=True, text=True, check=True)
    except subprocess.CalledProcessError as exc:
        if _is_rate_limited(exc):
            raise RateLimitError(
                f"GH rate-limit during self-apply label removal #{issue_number}"
            ) from exc
        msg = (
            f"could not strip self-apply label on #{issue_number}: "
            f"{exc.stderr or ''}"
        )
        logger.warning(msg)
        result.errors.append(msg)


# ---------------------------------------------------------------------------
# Per-audit activity-log helper
# ---------------------------------------------------------------------------


def _log_audit_outcome(
    config: Config,
    result: TickResult,
    audit: AuditIssue,
    outcome: dict[str, Any],
) -> None:
    """Append a per-audit entry to the activity log.

    Wrapped so log-write failures append to ``result.errors`` rather
    than blowing out the orchestration loop.
    """
    try:
        append_audit_entry(config, result, audit, outcome)
    except Exception as exc:
        msg = (
            f"activity log append failed for #{audit.issue_number}: "
            f"{type(exc).__name__}: {exc}"
        )
        logger.warning(msg)
        result.errors.append(msg)


def _append_tick_summary_log(
    config: Config,
    result: TickResult,
) -> Optional[Path]:
    """Append a per-tick ``## Tick`` summary entry to the daily log.

    Cycle-4 addition: ``main()``'s ``finally`` block already writes the
    structured ``last-tick.json`` (programmatic), but the operator's
    human-readable Obsidian-vault log (``doc-auditor-<date>.md``) only
    received entries when an audit was successfully processed (via
    :func:`_log_audit_outcome` → :func:`append_audit_entry`). That
    leaves operator blind spots in two important cases:

    - **Empty queue**: the tick ran successfully but processed nothing
      → no audit entry, log file does not gain a row → operator can't
      tell from the daily log alone whether the driver fired.
    - **Crashed mid-tick**: an exception escapes ``_run_tick`` before
      any audit completes → no audit entry, but the tick signal
      records a failure → operator should see the crash reflected in
      the log too.

    The entry format mirrors the per-audit entry shape so the daily
    log stays scannable. We emit a ``## Tick`` header (distinct from
    ``## Audit run`` to keep grep filters intact) plus the tick-level
    counters operators care about.

    Wrapped in a try/except by the caller (``main``) so a log-write
    failure here cannot crash the driver: the tick signal is the
    authoritative programmatic signal, and the daily-log entry is an
    operator-convenience surface.

    Returns the :class:`Path` written, or ``None`` if the write was
    skipped (caller-handled exception). The return value is primarily
    useful for tests.
    """
    now = datetime.now(LOCAL_TZ)
    today_local = now.date().isoformat()
    log_path = (
        Path(config.paths.activity_log_dir)
        / f"doc-auditor-{today_local}.md"
    )
    # Create parents + empty file if missing — matches the convention
    # used by ``activity_log.append_audit_entry``.
    log_path.parent.mkdir(parents=True, exist_ok=True)
    file_existed = log_path.exists()

    ts = now.strftime("%Y-%m-%dT%H:%M:%S%z")
    judgment_calls = result.judgment_calls or {}
    audits_processed = getattr(result, "audits_processed", []) or []
    lines = [
        f"## Tick — {ts}",
        f"- Status: {result.status}",
        f"- Signals seen: {result.signals_seen}",
        f"- Signals processed: {result.signals_processed}",
        f"- Audits processed: {len(audits_processed)}",
        f"- Drift events consumed: {result.drift_events_consumed}",
        f"- Pending approvals filed: {len(result.pending_approvals_filed)}",
        f"- Pending approvals applied: {len(result.pending_approvals_applied)}",
        f"- Debt issues filed: {len(result.debt_filed)}",
        (
            "- Judgment calls: "
            f"tier_classification={judgment_calls.get('tier_classification', 0)} "
            f"cross_file_implication={judgment_calls.get('cross_file_implication', 0)} "
            f"debt_body_generation={judgment_calls.get('debt_body_generation', 0)}"
        ),
        f"- Errors: {len(result.errors)}",
        "",  # trailing blank — matches the inter-entry separator
              # convention used by ``append_audit_entry``.
    ]
    entry_text = "\n".join(lines) + "\n"
    # If the file already has entries, lead with an extra newline so the
    # ``## Tick`` header is separated from the prior entry by a blank
    # line. (``append_audit_entry`` relies on each entry ending in two
    # newlines; we replicate the "two newlines between entries"
    # convention here without depending on that file content.)
    mode = "a" if file_existed and log_path.stat().st_size > 0 else "w"
    with log_path.open(mode, encoding="utf-8") as f:
        if mode == "a":
            # Ensure a blank-line separator before the new entry.
            f.write("\n")
        f.write(entry_text)
    return log_path


# ---------------------------------------------------------------------------
# Signal dispatch
# ---------------------------------------------------------------------------


def _process_signal(
    signal: Any,
    config: Config,
    args: argparse.Namespace,
    result: TickResult,
    judgment_client: JudgmentClient | None = None,
) -> None:
    """Dispatch a single signal to its kind-specific processor.

    ``judgment_client`` is constructed once per tick by ``_run_tick``
    and passed through so the prompt cache stays warm across the three
    judgment moments. ``None`` is acceptable — ``_process_audit_signal``
    will lazily construct a client on first need.
    """
    kind = signal.kind
    if kind == "pending_approval":
        _process_pending_approval(signal, config, args, result)
    elif kind in ("doc_audit", "weekly_doc_audit"):
        _process_audit_signal(
            signal, config, args, result, judgment_client=judgment_client,
        )
    else:
        # Unknown kind — surface as an error but don't crash.
        result.errors.append(
            f"unknown signal kind {kind!r} on {signal.id}; skipped"
        )


# ---------------------------------------------------------------------------
# Core orchestration loop (T027)
# ---------------------------------------------------------------------------


def _run_tick(
    config: Config,
    args: argparse.Namespace,
    result: TickResult,
) -> None:
    """The orchestration loop.

    Step 1: build sources.
    Step 2: drift events first (filing GH issues seen in step 4).
    Step 3: GH-issue scan (also feeds stuck-lock recovery).
    Step 4: process the full queue in (priority, created_utc) order.

    Rate-limit policy: a :class:`RateLimitError` BREAKs out of the
    per-signal loop. Other exceptions log + continue.
    """
    sources = _build_sources(config, args)

    # ---- Step 2: drift-event processing FIRST (per research D9) ----
    drift_source = next(
        (s for s in sources if s.name == "drift_event"), None
    )
    if drift_source is not None:
        _process_drift_events(drift_source, config, args, result)

    # ---- Step 3: GH-issue scan ----
    gh_source = next(
        (s for s in sources if s.name == "gh_issue"), None
    )
    if gh_source is None:
        return

    try:
        signals = list(gh_source.pending())
    except subprocess.CalledProcessError as exc:
        if _is_rate_limited(exc):
            result.errors.append(f"gh_issue.pending rate-limited: {exc}")
            result.status = "failure"
            return
        msg = (
            f"gh_issue.pending failed: rc={exc.returncode} "
            f"stderr={(exc.stderr or '').strip()!r}"
        )
        logger.error(msg)
        result.errors.append(msg)
        result.status = "failure"
        return
    except Exception as exc:
        msg = f"gh_issue.pending failed: {type(exc).__name__}: {exc}"
        logger.error(msg)
        result.errors.append(msg)
        result.status = "failure"
        return

    # ---- Step 3b: stuck-lock detection (FR-014) ----
    # Build the audit → pending-approval cross-reference index FIRST
    # so the stale-lock check can distinguish expected wait state
    # from a crashed-tick lock.
    #
    # Cycle-4 fix: use ``_build_pa_cross_reference_index`` (a dedicated
    # query of ALL open ``audit-pending-approval`` issues) instead of
    # ``_build_pending_approval_index(signals)``. The signal-source's
    # ``pending()`` filter only emits decided pending-approvals; an
    # audit awaiting a human decision would otherwise have NO matching
    # entry in the index and get flagged as a stuck lock — incorrectly
    # clearing the lock and reprocessing the audit. Both
    # awaiting-decision AND decided PAs represent expected wait state.
    try:
        pa_index = _build_pa_cross_reference_index(config)
    except RateLimitError as exc:
        result.errors.append(f"pa cross-ref query rate-limited: {exc}")
        result.status = "failure"
        return
    try:
        recovered = _recover_stuck_locks(config, pa_index, args, result)
    except RateLimitError as exc:
        result.errors.append(f"stuck-lock recovery rate-limited: {exc}")
        result.status = "failure"
        return
    # Cycle-2: process recovered stuck locks IN THIS TICK (option b
    # from the WP06 prompt). The fresh signals are added to the
    # signal queue and dispatched normally.
    if recovered:
        signals.extend(recovered)

    # ---- Step 4: sort + process the queue ----
    signals.sort(key=lambda s: (s.priority, s.created_utc))
    result.signals_seen = len(signals)

    audits_processed_numbers: list[int] = []
    rate_limited = False

    # Per-tick JudgmentClient: lazily constructed on the first audit
    # that needs it, then reused across the rest of the queue so the
    # prompt cache stays warm (research D2 / NFR-001).
    judgment_client: JudgmentClient | None = None
    if any(
        s.kind in ("doc_audit", "weekly_doc_audit") for s in signals
    ) and not args.dry_run:
        try:
            judgment_client = JudgmentClient(config)
        except Exception as exc:
            # Failure to build the client (missing API key, etc.) is
            # NOT fatal — audits without candidate edits skip the LLM
            # path entirely. Audits WITH candidate edits will hit a
            # downstream error and that's logged per-signal.
            msg = (
                f"JudgmentClient construction failed: "
                f"{type(exc).__name__}: {exc}"
            )
            logger.warning(msg)
            result.errors.append(msg)

    for signal in signals:
        if rate_limited:
            break
        try:
            _process_signal(
                signal, config, args, result,
                judgment_client=judgment_client,
            )
            try:
                gh_source.commit(signal, "success")
            except Exception as exc:
                # commit on gh_issue is a no-op; log + continue
                msg = (
                    f"gh_issue.commit failed for {signal.id}: "
                    f"{type(exc).__name__}: {exc}"
                )
                logger.warning(msg)
                result.errors.append(msg)
            result.signals_processed += 1
            if signal.kind in ("doc_audit", "weekly_doc_audit"):
                audits_processed_numbers.append(
                    int(signal.payload.get("issue_number", 0))
                )
        except RateLimitError as exc:
            # BREAK: rate-limit aborts the rest of the tick.
            result.errors.append(
                f"rate-limited on {signal.id}: {exc}"
            )
            result.status = "failure"
            rate_limited = True
        except subprocess.CalledProcessError as exc:
            if _is_rate_limited(exc):
                result.errors.append(
                    f"rate-limited on {signal.id}: {exc}"
                )
                result.status = "failure"
                rate_limited = True
            else:
                msg = (
                    f"signal {signal.id} failed: rc={exc.returncode} "
                    f"stderr={(exc.stderr or '').strip()!r}"
                )
                logger.error(msg)
                result.errors.append(msg)
                if result.status == "success":
                    result.status = "partial"
        except FileNotFoundError as exc:
            # Audit references a missing file — file a real debt issue +
            # close the audit. Fixes #348 (cycle-5 deferred half-handling).
            msg = (
                f"signal {signal.id} references missing file: {exc}"
            )
            logger.error(msg)
            result.errors.append(msg)
            issue_num = _handle_missing_file_signal(
                config, signal, exc, result,
            )
            if issue_num is not None:
                result.debt_filed.append(issue_num)
            if result.status == "success":
                result.status = "partial"
        except Exception as exc:
            # Any other per-signal failure: log + continue.
            msg = (
                f"signal {signal.id} failed: "
                f"{type(exc).__name__}: {exc}"
            )
            logger.error(msg)
            result.errors.append(msg)
            if result.status == "success":
                result.status = "partial"

    # Cycle-5 (finding 2): all-signals-failed promotes to failure.
    # If the tick saw signals but processed NONE of them and recorded
    # errors, the tick is a hard failure — not a partial outcome.
    # ``partial`` semantics (FR-007) imply "made some progress"; if no
    # signal succeeded, the tick is a failure for operator alerting.
    # The earlier per-signal except handlers set ``status="partial"``
    # when ANY signal fails; we promote here when ALL signals failed.
    if (
        result.signals_seen > 0
        and result.signals_processed == 0
        and result.errors
        and result.status != "failure"
    ):
        result.status = "failure"

    # Stash the processed audit numbers on the result for the tick
    # signal builder.
    setattr(result, "audits_processed", audits_processed_numbers)


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------


def main(argv: Optional[list[str]] = None) -> int:
    """CLI entry point.

    See ``contracts/driver-invocation.contract.md`` for the surface
    contract. Returns the process exit code.
    """
    args = _parse_args(argv)

    if args.version:
        print(__version__)
        return 0

    # Configure logging early so any module-level warnings during
    # config-load surface to stderr.
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(name)s %(levelname)s: %(message)s",
        stream=sys.stderr,
    )

    # Load config. A bad config path is an unrecoverable error → exit 1
    # with no tick signal (we have no idea where to write it).
    try:
        config_path = Path(args.config) if args.config else None
        config = load_config(config_path)
    except (FileNotFoundError, ValueError) as exc:
        print(
            f"FATAL: could not load config: {exc}",
            file=sys.stderr,
        )
        return 1

    result = TickResult(
        started_utc=_now_iso(),
        ended_utc="",  # filled at end of tick
        status="success",
        signals_seen=0,
        signals_processed=0,
        tier_a_commits=[],
        pending_approvals_filed=[],
        pending_approvals_applied=[],
        debt_filed=[],
        drift_events_consumed=0,
        errors=[],
        judgment_calls={
            "tier_classification": 0,
            "debt_body_generation": 0,
            "cross_file_implication": 0,
        },
        token_usage={
            "input_tokens": 0,
            "cache_hit_input_tokens": 0,
            "output_tokens": 0,
        },
    )

    try:
        _run_tick(config, args, result)
    except Exception as exc:
        # Top-level catch: anything that escapes _run_tick is logged
        # but the finally block STILL writes a tick signal so operator
        # observability is preserved.
        msg = f"unhandled exception in _run_tick: {type(exc).__name__}: {exc}"
        logger.exception(msg)
        result.errors.append(msg)
        result.status = "failure"
    finally:
        result.ended_utc = _now_iso()
        # Always write the tick signal — even on crash. The contract
        # makes this load-bearing: operators rely on last-tick.json
        # being current to alert on stale ticks.
        try:
            write_tick_signal(config, result, _compute_next_tick())
        except Exception as exc:
            print(
                f"FATAL: tick signal write failed: {exc}",
                file=sys.stderr,
            )
        # Cycle-4: also write a per-tick activity-log entry. The
        # per-audit entries (via ``_log_audit_outcome`` →
        # ``append_audit_entry`` inside ``_process_audit_signal``) only
        # cover successful audit processing; empty-queue ticks and
        # crashed-mid-tick ticks would otherwise leave NO trace in the
        # operator-visible daily log. Wrapped in try/except so a
        # log-write failure cannot crash the driver — the tick signal
        # is still the authoritative programmatic record.
        try:
            _append_tick_summary_log(config, result)
        except Exception as exc:
            print(
                f"WARN: tick activity-log entry failed: {exc}",
                file=sys.stderr,
            )
        try:
            print_summary_line(result)
        except Exception as exc:
            print(
                f"WARN: summary line print failed: {exc}",
                file=sys.stderr,
            )

    return {"success": 0, "partial": 2, "failure": 1}.get(result.status, 1)


if __name__ == "__main__":
    sys.exit(main())
