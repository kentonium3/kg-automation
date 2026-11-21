"""Read-only recurrence-rule damage inventory (mission felix-rrule-adaptation, #1111).

Compares the rule columns of a **read-only copy** of a pre-cutover snapshot DB
with each task's live state (``GET /api/v2/tasks/{id}``) and classifies every
candidate task. Contract:
``kitty-specs/felix-rrule-adaptation-01M7TKNX/contracts/repair-and-inventory-cli.md``;
statuses and ordering: ``data-model.md`` "Damage inventory entry" and
post-plan review findings 4 and 9 (re-review new-HIGH 2).

Usage::

    python3 -m scripts.vikunja.rule_inventory \\
        --baseline-db <READ-ONLY-COPY-of-snapshot-db> \\
        [--schedule-path scripts/habits/migrations/phase3-schedule.yaml] \\
        [--felix-logs <dir-or-file> ...] [--seed-ledger <seed-ledger.jsonl>] \\
        --out <private-json-path>

Statuses, decided in this order (the order matters):

``deleted``
    the live GET answers 404.
``unresolved``
    no usable restore source (the stored rule text does not parse, for
    example a date-only or floating UNTIL).
``ok``
    same rule and same ``repeats_from_current_date``.
``progressed``
    same rule except a lower COUNT (expected: completions decrement it).
``ended``
    done, and the baseline rule had COUNT and the rule is now gone (COUNT
    exhaustion), or it had UNTIL and the rule was kept.
``lost``
    no rule now, the baseline rule had neither COUNT nor UNTIL, **and** a
    successful, non-dry-run Felix write to the task (see
    :func:`load_felix_writes`) after the cutover lies within 120 s of the
    task's ``updated``. The only status ``rule_repair --apply`` acts on.
``removed``
    as ``lost`` but without attribution, or no rule now where the baseline had
    COUNT/UNTIL and a normal end could not be confirmed. Goes to Kent.
``changed``
    a different rule (or the same rule with a different from-current flag).

The seed-ledger cross-check runs after the normal-end check: a task the sync
seeded with no rule whose baseline rule was finite is ``ended`` or
``removed``, never ``lost``.

**Read-only by construction.** The DB is opened ``mode=ro``; the live DB and
anything under the live data directory, plus the original snapshot directory,
are refused before opening. The only Vikunja call is ``get_task_v2``.

**Privacy.** ``--out`` is written mode 600. Stdout carries task ids and rule
text only, plus titles for the habit ids already public on #1111
(:data:`PUBLIC_HABIT_IDS`). The last stdout line is the JSON summary.

Exit codes: 0 ok, 2 bad args or refused path, 3 Vikunja error.
"""

from __future__ import annotations

import argparse
import json
import os
import sqlite3
import sys
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import yaml

from scripts.common.et_datetime import parse_vikunja_instant
from scripts.common.vikunja_client import (
    VikunjaClient,
    VikunjaError,
    VikunjaNotFoundError,
)
from scripts.common.vikunja_rule import (
    has_rule,
    normalise,
    parts_to_rrule_text,
    rrule_text_to_parts,
    same_rule,
)

__all__ = [
    "ATTRIBUTION_SINCE",
    "ATTRIBUTION_WINDOW_SECONDS",
    "PUBLIC_HABIT_IDS",
    "STATUSES",
    "Baseline",
    "RefusedPath",
    "check_baseline_path",
    "classify",
    "current_rule_text",
    "fingerprint",
    "fingerprint_diff",
    "load_felix_writes",
    "load_schedule",
    "load_seed_ledger",
    "main",
    "read_baseline",
    "safe_cell",
]

#: The live Vikunja DB and its data directory. Never opened, even read-only.
LIVE_DB_PATH = Path("/data/services/vikunja/data/vikunja.db")
LIVE_DATA_DIR = Path("/data/services/vikunja/data")
#: Original snapshots. The runbook copies one to a private scratch dir first;
#: the helper refuses the originals so a copy is the only thing it can open.
ORIGINAL_SNAPSHOT_DIR = Path("/data/services/vikunja/snapshots")

#: Habit task ids whose titles are already public on #1111.
PUBLIC_HABIT_IDS: frozenset[int] = frozenset({14, 15, 16, 18, 19, 20, 65, 75, 76, 77})

#: A Felix write counts only after the cutover day (data-model.md).
ATTRIBUTION_SINCE = datetime(2026, 10, 30, tzinfo=timezone.utc)
#: ... and only when the task's live ``updated`` is within this window of it.
#: Timestamp proximity cannot prove which write removed a rule: a documented
#: residual risk (post-plan-review.md re-review 2, item 4).
ATTRIBUTION_WINDOW_SECONDS = 120

STATUSES: tuple[str, ...] = (
    "ok",
    "progressed",
    "ended",
    "lost",
    "removed",
    "changed",
    "unresolved",
    "deleted",
)

#: Fingerprint fields (data-model.md "Damage inventory entry").
FINGERPRINT_FIELDS: tuple[str, ...] = (
    "repeat",
    "repeats_rrule",
    "repeats_from_current_date",
    "reminders",
    "done",
    "due_date",
    "updated",
)

_RULE_COLUMN = "repeats"
_FROM_CURRENT_COLUMN = "repeats_from_current_date"


class RefusedPath(ValueError):
    """The baseline path is the live DB, under the live data dir, or an original."""


@dataclass(frozen=True)
class Baseline:
    """A task's baseline rule: stored text, from-current flag and source label."""

    rule_text: str
    from_current: bool
    source: str


@dataclass
class SeedInfo:
    """Seed-ledger rows for one task (duplicates tolerated)."""

    rows: int = 0
    seeded_no_rule: bool = False
    fields: set[str] = field(default_factory=set)


# ---------------------------------------------------------------------------
# Baseline DB (read-only copy)
# ---------------------------------------------------------------------------


def _is_within(path: Path, root: Path) -> bool:
    try:
        path.relative_to(root)
    except ValueError:
        return False
    return True


def check_baseline_path(raw: str | os.PathLike[str]) -> Path:
    """Resolve *raw* and refuse the live DB, the live data dir and originals.

    Symlinks are resolved first, so a link to the live DB is refused too.
    Raises :class:`RefusedPath`.
    """
    path = Path(raw).expanduser().resolve()
    live_db = LIVE_DB_PATH.resolve()
    if path == live_db or _is_within(path, LIVE_DATA_DIR.resolve()):
        raise RefusedPath(f"refusing the live Vikunja DB path: {path}")
    if _is_within(path, ORIGINAL_SNAPSHOT_DIR.resolve()):
        raise RefusedPath(
            f"refusing an original snapshot: {path}; copy it to a private scratch "
            "dir first (see docs/runbooks/vikunja-task-repair.md)"
        )
    return path


def discover_columns(conn: sqlite3.Connection) -> list[str]:
    """Return the ``tasks`` table's column names via ``PRAGMA table_info``."""
    return [str(row[1]) for row in conn.execute("PRAGMA table_info(tasks)")]


def read_baseline(path: Path) -> tuple[dict[int, tuple[str | None, bool]], list[str]]:
    """Read ``id -> (rule_text | None, from_current)`` from a read-only DB copy.

    Opens ``file:<path>?mode=ro`` (never creates or writes). The rule column
    names are discovered with ``PRAGMA table_info(tasks)`` and only ``id``,
    ``repeats`` and ``repeats_from_current_date`` are read. Raises
    ``ValueError`` when the expected columns are absent (for example a
    pre-RRULE interval schema, which this helper does not convert), and
    ``sqlite3.Error`` on an unreadable file.
    """
    if not path.is_file():
        raise ValueError(f"baseline DB not found: {path}")
    conn = sqlite3.connect(f"{path.as_uri()}?mode=ro", uri=True)
    try:
        columns = discover_columns(conn)
        if not columns:
            raise ValueError("baseline DB has no tasks table")
        missing = [c for c in ("id", _RULE_COLUMN, _FROM_CURRENT_COLUMN) if c not in columns]
        if missing:
            repeatish = sorted(c for c in columns if "repeat" in c)
            raise ValueError(
                f"baseline tasks table lacks columns {missing}; repeat columns "
                f"present: {repeatish}"
            )
        rows = conn.execute(
            f"SELECT id, {_RULE_COLUMN}, {_FROM_CURRENT_COLUMN} FROM tasks ORDER BY id"
        ).fetchall()
    finally:
        conn.close()
    out: dict[int, tuple[str | None, bool]] = {}
    for task_id, rule, from_current in rows:
        text = rule.strip() if isinstance(rule, str) else None
        out[int(task_id)] = (text or None, bool(from_current))
    return out, columns


# ---------------------------------------------------------------------------
# Second sources: habit schedule, Felix logs, seed ledger
# ---------------------------------------------------------------------------


def load_schedule(path: Path | None) -> dict[int, str]:
    """Return ``task_id -> rrule`` from a habit schedule's ``habits:`` block.

    Entries without an ``rrule`` (the pre-mission interval-seconds shape)
    are ignored. A missing path yields ``{}``.
    """
    if path is None:
        return {}
    data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    habits = data.get("habits") if isinstance(data, Mapping) else None
    out: dict[int, str] = {}
    for entry in habits or []:
        if not isinstance(entry, Mapping):
            continue
        task_id = entry.get("task_id")
        rrule = entry.get("rrule")
        if (
            isinstance(task_id, int)
            and not isinstance(task_id, bool)
            and isinstance(rrule, str)
            and rrule.strip()
        ):
            out[task_id] = rrule.strip()
    return out


def _iter_jsonl(path: Path) -> Iterable[Any]:
    """Yield parsed JSON lines; a malformed line yields the sentinel ``_BAD``."""
    with path.open("r", encoding="utf-8", errors="replace") as handle:
        for line in handle:
            if not line.strip():
                continue
            try:
                yield json.loads(line)
            except ValueError:
                yield _BAD


_BAD = object()


def _int_id(value: Any) -> int | None:
    if isinstance(value, int) and not isinstance(value, bool) and value > 0:
        return value
    return None


def _sweeper_writes(record: Any) -> list[tuple[int, datetime]]:
    """Sweeper ledger tick: day-specific auto-skips whose due-date PUT succeeded.

    Only a tick with ``dry_run is False`` counts, only its
    ``habits_auto_skipped`` entries carrying ``new_due_date_et`` (daily habits
    are never written by the sweeper), and never a task listed in ``errors``
    (its PUT failed). ``habits_evaluated`` (for example ``already_resolved``)
    is evaluation, not a write.
    """
    if not isinstance(record, Mapping) or record.get("dry_run") is not False:
        return []
    started = parse_vikunja_instant(record.get("started_at_utc"))
    if started is None:
        return []
    failed = {
        _int_id(e.get("task_id"))
        for e in record.get("errors") or []
        if isinstance(e, Mapping)
    }
    out: list[tuple[int, datetime]] = []
    for skip in record.get("habits_auto_skipped") or []:
        if not isinstance(skip, Mapping):
            continue
        task_id = _int_id(skip.get("task_id"))
        if task_id is None or task_id in failed or not skip.get("new_due_date_et"):
            continue
        out.append((task_id, started))
    return out


#: habits state_log states; each row is appended only after its Vikunja
#: ``done`` write succeeded (scripts/habits/record_completion.py steps 2-4).
_HABIT_WRITE_STATES = frozenset({"complete", "incomplete", "skipped"})
#: Positive write provenance for habits rows: the ``source`` Felix's
#: ``record_completion`` is invoked with (felix-admin-habits AGENTS.md
#: ``--source whatsapp``). ``vikunja-ui`` (reconcile: Kent ticked it in the
#: UI), ``historical-backfill`` and anything else are JSONL-only rows.
_HABIT_WRITE_SOURCES = frozenset({"whatsapp"})
#: escalation states that PATCH Vikunja before the JSONL append
#: (scripts/escalation/record_completion.py ``_vikunja_side_effects``).
_ESCALATION_WRITE_STATES = frozenset({"done", "rescheduled"})
#: Positive write provenance for escalation rows: the agent-path sources
#: (escalation SKILL.md ``--source <agent|kent_reply>``). ``reconcile`` rows are
#: synthesized with ``record_event(skip_vikunja=True)``; ``backfill`` and
#: ``operator_repair`` are operator JSONL repairs. None of those wrote Vikunja.
_ESCALATION_WRITE_SOURCES = frozenset({"agent", "kent_reply"})


def _state_log_writes(
    domain: str, states: frozenset[str], sources: frozenset[str]
) -> Any:
    def parse(record: Any) -> list[tuple[int, datetime]]:
        if (
            not isinstance(record, Mapping)
            or "event_type" in record
            or record.get("domain") != domain
            or record.get("state") not in states
            or record.get("source") not in sources
        ):
            return []
        task_id = _int_id(record.get("task_id"))
        stamp = parse_vikunja_instant(record.get("timestamp"))
        if task_id is None or stamp is None:
            return []
        return [(task_id, stamp)]

    return parse


def _intake_writes(record: Any) -> list[tuple[int, datetime]]:
    """Intake apply ledger: an executed ``done`` task-body write only.

    ``applied`` records the *requested* ``project`` / ``due_date`` even when
    they already matched and no task-body write happened (apply_reply
    ``_plan_line``), and the ledger does not log ``field_changes``. Only
    ``applied["done"] is True`` is set together with a ``field_changes``
    entry, so it is the one unambiguous evidence of a task-body write;
    project/due-only records are conservatively not attribution.
    """
    if not isinstance(record, Mapping) or record.get("status") != "applied":
        return []
    applied = record.get("applied")
    if not isinstance(applied, Mapping) or applied.get("done") is not True:
        return []
    task_id = _int_id(record.get("task_id"))
    stamp = parse_vikunja_instant(record.get("applied_at_utc"))
    if task_id is None or stamp is None:
        return []
    return [(task_id, stamp)]


def _parser_for(path: Path) -> Any:
    """The source-specific parser for a Felix log file, or None (not attribution)."""
    name = path.name
    if name == "sweeper-ledger.jsonl":
        return _sweeper_writes
    if name == "habits-history.jsonl":
        return _state_log_writes("habits", _HABIT_WRITE_STATES, _HABIT_WRITE_SOURCES)
    if name.endswith("-escalation-history.jsonl"):
        return _state_log_writes(
            "escalation", _ESCALATION_WRITE_STATES, _ESCALATION_WRITE_SOURCES
        )
    if name.startswith("intake-apply-") and name.endswith(".jsonl"):
        return _intake_writes
    return None


def load_felix_writes(paths: Sequence[Path]) -> tuple[dict[int, list[datetime]], dict[str, int]]:
    """Return ``task_id -> [write instants]`` from Felix's JSONL logs.

    Each path is a file or a directory (its ``*.jsonl`` files, not recursive).
    Files are dispatched by name to a source-specific parser that counts
    **only successful, non-dry-run writes that changed the task**:

    - ``sweeper-ledger.jsonl``: see :func:`_sweeper_writes`;
    - ``habits-history.jsonl``: ``domain=habits`` completion rows with
      ``source=whatsapp`` (``vikunja-ui`` / backfill rows and ``event_type``
      rows such as ``auto_skipped`` do not count);
    - ``*-escalation-history.jsonl``: ``state`` ``done`` / ``rescheduled`` with
      ``source`` ``agent`` / ``kent_reply`` (``reconcile`` rows are synthesized
      without a Vikunja write);
    - ``intake-apply-*.jsonl``: ``status=applied`` with ``applied.done`` true.

    Any other file, and any record a parser does not recognise, is not
    attribution. Only writes after :data:`ATTRIBUTION_SINCE` are kept.
    Malformed lines, unrecognised files and missing paths are counted.
    """
    writes: dict[int, list[datetime]] = {}
    stats = {"files": 0, "records": 0, "skipped_lines": 0, "missing_paths": 0,
             "unrecognised_files": 0}
    files: list[Path] = []
    for raw in paths:
        if raw.is_dir():
            files.extend(sorted(p for p in raw.glob("*.jsonl") if p.is_file()))
        elif raw.is_file():
            files.append(raw)
        else:
            stats["missing_paths"] += 1
    for path in files:
        parse = _parser_for(path)
        if parse is None:
            stats["unrecognised_files"] += 1
            continue
        stats["files"] += 1
        try:
            for record in _iter_jsonl(path):
                if record is _BAD:
                    stats["skipped_lines"] += 1
                    continue
                stats["records"] += 1
                for task_id, stamp in parse(record):
                    if stamp >= ATTRIBUTION_SINCE:
                        writes.setdefault(task_id, []).append(stamp)
        except OSError:
            stats["missing_paths"] += 1
    return {tid: sorted(stamps) for tid, stamps in writes.items()}, stats


def _seeded_rule(value: Any) -> tuple[bool, bool]:
    """``(valid, is_no_rule)`` for a ``repeat`` seed value."""
    if value is None:
        return True, True
    if not isinstance(value, Mapping):
        return False, False
    freq = value.get("freq")
    if freq is not None and not isinstance(freq, str):
        return False, False
    try:
        return True, normalise(value) is None
    except (AttributeError, TypeError, ValueError):
        return False, False


def load_seed_ledger(path: Path | None) -> tuple[dict[int, SeedInfo], dict[str, int]]:
    """Return per-task seed info from the sync's ``seed-ledger.jsonl``.

    Duplicate ``(task_id, field)`` rows (a retried cycle) collapse into one
    :class:`SeedInfo`. Malformed lines and rows without an int ``task_id`` are
    skipped and counted. A missing path yields an empty result.
    """
    stats = {"rows": 0, "skipped_lines": 0}
    out: dict[int, SeedInfo] = {}
    if path is None:
        return out, stats
    for record in _iter_jsonl(path):
        task_id = record.get("task_id") if isinstance(record, Mapping) else None
        fld = record.get("field") if isinstance(record, Mapping) else None
        if (
            record is _BAD
            or not isinstance(task_id, int)
            or isinstance(task_id, bool)
            or not isinstance(fld, str)
        ):
            stats["skipped_lines"] += 1
            continue
        no_rule = False
        if fld == "repeat":
            valid, no_rule = _seeded_rule(record.get("seeded_value"))
            if not valid:
                stats["skipped_lines"] += 1
                continue
        stats["rows"] += 1
        info = out.setdefault(task_id, SeedInfo())
        info.rows += 1
        info.fields.add(fld)
        if no_rule:
            info.seeded_no_rule = True
    return out, stats


# ---------------------------------------------------------------------------
# Fingerprint
# ---------------------------------------------------------------------------


def fingerprint(task: Mapping[str, Any]) -> dict[str, Any]:
    """The drift fingerprint of a v2 task (data-model.md)."""
    return {key: task.get(key) for key in FINGERPRINT_FIELDS}


def fingerprint_diff(expected: Mapping[str, Any], actual: Mapping[str, Any]) -> list[str]:
    """Fields that differ between two fingerprints (``repeat`` by normal form)."""
    diff: list[str] = []
    for key in FINGERPRINT_FIELDS:
        if key == "repeat":
            if not same_rule(expected.get("repeat"), actual.get("repeat")):
                diff.append(key)
        elif expected.get(key) != actual.get(key):
            diff.append(key)
    return diff


def current_rule_text(task: Mapping[str, Any]) -> str | None:
    """The task's rule as RFC 5545 text, or None when it has no rule."""
    if not has_rule(task):
        return None
    text = task.get("repeats_rrule")
    if isinstance(text, str) and text.strip():
        return text.strip()
    return parts_to_rrule_text(task["repeat"])


def safe_cell(value: Any) -> str:
    """Render *value* for public output: no ``@`` (no mentions), no pipes."""
    return str(value).replace("@", " at ").replace("|", "/").replace("\n", " ")


# ---------------------------------------------------------------------------
# Classification
# ---------------------------------------------------------------------------


def _without_count(rule: Mapping[str, Any]) -> dict[str, Any]:
    out = dict(rule)
    out.pop("count", None)
    return out


def _attributed(task: Mapping[str, Any], writes: Sequence[datetime]) -> list[str]:
    updated = parse_vikunja_instant(task.get("updated"))
    if updated is None:
        return []
    return [
        w.strftime("%Y-%m-%dT%H:%M:%SZ")
        for w in writes
        if abs((updated - w).total_seconds()) <= ATTRIBUTION_WINDOW_SECONDS
    ]


def classify(
    baseline: Baseline,
    live: Mapping[str, Any] | None,
    *,
    attribution: Sequence[str] = (),
    seeded_no_rule: bool = False,
) -> tuple[str, str, dict[str, Any] | None]:
    """Classify one task. Returns ``(status, reason, proposed_restore)``.

    *live* is the v2 GET body, or ``None`` for a 404. *attribution* lists the
    matched Felix write instants (empty means no attribution). Pure.
    """
    if live is None:
        return "deleted", "task not found (404)", None
    try:
        parts = rrule_text_to_parts(baseline.rule_text)
        canonical = parts_to_rrule_text(parts)
    except ValueError:
        return "unresolved", "baseline rule text does not parse; no restore source", None
    proposed = {
        "repeats_rrule": canonical,
        "repeats_from_current_date": baseline.from_current,
    }
    base = normalise(parts)
    assert base is not None  # rrule_text_to_parts guarantees FREQ
    cur = normalise(live.get("repeat"))
    live_flag = bool(live.get("repeats_from_current_date"))
    done = live.get("done") is True
    finite = "count" in base or "until" in base

    # (a) ok
    if cur is not None and cur == base:
        if live_flag == baseline.from_current:
            return "ok", "same rule", proposed
        return "changed", "same rule, different repeats_from_current_date", proposed
    # (b) progressed
    if (
        cur is not None
        and isinstance(base.get("count"), int)
        and isinstance(cur.get("count"), int)
        and cur["count"] < base["count"]
        and _without_count(cur) == _without_count(base)
    ):
        if live_flag == baseline.from_current:
            return "progressed", "same rule, lower COUNT", proposed
        return "changed", "lower COUNT, different repeats_from_current_date", proposed
    # (c) ended
    if done and cur is None and "count" in base:
        return "ended", "done, COUNT rule cleared (series exhausted)", proposed
    if done and cur is not None and "until" in base and same_rule(cur, base):
        return "ended", "done, UNTIL rule kept", proposed
    # Seed-ledger cross-check, after the normal-end check (re-review new-HIGH 2).
    if cur is None and seeded_no_rule and finite:
        return (
            "removed",
            "sync seeded no rule; finite baseline rule; normal end not confirmed",
            proposed,
        )
    if cur is None:
        if finite:
            # (e) a finite rule gone where a normal end could not be confirmed
            return "removed", "rule absent; finite baseline; normal end not confirmed", proposed
        if attribution:
            # (d)
            return "lost", "rule absent; Felix write within 120 s of updated", proposed
        # (e)
        return "removed", "rule absent; no Felix write attribution", proposed
    # (f)
    return "changed", "different rule", proposed


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


def _write_private_json(path: Path, document: Mapping[str, Any]) -> None:
    """Write *document* to *path* atomically with mode 600."""
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(f".{path.name}.tmp")
    fd = os.open(tmp, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            json.dump(document, handle, indent=2, sort_keys=True)
            handle.write("\n")
            handle.flush()
            os.fsync(handle.fileno())
        os.chmod(tmp, 0o600)
        os.replace(tmp, path)
    except BaseException:
        try:
            tmp.unlink()
        except FileNotFoundError:
            pass
        raise


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="python3 -m scripts.vikunja.rule_inventory",
        description="Read-only recurrence-rule damage inventory (#1111).",
    )
    parser.add_argument("--baseline-db", required=True, help="READ-ONLY COPY of a snapshot DB")
    parser.add_argument("--schedule-path", default=None, help="habit schedule YAML (2nd source)")
    parser.add_argument("--felix-logs", nargs="*", default=[], help="Felix JSONL logs (files/dirs)")
    parser.add_argument("--seed-ledger", default=None, help="sync seed-ledger.jsonl")
    parser.add_argument("--out", required=True, help="private JSON output path (mode 600)")
    return parser


def _summary_line(entry: Mapping[str, Any]) -> str:
    tid = entry["task_id"]
    title = f" ({entry['title']})" if entry.get("title") else ""
    return safe_cell(
        f"{tid}{title}: {entry['status']} baseline={entry['baseline_rule']} "
        f"current={entry['current_rule'] or '(none)'}"
    )


def main(argv: Sequence[str] | None = None, *, client: VikunjaClient | None = None) -> int:
    """CLI entry point. *client* is injectable for tests."""
    parser = _parser()
    try:
        args = parser.parse_args(argv)
    except SystemExit as exc:
        return 2 if exc.code else 0

    def fail(code: int, message: str) -> int:
        print(f"rule_inventory: {message}", file=sys.stderr)
        print(json.dumps({"ok": False, "error": message}))
        return code

    try:
        db_path = check_baseline_path(args.baseline_db)
    except RefusedPath as exc:
        return fail(2, str(exc))
    try:
        rows, columns = read_baseline(db_path)
    except (ValueError, sqlite3.Error) as exc:
        return fail(2, f"cannot read baseline DB: {exc}")
    try:
        schedule = load_schedule(Path(args.schedule_path) if args.schedule_path else None)
    except (OSError, yaml.YAMLError) as exc:
        return fail(2, f"cannot read schedule: {exc}")
    writes, log_stats = load_felix_writes([Path(p) for p in args.felix_logs])
    seed_path = Path(args.seed_ledger) if args.seed_ledger else None
    if seed_path is not None and not seed_path.is_file():
        return fail(2, f"seed ledger not found: {seed_path}")
    seeds, seed_stats = load_seed_ledger(seed_path)

    source = f"snapshot:{db_path.parent}"
    candidates: dict[int, Baseline] = {}
    for task_id, (text, from_current) in rows.items():
        if text:
            candidates[task_id] = Baseline(text, from_current, source)
    for task_id, text in schedule.items():
        if task_id not in candidates:
            from_current = rows.get(task_id, (None, False))[1]
            candidates[task_id] = Baseline(text, from_current, "schedule")

    if client is None:
        client = VikunjaClient()
    entries: list[dict[str, Any]] = []
    for task_id in sorted(candidates):
        baseline = candidates[task_id]
        try:
            live: dict[str, Any] | None = client.get_task_v2(task_id)
        except VikunjaNotFoundError:
            live = None
        except VikunjaError as exc:
            return fail(3, f"Vikunja error reading task {task_id}: {type(exc).__name__}")
        attribution = _attributed(live, writes.get(task_id, [])) if live else []
        seed = seeds.get(task_id)
        status, reason, proposed = classify(
            baseline,
            live,
            attribution=attribution,
            seeded_no_rule=bool(seed and seed.seeded_no_rule),
        )
        entry: dict[str, Any] = {
            "task_id": task_id,
            "project_id": live.get("project_id") if live else None,
            "baseline_rule": baseline.rule_text,
            "baseline_from_current": baseline.from_current,
            "baseline_source": baseline.source,
            "schedule_rule": schedule.get(task_id),
            "current_rule": current_rule_text(live) if live else None,
            "current_repeat": live.get("repeat") if live else None,
            "status": status,
            "reason": reason,
            "proposed_restore": proposed,
            "attribution": attribution,
            "seed_ledger": {
                "rows": seed.rows if seed else 0,
                "seeded_no_rule": bool(seed and seed.seeded_no_rule),
            },
            "current_fingerprint": fingerprint(live) if live else None,
        }
        if task_id in PUBLIC_HABIT_IDS and live and isinstance(live.get("title"), str):
            entry["title"] = live["title"]
        entries.append(entry)

    out_path = Path(args.out).expanduser()
    document = {
        "schema": "vikunja-rule-inventory/v1",
        "generated_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "baseline_db": str(db_path),
        "baseline_columns": [c for c in columns if c in ("id", _RULE_COLUMN, _FROM_CURRENT_COLUMN)],
        "schedule_path": args.schedule_path,
        "felix_logs": log_stats,
        "seed_ledger": seed_stats,
        "entries": entries,
    }
    try:
        _write_private_json(out_path, document)
    except OSError as exc:
        return fail(2, f"cannot write --out: {exc}")

    counts = {s: 0 for s in STATUSES}
    for entry in entries:
        counts[entry["status"]] += 1
        if entry["status"] != "ok":
            print(_summary_line(entry))
    summary = {
        "ok": True,
        "checked": len(entries),
        "unchanged": counts["ok"],
        **{s: counts[s] for s in STATUSES if s != "ok"},
        "ids": {
            s: [e["task_id"] for e in entries if e["status"] == s]
            for s in STATUSES
            if s != "ok" and counts[s]
        },
        "seed_ledger_rows": seed_stats["rows"],
        "seed_ledger_skipped": seed_stats["skipped_lines"],
        "felix_log_skipped": log_stats["skipped_lines"],
        "out": str(out_path),
    }
    print(json.dumps(summary, sort_keys=True))
    return 0


if __name__ == "__main__":  # pragma: no cover
    sys.exit(main())
