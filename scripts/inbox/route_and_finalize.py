#!/usr/bin/env python3
"""Note-level finalize transaction for felix-admin-capture (mission #746).

The single deterministic command the capture agent runs **per note** (not per
route). The agent classifies the note's blocks (LLM judgment), assembles a
per-block routing plan, and invokes this helper ONCE. The helper routes every
block, verifies every artifact, writes a per-block routing-log entry, and marks
the note processed **once, only after all blocks are logged** — fail-loud and
retry-safe. This closes the #746 silent-loss class where a note could be marked
processed while a later route silently dropped.

CLI (mandatory ``-m`` form per ``[[feedback_helper_m_invocation_form]]``)::

    cd /home/claude/kg-automation && python3 -m scripts.inbox.route_and_finalize \\
        --source-path <abs-path-of-source-note> \\
        --plan-file <abs-path-of-routing-plan.json> \\
        [--dry-run]

Authoritative contracts: ``contracts/route-and-finalize-cli.md``,
``data-model.md`` (RoutingPlan, FinalizeResult), ``research.md`` (D8-D12). This
module generalizes the proven ``route_calendar_event._run_finalize`` shape (#737)
to a note-level state machine across all route kinds.

State machine (D9, log-before-mark at the note level)
-----------------------------------------------------
Per block, in ``block_index`` order:
  route -> verify artifact (and provenance for delegated kinds) -> write the
  block's routing-log entry (keyed on filename + block_index + block_hash).
A block whose key is already logged is **skipped** (idempotent; no side effect).
After **all** blocks are routed + logged, ``mark_processed`` is invoked ONCE as a
subprocess. Any block failure aborts before the mark: the note is left
UNPROCESSED, exit is non-zero, and already-logged blocks are not repeated on the
next tick (per-block idempotency via WP01's ``RoutingLogReader.has_block``).

Load-bearing invariants (do NOT violate)
----------------------------------------
- ``mark_processed`` MUST be a **subprocess** (``sys.executable -m
  scripts.inbox.mark_processed --path <p>``), never an in-process call: the
  ``_private`` refusal (exit 3), inbox-root validation, and symlink
  ``.resolve()`` guard live in ``mark_processed.main()``.
- Exit code derives from the **note-level outcome**, never from an always-0
  route step.
- No note is marked processed except through a successful all-blocks finalize
  (or the verified ``empty`` disposition).

Stdlib + internal helpers only (NFR-002). The calendar helper subprocess uses
its own google venv python (as today, inherited from ``route_calendar_event``).
"""
from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
import tempfile
from pathlib import Path
from typing import Optional

from scripts.common.vikunja_client import VikunjaClient, VikunjaError
from scripts.inbox import classify_content
from scripts.inbox import route_calendar_event as rce
from scripts.inbox import route_journal_entry as rje
from scripts.inbox import route_someday
from scripts.inbox.routing_log import (
    RoutingLogReader,
    RoutingLogWriter,
    block_hash,
)

# The mark_processed subprocess mirrors route_calendar_event: a stuck mark must
# fail cleanly rather than hang until the openclaw cron limit kills the turn.
MARK_PROCESSED_TIMEOUT_SECONDS = 30
ISSUE_FILER_TIMEOUT_SECONDS = 45
GH_VIEW_TIMEOUT_SECONDS = 20
_TIMEOUT_RETURNCODE = 124  # conventional timeout exit code

# The route kinds this finalize understands. ``kind`` on-disk stays a permissive
# str (routing_log.KNOWN_KINDS); this is the CLI-accepted plan vocabulary.
_KNOWN_KINDS: frozenset[str] = frozenset(
    {"calendar", "someday", "vikunja_task", "journal", "github_issue", "empty"}
)

# felix-file-issue lives in the MAIN agent's workspace (kg-felix-bot identity).
_ISSUE_FILER_MODULE = "scripts.openclaw.agents.main.felix-file-issue"
_ISSUE_FILER_PATH = (
    Path(__file__).resolve().parent.parent
    / "openclaw"
    / "agents"
    / "main"
    / "felix-file-issue.py"
)
_GH_REPO = "kentonium3/kg-automation"

# Templater cursor tags (``<% tp.file.cursor() %>``) and bare ``<%%>`` cursors
# are the only non-whitespace content a genuinely-empty templated note carries.
_TEMPLATER_TAG = re.compile(r"<%.*?%>", re.DOTALL)


# ---------------------------------------------------------------------------
# Subprocess seams (monkeypatched in tests; never hit live services under CI)
# ---------------------------------------------------------------------------


def _invoke_mark_processed(source_path: str) -> "subprocess.CompletedProcess[str]":
    """Run ``mark_processed`` as a subprocess and return the completed process.

    Deliberately a subprocess, not an in-process import of ``mark_processed()``:
    the C-001 ``_private`` refusal (exit 3), inbox-root validation, and — most
    critically — the symlink ``.resolve()`` guard all live in
    ``mark_processed.main()``. Calling the bare function would let a symlinked
    vault note "mark" the symlink while the real target stays ``unprocessed``,
    re-introducing the silent-loss class this mission closes. The subprocess also
    isolates ``mark_processed``'s stdout JSON from this helper's single-result
    contract. ``mark_processed`` is stdlib-only, so ``sys.executable`` is correct.
    """
    try:
        return subprocess.run(
            [sys.executable, "-m", "scripts.inbox.mark_processed", "--path", source_path],
            capture_output=True,
            text=True,
            check=False,
            timeout=MARK_PROCESSED_TIMEOUT_SECONDS,
        )
    except subprocess.TimeoutExpired:
        return subprocess.CompletedProcess(
            args=["mark_processed"],
            returncode=_TIMEOUT_RETURNCODE,
            stdout="",
            stderr=f"ERROR: mark_processed timed out after {MARK_PROCESSED_TIMEOUT_SECONDS}s",
        )


def _create_vikunja_task(
    title: str, body: str, note_filename: str, project: str
) -> int:
    """Create a ``q:schedule`` + no-due-date Vikunja task; return its id.

    Thin seam over ``route_someday.route_someday`` (the durable-landing creator)
    so the in-process ``someday`` / ``vikunja_task`` paths share one create
    implementation and tests can monkeypatch this single call site.
    """
    return route_someday.route_someday(title, body, note_filename, project)


def _fetch_vikunja_task(task_id: int) -> dict:
    """Fetch a task by id (verify it resolves). Returns the parsed task dict.

    felix-bot can READ kent-shared tasks (the #715 boundary only blocks label
    *attach*), so a ``GET /tasks/<id>`` verify is available. A 404 surfaces as a
    ``VikunjaError`` the caller maps to a verify failure.
    """
    client = VikunjaClient()
    task = client.get(f"/tasks/{task_id}")
    return task if isinstance(task, dict) else {}


def _invoke_issue_filer(payload: dict) -> "subprocess.CompletedProcess[str]":
    """File a GitHub issue via the MAIN-agent helper ``felix-file-issue.py``.

    Agent-hop note (D11): ``felix-file-issue.py`` runs under the main agent's
    kg-felix-bot identity (capture cannot file issues directly — governance). In
    the delegated architecture the main agent files the issue and threads the
    returned number back into the plan; this in-process path exists for the
    in-line provenance where the plan carries the filing ``payload`` instead of a
    pre-obtained ``issue_number``. The helper reads the problem statement from a
    tempfile, so we materialize one for it.
    """
    fd, tmp_name = tempfile.mkstemp(prefix="issue-problem.", suffix=".txt")
    try:
        with open(fd, "w", encoding="utf-8") as fh:
            fh.write(str(payload.get("problem_statement", "")))
        cmd = [
            sys.executable,
            str(_ISSUE_FILER_PATH),
            "--type",
            str(payload.get("type", "bug")),
            "--title",
            str(payload.get("title", "")),
            "--problem-statement-file",
            tmp_name,
            "--tier-hypothesis",
            str(payload.get("tier_hypothesis", "unknown")),
            "--area",
            str(payload.get("area", "felix-core")),
            "--priority",
            str(payload.get("priority", "P2")),
        ]
        if payload.get("related_issues"):
            cmd += ["--related-issues", str(payload["related_issues"])]
        try:
            return subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                check=False,
                timeout=ISSUE_FILER_TIMEOUT_SECONDS,
            )
        except subprocess.TimeoutExpired:
            return subprocess.CompletedProcess(
                args=["felix-file-issue"],
                returncode=_TIMEOUT_RETURNCODE,
                stdout="",
                stderr=f"ERROR: felix-file-issue timed out after {ISSUE_FILER_TIMEOUT_SECONDS}s",
            )
    finally:
        try:
            Path(tmp_name).unlink()
        except OSError:  # pragma: no cover - cleanup best-effort
            pass


def _verify_issue_exists(issue_number: int) -> bool:
    """Return True iff issue ``#issue_number`` exists (``gh issue view``).

    A null/missing number is handled by the caller before this runs (FR-012); a
    non-existent number (gh non-zero) is a verify failure so a bogus number never
    contributes to the note's mark.
    """
    try:
        proc = subprocess.run(
            [
                "gh",
                "issue",
                "view",
                str(issue_number),
                "--repo",
                _GH_REPO,
                "--json",
                "number",
            ],
            capture_output=True,
            text=True,
            check=False,
            timeout=GH_VIEW_TIMEOUT_SECONDS,
        )
    except (FileNotFoundError, subprocess.TimeoutExpired):
        return False
    return proc.returncode == 0


# ---------------------------------------------------------------------------
# Per-block key + excerpt
# ---------------------------------------------------------------------------


def _block_key_hash(block: dict) -> str:
    """Return a stable per-block content hash for the D10 idempotency key.

    Prefers the raw block text (``content``) the agent copies from
    ``classify_content`` output — the strongest, most stable key. Falls back to a
    canonical (sorted-key) JSON of the routable payload so re-runs with the same
    plan re-hash identically (the property ``has_block`` relies on).
    """
    content = block.get("content")
    if isinstance(content, str) and content.strip():
        return block_hash(content)
    keyable = {
        k: block[k]
        for k in ("kind", "payload", "task_id", "issue_number")
        if k in block
    }
    return block_hash(json.dumps(keyable, sort_keys=True, ensure_ascii=False))


def _block_excerpt(block: dict) -> str:
    """Return a short note-excerpt for the routing-log row (<=120 chars)."""
    payload = block.get("payload") if isinstance(block.get("payload"), dict) else {}
    for source in (payload, block):
        for key in ("title", "content", "body"):
            value = source.get(key)
            if isinstance(value, str) and value.strip():
                return value.strip()[:120]
    return str(block.get("kind", ""))


# ---------------------------------------------------------------------------
# Per-kind route+verify adapters
# ---------------------------------------------------------------------------
#
# Each adapter returns ``(status, sub, log_fields)`` where:
#   status     : "routed" | "needs_clarification" | "error"
#   sub        : dict merged into the block's result (artifact / missing / error)
#   log_fields : kwargs for RoutingLogWriter.append when routed (else None)
# The orchestrator owns the block-key skip, the routing-log write, and the mark.


def _adapt_calendar(
    block: dict, source_path: str, account: str
) -> tuple[str, dict, Optional[dict]]:
    """Calendar block: reuse ``route_calendar_event`` create + event_id verify.

    Preserves #737 semantics verbatim (NFR-003): an invalid payload is
    ``needs_clarification`` (helper NOT called); a create failure / missing
    event_id is ``error``. The source-path idempotency key (the calendar helper
    dedups on it) is kept — a re-create returns the same event, never a duplicate.
    """
    payload = block.get("payload")
    result, _ = rce._run_create(
        payload if isinstance(payload, dict) else {}, source_path, account
    )
    status = result.get("status")
    if status == "needs_clarification":
        return "needs_clarification", {"missing": result.get("missing", [])}, None
    if status != "created" or not result.get("event_id"):
        return (
            "error",
            {"stage": "route", "error": (result.get("error") or str(result)).strip()},
            None,
        )
    event_id = result["event_id"]
    return (
        "routed",
        {"artifact": event_id, "html_link": result.get("html_link", "")},
        {"kind": "calendar", "destination": event_id},
    )


def _create_and_verify_task(
    block: dict, note_filename: str, kind: str
) -> tuple[str, dict, Optional[dict]]:
    """In-process create (someday / vikunja_task) then verify the id resolves."""
    payload = block.get("payload") if isinstance(block.get("payload"), dict) else {}
    title = payload.get("title")
    if not isinstance(title, str) or not title.strip():
        return "error", {"stage": "route", "error": "missing task title"}, None
    body = payload.get("body", "") if isinstance(payload.get("body", ""), str) else ""
    project = payload.get("project", "inbox") or "inbox"

    try:
        task_id = _create_vikunja_task(title, body, note_filename, project)
    except route_someday.RouteSomedayError as exc:
        return "error", {"stage": "route", "error": str(exc)}, None

    try:
        task = _fetch_vikunja_task(int(task_id))
    except (VikunjaError, ConnectionError, ValueError) as exc:
        return "error", {"stage": "verify", "error": str(exc)}, None
    if not isinstance(task, dict) or int(task.get("id", 0)) != int(task_id):
        return (
            "error",
            {"stage": "verify", "error": f"task {task_id} did not resolve"},
            None,
        )
    return (
        "routed",
        {"artifact": str(task_id)},
        {"kind": kind, "destination": str(task_id), "vikunja_task_id": int(task_id)},
    )


def _adapt_someday(
    block: dict, note_filename: str
) -> tuple[str, dict, Optional[dict]]:
    """Someday block: create the q:schedule task, verify the id resolves."""
    return _create_and_verify_task(block, note_filename, "someday")


def _adapt_vikunja_task(
    block: dict, note_filename: str
) -> tuple[str, dict, Optional[dict]]:
    """Vikunja task block: in-process create OR tasker-delegated id (D11).

    Delegated (``task_id`` present): do NOT create — verify the id exists AND
    belongs to this note via source provenance (the ``Source: <note-filename>``
    footer ``route_someday`` writes, carried in the task description). A
    mismatched / absent-provenance id is a finalize failure (FR-006); a re-run
    keyed on the block never re-delegates.
    """
    task_id_raw = block.get("task_id")
    if task_id_raw is None:
        # In-process provenance — create like someday, but log kind=vikunja_task.
        return _create_and_verify_task(block, note_filename, "vikunja_task")

    try:
        task_id = int(task_id_raw)
    except (TypeError, ValueError):
        return "error", {"stage": "verify", "error": f"invalid task_id {task_id_raw!r}"}, None

    try:
        task = _fetch_vikunja_task(task_id)
    except (VikunjaError, ConnectionError, ValueError) as exc:
        return "error", {"stage": "verify", "error": str(exc)}, None
    if not isinstance(task, dict) or int(task.get("id", 0)) != task_id:
        return "error", {"stage": "verify", "error": f"task {task_id} did not resolve"}, None

    description = task.get("description", "") or ""
    if note_filename not in description:
        return (
            "error",
            {
                "stage": "verify",
                "error": (
                    f"task {task_id} provenance mismatch: note {note_filename!r} "
                    "not found in task description (does not belong to this note)"
                ),
            },
            None,
        )
    return (
        "routed",
        {"artifact": str(task_id), "delegated": True},
        {"kind": "vikunja_task", "destination": str(task_id), "vikunja_task_id": task_id},
    )


def _adapt_journal(
    block: dict, note_filename: str
) -> tuple[str, dict, Optional[dict]]:
    """Journal block: append a dated section with a per-block sentinel (FR-010).

    The sentinel ``<!-- src: <filename>#<block_index> -->`` is written into the
    appended section and **verified before append** so a reprocess never
    duplicates a section even if the routing-log entry was lost. Verifies the
    target file exists + the sentinel is present after the write.
    """
    payload = block.get("payload") if isinstance(block.get("payload"), dict) else {}
    content = payload.get("content") or payload.get("body") or block.get("content")
    if not isinstance(content, str) or not content.strip():
        return "error", {"stage": "route", "error": "empty journal content"}, None
    dt_raw = payload.get("datetime")
    if not isinstance(dt_raw, str) or not dt_raw.strip():
        return "error", {"stage": "route", "error": "missing journal datetime"}, None
    try:
        dt = rje._parse_iso_datetime(dt_raw)
    except ValueError as exc:
        return "error", {"stage": "route", "error": f"invalid datetime {dt_raw!r}: {exc}"}, None

    block_index = block.get("block_index")
    sentinel = f"<!-- src: {note_filename}#{block_index} -->"
    try:
        journal_dir = rje.resolve_journal_dir()
    except Exception as exc:  # registry / unknown name
        return "error", {"stage": "route", "error": f"journal vault unresolvable: {exc}"}, None
    target = journal_dir / rje.target_filename(dt)

    try:
        already_present = target.exists() and sentinel in target.read_text(encoding="utf-8")
        if not already_present:
            heading = rje.make_heading(dt, content)
            section_body = content.rstrip("\n") + "\n\n" + sentinel
            rje.ensure_journal_file(target, dt)
            rje.append_section(target, heading, section_body)
        # Verify: the target exists and carries the sentinel.
        if not target.exists() or sentinel not in target.read_text(encoding="utf-8"):
            return "error", {"stage": "verify", "error": f"sentinel missing in {target}"}, None
    except OSError as exc:
        return "error", {"stage": "route", "error": f"{target}: {exc}"}, None

    return (
        "routed",
        {"artifact": str(target)},
        {"kind": "journal", "destination": str(target)},
    )


def _adapt_github_issue(
    block: dict, note_filename: str
) -> tuple[str, dict, Optional[dict]]:
    """GitHub issue block: verify the issue number, then log (FR-012, D11).

    Two provenances mirror vikunja_task: (1) delegated — the plan carries an
    ``issue_number`` the MAIN agent already obtained from ``felix-file-issue.py``;
    (2) in-line — the plan carries a filing ``payload`` and this path invokes the
    filer. Either way a **null / missing** issue number is a finalize failure, and
    the number is verified to exist (``gh issue view``) before it contributes to
    the note's mark.
    """
    issue_number = block.get("issue_number")

    if issue_number is None and isinstance(block.get("payload"), dict):
        proc = _invoke_issue_filer(block["payload"])
        if proc.returncode != 0:
            return (
                "error",
                {"stage": "route", "error": (proc.stderr or proc.stdout).strip()},
                None,
            )
        issue_number = _parse_filed_issue_number(proc.stdout)

    if issue_number is None:
        return (
            "error",
            {"stage": "route", "error": "github filer returned a null/missing issue number"},
            None,
        )
    try:
        issue_number = int(issue_number)
    except (TypeError, ValueError):
        return "error", {"stage": "route", "error": f"invalid issue number {issue_number!r}"}, None

    if not _verify_issue_exists(issue_number):
        return (
            "error",
            {"stage": "verify", "error": f"issue #{issue_number} not found"},
            None,
        )
    return (
        "routed",
        {"artifact": str(issue_number)},
        {"kind": "github_issue", "destination": str(issue_number), "issue_number": issue_number},
    )


def _parse_filed_issue_number(stdout: str) -> Optional[int]:
    """Extract ``issue_number`` from ``felix-file-issue.py`` JSON stdout.

    The filer prints a JSON object line then a ``SUMMARY:`` line; scan for the
    first line that parses to a dict carrying a non-null ``issue_number``.
    """
    for line in stdout.splitlines():
        line = line.strip()
        if not line.startswith("{"):
            continue
        try:
            obj = json.loads(line)
        except json.JSONDecodeError:
            continue
        if isinstance(obj, dict) and obj.get("issue_number") is not None:
            return int(obj["issue_number"])
    return None


def _route_and_verify_block(
    block: dict, source_path: str, note_filename: str, account: str
) -> tuple[str, dict, Optional[dict]]:
    """Dispatch a single block to its per-kind adapter."""
    kind = block.get("kind")
    if kind == "calendar":
        return _adapt_calendar(block, source_path, account)
    if kind == "someday":
        return _adapt_someday(block, note_filename)
    if kind == "vikunja_task":
        return _adapt_vikunja_task(block, note_filename)
    if kind == "journal":
        return _adapt_journal(block, note_filename)
    if kind == "github_issue":
        return _adapt_github_issue(block, note_filename)
    return "error", {"stage": "route", "error": f"unknown kind {kind!r}"}, None


# ---------------------------------------------------------------------------
# Empty disposition (D12) — verify genuinely empty, then log kind=empty + mark
# ---------------------------------------------------------------------------


def _validate_empty_body(source_path: str) -> tuple[bool, str]:
    """Return ``(is_empty, reason)`` for the note at ``source_path``.

    Mirrors the intent of ``prescan``'s empty detection: the body is genuinely
    empty when only whitespace remains after stripping Templater cursor tags. A
    non-empty body is refused loudly so ``empty`` can never bury real content
    (the silent-loss escape hatch this mission closes).
    """
    try:
        _fm, body = classify_content.read_note(Path(source_path))
    except OSError as exc:
        return False, f"could not read note {source_path}: {exc}"
    remaining = _TEMPLATER_TAG.sub("", body).strip()
    if remaining:
        return False, "note body is not empty (empty disposition refused to avoid silent loss)"
    return True, ""


def _finalize_empty(source_path: str, note_filename: str) -> tuple[dict, int]:
    """Verify the body is empty, write a kind=empty log row, mark once (FR-007)."""
    is_empty, reason = _validate_empty_body(source_path)
    if not is_empty:
        return (
            {
                "status": "error",
                "note_filename": note_filename,
                "blocks": [{"kind": "empty", "stage": "verify", "error": reason}],
            },
            1,
        )

    reader = RoutingLogReader()
    if not reader.has(note_filename):
        try:
            RoutingLogWriter().append(
                filename=note_filename,
                kind="empty",
                destination="",
                note_excerpt="(empty note)",
            )
        except OSError as exc:
            return (
                {
                    "status": "error",
                    "note_filename": note_filename,
                    "blocks": [{"kind": "empty", "stage": "log", "error": str(exc)}],
                },
                1,
            )

    proc = _invoke_mark_processed(source_path)
    if proc.returncode != 0:
        return (
            {
                "status": "error",
                "note_filename": note_filename,
                "stage": "mark_processed",
                "exit_code": proc.returncode,
                "error": (proc.stderr or proc.stdout).strip(),
                "blocks": [{"kind": "empty"}],
            },
            1,
        )
    return (
        {
            "status": "finalized",
            "note_filename": note_filename,
            "marked_processed": True,
            "blocks": [{"kind": "empty", "logged": True}],
        },
        0,
    )


# ---------------------------------------------------------------------------
# Note-level orchestration (the atomic transaction)
# ---------------------------------------------------------------------------


def _is_empty_plan(blocks: list) -> bool:
    """True when the plan selects the empty disposition."""
    if not blocks:
        return True
    return all(isinstance(b, dict) and b.get("kind") == "empty" for b in blocks)


def _run_finalize(source_path: str, plan: dict, account: str) -> tuple[dict, int]:
    """Execute the note-level finalize transaction. Returns ``(result, code)``.

    Routes every block, verifies each artifact, writes a per-block routing-log
    entry, then marks the note processed ONCE — only after all blocks are logged.
    Any block error → note left unprocessed, non-zero exit. Any block
    needs_clarification (and no error) → note left unprocessed, exit 0 (capture
    enters the kind's clarification flow; calendar only, today). A block already
    logged (block key present) is skipped with no repeated side effect.
    """
    note_filename = Path(source_path).name
    blocks = plan.get("blocks") if isinstance(plan.get("blocks"), list) else []

    if _is_empty_plan(blocks):
        return _finalize_empty(source_path, note_filename)

    reader = RoutingLogReader()
    writer = RoutingLogWriter()
    block_results: list[dict] = []
    had_error = False
    had_clarification = False

    for block in sorted(blocks, key=lambda b: _sort_index(b)):
        idx = block.get("block_index")
        kind = block.get("kind")
        key_hash = _block_key_hash(block)

        # Re-run reconciliation (D9/D10): an already-logged block is skipped, no
        # side effect repeated — this is the retry-safety guard that makes
        # log-before-mark idempotent across ticks.
        if idx is not None and reader.has_block(note_filename, idx, key_hash):
            block_results.append(
                {"block_index": idx, "kind": kind, "skipped": True, "logged": True}
            )
            continue

        status, sub, log_fields = _route_and_verify_block(
            block, source_path, note_filename, account
        )

        if status == "error":
            had_error = True
            block_results.append(
                {"block_index": idx, "kind": kind, "stage": sub.get("stage"), "error": sub.get("error")}
            )
            continue
        if status == "needs_clarification":
            had_clarification = True
            block_results.append(
                {"block_index": idx, "kind": kind, "missing": sub.get("missing", [])}
            )
            continue

        # Routed: write the block's routing-log entry BEFORE the note-level mark.
        assert log_fields is not None
        try:
            writer.append(
                filename=note_filename,
                note_excerpt=_block_excerpt(block),
                block_index=idx,
                block_hash=key_hash,
                **log_fields,
            )
        except OSError as exc:
            had_error = True
            block_results.append(
                {"block_index": idx, "kind": kind, "stage": "log", "error": str(exc)}
            )
            continue

        entry = {"block_index": idx, "kind": kind, "logged": True, "skipped": False}
        entry.update(sub)
        block_results.append(entry)

    if had_error:
        return (
            {"status": "error", "note_filename": note_filename, "blocks": block_results},
            1,
        )
    if had_clarification:
        return (
            {
                "status": "needs_clarification",
                "note_filename": note_filename,
                "blocks": block_results,
            },
            0,
        )

    # All blocks routed + logged (or skipped) → mark the note ONCE.
    proc = _invoke_mark_processed(source_path)
    if proc.returncode != 0:
        return (
            {
                "status": "error",
                "note_filename": note_filename,
                "stage": "mark_processed",
                "exit_code": proc.returncode,
                "error": (proc.stderr or proc.stdout).strip(),
                "blocks": block_results,
            },
            1,
        )
    return (
        {
            "status": "finalized",
            "note_filename": note_filename,
            "marked_processed": True,
            "blocks": block_results,
        },
        0,
    )


def _sort_index(block: dict) -> int:
    """Sort key: order blocks by ``block_index`` (missing/None sort last)."""
    idx = block.get("block_index")
    return idx if isinstance(idx, int) else 1_000_000


# ---------------------------------------------------------------------------
# Dry-run (credential-free wiring check; no side effects)
# ---------------------------------------------------------------------------


def _dry_run(source_path: str, plan: dict) -> dict:
    """Validate the plan + report ``would_finalize`` without any side effect."""
    note_filename = Path(source_path).name
    blocks = plan.get("blocks") if isinstance(plan.get("blocks"), list) else []
    issues: list[dict] = []

    if _is_empty_plan(blocks):
        ok, reason = _validate_empty_body(source_path)
        if not ok:
            issues.append({"kind": "empty", "error": reason})
        return _dry_run_result(note_filename, issues)

    for block in blocks:
        idx = block.get("block_index") if isinstance(block, dict) else None
        kind = block.get("kind") if isinstance(block, dict) else None
        if kind not in _KNOWN_KINDS:
            issues.append({"block_index": idx, "kind": kind, "error": "unknown kind"})
            continue
        problem = _dry_run_validate_block(kind, block)
        if problem is not None:
            problem["block_index"] = idx
            problem["kind"] = kind
            issues.append(problem)

    return _dry_run_result(note_filename, issues)


def _dry_run_validate_block(kind: str, block: dict) -> Optional[dict]:
    """Light per-kind validation for dry-run (no routing). Returns issue or None."""
    payload = block.get("payload") if isinstance(block.get("payload"), dict) else {}
    if kind == "calendar":
        valid, missing = rce.validate_payload(payload)
        return None if valid else {"missing": missing}
    if kind == "someday":
        title = payload.get("title")
        return None if isinstance(title, str) and title.strip() else {"error": "missing title"}
    if kind == "vikunja_task":
        if block.get("task_id") is not None:
            return None
        title = payload.get("title")
        return None if isinstance(title, str) and title.strip() else {"error": "missing title/task_id"}
    if kind == "journal":
        content = payload.get("content") or payload.get("body") or block.get("content")
        has_dt = isinstance(payload.get("datetime"), str) and payload.get("datetime").strip()
        if not (isinstance(content, str) and content.strip()):
            return {"error": "missing content"}
        return None if has_dt else {"error": "missing datetime"}
    if kind == "github_issue":
        if block.get("issue_number") is not None or isinstance(block.get("payload"), dict):
            return None
        return {"error": "missing issue_number/payload"}
    return None  # pragma: no cover - _KNOWN_KINDS gate precedes this


def _dry_run_result(note_filename: str, issues: list[dict]) -> dict:
    result = {"status": "dry_run", "note_filename": note_filename, "would_finalize": not issues}
    if issues:
        result["blocks"] = issues
    return result


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


def _emit_error(kind: str, detail: str) -> None:
    """Write a structured error JSON to stderr."""
    sys.stderr.write(json.dumps({"error": kind, "detail": detail}) + "\n")


def _load_plan(path: Path) -> tuple[Optional[dict], Optional[int]]:
    """Read + parse the routing plan JSON. Returns ``(plan, None)`` or ``(None, code)``."""
    if not path.exists():
        _emit_error("file_not_found", str(path))
        return None, 1
    try:
        raw = path.read_text(encoding="utf-8")
    except OSError as exc:  # pragma: no cover - exists() but unreadable is rare
        _emit_error("read_failed", f"{path}: {exc}")
        return None, 1
    try:
        parsed = json.loads(raw)
    except json.JSONDecodeError as exc:
        _emit_error("malformed_json", str(exc))
        return None, 1
    if not isinstance(parsed, dict):
        _emit_error("invalid_plan", "plan must be a JSON object")
        return None, 1
    return parsed, None


def main(argv: Optional[list[str]] = None) -> int:
    parser = argparse.ArgumentParser(
        prog="python3 -m scripts.inbox.route_and_finalize",
        description=(
            "Note-level finalize transaction: route every block in the plan, "
            "verify each artifact, write a per-block routing-log entry, and mark "
            "the source note processed ONCE — atomic, fail-loud, retry-safe."
        ),
    )
    parser.add_argument(
        "--source-path",
        required=True,
        help="Absolute inbox path of the source note (the mark_processed target).",
    )
    parser.add_argument(
        "--plan-file",
        required=True,
        help="Absolute path to the agent-assembled RoutingPlan JSON.",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help=(
            "Validate the plan + report `would_finalize` WITHOUT routing, marking, "
            "or logging (credential-free wiring check)."
        ),
    )
    parser.add_argument(
        "--account",
        default=rce.DEFAULT_ACCOUNT,
        help=(
            "Credential-set selector passed to the calendar helper for calendar "
            f"blocks (default {rce.DEFAULT_ACCOUNT!r})."
        ),
    )
    args = parser.parse_args(argv)

    plan, err_code = _load_plan(Path(args.plan_file))
    if err_code is not None:
        return err_code
    assert plan is not None

    if args.dry_run:
        result = _dry_run(args.source_path, plan)
        sys.stdout.write(json.dumps(result) + "\n")
        return 0

    result, code = _run_finalize(args.source_path, plan, args.account)
    sys.stdout.write(json.dumps(result) + "\n")
    return code


if __name__ == "__main__":
    sys.exit(main())
