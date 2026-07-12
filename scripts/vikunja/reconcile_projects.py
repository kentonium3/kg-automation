#!/usr/bin/env python3
"""Reconcile the live Vikunja project structure toward the canonical layout (#716).

Deterministic, idempotent helper (Felix Constitution Directive 6): no LLM, no
global state, no caching. It **additively** creates any missing topic project
(as kent), verifies Kent's ``Inbox`` without recreating it, and — only behind an
explicit backup-gated flag — deletes the five legacy saved filters. **No project
is ever deleted** (that plus task migration is #717); the plan is asserted to
contain zero project-delete operations.

Ownership is enforced without a whoami endpoint (``GET /user`` is 401 for API
tokens, R-07): the token is read ONLY from an explicit ``--token-file`` that
defaults to the kent secret — never the ``VikunjaClient`` felix-bot default —
matching considers only ``owner.username == "kent"`` projects, and every create
response's owner is asserted ``== "kent"`` (aborting fail-loud otherwise). This
is what ignores felix-bot's own ``Inbox`` (id 14) and prevents creating
kent-invisible, felix-bot-owned projects (the #715 failure).

Create is ``PUT /projects`` with ``{"title", "parent_project_id"}`` (``0`` for
top-level; the resolved ``Clients`` id for its children). Legacy filters surface
as negative-id pseudo-projects: for ``id <= -2`` (never ``-1`` / native
``Favorites``) whose title is legacy, the filter id is ``-id - 1``; a
``GET /filters/{id}`` title readback precedes each ``DELETE /filters/{id}``.

The **live run is operator-invoked post-merge** — this module ships the code +
tests + the design-doc edit only. Run it on office2 as::

    python3 -m scripts.vikunja.reconcile_projects [options]

Wraps the deterministic ``scripts.common.vikunja_client.VikunjaClient`` — the
canonical stdlib HTTP boundary. No new HTTP path, no ``requests`` dependency.
"""
from __future__ import annotations

import argparse
import json
import os
import sys
from dataclasses import dataclass, field
from typing import Any

from scripts.common.vikunja_client import VikunjaError

__all__ = [
    "DEFAULT_KENT_TOKEN_FILE",
    "KENT_USERNAME",
    "LEGACY_FILTER_TITLES",
    "INBOX_TITLE",
    "TargetProject",
    "TARGET_PROJECTS",
    "ReconcileOutcome",
    "ReconcileError",
    "list_projects",
    "build_plan",
    "reconcile",
    "main",
]

# The kent-owned, all-perms token (#715 two-token model). Read ONLY this file;
# never fall back to VikunjaClient's felix-bot default token path.
DEFAULT_KENT_TOKEN_FILE = "/data/services/openclaw/secrets/vikunja-api-kent"

# The felix-bot task-CRUD token path. Explicitly refused as a token source: a
# felix-bot run would create kent-invisible, felix-bot-owned projects (the #715
# failure). Rejecting the path up front is a pre-mutation guard that does not
# depend on a create response firing (post-merge review HIGH #1).
FELIX_BOT_TOKEN_FILE = "/data/services/openclaw/secrets/vikunja-api"

KENT_USERNAME = "kent"

# Vikunja caps ``per_page`` at 50 on this instance (R-05a); a ``len < 100`` stop
# condition would be wrong.
_PAGE_SIZE = 50

INBOX_TITLE = "Inbox"

# Sentinel parent for top-level projects. Real ``Clients`` id is resolved live.
_TOP_LEVEL_PARENT = 0

# Legacy saved filters removed here (#716). Ids are environment-specific and are
# NEVER hardcoded — each is derived live from its negative-id pseudo-project.
LEGACY_FILTER_TITLES: tuple[str, ...] = (
    "Today",
    "Upcoming",
    "Overdue",
    "Goals",
    "Completed",
)


class ReconcileError(Exception):
    """Fail-loud reconciliation error (ambiguity, owner mismatch, inconsistency).

    Raised for any condition where continuing could bind to the wrong project,
    create a duplicate, or act under the wrong owner. Surfaced by :func:`main`
    as a non-zero exit — never swallowed.
    """


@dataclass(frozen=True)
class TargetProject:
    """A project the helper intends to exist. Pure declared data.

    ``parent_title`` is ``None`` for a top-level project or the title of the
    parent project (resolved to a live id at create time) for a sub-project.
    """

    title: str
    parent_title: str | None  # None == top-level


# Single in-code source of truth for the canonical target structure. Ordered so
# ``Clients`` precedes its children (its live id is resolved before they create).
TARGET_PROJECTS: tuple[TargetProject, ...] = (
    TargetProject("Felix / kg-automation", None),
    TargetProject("Clients", None),
    TargetProject("PointerHealth", "Clients"),
    TargetProject("spec-kitty", "Clients"),
    TargetProject("Personal", None),
)


@dataclass(frozen=True)
class ReconcileOutcome:
    """One emitted per project/filter/Inbox acted on or examined.

    ``action`` is one of: ``created`` | ``already-present`` (verified) |
    ``deleted`` | ``already-absent`` | ``skipped-no-flag`` | ``verified-inbox``
    | ``skipped`` (not reached due to a mid-run abort).
    """

    kind: str  # project | filter | inbox
    title: str
    action: str
    id: int | None = None
    filter_id: int | None = None


@dataclass
class ReconcilePlan:
    """What the reconcile would do — computed without mutating (data-model.md).

    ``projects_to_create`` is ordered parent-before-children.
    ``filters_to_delete`` maps a legacy title to its derived ``filter_id`` and
    the negative pseudo-project id it came from. ``clients_existing_id`` is set
    when an active top-level kent-owned ``Clients`` already exists.
    """

    projects_to_create: list[TargetProject] = field(default_factory=list)
    projects_verified: dict[str, int] = field(default_factory=dict)
    filters_to_delete: list[tuple[str, int, int]] = field(default_factory=list)
    filters_absent: list[str] = field(default_factory=list)
    inbox_id: int | None = None
    clients_existing_id: int | None = None


# ---------------------------------------------------------------------------
# Read
# ---------------------------------------------------------------------------


def list_projects(client: Any) -> list[dict]:
    """Return every project element from a paginated ``GET /projects``.

    Pages ``per_page=50`` from page 1, accumulating until a page returns fewer
    than 50 items (or empty). A ``null`` body (Vikunja's empty-collection quirk,
    R-03) is normalised to ``[]``. Both real (positive id) and pseudo-project
    (negative id) elements are kept — the negative ids drive filter derivation.
    Any non-list, non-null 200 body is a contract violation → surfaced.
    """
    projects: list[dict] = []
    page = 1
    while True:
        batch = client.get(
            "/projects",
            params={"per_page": str(_PAGE_SIZE), "page": str(page)},
        )
        if batch is None:
            # Vikunja returns JSON ``null`` (not ``[]``) for an empty/exhausted
            # collection — treat as an empty page and stop (the #715 quirk).
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


def _owner_username(project: dict) -> str | None:
    owner = project.get("owner")
    if isinstance(owner, dict):
        username = owner.get("username")
        if isinstance(username, str):
            return username
    return None


def _is_kent_owned(project: dict) -> bool:
    return _owner_username(project) == KENT_USERNAME


def _project_id(project: dict) -> int | None:
    pid = project.get("id")
    return pid if isinstance(pid, int) else None


# ---------------------------------------------------------------------------
# Plan (match + ambiguity + derivation) — no mutation
# ---------------------------------------------------------------------------


def _match_candidates(
    projects: list[dict], title: str, expected_parent: int
) -> list[dict]:
    """Active, kent-owned projects with the given title AND expected parent.

    The full match key (data-model.md): ``owner == "kent"`` AND
    ``is_archived == false`` AND ``parent_project_id == expected_parent``.
    """
    matches: list[dict] = []
    for project in projects:
        if project.get("title") != title:
            continue
        if not _is_kent_owned(project):
            continue
        if project.get("is_archived") is True:
            continue
        if project.get("parent_project_id", _TOP_LEVEL_PARENT) != expected_parent:
            continue
        matches.append(project)
    return matches


def _title_seen_anywhere(projects: list[dict], title: str) -> list[dict]:
    """Any project with this title, regardless of owner/archived/parent.

    Used to detect an ambiguous collision (an archived / wrong-parent /
    wrong-owner project sharing the title) so the helper aborts rather than
    creating a silent duplicate (FR-014).
    """
    return [p for p in projects if p.get("title") == title]


def _resolve_target(
    projects: list[dict], title: str, expected_parent: int
) -> int | None:
    """Resolve a single target: existing id, ``None`` (create), or abort.

    Zero active/correct matches → ``None`` (create). Exactly one → its id
    (reuse). More than one active/correct match, OR a title collision with an
    archived / wrong-parent / wrong-owner project → :class:`ReconcileError`
    (fail-loud, no duplicate, no wrong bind).
    """
    candidates = _match_candidates(projects, title, expected_parent)
    if len(candidates) > 1:
        ids = sorted(
            pid for c in candidates if (pid := _project_id(c)) is not None
        )
        raise ReconcileError(
            f"Ambiguous target {title!r}: {len(candidates)} active, correctly "
            f"parented kent-owned projects match (ids {ids}). Refusing to bind "
            f"or duplicate — resolve manually."
        )
    if candidates:
        existing_id = _project_id(candidates[0])
        if existing_id is None:
            raise ReconcileError(
                f"Target {title!r} matched a project with a non-integer id "
                f"{candidates[0].get('id')!r}; refusing to proceed."
            )
        # A title collision alongside the one good match (e.g. an archived or
        # felix-bot-owned twin) is still ambiguous — abort rather than reuse.
        collisions = _title_seen_anywhere(projects, title)
        if len(collisions) > 1:
            raise ReconcileError(
                f"Title {title!r} collides: one active kent-owned match plus "
                f"{len(collisions) - 1} other project(s) share the title "
                f"(archived / wrong-parent / wrong-owner). Refusing to reuse."
            )
        return existing_id
    # No active/correct match. If some OTHER project owns the title, that is an
    # ambiguous collision — abort rather than create a confusing duplicate.
    collisions = _title_seen_anywhere(projects, title)
    if collisions:
        raise ReconcileError(
            f"No active, correctly-parented kent-owned project titled "
            f"{title!r}, but {len(collisions)} project(s) share the title "
            f"(archived / wrong-parent / wrong-owner). Refusing to create a "
            f"duplicate — resolve manually."
        )
    return None


def _derive_legacy_filters(projects: list[dict]) -> list[tuple[str, int, int]]:
    """Derive ``(title, filter_id, pseudo_id)`` for present legacy filters.

    From **kent-owned** negative-id pseudo-projects with ``id <= -2`` (excludes
    native ``Favorites`` at ``-1``) whose title is in the legacy set, compute
    ``filter_id = -id - 1``. Favorites (``-1``) is never derived or targeted.
    The owner check (post-merge review HIGH #2) is defense-in-depth: filters are
    per-user, but deriving only from kent-owned pseudo-projects guarantees a
    shared/other-user filter with a legacy title is never queued for deletion.
    """
    derived: list[tuple[str, int, int]] = []
    for project in projects:
        pseudo_id = _project_id(project)
        if pseudo_id is None or pseudo_id > -2:
            # Skips positive real projects, 0, and Favorites (-1).
            continue
        if not _is_kent_owned(project):
            # Only delete Kent's own legacy filters.
            continue
        title = project.get("title")
        if not isinstance(title, str) or title not in LEGACY_FILTER_TITLES:
            continue
        filter_id = -pseudo_id - 1
        derived.append((title, filter_id, pseudo_id))
    return derived


def build_plan(projects: list[dict]) -> ReconcilePlan:
    """Compute the reconcile plan from live projects. Never mutates.

    Resolves each target (create / reuse / abort), requires ``Clients`` to be
    unambiguous before its children, verifies Kent's ``Inbox`` exists, and
    derives the legacy filters to delete. Asserts (invariant 3) the plan holds
    zero project-delete operations — there is no such field, so this is
    structural, but the ``_assert_no_project_delete`` guard makes it explicit.
    """
    plan = ReconcilePlan()

    # Inbox: verify Kent's native Inbox exists (top-level, kent-owned). Never
    # recreate; if absent it is a hard error (Inbox is native — do not create).
    inbox_candidates = _match_candidates(
        projects, INBOX_TITLE, _TOP_LEVEL_PARENT
    )
    if not inbox_candidates:
        raise ReconcileError(
            f"Kent's native {INBOX_TITLE!r} project was not found among "
            f"active top-level kent-owned projects. Inbox is native and must "
            f"not be created — aborting."
        )
    if len(inbox_candidates) > 1:
        raise ReconcileError(
            f"Multiple active top-level kent-owned {INBOX_TITLE!r} projects "
            f"found — ambiguous. Aborting."
        )
    plan.inbox_id = _project_id(inbox_candidates[0])

    # Resolve Clients FIRST so children can reference its id (create or reuse).
    clients_existing = _resolve_target(projects, "Clients", _TOP_LEVEL_PARENT)
    plan.clients_existing_id = clients_existing

    for target in TARGET_PROJECTS:
        expected_parent = _TOP_LEVEL_PARENT
        if target.parent_title is not None:
            # Children resolve against the existing Clients id if present; if
            # Clients does not yet exist, no child can already exist under it,
            # so resolution uses the sentinel and any collision still aborts.
            expected_parent = (
                clients_existing
                if clients_existing is not None
                else _TOP_LEVEL_PARENT
            )
            if clients_existing is None:
                # Clients will be created; a child cannot pre-exist under a
                # not-yet-created parent. Still guard against a title collision.
                collisions = _title_seen_anywhere(projects, target.title)
                if collisions:
                    raise ReconcileError(
                        f"Child target {target.title!r} shares its title with "
                        f"{len(collisions)} existing project(s) while its "
                        f"parent 'Clients' does not yet exist — ambiguous. "
                        f"Aborting."
                    )
                plan.projects_to_create.append(target)
                continue

        existing_id = _resolve_target(projects, target.title, expected_parent)
        if existing_id is None:
            plan.projects_to_create.append(target)
        else:
            plan.projects_verified[target.title] = existing_id

    for title, filter_id, pseudo_id in _derive_legacy_filters(projects):
        plan.filters_to_delete.append((title, filter_id, pseudo_id))
    present_filter_titles = {t for t, _fid, _pid in plan.filters_to_delete}
    plan.filters_absent = [
        t for t in LEGACY_FILTER_TITLES if t not in present_filter_titles
    ]

    _assert_no_project_delete(plan)
    return plan


def _assert_no_project_delete(plan: ReconcilePlan) -> None:
    """Structural invariant 3: the plan contains no project-delete operation.

    The plan type has no delete-project field by construction; this guard makes
    the invariant explicit and would catch a future field being misused.
    """
    forbidden = {"projects_to_delete", "project_delete", "delete_projects"}
    for name in forbidden:
        if getattr(plan, name, None):
            raise ReconcileError(
                f"Invariant violation: plan carries {name!r} — no project may "
                f"be deleted by this mission (#717 owns deletions)."
            )


# ---------------------------------------------------------------------------
# Execute — create pass + filter-delete pass
# ---------------------------------------------------------------------------


def _create_pass(
    client: Any,
    plan: ReconcilePlan,
    outcomes: list[ReconcileOutcome],
    *,
    dry_run: bool,
) -> None:
    """Additively create the missing projects, asserting kent ownership.

    ``Clients`` (if being created) is created first and its live id resolved
    before its children. Each create response's ``owner.username`` is asserted
    ``== "kent"`` (abort fail-loud otherwise — wrong token despite the path).
    On any error the already-created projects are reported and the remaining
    ones marked ``skipped`` so the summary shows completed vs skipped (NFR-005).
    """
    # Resolve the Clients id: an already-present one, else the create response.
    clients_id = plan.clients_existing_id
    to_create = list(plan.projects_to_create)

    def _remaining_skipped(from_index: int) -> None:
        for pending in to_create[from_index:]:
            outcomes.append(
                ReconcileOutcome("project", pending.title, "skipped")
            )

    for index, target in enumerate(to_create):
        parent_id = _TOP_LEVEL_PARENT
        if target.parent_title is not None:
            if clients_id is None:
                # Should not happen: Clients precedes children in the plan
                # order. Fail loud rather than create an orphan.
                _remaining_skipped(index)
                raise ReconcileError(
                    f"Cannot create child {target.title!r}: parent 'Clients' "
                    f"id unresolved. Aborting."
                )
            parent_id = clients_id

        if dry_run:
            outcomes.append(
                ReconcileOutcome("project", target.title, "created", id=None)
            )
            if target.title == "Clients":
                # Give children a non-sentinel parent in the plan printout.
                clients_id = clients_id if clients_id is not None else -100
            continue

        try:
            response = client.put(
                "/projects",
                json={"title": target.title, "parent_project_id": parent_id},
            )
        except Exception:
            _remaining_skipped(index)
            raise

        if not isinstance(response, dict):
            _remaining_skipped(index)
            raise ReconcileError(
                f"Create of {target.title!r} returned a non-object response; "
                f"refusing to proceed."
            )
        if _owner_username(response) != KENT_USERNAME:
            _remaining_skipped(index)
            raise ReconcileError(
                f"Create of {target.title!r} returned owner "
                f"{_owner_username(response)!r}, not {KENT_USERNAME!r}. Wrong "
                f"token despite the token-file path — aborting fail-loud."
            )
        new_id = _project_id(response)
        outcomes.append(
            ReconcileOutcome("project", target.title, "created", id=new_id)
        )
        if target.title == "Clients":
            if new_id is None:
                _remaining_skipped(index + 1)
                raise ReconcileError(
                    "Create of 'Clients' returned no integer id; cannot parent "
                    "its children. Aborting."
                )
            clients_id = new_id


def _delete_filters_pass(
    client: Any,
    plan: ReconcilePlan,
    outcomes: list[ReconcileOutcome],
    *,
    dry_run: bool,
) -> None:
    """Delete the derived legacy filters, readback-guarded and never ``-1``.

    For each ``(title, filter_id, pseudo_id)``: assert ``pseudo_id != -1``,
    ``GET /filters/{filter_id}`` and confirm the returned title equals the
    intended legacy title, then ``DELETE /filters/{filter_id}``. A readback
    title mismatch skips the delete and fails loud (guards the derivation).
    """
    to_delete = list(plan.filters_to_delete)

    def _remaining_skipped(from_index: int) -> None:
        for title, filter_id, _pid in to_delete[from_index:]:
            outcomes.append(
                ReconcileOutcome(
                    "filter", title, "skipped", filter_id=filter_id
                )
            )

    for index, (title, filter_id, pseudo_id) in enumerate(to_delete):
        # Absolute guard: never derive/act on native Favorites.
        if pseudo_id == -1:
            _remaining_skipped(index)
            raise ReconcileError(
                "Refusing to derive a filter for Favorites (pseudo id -1)."
            )
        if dry_run:
            outcomes.append(
                ReconcileOutcome("filter", title, "deleted", filter_id=filter_id)
            )
            continue

        try:
            readback = client.get(f"/filters/{filter_id}")
        except Exception:
            _remaining_skipped(index)
            raise
        readback_title = (
            readback.get("title") if isinstance(readback, dict) else None
        )
        if readback_title != title:
            # Derivation/readback disagree — do NOT delete. Fail loud so a wrong
            # filter is never removed (guards filter_id = -pseudo_id - 1).
            _remaining_skipped(index)
            raise ReconcileError(
                f"Filter readback mismatch for {title!r}: GET /filters/"
                f"{filter_id} returned title {readback_title!r}. Refusing to "
                f"delete — the id derivation may be wrong."
            )
        try:
            client.delete(f"/filters/{filter_id}")
        except Exception:
            _remaining_skipped(index)
            raise
        outcomes.append(
            ReconcileOutcome("filter", title, "deleted", filter_id=filter_id)
        )


def reconcile(
    client: Any,
    *,
    delete_legacy: bool = False,
    backup_confirmed: str | None = None,
    dry_run: bool = False,
) -> tuple[list[ReconcileOutcome], ReconcilePlan]:
    """Read live state, build the plan, create projects, optionally delete filters.

    Returns ``(outcomes, plan)``. Additive create runs always; the destructive
    filter-delete pass runs only when ``delete_legacy`` is set. The backup gate
    is enforced at THIS function boundary too (not only in :func:`main`): a
    programmatic caller must not delete legacy filters without a non-blank
    ``backup_confirmed`` ref (mirrors the #715 helper).

    Any :class:`VikunjaError`, :class:`ReconcileError`, or unexpected exception
    propagates to the caller (:func:`main` maps it to a non-zero exit). Outcomes
    accumulated before the failure — plus the ``skipped`` remainder — are
    attached to the raised error via :func:`_raise_with_partial` so the summary
    can report completed vs skipped (NFR-005).
    """
    if delete_legacy and not (backup_confirmed and backup_confirmed.strip()):
        raise ValueError(
            "delete_legacy=True requires a non-empty backup_confirmed reference"
        )

    outcomes: list[ReconcileOutcome] = []

    try:
        projects = list_projects(client)
        plan = build_plan(projects)

        outcomes.append(
            ReconcileOutcome(
                "inbox", INBOX_TITLE, "verified-inbox", id=plan.inbox_id
            )
        )
        for title, existing_id in plan.projects_verified.items():
            outcomes.append(
                ReconcileOutcome(
                    "project", title, "already-present", id=existing_id
                )
            )

        _create_pass(client, plan, outcomes, dry_run=dry_run)

        if delete_legacy:
            _delete_filters_pass(client, plan, outcomes, dry_run=dry_run)
        else:
            for title, filter_id, _pid in plan.filters_to_delete:
                outcomes.append(
                    ReconcileOutcome(
                        "filter", title, "skipped-no-flag", filter_id=filter_id
                    )
                )
        for title in plan.filters_absent:
            outcomes.append(
                ReconcileOutcome("filter", title, "already-absent")
            )
    except Exception as exc:  # noqa: BLE001 - attach partial progress, re-raise
        _attach_partial(exc, outcomes)
        raise

    return outcomes, plan


def _attach_partial(exc: Exception, outcomes: list[ReconcileOutcome]) -> None:
    """Attach accumulated outcomes to a raised exception for the summary."""
    exc.reconcile_outcomes = list(outcomes)  # type: ignore[attr-defined]


# ---------------------------------------------------------------------------
# Summary rendering
# ---------------------------------------------------------------------------


def _outcome_to_dict(outcome: ReconcileOutcome) -> dict[str, Any]:
    record: dict[str, Any] = {
        "kind": outcome.kind,
        "title": outcome.title,
        "action": outcome.action,
    }
    if outcome.id is not None:
        record["id"] = outcome.id
    if outcome.filter_id is not None:
        record["filter_id"] = outcome.filter_id
    return record


def _summarize(outcomes: list[ReconcileOutcome]) -> dict[str, list[str]]:
    """Group outcome titles by their disposition for the human summary."""
    buckets: dict[str, list[str]] = {
        "created": [],
        "verified": [],
        "deleted": [],
        "skipped": [],
    }
    for outcome in outcomes:
        if outcome.action == "created":
            buckets["created"].append(outcome.title)
        elif outcome.action in ("already-present", "verified-inbox"):
            buckets["verified"].append(outcome.title)
        elif outcome.action == "deleted":
            buckets["deleted"].append(outcome.title)
        elif outcome.action in (
            "skipped",
            "skipped-no-flag",
            "already-absent",
        ):
            buckets["skipped"].append(outcome.title)
    return buckets


def _print_human(
    outcomes: list[ReconcileOutcome],
    backup_confirmed: str | None,
    *,
    dry_run: bool,
    failed: bool,
) -> None:
    header = "PLAN (dry-run)" if dry_run else "RECONCILE"
    if failed:
        header += " (ABORTED mid-run)"
    print(f"--- {header} ---")
    width = max((len(o.title) for o in outcomes), default=0)
    for outcome in outcomes:
        detail = ""
        if outcome.id is not None:
            detail = f"id={outcome.id}"
        elif outcome.filter_id is not None:
            detail = f"filter_id={outcome.filter_id}"
        print(
            f"  {outcome.kind.ljust(7)}  {outcome.title.ljust(width)}  "
            f"{outcome.action.ljust(16)}  {detail}"
        )
    buckets = _summarize(outcomes)
    print("--- summary ---")
    for name in ("created", "verified", "deleted", "skipped"):
        titles = buckets[name]
        print(f"  {name.ljust(9)} ({len(titles)}): {', '.join(titles) or '-'}")
    if backup_confirmed is not None:
        print(f"backup_confirmed: {backup_confirmed}")


def _emit_json(
    outcomes: list[ReconcileOutcome],
    backup_confirmed: str | None,
    *,
    failed: bool,
) -> None:
    print(
        json.dumps(
            {
                "outcomes": [_outcome_to_dict(o) for o in outcomes],
                "summary": _summarize(outcomes),
                "backup_confirmed": backup_confirmed,
                "failed": failed,
            },
            ensure_ascii=False,
        )
    )


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="scripts.vikunja.reconcile_projects",
        description=(
            "Reconcile Vikunja's project structure toward the canonical layout "
            "(#716). Additively creates missing topic projects as kent and "
            "verifies Inbox; --delete-legacy (backup-gated) also removes the "
            "five legacy saved filters. Never deletes any project."
        ),
    )
    parser.add_argument(
        "--token-file",
        default=DEFAULT_KENT_TOKEN_FILE,
        metavar="PATH",
        help=(
            "read the kent-owned API token from this file (default: "
            f"{DEFAULT_KENT_TOKEN_FILE}). Never falls back to the felix-bot "
            "default token."
        ),
    )
    parser.add_argument(
        "--delete-legacy",
        action="store_true",
        help=(
            "also delete the legacy saved filters (Today, Upcoming, Overdue, "
            "Goals, Completed); requires --backup-confirmed"
        ),
    )
    parser.add_argument(
        "--backup-confirmed",
        default=None,
        metavar="REF",
        help=(
            "Restic snapshot id / ISO timestamp asserting a recent backup; "
            "mandatory companion to --delete-legacy (Tier-2 change)"
        ),
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="compute and print the plan without any create/delete",
    )
    parser.add_argument(
        "--json",
        action="store_true",
        help="emit outcomes + summary as JSON on stdout",
    )
    parser.add_argument(
        "--base-url",
        default=None,
        help="override Vikunja base URL (else canonical config)",
    )
    return parser


def _read_token_file(path: str) -> str:
    """Read the kent token from ``path``; abort if missing or blank.

    Reads ONLY this file — never the VikunjaClient felix-bot default. The
    known felix-bot token path is refused outright (pre-mutation guard,
    independent of the create-response owner assertion). A
    missing/unreadable/blank file is a hard error whose message names the
    credential so the operator can provision/refresh ``vikunja-api-kent``.
    """
    if os.path.abspath(path) == os.path.abspath(FELIX_BOT_TOKEN_FILE):
        raise ReconcileError(
            f"refusing to use the felix-bot token file {path!r}: this helper "
            f"makes kent-owned config changes and must use the "
            f"'vikunja-api-kent' credential. A felix-bot run would create "
            f"kent-invisible, felix-bot-owned projects (#715)."
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
    """CLI entrypoint. Returns 0 on full success/dry-run, non-zero otherwise.

    Exit codes (contracts/vikunja-api.md): ``0`` success or dry-run; ``2`` when
    ``--delete-legacy`` lacks a non-blank ``--backup-confirmed`` ref (refused
    before any mutation); ``1`` on any API error / owner-assertion failure /
    inconsistency (a partial run never reports success).
    """
    args = _build_parser().parse_args(argv)

    # Gate the destructive pass on BOTH --delete-legacy AND a non-blank
    # --backup-confirmed — refuse BEFORE any mutation (C-002/NFR-004). A
    # whitespace-only ref is not a meaningful Restic reference.
    backup_ref_clean = (
        args.backup_confirmed.strip() if args.backup_confirmed else ""
    )
    if args.delete_legacy and not backup_ref_clean:
        print(
            "ERROR: --delete-legacy requires --backup-confirmed <ref> "
            "(a Restic snapshot id or ISO timestamp). Refusing to delete.",
            file=sys.stderr,
        )
        return 2

    backup_ref = backup_ref_clean if args.delete_legacy else None

    try:
        active_client = client if client is not None else _build_client(args)
        outcomes, _plan = reconcile(
            active_client,
            delete_legacy=args.delete_legacy,
            backup_confirmed=backup_ref_clean or None,
            dry_run=args.dry_run,
        )
    except (VikunjaError, ReconcileError, ValueError) as exc:
        partial = getattr(exc, "reconcile_outcomes", None)
        if partial:
            if args.json:
                _emit_json(partial, backup_ref, failed=True)
            else:
                _print_human(
                    partial, backup_ref, dry_run=args.dry_run, failed=True
                )
        print(f"ERROR: {type(exc).__name__}: {exc}", file=sys.stderr)
        return 1
    except Exception as exc:  # noqa: BLE001 - CLI boundary: report, exit 1
        partial = getattr(exc, "reconcile_outcomes", None)
        if partial:
            if args.json:
                _emit_json(partial, backup_ref, failed=True)
            else:
                _print_human(
                    partial, backup_ref, dry_run=args.dry_run, failed=True
                )
        print(f"ERROR: {type(exc).__name__}: {exc}", file=sys.stderr)
        return 1

    if args.json:
        _emit_json(outcomes, backup_ref, failed=False)
    else:
        _print_human(outcomes, backup_ref, dry_run=args.dry_run, failed=False)

    return 0


if __name__ == "__main__":  # pragma: no cover - CLI entry
    sys.exit(main())
