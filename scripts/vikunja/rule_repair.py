"""Reversible recurrence-rule repair (mission felix-rrule-adaptation, #1111).

Contract:
``kitty-specs/felix-rrule-adaptation-01M7TKNX/contracts/repair-and-inventory-cli.md``;
restore algorithm and Invariant 5: ``data-model.md``.

Usage::

    python3 -m scripts.vikunja.rule_repair --plan <inventory.json> [--task-id N ...] --dry-run
    python3 -m scripts.vikunja.rule_repair --plan <inventory.json> [--task-id N ... --accept-changed] --apply
    python3 -m scripts.vikunja.rule_repair --resume <run_id>
    python3 -m scripts.vikunja.rule_repair --restore <run_dir>/<id>.before.json
    python3 -m scripts.vikunja.rule_repair --emit-issue-markdown <run_id> [--markdown-out FILE]

``--apply`` acts on inventory status ``lost`` only. ``removed``, ``ended``,
``changed`` and ``progressed`` tasks are written only when named with
``--task-id`` **and** ``--accept-changed`` is passed (Kent's explicit choice).
``ok``, ``deleted`` and ``unresolved`` tasks are never written.

Per task (``--apply``):

1. fresh ``get_task_v2`` and drift check against the inventory's
   ``current_fingerprint``; any difference -> outcome ``skipped_drift``, next task;
2. ``<run>/<id>.before.json`` (mode 600, fsync), then an ``intent`` journal
   line (fsync). Either failing stops the run before any Vikunja write;
3. clear-first rule write: ``{"repeat": null}`` when a rule exists, then
   ``{"repeats_rrule": text, "repeats_from_current_date": bool}``;
4. readback with ``get_task_v2`` and ``same_rule``;
5. an ``outcome`` journal line for every attempt: ``ok | mismatch | unknown``.
   ``mismatch`` or ``unknown`` stops the run and prints the restore command.

``--resume`` resolves every intent whose latest outcome is missing or
``unknown`` with a fresh read **before anything else**, then continues with
the run's remaining planned tasks.

The rule write and the restore share one internal writer; it is the only
caller of the client's private ``_allow_null`` (``repeat`` and, on restore,
``due_date``).

Exit codes: 0 ok, 2 bad args or refused, 3 Vikunja read error (the message
names the run id and the writes the run already made; after any write,
``--resume`` that run and emit it before a new ``--apply``),
4 local state write failed (no Vikunja write after it), 5 stopped on
``mismatch``/``unknown`` (the restore command is printed).
"""

from __future__ import annotations

import argparse
import getpass
import hashlib
import json
import os
import sys
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from scripts.common.et_datetime import parse_vikunja_instant
from scripts.common.vikunja_client import (
    VikunjaClient,
    VikunjaError,
    VikunjaNotFoundError,
)
from scripts.common.vikunja_rule import (
    has_rule,
    parts_to_rrule_text,
    rrule_text_to_parts,
    same_rule,
)
from scripts.habits.sweeper import new_tick_id
from scripts.vikunja.rule_inventory import (
    PUBLIC_HABIT_IDS,
    current_rule_text,
    fingerprint,
    fingerprint_diff,
    safe_cell,
)

__all__ = [
    "DEFAULT_STATE_DIR",
    "EXIT_REFUSED",
    "EXIT_STATE",
    "EXIT_STOPPED",
    "EXIT_VIKUNJA",
    "main",
    "restore_command",
]

DEFAULT_STATE_DIR = Path("/data/services/openclaw/state/vikunja-repair")

EXIT_OK = 0
EXIT_REFUSED = 2
EXIT_VIKUNJA = 3
EXIT_STATE = 4
EXIT_STOPPED = 5

#: Statuses ``--apply`` acts on without ``--accept-changed``.
AUTO_STATUSES = frozenset({"lost"})
#: Statuses that need ``--task-id N --accept-changed``.
ACCEPT_STATUSES = frozenset({"removed", "ended", "changed", "progressed"})

#: Fields recorded as ``before`` / ``after`` (data-model.md Live-write record).
RECORD_FIELDS: tuple[str, ...] = (
    "repeat",
    "repeats_rrule",
    "repeats_from_current_date",
    "reminders",
    "done",
    "due_date",
)

JOURNAL_NAME = "journal.jsonl"
#: Bytes of a torn final journal line, kept as evidence when the tail is repaired.
TORN_NAME = "journal.jsonl.torn"
RUN_NAME = "run.json"


class StateWriteError(Exception):
    """A snapshot, run record or journal write failed."""


class Refused(Exception):
    """The request is refused before any write."""


@dataclass
class Stop(Exception):
    """The run stops on ``mismatch`` / ``unknown``."""

    task_id: int
    outcome: str
    restore: str


def _now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def restore_command(snapshot_path: Path) -> str:
    """The exact command that undoes one write (data-model.md)."""
    return f"python3 -m scripts.vikunja.rule_repair --restore {snapshot_path}"


def _record(task: Mapping[str, Any] | None) -> dict[str, Any] | None:
    if task is None:
        return None
    return {key: task.get(key) for key in RECORD_FIELDS}


def _error_info(exc: BaseException) -> dict[str, Any]:
    return {"type": type(exc).__name__, "status": getattr(exc, "status", None)}


# ---------------------------------------------------------------------------
# Durable local state
# ---------------------------------------------------------------------------


def _fsync_dir(path: Path) -> None:
    fd = os.open(path, os.O_RDONLY)
    try:
        os.fsync(fd)
    finally:
        os.close(fd)


def _make_run_dir(state_dir: Path, run_id: str) -> Path:
    try:
        state_dir.mkdir(mode=0o700, parents=True, exist_ok=True)
        run_dir = state_dir / run_id
        run_dir.mkdir(mode=0o700)
        _fsync_dir(state_dir)
    except OSError as exc:
        raise StateWriteError(f"cannot create run dir: {exc}") from exc
    return run_dir


def _write_snapshot_file(path: Path, document: Mapping[str, Any]) -> None:
    """Create *path* (mode 600, exclusive), write, fsync file and directory."""
    try:
        fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            json.dump(document, handle, indent=2, sort_keys=True)
            handle.write("\n")
            handle.flush()
            os.fsync(handle.fileno())
        _fsync_dir(path.parent)
    except OSError as exc:
        raise StateWriteError(f"cannot write {path.name}: {exc}") from exc


def _parses_as_record(fragment: bytes) -> bool:
    """The same test :func:`_read_journal` applies to a line."""
    try:
        return isinstance(json.loads(fragment.decode("utf-8")), dict)
    except ValueError:
        return False


def _repair_torn_tail(run_dir: Path) -> None:
    """Make the journal end on a newline before appending.

    The bytes after the last ``\n`` are judged exactly as :func:`_read_journal`
    judges a line. A complete JSON record (the crash came after the record but
    before its newline) is kept and terminated with ``\n``. Anything else is
    an incomplete record: it is appended to :data:`TORN_NAME` (mode 600, fsync)
    as evidence, then the journal is truncated to its last complete line and
    fsynced. Either way the next record starts on its own line.
    """
    path = run_dir / JOURNAL_NAME
    if not path.exists():
        return
    data = path.read_bytes()
    if not data or data.endswith(b"\n"):
        return
    keep = data.rfind(b"\n") + 1
    fragment = data[keep:]
    if _parses_as_record(fragment):
        fd = os.open(path, os.O_WRONLY | os.O_APPEND)
        try:
            os.write(fd, b"\n")
            os.fsync(fd)
        finally:
            os.close(fd)
        return
    fd = os.open(run_dir / TORN_NAME, os.O_WRONLY | os.O_APPEND | os.O_CREAT, 0o600)
    try:
        os.write(fd, fragment)
        os.fsync(fd)
    finally:
        os.close(fd)
    fd = os.open(path, os.O_WRONLY)
    try:
        os.ftruncate(fd, keep)
        os.fsync(fd)
    finally:
        os.close(fd)
    _fsync_dir(run_dir)


def _append_journal(run_dir: Path, record: Mapping[str, Any]) -> None:
    """Append one JSON line to the run journal (mode 600) and fsync it.

    A torn final line is repaired first (:func:`_repair_torn_tail`).
    """
    path = run_dir / JOURNAL_NAME
    try:
        _repair_torn_tail(run_dir)
        created = not path.exists()
        fd = os.open(path, os.O_WRONLY | os.O_APPEND | os.O_CREAT, 0o600)
        with os.fdopen(fd, "a", encoding="utf-8") as handle:
            handle.write(json.dumps(record, sort_keys=True) + "\n")
            handle.flush()
            os.fsync(handle.fileno())
        if created:
            _fsync_dir(run_dir)
    except OSError as exc:
        raise StateWriteError(f"cannot append journal: {exc}") from exc


def _read_journal(run_dir: Path) -> list[dict[str, Any]]:
    path = run_dir / JOURNAL_NAME
    if not path.exists():
        return []
    out: list[dict[str, Any]] = []
    for line in path.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        try:
            record = json.loads(line)
        except ValueError:
            continue  # a torn last line from a crash: its intent is re-read
        if isinstance(record, dict):
            out.append(record)
    return out


def _load_json(path: Path) -> Any:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        raise Refused(f"cannot read {path}: {exc}") from exc


# ---------------------------------------------------------------------------
# Writers (the only _allow_null users)
# ---------------------------------------------------------------------------


def _write_rule(
    client: VikunjaClient,
    task_id: int,
    current: Mapping[str, Any],
    text: str | None,
    from_current: bool,
) -> None:
    """Set the rule to *text* (clear-first), or clear it when *text* is None.

    Clearing first defeats the stale-COUNT echo and stops structured parts
    merging (task_repeat_update.go:96-110).
    """
    if text is None:
        if has_rule(current):
            client.patch_task(
                task_id,
                {"repeat": None, "repeats_from_current_date": from_current},
                _allow_null=frozenset({"repeat"}),
            )
        elif bool(current.get("repeats_from_current_date")) != from_current:
            client.patch_task(task_id, {"repeats_from_current_date": from_current})
        return
    if has_rule(current):
        client.patch_task(task_id, {"repeat": None}, _allow_null=frozenset({"repeat"}))
    client.patch_task(
        task_id, {"repeats_rrule": text, "repeats_from_current_date": from_current}
    )


def _rule_matches(task: Mapping[str, Any], text: str | None, from_current: bool) -> bool:
    want = rrule_text_to_parts(text) if text else None
    return same_rule(task.get("repeat"), want) and (
        bool(task.get("repeats_from_current_date")) == from_current
    )


def _reminder_key(reminders: Any) -> list[tuple[str, int, str]]:
    out: list[tuple[str, int, str]] = []
    for item in reminders or []:
        if not isinstance(item, Mapping):
            continue
        relative_to = str(item.get("relative_to") or "")
        period = int(item.get("relative_period") or 0)
        instant = ""
        if not relative_to:
            parsed = parse_vikunja_instant(item.get("reminder"))
            instant = parsed.isoformat() if parsed else str(item.get("reminder"))
        out.append((relative_to, period, instant))
    return sorted(out)


def _snapshot_rule_text(snapshot: Mapping[str, Any]) -> str | None:
    if not has_rule(snapshot):
        return None
    text = snapshot.get("repeats_rrule")
    if isinstance(text, str) and text.strip():
        return text.strip()
    return parts_to_rrule_text(snapshot["repeat"])


def _restore_diff(snapshot: Mapping[str, Any], task: Mapping[str, Any]) -> list[str]:
    """Every restored field that differs between *task* and *snapshot*."""
    diff: list[str] = []
    if not same_rule(snapshot.get("repeat"), task.get("repeat")):
        diff.append("repeat")
    if bool(snapshot.get("repeats_from_current_date")) != bool(
        task.get("repeats_from_current_date")
    ):
        diff.append("repeats_from_current_date")
    return diff + _preserved_diff(snapshot, task)


def _preserved_diff(before: Mapping[str, Any], task: Mapping[str, Any]) -> list[str]:
    """Non-rule fields a write must leave as they were: reminders, due date, done.

    Relative reminders compare by ``(relative_to, relative_period)`` (the
    server may recompute their instant); absolute ones by exact instant.
    """
    diff: list[str] = []
    if _reminder_key(before.get("reminders")) != _reminder_key(task.get("reminders")):
        diff.append("reminders")
    if parse_vikunja_instant(before.get("due_date")) != parse_vikunja_instant(
        task.get("due_date")
    ):
        diff.append("due_date")
    if bool(before.get("done")) != bool(task.get("done")):
        diff.append("done")
    return diff


def _restore_refusal(snapshot: Mapping[str, Any], current: Mapping[str, Any]) -> str | None:
    if (
        snapshot.get("done") is True
        and current.get("done") is not True
        and (has_rule(snapshot) or has_rule(current))
    ):
        return (
            "refusing to restore done=true on a task with a rule: completing it "
            "would advance the series; handle manually"
        )
    return None


def _apply_restore(
    client: VikunjaClient, task_id: int, snapshot: Mapping[str, Any], current: Mapping[str, Any]
) -> None:
    """The ordered restore algorithm (data-model.md): rule, reminders, due, done."""
    text = _snapshot_rule_text(snapshot)
    from_current = bool(snapshot.get("repeats_from_current_date"))
    # 1. Rule.
    if not same_rule(current.get("repeat"), snapshot.get("repeat")) or (
        bool(current.get("repeats_from_current_date")) != from_current
    ):
        _write_rule(client, task_id, current, text, from_current)
    # 2. Reminders ([] for null).
    want_reminders = list(snapshot.get("reminders") or [])
    if _reminder_key(want_reminders) != _reminder_key(current.get("reminders")):
        client.patch_task(task_id, {"reminders": want_reminders})
    # 3. Due date (a sanctioned null when the snapshot had none).
    want_due = parse_vikunja_instant(snapshot.get("due_date"))
    if want_due != parse_vikunja_instant(current.get("due_date")):
        if want_due is None:
            client.patch_task(task_id, {"due_date": None}, _allow_null=frozenset({"due_date"}))
        else:
            client.patch_task(task_id, {"due_date": snapshot.get("due_date")})
    # 4. Done (refusal already checked before any write).
    if snapshot.get("done") is not True and current.get("done") is True:
        client.patch_task(task_id, {"done": False})
    elif snapshot.get("done") is True and current.get("done") is not True:
        client.patch_task(task_id, {"done": True})


# ---------------------------------------------------------------------------
# Plan selection
# ---------------------------------------------------------------------------


def _load_plan(path: Path) -> dict[int, dict[str, Any]]:
    document = _load_json(path)
    entries = document.get("entries") if isinstance(document, Mapping) else None
    if not isinstance(entries, list):
        raise Refused(f"{path} is not a rule_inventory output (no entries)")
    out: dict[int, dict[str, Any]] = {}
    for entry in entries:
        if isinstance(entry, Mapping) and isinstance(entry.get("task_id"), int):
            out[entry["task_id"]] = dict(entry)
    return out


def _select(
    plan: Mapping[int, Mapping[str, Any]], task_ids: Sequence[int], accept_changed: bool
) -> list[int]:
    if not task_ids:
        return sorted(tid for tid, e in plan.items() if e.get("status") in AUTO_STATUSES)
    selected: list[int] = []
    # A repeated --task-id is processed once: a second attempt in the same run
    # would replace the first attempt's completed outcome (review cycle 3).
    for tid in dict.fromkeys(task_ids):
        entry = plan.get(tid)
        if entry is None:
            raise Refused(f"task {tid} is not in the plan")
        status = entry.get("status")
        if status in AUTO_STATUSES:
            pass
        elif status in ACCEPT_STATUSES:
            if not accept_changed:
                raise Refused(
                    f"task {tid} has status {status!r}; acting on it needs "
                    "--task-id N --accept-changed (Kent's explicit choice)"
                )
        else:
            raise Refused(f"task {tid} has status {status!r}; it is never repaired")
        if not entry.get("proposed_restore") or not entry.get("current_fingerprint"):
            raise Refused(f"task {tid} has no proposed restore or fingerprint")
        selected.append(tid)
    return selected


# ---------------------------------------------------------------------------
# Apply / resume
# ---------------------------------------------------------------------------


def _apply_one(
    client: VikunjaClient, run_dir: Path, run_id: str, entry: Mapping[str, Any]
) -> str:
    """Steps 1-5 for one task. Returns the outcome; raises Stop/StateWriteError."""
    task_id = int(entry["task_id"])
    try:
        fresh = client.get_task_v2(task_id)
    except VikunjaError as exc:
        raise _ReadFailure(task_id, exc) from exc
    drift = fingerprint_diff(entry["current_fingerprint"], fingerprint(fresh))
    if drift:
        _append_journal(
            run_dir,
            {
                "phase": "outcome",
                "run_id": run_id,
                "task_id": task_id,
                "outcome": "skipped_drift",
                "drift_fields": drift,
                "at": _now(),
            },
        )
        return "skipped_drift"
    proposed = entry["proposed_restore"]
    intended = {
        "repeats_rrule": proposed["repeats_rrule"],
        "repeats_from_current_date": bool(proposed["repeats_from_current_date"]),
    }
    snapshot_path = run_dir / f"{task_id}.before.json"
    _write_snapshot_file(snapshot_path, fresh)
    restore = restore_command(snapshot_path)
    _append_journal(
        run_dir,
        {
            "phase": "intent",
            "kind": "apply",
            "run_id": run_id,
            "task_id": task_id,
            "snapshot_path": str(snapshot_path),
            "before": _record(fresh),
            "intended": intended,
            "restore_command": restore,
            "at": _now(),
        },
    )
    try:
        _write_rule(
            client,
            task_id,
            fresh,
            intended["repeats_rrule"],
            intended["repeats_from_current_date"],
        )
        readback = client.get_task_v2(task_id)
    except VikunjaError as exc:
        _append_journal(
            run_dir,
            {
                "phase": "outcome",
                "run_id": run_id,
                "task_id": task_id,
                "outcome": "unknown",
                "after": None,
                "error": _error_info(exc),
                "at": _now(),
            },
        )
        raise Stop(task_id, "unknown", restore) from exc
    return _record_outcome(run_dir, run_id, task_id, readback, _verify_intent(
        {"kind": "apply", "intended": intended, "before": _record(fresh)}, readback
    ), restore)


class _ReadFailure(Exception):
    def __init__(self, task_id: int, exc: VikunjaError) -> None:
        super().__init__(f"task {task_id}: {type(exc).__name__}")
        self.task_id = task_id
        #: Set when the failure happens inside a run (``_run_tasks``).
        self.run_id: str | None = None
        #: Writes the run made before the failure (its ``intent`` records).
        self.writes = 0


def _verify_intent(intent: Mapping[str, Any], task: Mapping[str, Any]) -> list[str]:
    """Fields that differ from what *intent* meant to write."""
    if intent.get("kind") == "restore":
        return _restore_diff(intent["intended"], task)
    intended = intent["intended"]
    diff: list[str] = []
    if not _rule_matches(task, intended["repeats_rrule"], intended["repeats_from_current_date"]):
        diff.append("repeat")
    return diff + _preserved_diff(intent.get("before") or {}, task)


def _record_outcome(
    run_dir: Path,
    run_id: str,
    task_id: int,
    readback: Mapping[str, Any],
    diff: list[str],
    restore: str,
    *,
    resolved_by: str | None = None,
) -> str:
    outcome = "ok" if not diff else "mismatch"
    record: dict[str, Any] = {
        "phase": "outcome",
        "run_id": run_id,
        "task_id": task_id,
        "outcome": outcome,
        "after": _record(readback),
        "readback_ok": not diff,
        "at": _now(),
    }
    if diff:
        record["diff_fields"] = diff
    if resolved_by:
        record["resolved_by"] = resolved_by
    _append_journal(run_dir, record)
    if outcome != "ok":
        raise Stop(task_id, outcome, restore)
    return outcome


def _latest_by_task(journal: Sequence[Mapping[str, Any]]) -> tuple[dict[int, dict], dict[int, dict]]:
    intents: dict[int, dict] = {}
    outcomes: dict[int, dict] = {}
    for record in journal:
        tid = record.get("task_id")
        if not isinstance(tid, int):
            continue
        if record.get("phase") == "intent":
            intents[tid] = dict(record)
            outcomes.pop(tid, None)
        elif record.get("phase") == "outcome":
            outcomes[tid] = dict(record)
    return intents, outcomes


def _resolve_pending(client: VikunjaClient, run_dir: Path, run_id: str) -> None:
    """Resolve intents whose latest outcome is missing or ``unknown``."""
    intents, outcomes = _latest_by_task(_read_journal(run_dir))
    for tid in sorted(intents):
        latest = outcomes.get(tid)
        if latest is not None and latest.get("outcome") != "unknown":
            if latest.get("outcome") == "mismatch":
                raise Stop(tid, "mismatch", intents[tid]["restore_command"])
            continue
        intent = intents[tid]
        try:
            readback = client.get_task_v2(tid)
        except VikunjaError as exc:
            _append_journal(
                run_dir,
                {
                    "phase": "outcome",
                    "run_id": run_id,
                    "task_id": tid,
                    "outcome": "unknown",
                    "after": None,
                    "error": _error_info(exc),
                    "resolved_by": "resume",
                    "at": _now(),
                },
            )
            raise Stop(tid, "unknown", intent["restore_command"]) from exc
        _record_outcome(
            run_dir,
            run_id,
            tid,
            readback,
            _verify_intent(intent, readback),
            intent["restore_command"],
            resolved_by="resume",
        )


def _run_tasks(
    client: VikunjaClient,
    run_dir: Path,
    run_id: str,
    plan: Mapping[int, Mapping[str, Any]],
    task_ids: Sequence[int],
) -> dict[str, list[int]]:
    _, outcomes = _latest_by_task(_read_journal(run_dir))
    results: dict[str, list[int]] = {}
    for tid in task_ids:
        if tid in outcomes:
            results.setdefault(outcomes[tid]["outcome"], []).append(tid)
            continue
        try:
            outcome = _apply_one(client, run_dir, run_id, plan[tid])
        except _ReadFailure as exc:
            exc.run_id = run_id
            exc.writes = sum(1 for r in _read_journal(run_dir) if r.get("phase") == "intent")
            raise
        results.setdefault(outcome, []).append(tid)
    return results


# ---------------------------------------------------------------------------
# Emit
# ---------------------------------------------------------------------------


def _rule_cell(record: Mapping[str, Any] | None) -> str:
    if not record:
        return "(unknown)"
    return current_rule_text(record) or "(none)"


def render_issue_markdown(run_dir: Path) -> str:
    """Markdown table for #1111: ids and rule text, allowed titles only, no ``@``."""
    run = _load_json(run_dir / RUN_NAME)
    intents, outcomes = _latest_by_task(_read_journal(run_dir))
    task_ids = sorted(set(intents) | set(outcomes))
    lines = [
        f"### Vikunja rule repair run `{safe_cell(run.get('run_id'))}`",
        "",
        f"- Mode: {safe_cell(run.get('mode'))}",
        f"- Started: {safe_cell(run.get('started_at'))}",
        f"- Operator: {safe_cell(run.get('operator'))}",
        "",
        "| task id | before rule | after rule | readback | outcome | restore command |",
        "|---|---|---|---|---|---|",
    ]
    for tid in task_ids:
        intent = intents.get(tid, {})
        outcome = outcomes.get(tid, {})
        label = str(tid)
        title = run.get("titles", {}).get(str(tid)) if tid in PUBLIC_HABIT_IDS else None
        if title:
            label = f"{tid} ({title})"
        before = _rule_cell(intent.get("before")) if intent else "(not written)"
        after = _rule_cell(outcome.get("after")) if outcome.get("after") else "(none read)"
        readback = (
            "ok" if outcome.get("readback_ok") else
            ("differs: " + ",".join(outcome.get("diff_fields", [])) if outcome.get("diff_fields")
             else "n/a")
        )
        restore = f"`{intent['restore_command']}`" if intent.get("restore_command") else "n/a"
        cells = [label, before, after, readback, outcome.get("outcome", "(pending)"), restore]
        lines.append("| " + " | ".join(safe_cell(c) for c in cells) + " |")
    lines.append("")
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="python3 -m scripts.vikunja.rule_repair",
        description="Reversible recurrence-rule repair (#1111).",
    )
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--dry-run", action="store_true")
    mode.add_argument("--apply", action="store_true")
    mode.add_argument("--resume", metavar="RUN_ID")
    mode.add_argument("--restore", metavar="SNAPSHOT")
    mode.add_argument("--emit-issue-markdown", metavar="RUN_ID")
    parser.add_argument("--plan", help="rule_inventory --out file")
    parser.add_argument("--task-id", type=int, action="append", default=[])
    parser.add_argument("--accept-changed", action="store_true")
    parser.add_argument("--state-dir", default=str(DEFAULT_STATE_DIR))
    parser.add_argument("--operator", default=None, help="name recorded on the run")
    parser.add_argument("--markdown-out", default=None, help="emit target (default <run>/issue-comment.md)")
    return parser


def _titles(plan: Mapping[int, Mapping[str, Any]], ids: Sequence[int]) -> dict[str, str]:
    return {
        str(tid): str(plan[tid]["title"])
        for tid in ids
        if tid in PUBLIC_HABIT_IDS and plan.get(tid, {}).get("title")
    }


def _operator(args: argparse.Namespace) -> str:
    if args.operator:
        return str(args.operator)
    try:
        return getpass.getuser()
    except Exception:  # noqa: BLE001 - cosmetic field only
        return "unknown"


def _dry_run(client: VikunjaClient, args: argparse.Namespace, state_dir: Path) -> int:
    plan = _load_plan(Path(args.plan))
    ids = _select(plan, args.task_id, args.accept_changed)
    preview_run = new_tick_id()
    rows: list[dict[str, Any]] = []
    for tid in ids:
        entry = plan[tid]
        try:
            fresh = client.get_task_v2(tid)
        except VikunjaNotFoundError:
            rows.append({"task_id": tid, "drift": "deleted"})
            continue
        except VikunjaError as exc:
            print(f"rule_repair: read failed for {tid}: {type(exc).__name__}", file=sys.stderr)
            return EXIT_VIKUNJA
        drift = fingerprint_diff(entry["current_fingerprint"], fingerprint(fresh))
        row = {
            "task_id": tid,
            "status": entry.get("status"),
            "before": current_rule_text(fresh) or "(none)",
            "intended": entry["proposed_restore"]["repeats_rrule"],
            "intended_from_current": entry["proposed_restore"]["repeats_from_current_date"],
            "drift": "drift:" + ",".join(drift) if drift else "none",
            "snapshot_path": str(state_dir / preview_run / f"{tid}.before.json"),
        }
        rows.append(row)
        title = f" ({entry['title']})" if tid in PUBLIC_HABIT_IDS and entry.get("title") else ""
        print(safe_cell(
            f"{tid}{title}: before={row['before']} intended={row['intended']} "
            f"from_current={row['intended_from_current']} drift={row['drift']} "
            f"snapshot={row['snapshot_path']}"
        ))
    print(json.dumps({"ok": True, "mode": "dry-run", "planned": len(ids), "tasks": rows},
                     sort_keys=True))
    return EXIT_OK


def _start_run(
    state_dir: Path, mode: str, args: argparse.Namespace, extra: Mapping[str, Any]
) -> tuple[str, Path]:
    run_id = new_tick_id()
    run_dir = _make_run_dir(state_dir, run_id)
    run = {
        "run_id": run_id,
        "mode": mode,
        "started_at": _now(),
        "operator": _operator(args),
        **extra,
    }
    _write_snapshot_file(run_dir / RUN_NAME, run)
    return run_id, run_dir


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _apply(client: VikunjaClient, args: argparse.Namespace, state_dir: Path) -> int:
    plan_path = Path(args.plan).resolve()
    plan = _load_plan(plan_path)
    ids = _select(plan, args.task_id, args.accept_changed)
    # The selected entries (status, proposal, fingerprint) are the consent
    # record: persisted immutably with the run so --resume never re-reads them
    # from a plan file that may since have been replaced (review cycle 1, #2).
    run_id, run_dir = _start_run(
        state_dir,
        "apply",
        args,
        {
            "plan": str(plan_path),
            "plan_sha256": _sha256(plan_path),
            "task_ids": ids,
            "entries": [plan[tid] for tid in ids],
            "accept_changed": bool(args.accept_changed),
            "titles": _titles(plan, ids),
        },
    )
    results = _run_tasks(client, run_dir, run_id, plan, ids)
    print(json.dumps({"ok": True, "mode": "apply", "run_id": run_id,
                      "run_dir": str(run_dir), "results": results}, sort_keys=True))
    return EXIT_OK


def _persisted_selection(run: Mapping[str, Any]) -> tuple[dict[int, dict[str, Any]], list[int]]:
    """The apply-time entries from ``run.json``; refuse if the inventory changed.

    The plan file is no longer read for its contents. If it still exists and
    its digest differs from the one recorded at apply time, resume refuses
    before any Vikunja call: the consent and the drift fingerprints belong to
    the original inventory. The persisted selection is re-checked against the
    same consent rules as ``--apply``.
    """
    raw = run.get("entries")
    if not isinstance(raw, list) or not isinstance(run.get("plan_sha256"), str):
        raise Refused("run.json has no persisted selection; cannot resume safely")
    plan_path = Path(str(run.get("plan")))
    if plan_path.exists() and _sha256(plan_path) != run["plan_sha256"]:
        raise Refused(
            f"inventory changed since apply ({plan_path}); resume uses the apply-time "
            "selection only. Put the original inventory back, or start a new --apply"
        )
    entries = {
        int(e["task_id"]): dict(e)
        for e in raw
        if isinstance(e, Mapping) and isinstance(e.get("task_id"), int)
    }
    ids = [int(t) for t in run.get("task_ids", [])]
    if sorted(ids) != sorted(entries):
        raise Refused("run.json selection is inconsistent; cannot resume safely")
    _select(entries, ids, bool(run.get("accept_changed")))
    return entries, ids


def _resume(client: VikunjaClient, args: argparse.Namespace, state_dir: Path) -> int:
    run_id = args.resume
    run_dir = state_dir / run_id
    run = _load_json(run_dir / RUN_NAME)
    entries: dict[int, dict[str, Any]] = {}
    ids: list[int] = []
    if run.get("mode") == "apply":
        entries, ids = _persisted_selection(run)
    _resolve_pending(client, run_dir, run_id)
    results: dict[str, list[int]] = {}
    if run.get("mode") == "apply":
        results = _run_tasks(client, run_dir, run_id, entries, ids)
    print(json.dumps({"ok": True, "mode": "resume", "run_id": run_id,
                      "results": results}, sort_keys=True))
    return EXIT_OK


def _restore(client: VikunjaClient, args: argparse.Namespace, state_dir: Path) -> int:
    source = Path(args.restore).resolve()
    snapshot = _load_json(source)
    if not isinstance(snapshot, Mapping) or not isinstance(snapshot.get("id"), int):
        raise Refused(f"{source} is not a task snapshot")
    task_id = int(snapshot["id"])
    try:
        current = client.get_task_v2(task_id)
    except VikunjaError as exc:
        raise _ReadFailure(task_id, exc) from exc
    refusal = _restore_refusal(snapshot, current)
    if refusal:
        raise Refused(f"task {task_id}: {refusal}")
    run_id, run_dir = _start_run(
        state_dir,
        "restore",
        args,
        {"source_snapshot": str(source), "task_ids": [task_id], "titles": {}},
    )
    pre_restore = run_dir / f"{task_id}.before.json"
    _write_snapshot_file(pre_restore, current)
    restore = restore_command(pre_restore)
    _append_journal(
        run_dir,
        {
            "phase": "intent",
            "kind": "restore",
            "run_id": run_id,
            "task_id": task_id,
            "snapshot_path": str(pre_restore),
            "source_snapshot": str(source),
            "before": _record(current),
            "intended": _record(snapshot),
            "restore_command": restore,
            "at": _now(),
        },
    )
    try:
        _apply_restore(client, task_id, snapshot, current)
        readback = client.get_task_v2(task_id)
    except VikunjaError as exc:
        _append_journal(
            run_dir,
            {
                "phase": "outcome",
                "run_id": run_id,
                "task_id": task_id,
                "outcome": "unknown",
                "after": None,
                "error": _error_info(exc),
                "at": _now(),
            },
        )
        raise Stop(task_id, "unknown", restore) from exc
    _record_outcome(run_dir, run_id, task_id, readback, _restore_diff(snapshot, readback), restore)
    print(json.dumps({"ok": True, "mode": "restore", "run_id": run_id, "task_id": task_id,
                      "outcome": "ok"}, sort_keys=True))
    return EXIT_OK


def _emit(args: argparse.Namespace, state_dir: Path) -> int:
    run_dir = state_dir / args.emit_issue_markdown
    markdown = render_issue_markdown(run_dir)
    out = Path(args.markdown_out) if args.markdown_out else run_dir / "issue-comment.md"
    try:
        fd = os.open(out, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            handle.write(markdown)
    except OSError as exc:
        raise StateWriteError(f"cannot write markdown: {exc}") from exc
    print(json.dumps({"ok": True, "mode": "emit", "markdown": str(out),
                      "post_with": f"gh issue comment 1111 --repo kentonium3/kg-automation "
                                   f"--body-file {out}"}, sort_keys=True))
    return EXIT_OK


def main(argv: Sequence[str] | None = None, *, client: VikunjaClient | None = None) -> int:
    """CLI entry point. *client* is injectable for tests."""
    parser = _parser()
    try:
        args = parser.parse_args(argv)
    except SystemExit as exc:
        return EXIT_REFUSED if exc.code else EXIT_OK
    state_dir = Path(args.state_dir).expanduser()

    def fail(code: int, message: str, **extra: Any) -> int:
        print(f"rule_repair: {message}", file=sys.stderr)
        print(json.dumps({"ok": False, "error": message, **extra}, sort_keys=True))
        return code

    if (args.dry_run or args.apply) and not args.plan:
        return fail(EXIT_REFUSED, "--dry-run/--apply need --plan")
    if args.accept_changed and not args.task_id:
        return fail(EXIT_REFUSED, "--accept-changed needs explicit --task-id")
    try:
        if args.emit_issue_markdown:
            return _emit(args, state_dir)
        if client is None:
            client = VikunjaClient()
        if args.dry_run:
            return _dry_run(client, args, state_dir)
        if args.apply:
            return _apply(client, args, state_dir)
        if args.resume:
            return _resume(client, args, state_dir)
        return _restore(client, args, state_dir)
    except Refused as exc:
        return fail(EXIT_REFUSED, str(exc))
    except _ReadFailure as exc:
        extra: dict[str, Any] = {"writes": exc.writes}
        if exc.run_id:
            extra["run_id"] = exc.run_id
        if exc.writes:
            return fail(
                EXIT_VIKUNJA,
                f"Vikunja read failed ({exc}) after {exc.writes} write(s) in run "
                f"{exc.run_id}. Run --resume {exc.run_id}, then --emit-issue-markdown "
                f"{exc.run_id}, before any new --apply",
                **extra,
            )
        where = f" in run {exc.run_id}" if exc.run_id else ""
        return fail(EXIT_VIKUNJA, f"Vikunja read failed before any write{where}: {exc}",
                    **extra)
    except StateWriteError as exc:
        return fail(EXIT_STATE, f"stopped; local state write failed: {exc}")
    except Stop as stop:
        print(f"rule_repair: STOPPED on task {stop.task_id} ({stop.outcome}). "
              f"Restore with: {stop.restore}", file=sys.stderr)
        return fail(EXIT_STOPPED, f"stopped on {stop.outcome}", task_id=stop.task_id,
                    restore_command=stop.restore)


if __name__ == "__main__":  # pragma: no cover
    sys.exit(main())
