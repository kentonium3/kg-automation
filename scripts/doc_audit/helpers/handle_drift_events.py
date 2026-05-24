#!/usr/bin/env python3
"""Consume audit.sh drift-events.jsonl and route to doc-audit issue filing.

Implements the signal-driven doc-audit pipeline (#278). Deterministic
detection of system state changes (by audit.sh) → deterministic mapping
to documentation surfaces (via signal-to-doc-map.json) → either an
auto-filed [doc-audit] issue (matched signals) or routing to
unmapped-events.jsonl for AI review (unmatched signals).

Extended by mission ``drift-event-auto-resolution-01KS8J32`` (#362) to
wire Moment 0 (LLM drift interpretation) into the loop, and refactored
by mission ``moment0-integration-fix-01KS8XRM`` to extract the Moment 0
routing into the shared ``doc_audit.routing.drift_moment0`` helper.
When ``[drift_interpretation].enabled = true`` in config.toml, each
mapped event is passed through ``route_drift_event(...)`` which drives
``drift_interpretation.interpret`` and dispatches per verdict
(PROPOSED_EDIT → tier_classification dispatch, JUDGMENT_REQUIRED →
file issue with LLM's question, NO_CHANGE_NEEDED → ledger only).
Every event produces exactly one ledger row (FR-010). Retry exhaustion
falls back to the pre-#362 issue path (FR-009).

The pre-#362 CLI surface is preserved verbatim (per C-002). Per-#362
additions:
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

The Moment 0 ``RoutingOutcome`` type is re-exported from
``doc_audit.routing.drift_moment0`` for back-compat with any existing
imports (``from doc_audit.helpers.handle_drift_events import
RoutingOutcome`` still works).

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
import subprocess
import sys
import tempfile
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Optional

from doc_audit.judgment.drift_interpretation import DriftInterpretationError
from doc_audit.output.drift_ledger import RETRY_MAX_ATTEMPTS
from doc_audit.routing.drift_moment0 import (
    RoutingOutcome,
    _append_ledger_entry,
    _parse_issue_number,
    _resolve_repo_root,
    route_drift_event,
)


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

    Mission ``moment0-integration-fix-01KS8XRM`` refactor: the Moment 0
    routing logic is now invoked via the shared
    :func:`doc_audit.routing.drift_moment0.route_drift_event` helper.
    The :class:`DriftInterpretationError` (retry exhausted) fallback is
    handled HERE (caller of the helper) so the pre-#362 ``[doc-audit]``
    issue path remains the recovery surface and the helper stays free of
    that concern.

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
            outcome = _handle_moment0_event_via_helper(
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


def _handle_moment0_event_via_helper(
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
    """Invoke the shared :func:`route_drift_event` helper and handle its
    documented failure mode.

    Per ``contracts/routing-helper.md`` (mission
    ``moment0-integration-fix-01KS8XRM``), the helper raises
    :class:`DriftInterpretationError` on retry exhaustion (and on
    semantic violations like an out-of-set ``doc_path``). The caller is
    responsible for the RETRY_EXHAUSTED fallback path:

    1. File the pre-#362 ``[doc-audit]`` issue with the
       ``DriftInterpretationError.to_diagnostic_block`` payload.
    2. Append a ``RETRY_EXHAUSTED`` ledger row.
    3. Return a synthetic ``RoutingOutcome`` so the loop's cursor
       advance + counter increments behave identically to before the
       refactor.

    Returns the same :class:`RoutingOutcome` shape ``route_drift_event``
    returns; on the fallback path we manufacture one so the caller's
    counter logic stays uniform.
    """
    event_start = time.perf_counter()
    timestamp_utc = str(event.get("timestamp", ""))
    event_id = f"{cursor_line}:{timestamp_utc}"

    try:
        return route_drift_event(
            event=event,
            mapping=mapping,
            config=config,
            client=judgment_client,
            ledger_path=ledger_path,
            repo=repo,
            event_id=event_id,
            timestamp_utc=timestamp_utc,
            cursor_line=cursor_line,
            repo_root=repo_root,
            dry_run=dry_run,
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
            issue_number = None
        latency_ms = int((time.perf_counter() - event_start) * 1000)
        attempts = getattr(exc, "attempts", 0)
        # Clamp retry_count to the ledger schema's [0, RETRY_MAX_ATTEMPTS] bound.
        retry_count = min(RETRY_MAX_ATTEMPTS, max(0, int(attempts)))
        baseline = str(
            event.get("baseline_name", event.get("baseline", "unknown"))
        )
        if not dry_run:
            _append_ledger_entry(
                ledger_path=ledger_path,
                event_id=event_id,
                baseline=baseline,
                mapping_id=mapping.id,
                verdict_value="RETRY_EXHAUSTED",
                confidence=None,
                outcome="retry_exhausted",
                doc_paths=list(mapping.doc_targets),
                retry_count=retry_count,
                latency_ms=latency_ms,
                tier_classification_outcome=None,
                github_issue_number=issue_number,
            )
        return RoutingOutcome(
            outcome="retry_exhausted",
            tier_classification_outcome=None,
            github_issue_number=issue_number,
            success=True,
            retry_count=retry_count,
            latency_ms=latency_ms,
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
