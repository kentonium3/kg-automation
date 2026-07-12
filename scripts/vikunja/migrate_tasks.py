#!/usr/bin/env python3
"""Migrate surviving Vikunja tasks into topic projects and delete emptied legacy
projects (#717).

Deterministic, idempotent helper (Felix Constitution Directive 6): no LLM, no
global state, no caching. Driven by the committed routing manifest
``scripts/vikunja/task_migration_manifest.yaml`` (Kent's human-judgment routing,
#717). It:

- **moves** 29 surviving tasks out of the task-bearing legacy projects into
  their correct topic project (Personal 20, Felix / kg-automation 16,
  Intentional LLC 9), preserving each task's writable fields via an allowlisted
  read-modify-write with a post-move readback diff (NFR-001, #524);
- **labels** 11 Habits tasks with ``t:habit`` (they stay in Habits 13, FR-002);
- **deletes** two test-artifact tasks (#89, #44) — BEFORE the project
  empty-check so a doomed project holding a test task does not self-block (H-5);
- **deletes** six emptied legacy projects (Someday 4, Everyday 2, Personal
  Growth 5, Household 15, Goals 11, Research 12), children before parents, each
  re-listed for emptiness *immediately* before its delete off a fresh, done-
  inclusive ``/tasks/all`` enumeration (FR-004/FR-006/NFR-004).

Ownership is enforced without a whoami endpoint (``GET /user`` is 401 for API
tokens): the token is read ONLY from an explicit ``--token-file`` that defaults
to the kent secret (never the ``VikunjaClient`` felix-bot default). The known
felix-bot token path is refused up front (pre-mutation guard), and the live
preflight asserts every target and doomed project resolves with
``owner.username == "kent"`` (aborting fail-loud otherwise, FR-010). This is the
#715 two-token model: config/label-attach requires the kent, all-perms token.

The **live run is operator-invoked post-merge** — this module ships the code +
tests + manifest + the design-doc edit only. Run it on office2 as::

    python3 -m scripts.vikunja.migrate_tasks [options]

Dry-run by default; ``--apply`` executes; any deletion requires a non-empty
``--backup-ref`` (NFR-002, Change-Risk Tier 2). Wraps the deterministic
``scripts.common.vikunja_client.VikunjaClient`` — the canonical stdlib HTTP
boundary. No new HTTP path, no ``requests`` dependency.
"""
from __future__ import annotations

import argparse
import json
import os
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from scripts.common.vikunja_client import VikunjaError

__all__ = [
    "DEFAULT_KENT_TOKEN_FILE",
    "FELIX_BOT_TOKEN_FILE",
    "DEFAULT_MANIFEST_PATH",
    "KENT_USERNAME",
    "HABIT_LABEL_TITLE",
    "PROJECT_TITLES",
    "PROJECT_PARENTS",
    "Manifest",
    "MigrationPlan",
    "ReconcileError",
    "load_manifest",
    "list_all_tasks",
    "tasks_in_project",
    "preflight",
    "build_plan",
    "move_task",
    "apply_habit_label",
    "reconcile",
    "main",
]

# The kent-owned, all-perms token (#715 two-token model). Read ONLY this file;
# never fall back to VikunjaClient's felix-bot default token path.
DEFAULT_KENT_TOKEN_FILE = "/data/services/openclaw/secrets/vikunja-api-kent"

# The felix-bot task-CRUD token path. Explicitly refused as a token source: a
# felix-bot run makes kent-invisible changes and cannot attach a kent label
# (403). Rejecting the path up front is a pre-mutation guard that does not
# depend on a preflight owner assertion firing.
FELIX_BOT_TOKEN_FILE = "/data/services/openclaw/secrets/vikunja-api"

DEFAULT_MANIFEST_PATH = str(
    Path(__file__).with_name("task_migration_manifest.yaml")
)

KENT_USERNAME = "kent"

# The habit tag resolved live to a single kent-visible label id (FR-002/FR-010).
HABIT_LABEL_TITLE = "t:habit"

# Vikunja caps ``per_page`` at 50 on this instance; a ``len < 100`` stop
# condition would be wrong (NFR-004).
_PAGE_SIZE = 50

# The valid target-project selector keys → their locked #716 live ids. The
# manifest's ``target_projects`` must equal this map exactly (invariant 5).
_LOCKED_TARGET_PROJECTS: dict[str, int] = {
    "personal": 20,
    "felix": 16,
    "intentional": 9,
    "habits": 13,
}

# Expected live titles for every project the helper touches — targets AND doomed
# projects — asserted at preflight (FR-010). Keyed by live project id.
PROJECT_TITLES: dict[int, str] = {
    # Targets (retained)
    20: "Personal",
    16: "Felix / kg-automation",
    9: "Intentional LLC",
    13: "Habits",
    # Doomed (deleted)
    4: "Someday",
    2: "Everyday",
    5: "Personal Growth & Transformation",
    15: "Household",
    11: "Goals",
    12: "Research",
}

# Expected parent_project_id for every touched project (0 == top-level). Someday
# (4) is the only child — its parent is Everyday (2). Used for the parent-id
# assertion at preflight (FR-010) and delete-order sanity.
PROJECT_PARENTS: dict[int, int] = {
    20: 0,
    16: 0,
    9: 0,
    13: 0,
    4: 2,
    2: 0,
    5: 0,
    15: 0,
    11: 0,
    12: 0,
}

# The writable-field allowlist for a task move (NFR-001). Every one of these is
# echoed back on the POST so Vikunja's partial-replace does not zero it (#524);
# a post-move readback asserts none of them changed. ``project_id`` is added
# separately as the one intended mutation.
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

# Complex-state fields that a plain move cannot safely preserve; any present →
# the task is preflight-blocked, not migrated (FR-011).
_COMPLEX_LIST_FIELDS: tuple[str, ...] = (
    "assignees",
    "related_tasks",
    "reminders",
    "attachments",
)


class ReconcileError(Exception):
    """Fail-loud migration error (identity, owner/title mismatch, non-empty
    doomed project, readback mismatch, missing backup evidence, manifest
    invariant violation).

    Raised for any condition where continuing could migrate to the wrong place,
    silently lose data, delete a non-empty project, or act under the wrong
    owner. Surfaced by :func:`main` as a non-zero exit — never swallowed.
    """


# ---------------------------------------------------------------------------
# Manifest
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class Manifest:
    """The validated routing manifest (data-model.md → "Manifest").

    ``target_projects`` maps a selector key to a live project id.
    ``moves`` maps a task id to a target selector key.
    ``label_habit`` / ``delete_tasks`` are task-id lists; ``delete_projects`` is
    an ordered project-id list (children before parents).
    """

    target_projects: dict[str, int]
    moves: dict[int, str]
    label_habit: list[int]
    delete_tasks: list[int]
    delete_projects: list[int]

    def target_id(self, task_id: int) -> int:
        """Resolve a task's move target to a live project id."""
        return self.target_projects[self.moves[task_id]]


def load_manifest(path: str | os.PathLike[str]) -> Manifest:
    """Parse and validate the routing manifest, failing loud on any violation.

    Static invariants (data-model.md → "Validation"):

    1. every ``moves`` value is a known ``target_projects`` key;
    2. every id (``moves`` keys, ``label_habit``/``delete_tasks``/
       ``delete_projects`` members, ``target_projects`` values) is a positive
       int;
    3. the id sets ``moves.keys()``, ``label_habit``, ``delete_tasks`` are
       pairwise disjoint;
    4. ``delete_projects`` lists Someday(4) before Everyday(2) (child before
       parent);
    5. ``target_projects`` equals the locked #716 ids exactly.

    Any violation raises :class:`ReconcileError`.
    """
    import yaml

    try:
        with open(path, encoding="utf-8") as handle:
            raw = yaml.safe_load(handle)
    except OSError as exc:
        raise ReconcileError(
            f"manifest {os.fspath(path)!r} could not be read: {exc}"
        ) from exc

    if not isinstance(raw, dict):
        raise ReconcileError(
            f"manifest {os.fspath(path)!r} must be a mapping, got "
            f"{type(raw).__name__}"
        )

    target_projects = raw.get("target_projects")
    moves = raw.get("moves")
    label_habit = raw.get("label_habit")
    delete_tasks = raw.get("delete_tasks")
    delete_projects = raw.get("delete_projects")

    if not isinstance(target_projects, dict):
        raise ReconcileError("manifest 'target_projects' must be a mapping")
    if not isinstance(moves, dict):
        raise ReconcileError("manifest 'moves' must be a mapping")
    for name, value in (
        ("label_habit", label_habit),
        ("delete_tasks", delete_tasks),
        ("delete_projects", delete_projects),
    ):
        if not isinstance(value, list):
            raise ReconcileError(f"manifest {name!r} must be a list")

    # --- invariant 5: target_projects equals the locked #716 ids exactly.
    if target_projects != _LOCKED_TARGET_PROJECTS:
        raise ReconcileError(
            f"manifest 'target_projects' {target_projects!r} does not match the "
            f"locked #716 ids {_LOCKED_TARGET_PROJECTS!r}"
        )

    # --- invariant 1: every moves value is a known target key.
    for task_id, key in moves.items():
        if key not in target_projects:
            raise ReconcileError(
                f"manifest 'moves' task {task_id!r} targets unknown project key "
                f"{key!r}; valid keys are {sorted(target_projects)}"
            )

    # --- invariant 2: every id is a positive int.
    def _assert_positive_int(value: Any, where: str) -> None:
        # ``bool`` is an ``int`` subclass — reject it explicitly.
        if isinstance(value, bool) or not isinstance(value, int) or value <= 0:
            raise ReconcileError(
                f"manifest {where} id {value!r} must be a positive integer"
            )

    for task_id in moves:
        _assert_positive_int(task_id, "'moves' key")
    for target_id in target_projects.values():
        _assert_positive_int(target_id, "'target_projects' value")
    for name, seq in (
        ("label_habit", label_habit),
        ("delete_tasks", delete_tasks),
        ("delete_projects", delete_projects),
    ):
        for member in seq:
            _assert_positive_int(member, f"{name!r} member")

    # --- invariant 3: moves.keys(), label_habit, delete_tasks pairwise disjoint.
    move_ids = set(moves.keys())
    label_ids = set(label_habit)
    del_task_ids = set(delete_tasks)
    for left_name, left, right_name, right in (
        ("moves", move_ids, "label_habit", label_ids),
        ("moves", move_ids, "delete_tasks", del_task_ids),
        ("label_habit", label_ids, "delete_tasks", del_task_ids),
    ):
        overlap = left & right
        if overlap:
            raise ReconcileError(
                f"manifest id sets {left_name!r} and {right_name!r} overlap on "
                f"{sorted(overlap)}; they must be pairwise disjoint"
            )

    # --- invariant 4: delete_projects lists Someday(4) before Everyday(2).
    if 4 in delete_projects and 2 in delete_projects:
        if delete_projects.index(4) >= delete_projects.index(2):
            raise ReconcileError(
                "manifest 'delete_projects' must list Someday(4) before its "
                f"parent Everyday(2); got {delete_projects!r}"
            )

    return Manifest(
        target_projects=dict(target_projects),
        moves={int(k): str(v) for k, v in moves.items()},
        label_habit=[int(x) for x in label_habit],
        delete_tasks=[int(x) for x in delete_tasks],
        delete_projects=[int(x) for x in delete_projects],
    )


# ---------------------------------------------------------------------------
# Read — task enumeration (paginated, done-inclusive) + per-project derivation
# ---------------------------------------------------------------------------


def list_all_tasks(client: Any) -> list[dict]:
    """Return every task via a paginated, done-inclusive ``GET /tasks/all``.

    Pages ``per_page=50`` from page 1, accumulating until a page returns fewer
    than 50 items. **No ``done`` filter** — done tasks are included (NFR-004),
    so this is the single source for both the move plan and the project empty-
    check. A ``null`` body (Vikunja's empty-collection quirk) is normalised to
    ``[]``; any non-list, non-null 200 body is a contract violation → raised.
    """
    tasks: list[dict] = []
    page = 1
    while True:
        batch = client.get(
            "/tasks/all",
            params={"per_page": str(_PAGE_SIZE), "page": str(page)},
        )
        if batch is None:
            break
        if not isinstance(batch, list):
            raise VikunjaError(path="/tasks/all", status=200)
        for element in batch:
            if isinstance(element, dict):
                tasks.append(element)
        if len(batch) < _PAGE_SIZE:
            break
        page += 1
    return tasks


def tasks_in_project(all_tasks: list[dict], pid: int) -> list[dict]:
    """Client-side filter: tasks whose ``project_id`` equals ``pid``."""
    return [t for t in all_tasks if t.get("project_id") == pid]


# ---------------------------------------------------------------------------
# Read helpers — projects, labels
# ---------------------------------------------------------------------------


def _owner_username(project: dict) -> str | None:
    owner = project.get("owner")
    if isinstance(owner, dict):
        username = owner.get("username")
        if isinstance(username, str):
            return username
    return None


def list_projects(client: Any) -> list[dict]:
    """Return every project element from a paginated ``GET /projects``.

    Mirrors the enumeration in ``reconcile_projects.list_projects``: pages
    ``per_page=50`` until a short page; a ``null`` body → stop; a non-list,
    non-null body → raise.
    """
    projects: list[dict] = []
    page = 1
    while True:
        batch = client.get(
            "/projects",
            params={"per_page": str(_PAGE_SIZE), "page": str(page)},
        )
        if batch is None:
            break
        if not isinstance(batch, list):
            raise VikunjaError(path="/projects", status=200)
        for element in batch:
            if isinstance(element, dict):
                projects.append(element)
        if len(batch) < _PAGE_SIZE:
            break
        page += 1
    return projects


def list_labels(client: Any) -> list[dict]:
    """Return every label element from a paginated ``GET /labels``."""
    labels: list[dict] = []
    page = 1
    while True:
        batch = client.get(
            "/labels",
            params={"per_page": str(_PAGE_SIZE), "page": str(page)},
        )
        if batch is None:
            break
        if not isinstance(batch, list):
            raise VikunjaError(path="/labels", status=200)
        for element in batch:
            if isinstance(element, dict):
                labels.append(element)
        if len(batch) < _PAGE_SIZE:
            break
        page += 1
    return labels


def _resolve_habit_label_id(labels: list[dict]) -> int:
    """Resolve ``t:habit`` to exactly one kent-visible label id (FR-010).

    Raises :class:`ReconcileError` if zero or more than one label carries the
    title (an ambiguous binding must never silently apply the wrong label).
    """
    matches = [
        lid
        for label in labels
        if label.get("title") == HABIT_LABEL_TITLE
        and isinstance((lid := label.get("id")), int)
        and not isinstance(lid, bool)
    ]
    if len(matches) != 1:
        raise ReconcileError(
            f"expected exactly one kent-visible {HABIT_LABEL_TITLE!r} label, "
            f"found {len(matches)} (ids {sorted(matches)}). Refusing to guess."
        )
    return matches[0]


def _task_has_label(task: dict, label_id: int) -> bool:
    for label in task.get("labels") or []:
        if isinstance(label, dict) and label.get("id") == label_id:
            return True
    return False


def _index_projects(projects: list[dict]) -> dict[int, dict]:
    index: dict[int, dict] = {}
    for project in projects:
        pid = project.get("id")
        if isinstance(pid, int) and not isinstance(pid, bool):
            index[pid] = project
    return index


# ---------------------------------------------------------------------------
# Preflight (identity + target + complex-state)
# ---------------------------------------------------------------------------


def _assert_project_shape(pid: int, project: dict | None) -> None:
    """Assert a touched project resolves with its expected title/parent/owner.

    Every project the helper touches (targets AND doomed) must resolve live with
    ``title == PROJECT_TITLES[pid]``, ``parent_project_id == PROJECT_PARENTS[pid]``,
    ``owner.username == "kent"``, and not archived (FR-010). Any mismatch raises.
    """
    if project is None:
        raise ReconcileError(
            f"project id {pid} ({PROJECT_TITLES[pid]!r}) not found live; "
            f"refusing to proceed."
        )
    title = project.get("title")
    if title != PROJECT_TITLES[pid]:
        raise ReconcileError(
            f"project id {pid} title mismatch: expected "
            f"{PROJECT_TITLES[pid]!r}, got {title!r}. Refusing to proceed."
        )
    parent = project.get("parent_project_id", 0)
    if parent != PROJECT_PARENTS[pid]:
        raise ReconcileError(
            f"project id {pid} ({title!r}) parent mismatch: expected "
            f"{PROJECT_PARENTS[pid]}, got {parent!r}. Refusing to proceed."
        )
    if _owner_username(project) != KENT_USERNAME:
        raise ReconcileError(
            f"project id {pid} ({title!r}) owner is "
            f"{_owner_username(project)!r}, not {KENT_USERNAME!r}. Wrong token "
            f"identity — aborting fail-loud."
        )
    if project.get("is_archived") is True:
        raise ReconcileError(
            f"project id {pid} ({title!r}) is archived; refusing to proceed."
        )


def _complex_state_reason(task: dict) -> str | None:
    """Return a reason string if a task carries move-unsafe complex state, else
    ``None`` (FR-011).

    Complex state: non-empty ``assignees`` / ``related_tasks`` / ``reminders`` /
    ``attachments``, a kanban ``bucket_id``, or a parent/subtask link.
    """
    for name in _COMPLEX_LIST_FIELDS:
        value = task.get(name)
        if value:  # non-empty list / mapping / truthy
            return f"has {name}"
    bucket_id = task.get("bucket_id")
    if isinstance(bucket_id, int) and not isinstance(bucket_id, bool) and bucket_id:
        return "has kanban bucket_id"
    if task.get("related_tasks"):
        return "has related_tasks"
    for name in ("parent_task_id", "parent_task", "subtasks"):
        if task.get(name):
            return f"has {name} (parent/subtask link)"
    return None


def preflight(
    client: Any,
    all_tasks: list[dict],
    projects: list[dict],
    labels: list[dict],
    manifest: Manifest,
) -> tuple[int, list[tuple[str, int, str]]]:
    """Validate live state before any mutation; return ``(habit_label_id, blocked)``.

    Asserts (FR-010/FR-011), raising on any identity/title/owner/parent mismatch:

    - every target project id AND every ``delete_projects`` id resolves live
      with the expected title + parent + ``owner.username == "kent"`` and is not
      archived;
    - ``t:habit`` resolves to exactly one kent-visible label id;
    - every ``label_habit`` task is currently in Habits(13).

    Scans each moved task for move-unsafe complex state and returns those as
    ``blocked`` ``(kind, task_id, reason)`` — they are NOT migrated (the caller
    fails loud at apply if any blocked item exists).
    """
    index = _index_projects(projects)

    # Target (retained) projects MUST always resolve — they never go away.
    for pid in sorted(set(manifest.target_projects.values())):
        _assert_project_shape(pid, index.get(pid))

    # Doomed projects are asserted only when still present: on an idempotent
    # re-run they are already deleted, which is the desired end state (FR-005).
    # A doomed project that IS still present must match its expected shape so we
    # never delete a wrong-owner / re-purposed project (FR-010).
    for pid in sorted(set(manifest.delete_projects)):
        project = index.get(pid)
        if project is not None:
            _assert_project_shape(pid, project)

    habit_label_id = _resolve_habit_label_id(labels)

    tasks_by_id = {
        tid: task
        for task in all_tasks
        if isinstance((tid := task.get("id")), int) and not isinstance(tid, bool)
    }

    habits_pid = manifest.target_projects["habits"]
    for task_id in manifest.label_habit:
        task = tasks_by_id.get(task_id)
        if task is None:
            raise ReconcileError(
                f"label_habit task {task_id} not found live; refusing to "
                f"proceed."
            )
        if task.get("project_id") != habits_pid:
            raise ReconcileError(
                f"label_habit task {task_id} is in project "
                f"{task.get('project_id')!r}, not Habits({habits_pid}); refusing "
                f"to proceed."
            )

    blocked: list[tuple[str, int, str]] = []
    for task_id in manifest.moves:
        task = tasks_by_id.get(task_id)
        if task is None:
            # Absent moved task: not blocked here — build_plan treats an absent
            # (or already-moved) task as a no-op / skip. Preflight only blocks on
            # complex state of a task that is present.
            continue
        reason = _complex_state_reason(task)
        if reason is not None:
            blocked.append(("move", task_id, reason))

    return habit_label_id, blocked


# ---------------------------------------------------------------------------
# Plan (pure diff) — no I/O
# ---------------------------------------------------------------------------


@dataclass
class MigrationPlan:
    """What the migration would do — computed without mutating (data-model.md).

    ``moves`` are ``(task_id, from_project_id, to_project_id)`` only where
    ``from != to``. ``labels`` are ``(task_id, label_id)`` only where the label
    is absent. ``task_deletes`` / ``project_deletes`` list only still-present
    items. ``skipped`` is idempotency evidence (already-satisfied actions).
    ``blocked`` is preflight complex-state + any doomed project observed non-
    empty at plan time.
    """

    moves: list[tuple[int, int, int]] = field(default_factory=list)
    labels: list[tuple[int, int]] = field(default_factory=list)
    task_deletes: list[int] = field(default_factory=list)
    project_deletes: list[tuple[int, str]] = field(default_factory=list)
    skipped: list[tuple[str, int, str]] = field(default_factory=list)
    blocked: list[tuple[str, int, str]] = field(default_factory=list)

    def has_deletes(self) -> bool:
        return bool(self.task_deletes or self.project_deletes)

    def is_empty(self) -> bool:
        """True when no mutating action remains (idempotent completion proof)."""
        return not (
            self.moves or self.labels or self.task_deletes or self.project_deletes
        )


def build_plan(
    projects: list[dict],
    all_tasks: list[dict],
    labels: list[dict],
    manifest: Manifest,
    blocked: list[tuple[str, int, str]],
    habit_label_id: int,
) -> MigrationPlan:
    """Compute the migration plan by diffing live state against the manifest.

    Pure: no I/O. Idempotent — a re-run over post-migration state (tasks already
    in their target project, labels present, doomed projects gone) yields an
    empty plan (``is_empty()`` True). ``blocked`` task ids from preflight are
    excluded from the ``moves`` list and carried through as ``blocked``.
    """
    plan = MigrationPlan()
    plan.blocked = list(blocked)
    blocked_task_ids = {tid for _kind, tid, _reason in blocked if _kind == "move"}

    tasks_by_id = {
        tid: task
        for task in all_tasks
        if isinstance((tid := task.get("id")), int) and not isinstance(tid, bool)
    }
    index = _index_projects(projects)

    # Moves: only where the task is present and its project differs from target.
    for task_id, key in manifest.moves.items():
        target_pid = manifest.target_projects[key]
        task = tasks_by_id.get(task_id)
        if task is None:
            plan.skipped.append(("move", task_id, "task absent (already moved/deleted)"))
            continue
        if task_id in blocked_task_ids:
            # Reported via blocked; never queued as a move.
            continue
        current_pid = task.get("project_id")
        if current_pid == target_pid:
            plan.skipped.append(("move", task_id, f"already in {target_pid}"))
            continue
        if not isinstance(current_pid, int) or isinstance(current_pid, bool):
            raise ReconcileError(
                f"task {task_id} has a non-integer project_id "
                f"{current_pid!r}; refusing to move."
            )
        plan.moves.append((task_id, current_pid, target_pid))

    # Labels: only where t:habit is absent on a present habit task.
    for task_id in manifest.label_habit:
        task = tasks_by_id.get(task_id)
        if task is None:
            plan.skipped.append(("label", task_id, "task absent"))
            continue
        if _task_has_label(task, habit_label_id):
            plan.skipped.append(("label", task_id, "t:habit already present"))
            continue
        plan.labels.append((task_id, habit_label_id))

    # Task deletes: only where the task is still present.
    for task_id in manifest.delete_tasks:
        if task_id in tasks_by_id:
            plan.task_deletes.append(task_id)
        else:
            plan.skipped.append(("delete_task", task_id, "task absent (already deleted)"))

    # Project deletes: only where the project is still present. A doomed project
    # observed non-empty *at plan time* is reported blocked (the apply-time
    # immediate re-list is the authoritative gate, but surfacing it early aids
    # the operator).
    for pid in manifest.delete_projects:
        project = index.get(pid)
        if project is None:
            plan.skipped.append(("delete_project", pid, "project absent (already deleted)"))
            continue
        title = project.get("title")
        title_str = title if isinstance(title, str) else PROJECT_TITLES.get(pid, str(pid))
        # Count remaining tasks EXCLUDING those the plan will move or delete —
        # those are still live at plan time but will be gone before the delete.
        remaining = [
            t
            for t in tasks_in_project(all_tasks, pid)
            if t.get("id") not in manifest.delete_tasks
            and (t.get("id") not in manifest.moves)
        ]
        if remaining:
            ids = sorted(
                tid for t in remaining if isinstance((tid := t.get("id")), int)
            )
            plan.blocked.append(
                (
                    "delete_project",
                    pid,
                    f"holds {len(remaining)} unrouted task(s) {ids}",
                )
            )
            continue
        plan.project_deletes.append((pid, title_str))

    return plan


# ---------------------------------------------------------------------------
# Execute — move (allowlisted RMW + readback), label attach, deletes
# ---------------------------------------------------------------------------


def _writable_payload(task: dict) -> dict[str, Any]:
    """Copy the writable-field allowlist from a task (NFR-001).

    Only fields present on the task are copied — an absent field is left out so
    the server keeps its default rather than being sent an explicit ``None``.
    ``project_id`` is added by :func:`move_task`, not here.
    """
    return {name: task[name] for name in _WRITABLE_FIELDS if name in task}


def move_task(client: Any, task: dict, to_pid: int) -> None:
    """Move ``task`` to project ``to_pid`` via an allowlisted RMW + readback.

    Builds the payload from :func:`_writable_payload` plus ``project_id`` (never
    a blind echo of GET output — Vikunja POST is partial-replace, #524), POSTs
    to ``/tasks/{id}``, then GETs the task back and asserts ``project_id`` is the
    new target AND every allowlisted field is unchanged. Any mismatch raises
    :class:`ReconcileError` (a readback mismatch is a hard failure, not a warn).
    """
    task_id = task.get("id")
    if not isinstance(task_id, int) or isinstance(task_id, bool):
        raise ReconcileError(f"cannot move task with non-integer id {task_id!r}")

    payload = _writable_payload(task)
    payload["project_id"] = to_pid

    client.post(f"/tasks/{task_id}", json=payload)

    readback = client.get(f"/tasks/{task_id}")
    if not isinstance(readback, dict):
        raise ReconcileError(
            f"move readback for task {task_id} returned a non-object; refusing "
            f"to trust the move."
        )
    if readback.get("project_id") != to_pid:
        raise ReconcileError(
            f"move readback for task {task_id}: project_id is "
            f"{readback.get('project_id')!r}, expected {to_pid}. Aborting."
        )
    for name in _WRITABLE_FIELDS:
        if name in payload and readback.get(name) != payload[name]:
            raise ReconcileError(
                f"move readback for task {task_id}: field {name!r} changed from "
                f"{payload[name]!r} to {readback.get(name)!r}. Vikunja may have "
                f"zeroed an unstated field — aborting fail-loud (#524)."
            )


def apply_habit_label(client: Any, task: dict, label_id: int) -> bool:
    """Attach ``t:habit`` to ``task`` if absent; return True iff it was attached.

    Idempotent: if the label is already present, no call is made and False is
    returned. Otherwise ``PUT /tasks/{id}/labels`` with ``{"label_id": id}``.
    """
    if _task_has_label(task, label_id):
        return False
    task_id = task.get("id")
    if not isinstance(task_id, int) or isinstance(task_id, bool):
        raise ReconcileError(f"cannot label task with non-integer id {task_id!r}")
    client.put(f"/tasks/{task_id}/labels", json={"label_id": label_id})
    return True


def _delete_task(client: Any, task_id: int) -> None:
    client.delete(f"/tasks/{task_id}")


def _delete_project_if_empty(client: Any, pid: int, title: str) -> None:
    """Delete project ``pid`` only after an immediate, fresh empty-check.

    Re-lists all tasks off a fresh done-inclusive ``/tasks/all`` *immediately*
    before deleting (not the plan-time snapshot), refuses (raises) if any task
    remains in ``pid``, else ``DELETE /projects/{id}`` (FR-004/FR-006).
    """
    fresh = list_all_tasks(client)
    remaining = tasks_in_project(fresh, pid)
    if remaining:
        ids = sorted(
            tid for t in remaining if isinstance((tid := t.get("id")), int)
        )
        raise ReconcileError(
            f"refusing to delete project {pid} ({title!r}): it still holds "
            f"{len(remaining)} task(s) {ids} at the immediate pre-delete "
            f"re-list. Aborting fail-loud."
        )
    client.delete(f"/projects/{pid}")


# ---------------------------------------------------------------------------
# Orchestration
# ---------------------------------------------------------------------------


@dataclass
class MigrationSummary:
    """Applied-run accounting for the summary (FR-009)."""

    mode: str
    backup_ref: str | None
    moved: int = 0
    labeled: int = 0
    tasks_deleted: int = 0
    projects_deleted: int = 0
    skipped: int = 0
    blocked: list[tuple[str, int, str]] = field(default_factory=list)
    actions: list[dict] = field(default_factory=list)


def reconcile(
    client: Any,
    manifest: Manifest,
    *,
    apply: bool,
    backup_ref: str | None,
) -> tuple[MigrationPlan, MigrationSummary]:
    """Read live state, preflight, plan, and — if ``apply`` — execute in order.

    Steps (data-model.md 1–8):

    1. fetch live projects/labels + **all tasks** (paginated, done-inclusive);
    2. ``preflight`` → abort on any identity/shape mismatch; collect complex-
       state ``blocked``;
    3. ``build_plan``;
    4. if not ``apply`` → return the dry-run plan (caller prints it), no
       mutation;
    5. if the plan has any delete and ``backup_ref`` is empty → raise (NFR-002);
    6. if ``blocked`` is non-empty → raise (FR-006/FR-011); never migrate/delete
       around a blocked item;
    7. execute **moves** (RMW + readback) → **labels** → **task-deletes** (incl.
       the test tasks, BEFORE the project empty-check — H-5) → **project-
       deletes** (each re-listed immediately, children before parents);
    8. return the plan + a summary classifying each action.

    Returns ``(plan, summary)``. The summary's ``mode`` is ``"dry-run"`` or
    ``"apply"``.
    """
    projects = list_projects(client)
    labels = list_labels(client)
    all_tasks = list_all_tasks(client)

    habit_label_id, blocked = preflight(
        client, all_tasks, projects, labels, manifest
    )
    plan = build_plan(
        projects, all_tasks, labels, manifest, blocked, habit_label_id
    )

    if not apply:
        summary = MigrationSummary(mode="dry-run", backup_ref=backup_ref)
        summary.moved = len(plan.moves)
        summary.labeled = len(plan.labels)
        summary.tasks_deleted = len(plan.task_deletes)
        summary.projects_deleted = len(plan.project_deletes)
        summary.skipped = len(plan.skipped)
        summary.blocked = list(plan.blocked)
        for task_id, from_pid, to_pid in plan.moves:
            summary.actions.append(
                {"kind": "move", "task": task_id, "from": from_pid, "to": to_pid}
            )
        return plan, summary

    if plan.has_deletes() and not (backup_ref and backup_ref.strip()):
        raise ReconcileError(
            "the plan contains deletions but --backup-ref is empty; a non-empty "
            "Restic snapshot id / ISO timestamp is required for any deletion "
            "(NFR-002, Tier 2). Refusing to delete."
        )

    if plan.blocked:
        raise ReconcileError(
            f"plan has {len(plan.blocked)} blocked item(s): {plan.blocked}. "
            f"Refusing to migrate or delete around them (FR-006/FR-011)."
        )

    summary = MigrationSummary(mode="apply", backup_ref=backup_ref)

    tasks_by_id = {
        tid: task
        for task in all_tasks
        if isinstance((tid := task.get("id")), int) and not isinstance(tid, bool)
    }

    # 7a. moves (allowlisted RMW + readback).
    for task_id, from_pid, to_pid in plan.moves:
        move_task(client, tasks_by_id[task_id], to_pid)
        summary.moved += 1
        summary.actions.append(
            {"kind": "move", "task": task_id, "from": from_pid, "to": to_pid}
        )

    # 7b. labels.
    for task_id, label_id in plan.labels:
        if apply_habit_label(client, tasks_by_id[task_id], label_id):
            summary.labeled += 1
            summary.actions.append(
                {"kind": "label", "task": task_id, "label": label_id}
            )

    # 7c. task-deletes — BEFORE the project empty-check (H-5: #89 lives in the
    # doomed Someday project, so deleting it first prevents a self-block).
    for task_id in plan.task_deletes:
        _delete_task(client, task_id)
        summary.tasks_deleted += 1
        summary.actions.append({"kind": "delete_task", "task": task_id})

    # 7d. project-deletes — each re-listed immediately (children before parents,
    # already ordered by the manifest / plan).
    for pid, title in plan.project_deletes:
        _delete_project_if_empty(client, pid, title)
        summary.projects_deleted += 1
        summary.actions.append({"kind": "delete_project", "project": pid})

    summary.skipped = len(plan.skipped)
    summary.blocked = list(plan.blocked)
    return plan, summary


# ---------------------------------------------------------------------------
# Summary rendering
# ---------------------------------------------------------------------------


def _print_plan_human(plan: MigrationPlan, *, dry_run: bool) -> None:
    header = "PLAN (dry-run)" if dry_run else "APPLY"
    print(f"--- {header} ---")
    print(
        f"  moves: {len(plan.moves)}   labels: {len(plan.labels)}   "
        f"task-deletes: {len(plan.task_deletes)}   "
        f"project-deletes: {len(plan.project_deletes)}   "
        f"skipped: {len(plan.skipped)}   blocked: {len(plan.blocked)}"
    )
    for task_id, from_pid, to_pid in plan.moves:
        print(f"  move   #{task_id}  {from_pid} -> {to_pid}")
    for task_id, label_id in plan.labels:
        print(f"  label  #{task_id}  {HABIT_LABEL_TITLE} (id {label_id})")
    for task_id in plan.task_deletes:
        print(f"  delete task #{task_id}")
    for pid, title in plan.project_deletes:
        print(f"  delete project {pid} {title!r}")
    for kind, ident, reason in plan.skipped:
        print(f"  skip   {kind} #{ident}  ({reason})")
    for kind, ident, reason in plan.blocked:
        print(f"  BLOCK  {kind} #{ident}  ({reason})")


def _print_summary_human(summary: MigrationSummary) -> None:
    print(f"--- summary ({summary.mode}) ---")
    print(
        f"  moved: {summary.moved}   labeled: {summary.labeled}   "
        f"tasks_deleted: {summary.tasks_deleted}   "
        f"projects_deleted: {summary.projects_deleted}   "
        f"skipped: {summary.skipped}   blocked: {len(summary.blocked)}"
    )
    for kind, ident, reason in summary.blocked:
        print(f"  BLOCK  {kind} #{ident}  ({reason})")
    print(f"  backup_ref: {summary.backup_ref if summary.backup_ref else '-'}")


def _summary_to_dict(summary: MigrationSummary) -> dict[str, Any]:
    return {
        "mode": summary.mode,
        "backup_ref": summary.backup_ref,
        "moved": summary.moved,
        "labeled": summary.labeled,
        "tasks_deleted": summary.tasks_deleted,
        "projects_deleted": summary.projects_deleted,
        "skipped": summary.skipped,
        "blocked": [
            {"kind": k, "id": i, "reason": r} for k, i, r in summary.blocked
        ],
        "actions": summary.actions,
    }


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="scripts.vikunja.migrate_tasks",
        description=(
            "Migrate surviving Vikunja tasks into topic projects, apply t:habit, "
            "delete two test tasks, and delete six emptied legacy projects "
            "(#717). Dry-run by default; --apply executes. Any deletion requires "
            "a non-empty --backup-ref (Tier 2). kent token only."
        ),
    )
    parser.add_argument(
        "--manifest",
        default=DEFAULT_MANIFEST_PATH,
        metavar="PATH",
        help=f"routing manifest (default: {DEFAULT_MANIFEST_PATH})",
    )
    parser.add_argument(
        "--token-file",
        default=DEFAULT_KENT_TOKEN_FILE,
        metavar="PATH",
        help=(
            "read the kent-owned API token from this file (default: "
            f"{DEFAULT_KENT_TOKEN_FILE}). The felix-bot token path is refused."
        ),
    )
    parser.add_argument(
        "--apply",
        action="store_true",
        help="execute the plan; without it, print the plan and exit 0 (dry-run)",
    )
    parser.add_argument(
        "--backup-ref",
        default=None,
        metavar="TEXT",
        help=(
            "Restic snapshot id / ISO timestamp of a <=24h vikunja.db snapshot; "
            "required (non-empty) for any deletion; echoed verbatim in the "
            "summary. The helper does not itself validate Restic."
        ),
    )
    parser.add_argument(
        "--json",
        action="store_true",
        help="emit the plan/summary as JSON instead of human text",
    )
    parser.add_argument(
        "--base-url",
        default=None,
        help="override Vikunja base URL (else canonical config)",
    )
    return parser


def _read_token_file(path: str) -> str:
    """Read the kent token from ``path``; refuse the felix-bot path; abort if
    missing/blank.

    Reads ONLY this file — never the VikunjaClient felix-bot default. The known
    felix-bot token path is refused outright (pre-mutation guard): a felix-bot
    run makes kent-invisible changes and cannot attach a kent label (403).
    """
    if os.path.abspath(path) == os.path.abspath(FELIX_BOT_TOKEN_FILE):
        raise ReconcileError(
            f"refusing to use the felix-bot token file {path!r}: this helper "
            f"makes kent-owned changes (moves + a kent label attach) and must "
            f"use the 'vikunja-api-kent' credential (#715 two-token model)."
        )
    try:
        with open(path, encoding="utf-8") as handle:
            token = handle.read()
    except OSError as exc:
        raise ReconcileError(
            f"kent token file {path!r} could not be read: {exc}. This helper "
            f"requires the kent-owned 'vikunja-api-kent' credential and never "
            f"falls back to the felix-bot token."
        ) from exc
    if not token.strip():
        raise ReconcileError(
            f"kent token file {path!r} is empty. Provision the kent-owned "
            f"'vikunja-api-kent' credential before running."
        )
    return token


def _build_client(args: argparse.Namespace) -> Any:
    from scripts.common.vikunja_client import VikunjaClient

    token = _read_token_file(args.token_file)
    return VikunjaClient(base_url=args.base_url, token=token)


def main(argv: list[str] | None = None, *, client: Any | None = None) -> int:
    """CLI entrypoint. Returns 0 on dry-run / apply-success / no-op, 1 otherwise.

    Exit codes (contracts/migrate_tasks_cli.md): ``0`` dry-run printed, apply
    succeeded, or nothing to do (idempotent); ``1`` fail-loud — non-empty doomed
    project, wrong identity, missing backup flag, owner/title mismatch, readback
    mismatch, or any Vikunja error.
    """
    args = _build_parser().parse_args(argv)

    try:
        manifest = load_manifest(args.manifest)
        # Refuse the felix-bot token path up front (independent of preflight).
        if client is None:
            active_client = _build_client(args)
        else:
            # Still enforce the token-path refusal even when a client is injected
            # (tests exercise the CLI guard by passing --token-file).
            if os.path.abspath(args.token_file) == os.path.abspath(
                FELIX_BOT_TOKEN_FILE
            ):
                raise ReconcileError(
                    f"refusing to use the felix-bot token file "
                    f"{args.token_file!r} (#715 two-token model)."
                )
            active_client = client

        backup_ref = args.backup_ref.strip() if args.backup_ref else None
        plan, summary = reconcile(
            active_client,
            manifest,
            apply=args.apply,
            backup_ref=backup_ref,
        )
    except (VikunjaError, ReconcileError) as exc:
        print(f"ERROR: {type(exc).__name__}: {exc}", file=sys.stderr)
        return 1
    except Exception as exc:  # noqa: BLE001 - CLI boundary: report, exit 1
        print(f"ERROR: {type(exc).__name__}: {exc}", file=sys.stderr)
        return 1

    if args.json:
        if args.apply:
            print(json.dumps(_summary_to_dict(summary), ensure_ascii=False))
        else:
            payload = _summary_to_dict(summary)
            print(json.dumps(payload, ensure_ascii=False))
    else:
        _print_plan_human(plan, dry_run=not args.apply)
        if args.apply:
            _print_summary_human(summary)

    return 0


if __name__ == "__main__":  # pragma: no cover - CLI entry
    sys.exit(main())
