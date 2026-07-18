#!/usr/bin/env python3
"""Deterministic Inbox scan + Tier-1 classification + collision-safe correlation
record (WP02, mission ``task-intake-validation-loop``, kentonium3/kg-automation#749).

This module rides the inbox-processing crons (FR-003). On each tick it:

1. **Enumerates** the not-done Vikunja **Inbox** tasks — the Inbox project id is
   resolved via the #748 ``vikunja_refs`` seam (never hardcoded), and the read
   uses the **felix-bot** token (the default :class:`~scripts.common.vikunja_client.VikunjaClient`,
   NOT the kent write token). ``GET /tasks/all`` is paged done-inclusive and
   filtered client-side to ``project_id == inbox && done == false`` (FR-001).
2. **Classifies** each task's Tier-1 completeness deterministically (FR-002):
   Tier-1-complete iff ``project != Inbox`` AND a schedulable friction label
   (``f:1-flow``/``f:2-growth``/``f:3-edge``) AND exactly one Eisenhower quadrant
   label (``q:do``/``q:schedule``/``q:delegate``/``q:eliminate``). ``f:4-overload``
   does NOT satisfy friction; a task already carrying ``f:4-overload`` is
   **decomposition-pending** and is excluded from the incomplete-for-prompting set
   (FR-009 — it must not re-prompt every tick).
3. **Persists** a **collision-safe** correlation record (FR-016): one **immutable**
   file per ``digest_id`` under ``<state-dir>/digests/intake-<digest_id>.json``,
   plus a ``<state-dir>/latest.json`` pointer, so a delayed reply across the 4
   daily ticks correlates to the right digest by line-number set + title evidence
   (never by position in the newest file alone). Prior digest files are **never**
   overwritten; files older than the retention window (48h, habits parity) expire.
4. **Emits** a per-tick observability artifact ``intake-tick-<ET-date>.json``
   (FR-014) with ``started_at_utc``, ``exit_status``, ``{scanned, incomplete,
   prompted}`` counts, and an ``errors[]`` list, mirroring the habits sweeper tick.
5. **Renders** the numbered ``digest_text`` (one message body — Output Discipline).
   ``incomplete == 0`` ⇒ empty ``digest_text`` and no digest record write beyond the
   tick artifact (SC-009).

Determinism (Directive 6): zero LLM calls; every decision is a pure data operation.
The clock is **injected** (``--now-utc`` / ``now_utc`` argument) — the module never
calls wall-clock time except at the single CLI boundary when ``--now-utc`` is
omitted (the habits-sweeper idiom), so classification and correlation are fully
deterministic under test.

CLI surface::

    python3 -m scripts.intake.scan_inbox \\
        [--state-dir /data/services/openclaw/state/intake] \\
        [--source-cron inbox-5pm] \\
        [--window-hours 48] \\
        [--now-utc 2026-07-17T22:00:00Z] \\
        [--dry-run] [--json]

Exit codes::

    0 -- scan completed (including the N == 0 "nothing to prompt" case, SC-009)
    1 -- infrastructure failure (Vikunja error, seam resolution failure, unhandled)

Reads the deterministic ``scripts.common.vikunja_client.VikunjaClient`` — the
canonical stdlib HTTP boundary. No ``requests`` dependency, no new HTTP path.
"""
from __future__ import annotations

import argparse
import json
import os
import sys
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo

from scripts.common import vikunja_refs
from scripts.common.vikunja_client import VikunjaError

__all__ = [
    "DEFAULT_STATE_DIR",
    "DEFAULT_WINDOW_HOURS",
    "SCHEDULABLE_FRICTION_LABELS",
    "OVERLOAD_LABEL",
    "QUADRANT_LABELS",
    "INBOX_PROJECT_NAME",
    "Classification",
    "DigestEntry",
    "ScanResult",
    "IntakeError",
    "classify_task",
    "list_inbox_tasks",
    "run_scan",
    "compute_digest_id",
    "build_digest_record",
    "render_digest_text",
    "write_digest_record",
    "update_latest_pointer",
    "expire_old_digests",
    "write_tick_artifact",
    "main",
]

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

#: Default per-feature state directory on office2 (habits-sibling layout).
DEFAULT_STATE_DIR = Path("/data/services/openclaw/state/intake")

#: Retention window for immutable digest records (48h == habits parity, FR-016).
DEFAULT_WINDOW_HOURS = 48

#: Vikunja caps ``per_page`` at 50 on this instance; a ``len < 100`` stop
#: condition would be wrong (mirrors ``migrate_tasks._PAGE_SIZE``).
_PAGE_SIZE = 50

#: Bound every external Vikunja call (seconds). The client also has its own
#: default, but the scan states its budget explicitly (Directive: idempotent,
#: bounded I/O).
_HTTP_TIMEOUT = 30.0

#: Logical Inbox project name resolved via the #748 seam (never hardcoded id).
INBOX_PROJECT_NAME = "inbox"

#: Friction labels that satisfy Tier-1 completeness (schedulable). ``f:4-overload``
#: is deliberately excluded — it is a decomposition trigger, not a friction
#: classification (FR-002/FR-009).
SCHEDULABLE_FRICTION_LABELS = frozenset({"f:1-flow", "f:2-growth", "f:3-edge"})

#: The decomposition-pending marker. A task carrying it is excluded from the
#: incomplete-for-prompting set (FR-009).
OVERLOAD_LABEL = "f:4-overload"

#: The Eisenhower quadrant labels; exactly one is required for completeness.
QUADRANT_LABELS = frozenset({"q:do", "q:schedule", "q:delegate", "q:eliminate"})

#: Canonical ordering of the missing-field tokens in the digest/record.
_MISSING_FIELD_ORDER = ("project", "friction", "quadrant")

ET_ZONE = ZoneInfo("America/New_York")


class IntakeError(Exception):
    """Fail-loud intake error (malformed enumeration, unreadable/immutable-collision
    state, or a broken invariant).

    Raised where continuing could mis-correlate a reply or trust a malformed
    Vikunja enumeration. Surfaced by :func:`main` as a non-zero exit — never
    swallowed.
    """


# ---------------------------------------------------------------------------
# Classification (T006)
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class Classification:
    """The Tier-1 verdict for one Inbox task (data-model.md → Inbox task).

    ``missing_fields`` is a subset of ``{project, friction, quadrant}`` in the
    canonical :data:`_MISSING_FIELD_ORDER`. A task is Tier-1-complete iff
    ``missing_fields`` is empty. ``decomposition_pending`` is True when the task
    carries ``f:4-overload`` — such a task is excluded from the
    incomplete-for-prompting set (FR-009) regardless of ``missing_fields``.
    """

    task_id: int
    title: str
    missing_fields: tuple[str, ...]
    decomposition_pending: bool

    @property
    def is_complete(self) -> bool:
        """True when nothing is missing (Tier-1-complete)."""
        return not self.missing_fields

    @property
    def prompts(self) -> bool:
        """True when this task belongs in the digest (incomplete AND not
        decomposition-pending)."""
        return bool(self.missing_fields) and not self.decomposition_pending


def _label_titles(task: dict[str, Any]) -> set[str]:
    """Return the set of label titles on ``task`` (missing/None → empty).

    Each label entry is ``{"id": ..., "title": ...}``; non-dict entries or
    entries without a string ``title`` are ignored (a malformed label entry must
    not silently satisfy a classification requirement).
    """
    titles: set[str] = set()
    for label in task.get("labels") or []:
        if isinstance(label, dict):
            title = label.get("title")
            if isinstance(title, str):
                titles.add(title)
    return titles


def classify_task(task: dict[str, Any], inbox_id: int) -> Classification:
    """Classify one task's Tier-1 completeness deterministically (FR-002).

    ``missing_fields`` accumulates, in canonical order:

    - ``project`` — the task's ``project_id`` equals the Inbox id (being in Inbox
      means the working project is unset by definition);
    - ``friction`` — no schedulable friction label
      (:data:`SCHEDULABLE_FRICTION_LABELS`; ``f:4-overload`` does not count);
    - ``quadrant`` — not exactly one Eisenhower quadrant label.

    A task carrying ``f:4-overload`` is flagged ``decomposition_pending``.
    """
    task_id = task.get("id")
    if not isinstance(task_id, int) or isinstance(task_id, bool):
        raise IntakeError(
            f"cannot classify task with non-integer id {task_id!r}; refusing to "
            f"trust the enumeration."
        )
    raw_title = task.get("title")
    title = raw_title if isinstance(raw_title, str) else ""

    titles = _label_titles(task)
    decomposition_pending = OVERLOAD_LABEL in titles

    missing: list[str] = []
    if task.get("project_id") == inbox_id:
        missing.append("project")
    if not (titles & SCHEDULABLE_FRICTION_LABELS):
        missing.append("friction")
    if len(titles & QUADRANT_LABELS) != 1:
        missing.append("quadrant")

    # Preserve canonical order regardless of append order (defensive).
    ordered = tuple(f for f in _MISSING_FIELD_ORDER if f in missing)
    return Classification(
        task_id=task_id,
        title=title,
        missing_fields=ordered,
        decomposition_pending=decomposition_pending,
    )


# ---------------------------------------------------------------------------
# Read path — enumerate not-done Inbox tasks (T005)
# ---------------------------------------------------------------------------


def list_inbox_tasks(client: Any, inbox_id: int) -> list[dict[str, Any]]:
    """Return every **not-done** task in the Inbox via paginated ``GET /tasks/all``.

    Pages ``per_page=50`` from page 1 (done-inclusive at the API, then filtered
    client-side to ``project_id == inbox_id && done == false``) until a short
    page. Mirrors ``migrate_tasks.list_all_tasks``: a ``null`` body → stop; a
    non-list, non-null 200 body → :class:`VikunjaError`; a malformed task element
    (non-dict, non-int id, non-int project_id) → :class:`IntakeError` (a dropped
    task must never make the Inbox look emptier than it is).
    """
    tasks: list[dict[str, Any]] = []
    page = 1
    while True:
        batch = client.get(
            "/tasks/all",
            params={"per_page": str(_PAGE_SIZE), "page": str(page)},
            timeout=_HTTP_TIMEOUT,
        )
        if batch is None:
            break
        if not isinstance(batch, list):
            raise VikunjaError(path="/tasks/all", status=200)
        for element in batch:
            if not isinstance(element, dict):
                raise IntakeError(
                    f"GET /tasks/all returned a non-dict task element "
                    f"{element!r}; refusing to trust the enumeration."
                )
            tid = element.get("id")
            if not isinstance(tid, int) or isinstance(tid, bool):
                raise IntakeError(
                    f"GET /tasks/all returned a task with a non-integer id "
                    f"{tid!r}; refusing to trust the enumeration."
                )
            pid = element.get("project_id")
            if not isinstance(pid, int) or isinstance(pid, bool):
                raise IntakeError(
                    f"GET /tasks/all task {tid} has a non-integer project_id "
                    f"{pid!r}; refusing to trust the enumeration."
                )
            if pid != inbox_id:
                continue
            if element.get("done") is True:
                continue
            tasks.append(element)
        if len(batch) < _PAGE_SIZE:
            break
        page += 1
    return tasks


# ---------------------------------------------------------------------------
# Scan result + digest rendering
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class DigestEntry:
    """One numbered line of the digest / correlation record (data-model.md)."""

    n: int
    task_id: int
    title: str
    missing_fields: tuple[str, ...]

    def to_dict(self) -> dict[str, Any]:
        return {
            "n": self.n,
            "task_id": self.task_id,
            "title": self.title,
            "missing_fields": list(self.missing_fields),
        }


@dataclass
class ScanResult:
    """The outcome of one scan: counts + the numbered incomplete entries.

    ``scanned`` is every not-done Inbox task; ``entries`` is the ordered,
    1-indexed set of incomplete-for-prompting tasks (excludes complete and
    decomposition-pending tasks). ``prompted`` equals ``len(entries)`` — a single
    digest prompts every incomplete task once (FR-011).
    """

    scanned: int
    entries: list[DigestEntry] = field(default_factory=list)

    @property
    def incomplete(self) -> int:
        return len(self.entries)

    @property
    def prompted(self) -> int:
        return len(self.entries)


def run_scan(client: Any, *, inbox_id: int) -> ScanResult:
    """Enumerate + classify the Inbox and build the numbered incomplete entries.

    Pure of any wall-clock or state I/O — only the Vikunja read. The caller
    (``main``) owns record/tick persistence so the scan stays testable in
    isolation.
    """
    tasks = list_inbox_tasks(client, inbox_id)
    entries: list[DigestEntry] = []
    n = 0
    for task in tasks:
        verdict = classify_task(task, inbox_id)
        if not verdict.prompts:
            continue
        n += 1
        entries.append(
            DigestEntry(
                n=n,
                task_id=verdict.task_id,
                title=verdict.title,
                missing_fields=verdict.missing_fields,
            )
        )
    return ScanResult(scanned=len(tasks), entries=entries)


def render_digest_text(entries: list[DigestEntry]) -> str:
    """Render the numbered digest as a single WhatsApp message body.

    Output Discipline (FR/one-message): a short header plus one numbered line per
    incomplete task, ``<n>. <title> — needs: <fields>``. Returns ``""`` for an
    empty set (SC-009 — no message).
    """
    if not entries:
        return ""
    count = len(entries)
    noun = "task" if count == 1 else "tasks"
    lines = [f"Inbox triage — {count} {noun} need info:"]
    for entry in entries:
        fields = ", ".join(entry.missing_fields) if entry.missing_fields else "-"
        lines.append(f"{entry.n}. {entry.title} — needs: {fields}")
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Correlation record + pointer + expiry (T007)
# ---------------------------------------------------------------------------


def _utc_iso(now_utc: datetime) -> str:
    """Return ``now_utc`` as ISO-8601 with an explicit ``Z`` suffix."""
    return (
        now_utc.astimezone(timezone.utc)
        .replace(microsecond=0)
        .strftime("%Y-%m-%dT%H:%M:%SZ")
    )


def compute_digest_id(now_utc: datetime, source_cron: str | None) -> str:
    """Compose the ``digest_id`` = compact-UTC + optional source-cron.

    Compact UTC is ``%Y-%m-%dT%H%MZ`` (minute precision, e.g. ``2026-07-17T2200Z``);
    a non-empty ``source_cron`` is appended as ``-<source_cron>`` (e.g.
    ``2026-07-17T2200Z-inbox-5pm``), matching the data-model example. The
    minute-precision UTC stamp is what makes the record collision-safe across
    the 4 daily ticks (FR-016).
    """
    compact = now_utc.astimezone(timezone.utc).strftime("%Y-%m-%dT%H%MZ")
    if source_cron:
        return f"{compact}-{source_cron}"
    return compact


def build_digest_record(
    *,
    digest_id: str,
    now_utc: datetime,
    source_cron: str | None,
    entries: list[DigestEntry],
) -> dict[str, Any]:
    """Assemble the immutable correlation record (data-model.md schema)."""
    return {
        "digest_id": digest_id,
        "created_utc": _utc_iso(now_utc),
        "created_et_date": now_utc.astimezone(ET_ZONE).date().isoformat(),
        "source_cron": source_cron,
        "entries": [entry.to_dict() for entry in entries],
    }


def _atomic_write_json(path: Path, payload: dict[str, Any]) -> None:
    """Write ``payload`` to ``path`` via tmp+fsync+rename (crash-safe).

    Mirrors ``sweeper._atomic_write_json`` / ``set_due_dates._atomic_write_json``.
    """
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    body = json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=False)
    try:
        with open(tmp, "w", encoding="utf-8") as handle:
            handle.write(body)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(tmp, path)
    except OSError:
        try:
            tmp.unlink(missing_ok=True)
        except OSError:  # pragma: no cover - defensive
            pass
        raise


def _digests_dir(state_dir: Path) -> Path:
    return state_dir / "digests"


def write_digest_record(state_dir: Path, record: dict[str, Any]) -> Path:
    """Write the **immutable** per-``digest_id`` correlation record; never overwrite.

    The target is ``<state-dir>/digests/intake-<digest_id>.json``. If a file for
    this ``digest_id`` already exists it is left **untouched** (immutability,
    FR-016 — a delayed reply must always map a number to the same task it was
    shown), and the existing path is returned. Otherwise the record is written
    atomically.
    """
    digest_id = record["digest_id"]
    path = _digests_dir(state_dir) / f"intake-{digest_id}.json"
    if path.exists():
        # Immutable: a prior record for this digest_id stands. Never overwrite.
        return path
    _atomic_write_json(path, record)
    return path


def update_latest_pointer(state_dir: Path, record: dict[str, Any]) -> Path:
    """Point ``<state-dir>/latest.json`` at the newest digest record.

    Unlike the digest record itself, the pointer is mutable — it is rewritten
    each tick to name the most recent ``digest_id`` (and its file), so the apply
    step has a cheap "newest first" starting point before it widens to the
    line-number/title correlation across the 48h window.
    """
    digest_id = record["digest_id"]
    pointer = {
        "digest_id": digest_id,
        "file": f"digests/intake-{digest_id}.json",
        "created_utc": record["created_utc"],
    }
    path = state_dir / "latest.json"
    _atomic_write_json(path, pointer)
    return path


def expire_old_digests(
    state_dir: Path, now_utc: datetime, window_hours: int
) -> list[str]:
    """Delete digest records whose ``created_utc`` is older than the window.

    Returns the ``digest_id`` list expired (for the tick artifact / logging). A
    record with an unparseable/absent ``created_utc`` is left in place (fail
    safe — never delete a record we cannot date). The ``latest.json`` pointer is
    not a dated digest and is never expired here.
    """
    digests_dir = _digests_dir(state_dir)
    if not digests_dir.exists():
        return []
    cutoff = now_utc.astimezone(timezone.utc) - timedelta(hours=window_hours)
    expired: list[str] = []
    for path in sorted(digests_dir.glob("intake-*.json")):
        try:
            record = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            continue
        created = record.get("created_utc") if isinstance(record, dict) else None
        parsed = _parse_iso_utc(created) if isinstance(created, str) else None
        if parsed is None:
            continue
        if parsed < cutoff:
            try:
                path.unlink()
            except OSError:  # pragma: no cover - defensive
                continue
            digest_id = record.get("digest_id")
            expired.append(digest_id if isinstance(digest_id, str) else path.stem)
    return expired


# ---------------------------------------------------------------------------
# Per-tick observability artifact (T008 / FR-014)
# ---------------------------------------------------------------------------


@dataclass
class TickRecord:
    """The per-tick observability artifact (data-model.md → observability).

    Scan-side fields only; the apply side (WP04/WP05) aggregates its own counters
    into the same daily artifact.
    """

    started_at_utc: str
    exit_status: str  # "success" | "failure"
    scanned: int = 0
    incomplete: int = 0
    prompted: int = 0
    digest_id: str | None = None
    expired: list[str] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "started_at_utc": self.started_at_utc,
            "exit_status": self.exit_status,
            "counts": {
                "scanned": self.scanned,
                "incomplete": self.incomplete,
                "prompted": self.prompted,
            },
            "digest_id": self.digest_id,
            "expired": list(self.expired),
            "errors": list(self.errors),
        }


def write_tick_artifact(state_dir: Path, tick: TickRecord) -> Path:
    """Atomically write ``intake-tick-<ET-date>.json`` + a stable latest pointer.

    The date is derived from ``started_at_utc`` converted to ET so the filename
    matches the ET day the operator thinks of as "the day the scan ran" (habits
    sweeper convention). A stable ``intake-tick-latest.json`` copy is also written
    so a fixed-path freshness/health probe can follow the rotating dated file.
    """
    started = datetime.strptime(
        tick.started_at_utc, "%Y-%m-%dT%H:%M:%SZ"
    ).replace(tzinfo=timezone.utc)
    et_date = started.astimezone(ET_ZONE).date().isoformat()
    path = state_dir / f"intake-tick-{et_date}.json"
    _atomic_write_json(path, tick.to_dict())
    _atomic_write_json(state_dir / "intake-tick-latest.json", tick.to_dict())
    return path


# ---------------------------------------------------------------------------
# Clock boundary
# ---------------------------------------------------------------------------


def _parse_iso_utc(value: str | None) -> datetime | None:
    """Parse an ISO-8601 timestamp (``Z`` or explicit offset) to aware UTC, or
    ``None`` if unparseable. Naive timestamps are treated as UTC."""
    if not value:
        return None
    raw = value
    if raw.endswith("Z"):
        raw = raw[:-1] + "+00:00"
    try:
        parsed = datetime.fromisoformat(raw)
    except ValueError:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def _parse_now_utc(value: str | None) -> datetime:
    """Resolve the injected clock. ``value is None`` falls back to wall-clock —
    the SINGLE permitted wall-clock touch, at the CLI boundary only (mirrors
    ``sweeper._parse_now_utc``). A malformed value raises :class:`ValueError`.
    """
    if value is None:
        return datetime.now(timezone.utc)
    parsed = _parse_iso_utc(value)
    if parsed is None:
        raise ValueError(f"could not parse --now-utc {value!r}")
    return parsed


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="scripts.intake.scan_inbox",
        description=(
            "Deterministically scan the Vikunja Inbox, classify Tier-1 "
            "completeness, write an immutable per-digest correlation record + a "
            "per-tick observability artifact, and render the numbered digest "
            "text. No LLM. Reads with the felix-bot token."
        ),
    )
    parser.add_argument(
        "--state-dir",
        default=str(DEFAULT_STATE_DIR),
        metavar="PATH",
        help=f"intake state directory (default: {DEFAULT_STATE_DIR})",
    )
    parser.add_argument(
        "--source-cron",
        default=None,
        metavar="NAME",
        help="originating inbox cron name; appended to the digest_id when set",
    )
    parser.add_argument(
        "--window-hours",
        type=int,
        default=DEFAULT_WINDOW_HOURS,
        metavar="H",
        help=f"digest retention window in hours (default: {DEFAULT_WINDOW_HOURS})",
    )
    parser.add_argument(
        "--now-utc",
        default=None,
        metavar="ISO",
        help=(
            "injected UTC clock (e.g. 2026-07-17T22:00:00Z); omit to use the "
            "wall clock (production). Injected for deterministic tests."
        ),
    )
    parser.add_argument(
        "--base-url",
        default=None,
        help="override Vikunja base URL (else canonical config)",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="classify + render only; write NO state (no record, no tick)",
    )
    parser.add_argument(
        "--json",
        action="store_true",
        help="emit the scan result as JSON instead of a human SUMMARY line",
    )
    return parser


def _build_client(base_url: str | None) -> Any:
    """Construct the default (felix-bot) :class:`VikunjaClient`.

    Passing no ``token`` selects the felix-bot credential — the scan is a **read**
    and must NEVER use the kent write token (reviewer guidance / #715 two-token
    model).
    """
    from scripts.common.vikunja_client import VikunjaClient

    return VikunjaClient(base_url=base_url, timeout=_HTTP_TIMEOUT)


def _result_to_dict(
    *, status: str, digest_id: str | None, result: ScanResult, digest_text: str
) -> dict[str, Any]:
    return {
        "status": status,
        "digest_id": digest_id,
        "scanned": result.scanned,
        "incomplete": result.incomplete,
        "entries": [entry.to_dict() for entry in result.entries],
        "digest_text": digest_text,
    }


def _print_summary_line(payload: dict[str, Any]) -> None:
    print(
        f"SUMMARY: status={payload['status']} "
        f"scanned={payload['scanned']} "
        f"incomplete={payload['incomplete']} "
        f"digest_id={payload['digest_id'] or '-'}"
    )


def main(argv: list[str] | None = None, *, client: Any | None = None) -> int:
    """CLI entrypoint. Returns 0 on a completed scan (including 0-incomplete,
    SC-009), 1 on infrastructure failure.

    On the happy path (non-dry-run) it writes the immutable digest record (only
    when ``incomplete >= 1``), updates ``latest.json``, expires stale digests, and
    writes the tick artifact. ``--dry-run`` performs the read + classify + render
    and writes nothing. Exit is non-zero ONLY for infrastructure failure — a scan
    that legitimately finds nothing to prompt exits 0.
    """
    args = _build_parser().parse_args(argv)

    try:
        now_utc = _parse_now_utc(args.now_utc)
    except ValueError as exc:
        print(f"ERROR: --now-utc invalid: {exc}", file=sys.stderr)
        return 1

    state_dir = Path(args.state_dir)

    try:
        inbox_id = vikunja_refs.project_id(INBOX_PROJECT_NAME)
        active_client = client if client is not None else _build_client(args.base_url)
        result = run_scan(active_client, inbox_id=inbox_id)
    except (VikunjaError, vikunja_refs.VikunjaRefError, IntakeError) as exc:
        return _fail(state_dir, now_utc, args.dry_run, exc)
    except Exception as exc:  # noqa: BLE001 - CLI boundary: report, exit 1
        return _fail(state_dir, now_utc, args.dry_run, exc)

    entries = result.entries
    digest_text = render_digest_text(entries)
    digest_id: str | None = None

    if not args.dry_run:
        tick = TickRecord(
            started_at_utc=_utc_iso(now_utc),
            exit_status="success",
            scanned=result.scanned,
            incomplete=result.incomplete,
            prompted=result.prompted,
        )
        try:
            if entries:
                digest_id = compute_digest_id(now_utc, args.source_cron)
                record = build_digest_record(
                    digest_id=digest_id,
                    now_utc=now_utc,
                    source_cron=args.source_cron,
                    entries=entries,
                )
                write_digest_record(state_dir, record)
                update_latest_pointer(state_dir, record)
                tick.digest_id = digest_id
            tick.expired = expire_old_digests(state_dir, now_utc, args.window_hours)
            write_tick_artifact(state_dir, tick)
        except OSError as exc:
            # State write failure is an infrastructure failure (exit 1). Attempt a
            # best-effort failure tick so operators still see something on disk.
            tick.exit_status = "failure"
            tick.errors.append(f"{type(exc).__name__}: {exc}")
            try:
                write_tick_artifact(state_dir, tick)
            except OSError:  # pragma: no cover - defensive
                pass
            print(f"ERROR: intake state write failed: {exc}", file=sys.stderr)
            return 1

    payload = _result_to_dict(
        status="ok", digest_id=digest_id, result=result, digest_text=digest_text
    )
    if args.json:
        print(json.dumps(payload, ensure_ascii=False))
    else:
        _print_summary_line(payload)
    return 0


def _fail(
    state_dir: Path, now_utc: datetime, dry_run: bool, exc: Exception
) -> int:
    """Record an infrastructure failure (best-effort tick) and return exit 1."""
    message = f"{type(exc).__name__}: {exc}"
    print(f"ERROR: {message}", file=sys.stderr)
    if not dry_run:
        tick = TickRecord(
            started_at_utc=_utc_iso(now_utc),
            exit_status="failure",
            errors=[message],
        )
        try:
            write_tick_artifact(state_dir, tick)
        except OSError:  # pragma: no cover - defensive
            pass
    return 1


if __name__ == "__main__":  # pragma: no cover - CLI entry
    sys.exit(main())
