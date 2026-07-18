#!/usr/bin/env python3
"""Deterministic apply engine for Kent's compact-shorthand intake reply (WP04,
mission ``task-intake-validation-loop``, kentonium3/kg-automation#749; closes
kentonium3/kg-automation#750).

Kent answers the intake digest (produced by :mod:`scripts.intake.scan_inbox`)
with a **compact-shorthand** reply — one line per digest number, supplying only
the fields the digest reported missing. This module:

1. **Correlates** (FR-016) the reply to the right immutable digest record within
   the retention window (48h) by the reply's **line-number set + task-title/
   content evidence** — never by position in the newest file alone — mirroring
   the habits ``correlate_reply_to_checkin`` semantics. Each ``<n>`` maps to a
   ``task_id``; a number with no unambiguous task across the live digests becomes
   ``echoed_back``.
2. **Parses + resolves** each line via WP03 (:mod:`scripts.intake.shorthand`),
   optionally folding a **constrained** LLM-fallback map (``--unresolved``)
   through :func:`scripts.intake.shorthand.resolve_with_fallback` (raw ids /
   free-form values are rejected there — the LLM can never inject an id).
3. **Applies** project + labels + applicable Tier-2 through the **kent token**
   only (``vikunja-api-kent``; the felix-bot path is refused — this is the #750
   fix, SC-008) with **read-modify-write** and a **readback diff** (Vikunja POST
   ``/tasks/<id>`` is partial-replace), enforcing **family-replace** (a new
   ``q:``/``f:`` removes the prior same-family label; all non-family labels are
   preserved; a task never ends with two quadrants — NFR-003).
4. Returns a precise **per-line status** in ``{applied, echoed_back,
   overload_flagged, noop, not_found, already_done, moved_conflict,
   access_denied}`` (plus ``failed`` for a write/verify error), emits
   ``aggregates`` counts, and appends an ``intake-apply-<ET-date>.jsonl`` ledger.

Determinism (Felix Constitution Directive 6): **zero LLM calls in this module.**
The LLM is a WP03 out-of-band fallback whose only channel in is the constrained
``--unresolved`` map. The clock is injected (``--now-utc``); the module touches
wall-clock only at the single CLI boundary when ``--now-utc`` is omitted.

Two-token model (#715 / FR-007): writes use the kent token read ONLY from
:data:`DEFAULT_KENT_TOKEN_FILE`; the felix-bot token path is refused up front, so
**no felix-bot label-attach path exists** (closes #750 / SC-008).

CLI surface::

    python3 -m scripts.intake.apply_reply \\
        (--reply - | --reply-file PATH) \\
        [--state-dir /data/services/openclaw/state/intake] \\
        [--window-hours 48] \\
        [--unresolved '[{"line":1,"token":"foo","position":2,"canonical_name":"personal"}]'] \\
        [--now-utc 2026-07-17T22:00:00Z] \\
        [--token-file /data/services/openclaw/secrets/vikunja-api-kent] \\
        [--dry-run] [--json]

Exit codes::

    0 -- apply completed (per-line failures are reported, not fatal)
    1 -- infrastructure failure (bad clock, unreadable state, token guard, etc.)

Wraps the deterministic :class:`scripts.common.vikunja_client.VikunjaClient` —
the canonical stdlib HTTP boundary. No ``requests`` dependency, no new HTTP path.
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

from scripts.common import et_datetime, vikunja_refs
from scripts.common.vikunja_client import (
    VikunjaAuthError,
    VikunjaError,
    VikunjaHttpError,
    VikunjaNotFoundError,
)
from scripts.intake.shorthand import (
    FallbackItemError,
    ParsedLine,
    parse_reply,
    resolve_with_fallback,
)

# The kent-owned, all-perms token + the refused felix-bot path (#715 two-token
# model). Imported from the migrate_tasks seam so the two writers share one
# definition of "which credential mutates kent-owned data".
from scripts.vikunja.migrate_tasks import (
    DEFAULT_KENT_TOKEN_FILE,
    FELIX_BOT_TOKEN_FILE,
)

__all__ = [
    "DEFAULT_STATE_DIR",
    "DEFAULT_WINDOW_HOURS",
    "DEFAULT_KENT_TOKEN_FILE",
    "FELIX_BOT_TOKEN_FILE",
    "KENT_TOKEN",
    "INBOX_PROJECT_NAME",
    "OVERLOAD_LABEL",
    "Q_FAMILY_PREFIX",
    "F_FAMILY_PREFIX",
    "STATUSES",
    "ApplyError",
    "ApplyResult",
    "correlate_digest",
    "load_digests",
    "apply_line",
    "apply_reply",
    "read_kent_token",
    "main",
]

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

#: Default per-feature state directory on office2 (scan/apply share it).
DEFAULT_STATE_DIR = Path("/data/services/openclaw/state/intake")

#: Correlation / retention window (48h == habits parity, FR-016).
DEFAULT_WINDOW_HOURS = 48

#: Bound every external Vikunja call (seconds); the client also has its own
#: default, but the apply states its budget explicitly (NFR-005).
_HTTP_TIMEOUT = 30.0

#: Logical Inbox project name resolved via the #748 seam (never hardcoded id).
INBOX_PROJECT_NAME = "inbox"

#: The owner-token namespace for every label id (#715): kent owns the write set.
KENT_TOKEN = "kent"

#: The decomposition-pending friction marker (FR-009).
OVERLOAD_LABEL = "f:4-overload"

#: Mutually-exclusive label family prefixes (FR-013 family-replace).
Q_FAMILY_PREFIX = "q:"
F_FAMILY_PREFIX = "f:"

#: The habit type label (non-family; preserved across family-replace).
HABIT_LABEL = "t:habit"

#: The Eisenhower quadrant that resolves a task by marking it done (FR-008).
ELIMINATE_QUADRANT = "q:eliminate"

#: Quadrants that make a supplied ``due:`` applicable and, when absent, trigger a
#: non-blocking due follow-up (FR-010 / SC-007).
_DUE_FOLLOWUP_QUADRANTS = frozenset({"q:do", "q:schedule"})

#: The complete per-line status set (FR-012). ``failed`` is the write/verify
#: error bucket (a Vikunja error mid-apply), reported per-line, never fatal.
STATUSES = (
    "applied",
    "echoed_back",
    "overload_flagged",
    "noop",
    "not_found",
    "already_done",
    "moved_conflict",
    "access_denied",
    "failed",
)

#: The writable-field allowlist echoed back on a task POST so Vikunja's
#: partial-replace does not zero an unstated field (#524, mirrors
#: ``migrate_tasks._WRITABLE_FIELDS``). Labels are a *separate* association
#: (PUT/DELETE endpoints) and are intentionally NOT in this list.
_WRITABLE_FIELDS: tuple[str, ...] = (
    "title",
    "description",
    "due_date",
    "repeat_after",
    "repeat_mode",
    "priority",
    "done",
    "done_at",
    "hex_color",
    "percent_done",
    "start_date",
    "end_date",
)

#: Vikunja's "unset" due-date sentinel — the zero instant. A due_date at or
#: before this is treated as "no due date present".
_UNSET_DUE_PREFIX = "0001-01-01"


class ApplyError(Exception):
    """Fail-loud apply infrastructure error (bad clock, unreadable state, token
    guard violation, malformed ``--unresolved`` payload).

    Raised where continuing could mis-apply or act under the wrong credential.
    Surfaced by :func:`main` as a non-zero exit — never swallowed. Per-line
    Vikunja failures are NOT this: they become a per-line ``failed`` status so
    one bad line never blocks the rest (FR-012).
    """


# ---------------------------------------------------------------------------
# Per-line result (data-model.md → "Apply result")
# ---------------------------------------------------------------------------


@dataclass
class ApplyResult:
    """One reply line's independent outcome (drives the confirmation message).

    ``status`` is one of :data:`STATUSES`. ``applied`` records what actually
    changed (project name, labels added/removed, due_date, done). ``notes`` are
    deterministic human-readable confirmations (e.g. the non-blocking due
    follow-up, an ignore-with-note, a decomposition-pending confirmation).
    ``understood`` / ``failed`` carry the echo-back detail for an
    ``echoed_back`` line (what was parsed vs. what could not be resolved).
    """

    line: int | None
    task_id: int | None
    status: str
    applied: dict[str, Any] = field(default_factory=dict)
    notes: list[str] = field(default_factory=list)
    understood: dict[str, Any] = field(default_factory=dict)
    failed: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "line": self.line,
            "task_id": self.task_id,
            "status": self.status,
            "applied": self.applied,
            "notes": list(self.notes),
            "understood": self.understood,
            "failed": list(self.failed),
        }


# ---------------------------------------------------------------------------
# Correlation (T014 / FR-016)
# ---------------------------------------------------------------------------


def _parse_iso_utc(value: str | None) -> datetime | None:
    """Parse an ISO-8601 timestamp (``Z`` or offset) to aware UTC, else ``None``.

    Naive timestamps are treated as UTC (mirrors ``scan_inbox._parse_iso_utc``).
    """
    if not value:
        return None
    raw = value[:-1] + "+00:00" if value.endswith("Z") else value
    try:
        parsed = datetime.fromisoformat(raw)
    except ValueError:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def load_digests(
    state_dir: Path, now_utc: datetime, window_hours: int
) -> list[dict[str, Any]]:
    """Return the immutable digest records within the retention window.

    Reads every ``<state-dir>/digests/intake-*.json`` whose ``created_utc`` is
    within ``window_hours`` of ``now_utc`` (FR-016), sorted **newest first** so
    the correlation tiebreak favours the most recent digest. Malformed or
    undateable records are skipped (a delayed reply must never crash on one
    stale file). Never raises for a missing directory (returns ``[]``).
    """
    digests_dir = state_dir / "digests"
    if not digests_dir.exists():
        return []
    cutoff = now_utc.astimezone(timezone.utc) - timedelta(hours=window_hours)
    records: list[dict[str, Any]] = []
    for path in sorted(digests_dir.glob("intake-*.json")):
        try:
            record = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            continue
        if not isinstance(record, dict):
            continue
        created = _parse_iso_utc(record.get("created_utc"))
        if created is None or created < cutoff:
            continue
        records.append(record)
    records.sort(
        key=lambda r: _parse_iso_utc(r.get("created_utc")) or cutoff, reverse=True
    )
    return records


def _entry_numbers(record: dict[str, Any]) -> dict[int, dict[str, Any]]:
    """Return ``{n: entry}`` for a digest record's well-shaped entries."""
    out: dict[int, dict[str, Any]] = {}
    for entry in record.get("entries") or []:
        if not isinstance(entry, dict):
            continue
        n = entry.get("n")
        if isinstance(n, int) and not isinstance(n, bool):
            out[n] = entry
    return out


def _title_evidence_score(
    lines: list[ParsedLine], entries: dict[int, dict[str, Any]]
) -> int:
    """Count reply lines whose raw text contains a title-token of their mapped
    entry — the task-title/content evidence tiebreak (FR-016).

    Compact-shorthand replies are usually pure numbers, so this is a *tiebreak*
    on top of the line-number-set overlap: when two digests both cover a reply's
    numbers, the one whose entry titles actually appear in the reply text wins.
    """
    score = 0
    for line in lines:
        if line.n is None:
            continue
        entry = entries.get(line.n)
        if entry is None:
            continue
        title = entry.get("title")
        if not isinstance(title, str) or not title:
            continue
        raw = line.raw.lower()
        if any(len(tok) >= 4 and tok in raw for tok in title.lower().split()):
            score += 1
    return score


def correlate_digest(
    lines: list[ParsedLine], digests: list[dict[str, Any]]
) -> tuple[dict[str, Any] | None, dict[int, int]]:
    """Select the correlated digest + the ``{n: task_id}`` map (FR-016).

    Scores each live digest by how many of the reply's line numbers it covers
    (the **line-number set** evidence); ties break on **task-title/content
    evidence** (:func:`_title_evidence_score`), then on recency (``digests`` is
    newest-first). Returns ``(record, mapping)`` for the winner, or
    ``(None, {})`` when the reply carries no usable number / no digest matches.
    A number absent from the winner is simply not in ``mapping`` — the caller
    ``echoed_back`` it (FR-012 orphan-number rule).
    """
    reply_numbers = {line.n for line in lines if line.n is not None}
    if not reply_numbers or not digests:
        return None, {}

    best: dict[str, Any] | None = None
    best_key: tuple[int, int] = (0, 0)
    for record in digests:
        entries = _entry_numbers(record)
        overlap = len(reply_numbers & entries.keys())
        if overlap == 0:
            continue
        title_score = _title_evidence_score(lines, entries)
        key = (overlap, title_score)
        # digests is newest-first, so the first record achieving a key wins ties
        # (strictly-greater comparison keeps the earlier — newer — record).
        if key > best_key:
            best_key = key
            best = record

    if best is None:
        return None, {}

    entries = _entry_numbers(best)
    mapping: dict[int, int] = {}
    for n, entry in entries.items():
        task_id = entry.get("task_id")
        if isinstance(task_id, int) and not isinstance(task_id, bool):
            mapping[n] = task_id
    return best, mapping


# ---------------------------------------------------------------------------
# Tier-2 helpers — ET end-of-day due date (#733)
#
# The ET end-of-day write and the Vikunja-instant parse both live in the
# canonical ``scripts.common.et_datetime`` module (#761):
# ``et_datetime.et_end_of_day`` (formerly the inline ``_et_eod``) and
# ``et_datetime.parse_vikunja_instant`` (formerly the inline ``_due_instant``).
# ---------------------------------------------------------------------------


# ---------------------------------------------------------------------------
# Label / task read helpers
# ---------------------------------------------------------------------------


def _live_labels(task: dict[str, Any]) -> list[dict[str, Any]]:
    """Return the task's well-shaped label entries (``{id, title}``)."""
    out: list[dict[str, Any]] = []
    for label in task.get("labels") or []:
        if not isinstance(label, dict):
            continue
        lid = label.get("id")
        title = label.get("title")
        if (
            isinstance(lid, int)
            and not isinstance(lid, bool)
            and isinstance(title, str)
        ):
            out.append({"id": lid, "title": title})
    return out


def _label_titles(task: dict[str, Any]) -> set[str]:
    return {label["title"] for label in _live_labels(task)}


def _family_members(labels: list[dict[str, Any]], prefix: str) -> list[dict[str, Any]]:
    return [label for label in labels if label["title"].startswith(prefix)]


def _has_due(task: dict[str, Any]) -> bool:
    """True iff the task carries a real (non-sentinel) due date."""
    due = task.get("due_date")
    return isinstance(due, str) and bool(due) and not due.startswith(_UNSET_DUE_PREFIX)


def _is_recurring(task: dict[str, Any]) -> bool:
    """True iff the task already carries native recurrence (``repeat_after``)."""
    repeat = task.get("repeat_after")
    return isinstance(repeat, int) and not isinstance(repeat, bool) and repeat > 0


def _resolve_project_id(name: str) -> int:
    return vikunja_refs.project_id(name)


def _resolve_label_id(name: str) -> int:
    return vikunja_refs.label_id(name, KENT_TOKEN)


# ---------------------------------------------------------------------------
# Write primitives (kent token; RMW + readback)
# ---------------------------------------------------------------------------


def _writable_payload(task: dict[str, Any]) -> dict[str, Any]:
    """Copy the writable-field allowlist from a task (non-clobber; #524)."""
    return {name: task[name] for name in _WRITABLE_FIELDS if name in task}


def _post_task_fields(
    client: Any, task: dict[str, Any], changes: dict[str, Any]
) -> None:
    """Apply task-field ``changes`` (project_id / due_date / done) via an
    allowlisted RMW POST + readback diff.

    Echoes the writable allowlist so Vikunja's partial-replace does not zero an
    unstated field, POSTs ``/tasks/<id>``, then GETs the task back and asserts
    every intended change took and no allowlisted field drifted. A readback
    mismatch raises :class:`ApplyError` (caller maps it to a per-line
    ``failed``).
    """
    task_id = task["id"]
    payload = _writable_payload(task)
    payload.update(changes)
    client.post(f"/tasks/{task_id}", json=payload, timeout=_HTTP_TIMEOUT)

    readback = client.get(f"/tasks/{task_id}", timeout=_HTTP_TIMEOUT)
    if not isinstance(readback, dict):
        raise ApplyError(
            f"field readback for task {task_id} returned a non-object; refusing "
            f"to trust the write."
        )
    for name, value in changes.items():
        got = readback.get(name)
        if name == "due_date":
            # Vikunja normalizes due_dates to UTC 'Z' (#733/#736), so compare the
            # INSTANT — a raw string compare of our ET-offset write against the
            # returned UTC form false-fails and triggers a retry storm (#757).
            if et_datetime.parse_vikunja_instant(
                got
            ) != et_datetime.parse_vikunja_instant(value):
                raise ApplyError(
                    f"field readback for task {task_id}: due_date instant is "
                    f"{got!r}, expected {value!r} (partial-replace drift, #524)."
                )
            continue
        if got != value:
            raise ApplyError(
                f"field readback for task {task_id}: {name!r} is "
                f"{got!r}, expected {value!r} (partial-replace drift, #524)."
            )


def _attach_label(client: Any, task_id: int, label_id: int) -> None:
    client.put(
        f"/tasks/{task_id}/labels",
        json={"label_id": label_id},
        timeout=_HTTP_TIMEOUT,
    )


def _remove_label(client: Any, task_id: int, label_id: int) -> None:
    client.delete(f"/tasks/{task_id}/labels/{label_id}", timeout=_HTTP_TIMEOUT)


# ---------------------------------------------------------------------------
# Per-line planning + apply (T015 / T016 / T017)
# ---------------------------------------------------------------------------


@dataclass
class _LinePlan:
    """The computed, not-yet-executed mutation for one line."""

    field_changes: dict[str, Any] = field(default_factory=dict)
    labels_add: list[tuple[str, int]] = field(default_factory=list)  # (title, id)
    labels_remove: list[tuple[str, int]] = field(default_factory=list)
    applied: dict[str, Any] = field(default_factory=dict)
    notes: list[str] = field(default_factory=list)
    is_overload: bool = False

    def has_work(self) -> bool:
        return bool(self.field_changes or self.labels_add or self.labels_remove)


def _plan_family_label(
    plan: _LinePlan,
    live_labels: list[dict[str, Any]],
    new_title: str,
    prefix: str,
) -> None:
    """Queue a family-replace: add ``new_title`` and remove any other same-family
    member (FR-013). A no-op if the task already carries exactly ``new_title``.
    """
    new_id = _resolve_label_id(new_title)
    existing = _family_members(live_labels, prefix)
    already = any(label["title"] == new_title for label in existing)
    for label in existing:
        if label["title"] != new_title:
            plan.labels_remove.append((label["title"], label["id"]))
    if not already:
        plan.labels_add.append((new_title, new_id))


def _plan_nonfamily_label(
    plan: _LinePlan, live_labels: list[dict[str, Any]], title: str
) -> None:
    """Queue a non-family label attach if absent (preserved, never replaces)."""
    if any(label["title"] == title for label in live_labels):
        return
    plan.labels_add.append((title, _resolve_label_id(title)))


def _plan_line(
    line: ParsedLine,
    task: dict[str, Any],
) -> _LinePlan:
    """Compute the sparse mutation for one resolved line against the live task.

    Applies only supplied fields (SC-010). Enforces family-replace for ``q:``/
    ``f:`` (FR-013), the Tier-2 compatibility matrix (FR-017), the ``f:4``
    decomposition-pending disposition (FR-009), and ``q:eliminate`` → done
    (FR-008). Field/label resolution errors (unprovisioned ref, bad ``due:``)
    are captured as echo-back notes rather than aborting the line.
    """
    plan = _LinePlan()
    live_labels = _live_labels(task)
    live_titles = _label_titles(task)

    is_overload = line.friction == OVERLOAD_LABEL
    plan.is_overload = is_overload

    # Effective quadrant governs the Tier-2 matrix: the line's quadrant if
    # supplied, else the task's current q:* label (for a sparse Tier-2-only line).
    live_q = next(
        (t for t in sorted(live_titles) if t.startswith(Q_FAMILY_PREFIX)), None
    )
    effective_q = line.quadrant or live_q

    # --- Friction (family f:) -------------------------------------------------
    if line.friction is not None:
        try:
            _plan_family_label(plan, live_labels, line.friction, F_FAMILY_PREFIX)
            plan.applied.setdefault("labels", []).append(line.friction)
        except vikunja_refs.VikunjaRefError as exc:
            plan.notes.append(f"could not resolve {line.friction}: {exc}")

    # --- Quadrant (family q:) + q:eliminate → done ---------------------------
    if line.quadrant is not None:
        try:
            _plan_family_label(plan, live_labels, line.quadrant, Q_FAMILY_PREFIX)
            plan.applied.setdefault("labels", []).append(line.quadrant)
        except vikunja_refs.VikunjaRefError as exc:
            plan.notes.append(f"could not resolve {line.quadrant}: {exc}")
        if line.quadrant == ELIMINATE_QUADRANT and not task.get("done"):
            plan.field_changes["done"] = True
            plan.applied["done"] = True
            plan.notes.append("marked done (eliminated) — resolves intake (FR-008)")

    # --- Project reassignment (skip for eliminate: no working project needed) -
    if line.project is not None and line.quadrant != ELIMINATE_QUADRANT:
        try:
            pid = _resolve_project_id(line.project)
            if task.get("project_id") != pid:
                plan.field_changes["project_id"] = pid
            plan.applied["project"] = line.project
        except vikunja_refs.VikunjaRefError as exc:
            plan.notes.append(f"could not resolve project {line.project}: {exc}")
    elif line.project is not None and line.quadrant == ELIMINATE_QUADRANT:
        plan.notes.append(
            f"ignored project {line.project} — eliminate needs no working project"
        )

    # --- f:4 overload disposition (FR-009 / SC-004): NOT scheduled -----------
    if is_overload:
        plan.notes.append(
            "decomposition-pending — flagged f:4-overload, not scheduled (FR-009)"
        )

    # --- Tier-2: due: (matrix FR-017 / FR-010) -------------------------------
    due_ignored = is_overload or effective_q == ELIMINATE_QUADRANT
    if line.due is not None:
        if due_ignored:
            plan.notes.append(
                f"ignored due:{line.due} — incompatible with "
                f"{'f:4-overload' if is_overload else ELIMINATE_QUADRANT} "
                f"(ignore-with-note)"
            )
        else:
            try:
                eod = et_datetime.et_end_of_day(line.due)
                if task.get("due_date") != eod:
                    plan.field_changes["due_date"] = eod
                plan.applied["due_date"] = eod
            except ValueError:
                # Malformed due: → echo-back token (never a garbage instant).
                line.unresolved_tokens.append(f"due:{line.due}")
    elif (
        not is_overload
        and effective_q in _DUE_FOLLOWUP_QUADRANTS
        and not _has_due(task)
    ):
        # q:do / q:schedule with no due: supplied AND no live due date → the
        # non-blocking follow-up (SC-007). The ``_has_due`` guard means a task
        # that already carries a due date never triggers a spurious "has no due
        # date" note when the reply omits ``due:`` (review cycle 1).
        plan.notes.append(
            f"follow-up: {effective_q} has no due date — reply with due:<date> "
            f"(non-blocking)"
        )
        plan.applied["due_followup"] = True

    # --- Tier-2: habit → t:habit (matrix FR-017) -----------------------------
    if line.habit:
        if due_ignored:
            plan.notes.append(
                "ignored habit — incompatible with eliminate/overload "
                "(ignore-with-note)"
            )
        else:
            _plan_nonfamily_label(plan, live_labels, HABIT_LABEL)
            plan.applied.setdefault("labels", []).append(HABIT_LABEL)
            if _is_recurring(task):
                plan.notes.append(
                    "t:habit noted — task already recurring, no double-recurrence"
                )

    # --- Tier-2: loe: (matrix FR-017 — apply in every valid column) ----------
    if line.loe is not None:
        try:
            _plan_nonfamily_label(plan, live_labels, line.loe)
            plan.applied.setdefault("labels", []).append(line.loe)
        except vikunja_refs.VikunjaRefError as exc:
            plan.notes.append(f"could not resolve {line.loe}: {exc}")

    return plan


def _verify_labels(
    client: Any,
    task_id: int,
    expected_present: set[str],
    expected_absent: set[str],
    preserved: set[str],
) -> None:
    """GET the task and assert the family-replace + zero-clobber invariants.

    ``expected_present`` must all be on the task; ``expected_absent`` none of
    them; every ``preserved`` (pre-existing non-family) label must survive. A
    violation raises :class:`ApplyError` (→ per-line ``failed``). Also asserts
    at most one ``q:`` and one ``f:`` label remain (NFR-003 — never two
    quadrants).
    """
    readback = client.get(f"/tasks/{task_id}", timeout=_HTTP_TIMEOUT)
    if not isinstance(readback, dict):
        raise ApplyError(
            f"label readback for task {task_id} returned a non-object."
        )
    titles = _label_titles(readback)
    missing = expected_present - titles
    if missing:
        raise ApplyError(
            f"label readback for task {task_id}: expected {sorted(missing)} "
            f"present, got {sorted(titles)}."
        )
    lingering = expected_absent & titles
    if lingering:
        raise ApplyError(
            f"label readback for task {task_id}: {sorted(lingering)} should have "
            f"been family-replaced but survived."
        )
    dropped = preserved - titles
    if dropped:
        raise ApplyError(
            f"label readback for task {task_id}: non-family labels "
            f"{sorted(dropped)} were clobbered (NFR-003)."
        )
    for prefix in (Q_FAMILY_PREFIX, F_FAMILY_PREFIX):
        fam = [t for t in titles if t.startswith(prefix)]
        if len(fam) > 1:
            raise ApplyError(
                f"label readback for task {task_id}: {len(fam)} {prefix!r} labels "
                f"{sorted(fam)} — a family must never leave two members (NFR-003)."
            )


def _classify_access_error(exc: VikunjaError) -> str:
    """Map a Vikunja error to a per-line status.

    401/403 → ``access_denied`` (kent token cannot write here, FR-012); 404 →
    ``not_found``; anything else → ``failed``.
    """
    if isinstance(exc, VikunjaAuthError):
        return "access_denied"
    if isinstance(exc, VikunjaNotFoundError):
        return "not_found"
    if isinstance(exc, VikunjaHttpError) and exc.status == 403:
        return "access_denied"
    return "failed"


def apply_line(
    client: Any,
    line: ParsedLine,
    task_id: int | None,
    *,
    inbox_id: int,
    dry_run: bool,
) -> ApplyResult:
    """Apply one resolved reply line; return its independent :class:`ApplyResult`.

    Status precedence (FR-012 / FR-013):

    - no number / no correlated task → ``echoed_back`` (orphan);
    - GET failure → ``not_found`` / ``access_denied`` / ``failed``;
    - task already done → ``already_done``;
    - line resolves no actionable field → ``echoed_back``;
    - the correlated task was moved out of Inbox to a *different* project than
      the reply intends → ``moved_conflict``;
    - ``f:4`` → ``overload_flagged``;
    - a plan with no live diff → ``noop``;
    - otherwise apply → ``applied``.

    ``dry_run`` plans + classifies without issuing any write.
    """
    if line.n is None:
        return ApplyResult(
            line=None,
            task_id=None,
            status="echoed_back",
            failed=list(line.unresolved_tokens) or [line.raw],
            notes=["no digest number on this line"],
        )
    if task_id is None:
        return ApplyResult(
            line=line.n,
            task_id=None,
            status="echoed_back",
            understood={"line": line.n},
            failed=["no correlated task for this number"],
        )

    try:
        task = client.get(f"/tasks/{task_id}", timeout=_HTTP_TIMEOUT)
    except VikunjaError as exc:
        return ApplyResult(
            line=line.n,
            task_id=task_id,
            status=_classify_access_error(exc),
            notes=[f"{type(exc).__name__}"],
        )
    if not isinstance(task, dict):
        return ApplyResult(
            line=line.n, task_id=task_id, status="failed",
            notes=["GET /tasks returned a non-object"],
        )

    if task.get("done") is True:
        return ApplyResult(
            line=line.n, task_id=task_id, status="already_done",
            notes=["task already done"],
        )

    has_action = any(
        (
            line.project is not None,
            line.friction is not None,
            line.quadrant is not None,
            line.due is not None,
            line.habit,
            line.loe is not None,
        )
    )
    if not has_action:
        return ApplyResult(
            line=line.n, task_id=task_id, status="echoed_back",
            understood={"line": line.n},
            failed=list(line.unresolved_tokens),
            notes=["no resolvable field on this line"],
        )

    # moved_conflict: another process routed the task out of Inbox to a project
    # other than the one the reply intends (never clobber someone else's move).
    if line.project is not None and line.quadrant != ELIMINATE_QUADRANT:
        live_pid = task.get("project_id")
        try:
            intended_pid = _resolve_project_id(line.project)
        except vikunja_refs.VikunjaRefError:
            intended_pid = None
        if (
            intended_pid is not None
            and isinstance(live_pid, int)
            and not isinstance(live_pid, bool)
            and live_pid != inbox_id
            and live_pid != intended_pid
        ):
            return ApplyResult(
                line=line.n, task_id=task_id, status="moved_conflict",
                notes=[
                    f"task left Inbox to project {live_pid}; reply intended "
                    f"{line.project} ({intended_pid}) — not clobbering"
                ],
            )

    plan = _plan_line(line, task)

    # Echo-back tokens surfaced during planning (e.g. malformed due:) ride along
    # as an informational note, but never demote a successful apply.
    echoed = list(line.unresolved_tokens)

    result = ApplyResult(
        line=line.n,
        task_id=task_id,
        status="applied",
        applied=dict(plan.applied),
        notes=list(plan.notes),
        failed=echoed,
    )

    if plan.is_overload:
        result.status = "overload_flagged"
    elif not plan.has_work():
        result.status = "noop"
        result.notes.append("live state already matches — nothing to apply")

    if dry_run or not plan.has_work():
        return result

    # --- Execute (kent token). One bad line → failed, never blocks the rest. --
    try:
        if plan.field_changes:
            _post_task_fields(client, task, plan.field_changes)
        for _title, lid in plan.labels_remove:
            _remove_label(client, task_id, lid)
        for _title, lid in plan.labels_add:
            _attach_label(client, task_id, lid)

        preserved = {
            label["title"]
            for label in _live_labels(task)
            if not label["title"].startswith(Q_FAMILY_PREFIX)
            and not label["title"].startswith(F_FAMILY_PREFIX)
        }
        _verify_labels(
            client,
            task_id,
            expected_present={t for t, _ in plan.labels_add},
            expected_absent={t for t, _ in plan.labels_remove},
            preserved=preserved,
        )
    except (VikunjaError, ApplyError) as exc:
        return ApplyResult(
            line=line.n, task_id=task_id,
            status=_classify_access_error(exc)
            if isinstance(exc, VikunjaError)
            else "failed",
            applied=dict(plan.applied),
            notes=[*plan.notes, f"write failed: {type(exc).__name__}"],
            failed=echoed,
        )

    return result


# ---------------------------------------------------------------------------
# Orchestration (T014 → T017)
# ---------------------------------------------------------------------------


def apply_reply(
    client: Any,
    reply_text: str,
    *,
    state_dir: Path,
    now_utc: datetime,
    window_hours: int = DEFAULT_WINDOW_HOURS,
    unresolved_map: list[dict[str, Any]] | None = None,
    dry_run: bool = False,
) -> dict[str, Any]:
    """Parse → correlate → apply a full reply; return the result document.

    Returns ``{digest_id, results:[ApplyResult...], aggregates:{...}}`` matching
    ``contracts/helpers.contract.md``. Pure of state *writes* beyond the Vikunja
    mutations and (via the caller) the ledger append — correlation reads are the
    only state I/O here. One failing line never blocks the rest (FR-012).
    """
    lines = parse_reply(reply_text)
    if unresolved_map:
        resolve_with_fallback(lines, unresolved_map)

    inbox_id = _resolve_project_id(INBOX_PROJECT_NAME)
    digests = load_digests(state_dir, now_utc, window_hours)
    record, mapping = correlate_digest(lines, digests)
    digest_id = record.get("digest_id") if isinstance(record, dict) else None

    results: list[ApplyResult] = []
    for line in lines:
        task_id = mapping.get(line.n) if line.n is not None else None
        results.append(
            apply_line(
                client, line, task_id, inbox_id=inbox_id, dry_run=dry_run
            )
        )

    aggregates = {status: 0 for status in STATUSES}
    for result in results:
        aggregates[result.status] = aggregates.get(result.status, 0) + 1

    return {
        "digest_id": digest_id,
        "results": [r.to_dict() for r in results],
        "aggregates": aggregates,
    }


# ---------------------------------------------------------------------------
# Ledger (FR-014)
# ---------------------------------------------------------------------------


def _et_date(now_utc: datetime) -> str:
    return et_datetime.to_et(now_utc).date().isoformat()


def append_ledger(
    state_dir: Path, now_utc: datetime, document: dict[str, Any]
) -> Path:
    """Append each ``ApplyResult`` to ``intake-apply-<ET-date>.jsonl`` (FR-014).

    One JSON object per line, stamped with the digest id + apply time, so the
    daily observability artifact carries the individual per-line outcomes
    alongside the scan-side tick. Creates ``state_dir`` if absent.
    """
    state_dir.mkdir(parents=True, exist_ok=True)
    path = state_dir / f"intake-apply-{_et_date(now_utc)}.jsonl"
    stamp = (
        now_utc.astimezone(timezone.utc)
        .replace(microsecond=0)
        .strftime("%Y-%m-%dT%H:%M:%SZ")
    )
    with open(path, "a", encoding="utf-8") as handle:
        for result in document["results"]:
            record = {
                "applied_at_utc": stamp,
                "digest_id": document["digest_id"],
                **result,
            }
            handle.write(json.dumps(record, ensure_ascii=False) + "\n")
    return path


# ---------------------------------------------------------------------------
# Token guard (#750 / FR-007) + clock
# ---------------------------------------------------------------------------


def read_kent_token(path: str) -> str:
    """Read the kent write token from ``path``; refuse the felix-bot path.

    Reuses the ``migrate_tasks`` two-token guard: the known felix-bot token path
    is refused outright (a felix-bot write makes kent-invisible changes and
    cannot attach a kent-owned label — the #750 403 path), and this helper reads
    ONLY the given file, never the ``VikunjaClient`` felix-bot default. There is
    thus **no felix-bot label-attach path** anywhere in the apply engine
    (SC-008). Raises :class:`ApplyError` on the refused path or an empty/missing
    file.
    """
    if os.path.abspath(path) == os.path.abspath(FELIX_BOT_TOKEN_FILE):
        raise ApplyError(
            f"refusing the felix-bot token file {path!r}: intake apply attaches "
            f"kent-owned labels and reassigns kent projects; it MUST use the "
            f"'vikunja-api-kent' credential (#715 two-token model / #750)."
        )
    try:
        with open(path, encoding="utf-8") as handle:
            token = handle.read()
    except OSError as exc:
        raise ApplyError(
            f"kent token file {path!r} could not be read: {exc}. Apply requires "
            f"the kent-owned 'vikunja-api-kent' credential and never falls back "
            f"to the felix-bot token."
        ) from exc
    if not token.strip():
        raise ApplyError(f"kent token file {path!r} is empty.")
    return token


def _parse_now_utc(value: str | None) -> datetime:
    """Resolve the injected clock; ``None`` → wall-clock (the single permitted
    touch, at the CLI boundary only). A malformed value raises ``ValueError``.
    """
    if value is None:
        return datetime.now(timezone.utc)
    parsed = _parse_iso_utc(value)
    if parsed is None:
        raise ValueError(f"could not parse --now-utc {value!r}")
    return parsed


# ---------------------------------------------------------------------------
# CLI (T018)
# ---------------------------------------------------------------------------


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="scripts.intake.apply_reply",
        description=(
            "Correlate Kent's compact-shorthand intake reply to the right digest "
            "and apply project + labels + applicable Tier-2 via the kent token "
            "(read-modify-write, family-replace, per-line statuses). No LLM. "
            "Closes #750: kent-token writes only."
        ),
    )
    source = parser.add_mutually_exclusive_group(required=True)
    source.add_argument(
        "--reply",
        metavar="TEXT",
        help="the reply text; pass '-' to read from stdin",
    )
    source.add_argument(
        "--reply-file",
        metavar="PATH",
        help="read the reply text from this file",
    )
    parser.add_argument(
        "--state-dir",
        default=str(DEFAULT_STATE_DIR),
        metavar="PATH",
        help=f"intake state directory (default: {DEFAULT_STATE_DIR})",
    )
    parser.add_argument(
        "--window-hours",
        type=int,
        default=DEFAULT_WINDOW_HOURS,
        metavar="H",
        help=f"correlation/retention window (default: {DEFAULT_WINDOW_HOURS})",
    )
    parser.add_argument(
        "--unresolved",
        default=None,
        metavar="JSON",
        help=(
            "constrained LLM-fallback map: a JSON list of "
            "{line, token, position, canonical_name}. Each canonical_name is "
            "re-resolved through the seam; raw ids / free-form values are "
            "rejected. Never a channel for arbitrary values."
        ),
    )
    parser.add_argument(
        "--token-file",
        default=DEFAULT_KENT_TOKEN_FILE,
        metavar="PATH",
        help=(
            "kent-owned API token file (default: "
            f"{DEFAULT_KENT_TOKEN_FILE}). The felix-bot token path is refused."
        ),
    )
    parser.add_argument(
        "--now-utc",
        default=None,
        metavar="ISO",
        help="injected UTC clock (e.g. 2026-07-17T22:00:00Z); omit for wall clock",
    )
    parser.add_argument(
        "--base-url",
        default=None,
        help="override Vikunja base URL (else canonical config)",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="correlate + plan + classify; issue NO writes and NO ledger append",
    )
    parser.add_argument(
        "--json",
        action="store_true",
        help="emit the full result document as JSON (else a SUMMARY line)",
    )
    return parser


def _read_reply(args: argparse.Namespace) -> str:
    if args.reply_file is not None:
        return Path(args.reply_file).read_text(encoding="utf-8")
    if args.reply == "-":
        return sys.stdin.read()
    return args.reply


def _build_client(args: argparse.Namespace) -> Any:
    """Construct a kent-token :class:`VikunjaClient` (never felix-bot)."""
    from scripts.common.vikunja_client import VikunjaClient

    token = read_kent_token(args.token_file)
    return VikunjaClient(base_url=args.base_url, token=token, timeout=_HTTP_TIMEOUT)


def _parse_unresolved(raw: str | None) -> list[dict[str, Any]] | None:
    if raw is None:
        return None
    try:
        parsed = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise ApplyError(f"--unresolved is not valid JSON: {exc}") from exc
    if not isinstance(parsed, list):
        raise ApplyError("--unresolved must be a JSON list of fallback items")
    return parsed


def main(argv: list[str] | None = None, *, client: Any | None = None) -> int:
    """CLI entrypoint. Returns 0 on a completed apply (per-line failures are
    reported, not fatal), 1 on infrastructure failure.
    """
    args = _build_parser().parse_args(argv)

    try:
        now_utc = _parse_now_utc(args.now_utc)
    except ValueError as exc:
        print(f"ERROR: --now-utc invalid: {exc}", file=sys.stderr)
        return 1

    state_dir = Path(args.state_dir)

    try:
        reply_text = _read_reply(args)
        unresolved_map = _parse_unresolved(args.unresolved)
        # Enforce the token guard even when a client is injected (tests exercise
        # the CLI refusal by passing --token-file); the felix-bot path never
        # yields a usable client.
        if os.path.abspath(args.token_file) == os.path.abspath(FELIX_BOT_TOKEN_FILE):
            raise ApplyError(
                f"refusing the felix-bot token file {args.token_file!r} "
                f"(#715 two-token model / #750)."
            )
        active_client = client if client is not None else _build_client(args)

        document = apply_reply(
            active_client,
            reply_text,
            state_dir=state_dir,
            now_utc=now_utc,
            window_hours=args.window_hours,
            unresolved_map=unresolved_map,
            dry_run=args.dry_run,
        )
        if not args.dry_run:
            append_ledger(state_dir, now_utc, document)
    except (ApplyError, FallbackItemError, VikunjaError, OSError, ValueError) as exc:
        print(f"ERROR: {type(exc).__name__}: {exc}", file=sys.stderr)
        return 1
    except vikunja_refs.VikunjaRefError as exc:
        print(f"ERROR: {type(exc).__name__}: {exc}", file=sys.stderr)
        return 1

    if args.json:
        print(json.dumps(document, ensure_ascii=False))
    else:
        agg = document["aggregates"]
        summary = " ".join(f"{k}={v}" for k, v in agg.items() if v)
        print(
            f"SUMMARY: digest_id={document['digest_id'] or '-'} "
            f"lines={len(document['results'])} {summary}".rstrip()
        )
    return 0


if __name__ == "__main__":  # pragma: no cover - CLI entry
    sys.exit(main())
