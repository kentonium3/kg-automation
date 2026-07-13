#!/usr/bin/env python3
"""Create the canonical Vikunja saved filters as kent (#718).

Deterministic, idempotent helper (Felix Constitution Directive 6): no LLM, no
global state, no caching. It **additively** creates the canonical cross-project
saved filters (the views that replaced the deleted pseudo-view projects), as
kent, matching by title. Re-running is a no-op once the filters exist. It never
deletes a filter (the legacy filters were removed by #716) and never touches a
project or task.

Five of the six designed filters ship here — **Someday is deferred to #725**:
its intended `due_date = null` (is-null) predicate is not expressible in Vikunja
v0.24.6 (both `= null` and `= 0` are rejected; `filter_include_nulls` only
*adds* nulls, it cannot isolate them). The remaining five are created here.

Query language facts, all verified live against office2 Vikunja v0.24.6:
- Field names are **snake_case** (`due_date`, `done`, `priority`) — the frontend
  camelCase (`dueDate`) crashes the parser with a 500.
- Labels are referenced by **numeric id** via ``labels in <id>`` — a title
  (``labels in t:habit``) is rejected (code 4019). Ids are environment-specific,
  so this helper NEVER hardcodes them: it resolves each required label title to
  its live id at runtime and fails loud if one is missing.
- ``&&`` is a true conjunction on labels: ``labels in A && labels in B`` matches
  tasks carrying BOTH labels (verified: ``labels in 26 && labels in 26`` returned
  exactly the Habits count).

Ownership follows the #715 two-token model. Saved filters are per-user; a
felix-bot run would create kent-invisible, felix-bot-owned filters. The token is
read ONLY from an explicit ``--token-file`` that defaults to the kent secret —
never the ``VikunjaClient`` felix-bot default — and the known felix-bot path is
refused outright (there is no whoami endpoint for API tokens, so the create
response owner cannot be asserted; the token-file guard is the ownership
guarantee). A pre-existing filter whose stored query disagrees with the
canonical query is a fail-loud error — this helper never clobbers a manual edit.

The **live run is operator-invoked** — this module ships the code + tests + the
design-doc edit only. Run it on office2 as::

    python3 -m scripts.vikunja.create_saved_filters --dry-run
    python3 -m scripts.vikunja.create_saved_filters --apply

Setting the dashboard "home" default to the Today filter is NOT done here: it is
a Vikunja user setting that requires web-JWT auth (the API token returns
"invalid token" for ``/user/settings/*``). That step is a manual web-UI action
by Kent — see the design doc / #718.

Wraps the deterministic ``scripts.common.vikunja_client.VikunjaClient`` — the
canonical stdlib HTTP boundary. No new HTTP path, no ``requests`` dependency.
"""
from __future__ import annotations

import argparse
import json
import os
import re
import sys
from dataclasses import dataclass, field
from typing import Any

from scripts.common.vikunja_client import VikunjaError

__all__ = [
    "DEFAULT_KENT_TOKEN_FILE",
    "FELIX_BOT_TOKEN_FILE",
    "KENT_USERNAME",
    "FilterSpec",
    "FILTER_SPECS",
    "list_projects",
    "build_label_map",
    "resolve_query",
    "build_plan",
    "create_filters",
    "main",
]

# The kent-owned, all-perms token (#715 two-token model). Read ONLY this file;
# never fall back to VikunjaClient's felix-bot default token path.
DEFAULT_KENT_TOKEN_FILE = "/data/services/openclaw/secrets/vikunja-api-kent"

# The felix-bot task-CRUD token path. Explicitly refused as a token source: a
# felix-bot run would create kent-invisible, felix-bot-owned filters (#715).
FELIX_BOT_TOKEN_FILE = "/data/services/openclaw/secrets/vikunja-api"

KENT_USERNAME = "kent"

# Vikunja caps ``per_page`` at 50 on this instance; a ``len < 100`` stop
# condition would be wrong.
_PAGE_SIZE = 50

# A label reference inside a query template: ``{label:<title>}``. Substituted
# with the label's live numeric id at resolve time.
_LABEL_TOKEN = re.compile(r"\{label:([^}]+)\}")


class SavedFilterError(Exception):
    """Fail-loud error (missing label, ownership, drift, API inconsistency).

    Raised for any condition where continuing could create a wrong/duplicate
    filter or clobber a manual edit. Surfaced by :func:`main` as a non-zero
    exit — never swallowed.
    """


@dataclass(frozen=True)
class FilterSpec:
    """One canonical saved filter. Pure declared data.

    ``query_template`` uses ``{label:<title>}`` placeholders for label refs;
    everything else (date/priority/done clauses) is literal snake_case query
    syntax. ``required_labels`` is the set of label titles the template
    references — resolved to live ids at build time; a missing one aborts.
    """

    title: str
    description: str
    query_template: str
    required_labels: tuple[str, ...] = ()


# Single in-code source of truth for the canonical filters (#718). Label refs
# are by TITLE via ``{label:...}`` — ids are resolved live, never hardcoded.
# NOTE: "Someday" (label q:schedule + no due date) is intentionally ABSENT —
# is-null date filtering is unsupported in v0.24.6; deferred to #725.
FILTER_SPECS: tuple[FilterSpec, ...] = (
    FilterSpec(
        title="Today",
        description="Primary daily driver — tasks due today or overdue, not done.",
        # `< now/d+1d` = everything due before the start of tomorrow = overdue +
        # all of today. `<= now/d` would silently drop a task due LATER today
        # (its due_date is > start-of-today), so it is wrong for a daily driver.
        # filter_include_nulls=False keeps no-due-date tasks out.
        query_template="due_date < now/d+1d && done = false",
    ),
    FilterSpec(
        title="Habits",
        description="All habit tasks (t:habit), not done. Felix's daily prompt source.",
        query_template="labels in {label:t:habit} && done = false",
        required_labels=("t:habit",),
    ),
    FilterSpec(
        title="Upcoming",
        description="Tasks due within the next 7 days, not done.",
        query_template="due_date > now/d && due_date < now+7d && done = false",
    ),
    FilterSpec(
        title="High Priority",
        description="Urgent items by native priority (>= 4), not done.",
        query_template="priority >= 4 && done = false",
    ),
    FilterSpec(
        title="Edge + Schedule",
        description=(
            "Highest-value, high-resistance work: f:3-edge AND q:schedule, not done."
        ),
        query_template=(
            "labels in {label:f:3-edge} && labels in {label:q:schedule} "
            "&& done = false"
        ),
        required_labels=("f:3-edge", "q:schedule"),
    ),
)

# The canonical titles this helper owns — used to decide when an unresolved-owner
# saved filter must fail loud (vs be ignored as none of our business).
CANONICAL_TITLES: frozenset[str] = frozenset(spec.title for spec in FILTER_SPECS)


@dataclass(frozen=True)
class FilterOutcome:
    """One emitted per canonical filter acted on or examined.

    ``action`` is one of: ``created`` | ``already-present`` (verified match) |
    ``skipped`` (not reached due to a mid-run abort). ``task_count`` is the
    best-effort post-create result-set size (``None`` when not measured).
    """

    title: str
    action: str
    filter_id: int | None = None
    query: str | None = None
    task_count: int | None = None


@dataclass
class FilterPlan:
    """What the run would do — computed without mutating.

    ``to_create`` holds ``(spec, resolved_query)`` for filters that do not yet
    exist. ``present`` maps an existing filter's title to its ``filter_id``.
    """

    to_create: list[tuple[FilterSpec, str]] = field(default_factory=list)
    present: dict[str, int] = field(default_factory=dict)


# ---------------------------------------------------------------------------
# Read helpers
# ---------------------------------------------------------------------------


def _paginate(client: Any, path: str) -> list[dict]:
    """Return every element from a paginated list endpoint.

    Pages ``per_page=50`` from page 1, accumulating until a page returns fewer
    than 50 items (or empty). A ``null`` body (Vikunja's empty-collection
    quirk) is normalised to ``[]`` and stops paging. Any non-list, non-null 200
    body is a contract violation → surfaced.
    """
    items: list[dict] = []
    page = 1
    while True:
        batch = client.get(
            path, params={"per_page": str(_PAGE_SIZE), "page": str(page)}
        )
        if batch is None:
            break
        if not isinstance(batch, list):
            raise VikunjaError(path=path, status=200)
        for element in batch:
            if isinstance(element, dict):
                items.append(element)
        if len(batch) < _PAGE_SIZE:
            break
        page += 1
    return items


def list_projects(client: Any) -> list[dict]:
    """Every project element from a paginated ``GET /projects``.

    Includes both real (positive id) and pseudo-project (negative id) elements;
    the negative ids are saved filters and drive existence/derivation.
    """
    return _paginate(client, "/projects")


def build_label_map(client: Any) -> dict[str, int]:
    """Map label ``title -> id`` from a paginated ``GET /labels``.

    A title with a non-integer id, or a duplicate title with conflicting ids,
    is a fail-loud error — the whole point is unambiguous id resolution.
    """
    label_map: dict[str, int] = {}
    for label in _paginate(client, "/labels"):
        title = label.get("title")
        lid = label.get("id")
        if not isinstance(title, str) or not isinstance(lid, int):
            continue
        if title in label_map and label_map[title] != lid:
            raise SavedFilterError(
                f"Ambiguous label title {title!r}: ids {label_map[title]} and "
                f"{lid} both present. Refusing to resolve a filter query."
            )
        label_map[title] = lid
    return label_map


def _owner_username(element: dict) -> str | None:
    owner = element.get("owner")
    if isinstance(owner, dict):
        username = owner.get("username")
        if isinstance(username, str):
            return username
    return None


def _project_id(element: dict) -> int | None:
    pid = element.get("id")
    return pid if isinstance(pid, int) else None


# ---------------------------------------------------------------------------
# Query resolution + normalisation
# ---------------------------------------------------------------------------


def resolve_query(template: str, label_map: dict[str, int]) -> str:
    """Substitute ``{label:<title>}`` refs with live ids; fail loud if missing.

    Every placeholder must resolve to a known label id. A referenced label that
    is absent from ``label_map`` aborts (a query that silently drops a clause,
    or one left with an unresolved token, would produce a wrong result set —
    the exact "silently returns nothing" failure #718 warns about).
    """

    def _sub(match: re.Match[str]) -> str:
        title = match.group(1)
        if title not in label_map:
            raise SavedFilterError(
                f"Label {title!r} referenced by a canonical filter does not "
                f"exist in Vikunja. Run the label taxonomy helper (#715) first."
            )
        return str(label_map[title])

    resolved = _LABEL_TOKEN.sub(_sub, template)
    if "{label:" in resolved:  # pragma: no cover - regex covers all tokens
        raise SavedFilterError(
            f"Unresolved label placeholder remains in query: {resolved!r}"
        )
    return resolved


def _normalise_query(query: str) -> str:
    """Collapse whitespace so a re-serialised stored query compares equal.

    Vikunja may re-serialise a saved filter's query with different spacing; a
    naive string compare would then read as spurious drift. Comparing on
    whitespace-collapsed forms makes idempotent re-runs stable without masking
    a genuine semantic difference (operators/values are preserved).
    """
    return " ".join(query.split())


# ---------------------------------------------------------------------------
# Plan (match existing + resolve queries) — no mutation
# ---------------------------------------------------------------------------


def _existing_saved_filters(projects: list[dict]) -> dict[str, int]:
    """Map ``title -> filter_id`` for kent-owned saved filters.

    Saved filters surface as negative-id pseudo-projects with ``id <= -2``
    (never ``-1`` / native ``Favorites``); ``filter_id = -id - 1``. Filters are
    per-user, so every such element returned to the kent token is kent's own —
    the owner field is present in practice (``owner.username == "kent"``).

    Ownership is handled without silently dropping a canonical-titled filter
    whose owner is missing/unknown: a **canonical** title on a negative-id
    pseudo-project with an unresolved owner is fail-loud (we cannot tell if it
    is the filter we would otherwise duplicate). A known non-kent owner is
    skipped; a non-canonical unknown-owner filter is ignored (not our concern).
    A duplicate canonical title is fail-loud (ambiguous existence).
    """
    existing: dict[str, int] = {}
    for project in projects:
        pseudo_id = _project_id(project)
        if pseudo_id is None or pseudo_id > -2:
            continue
        title = project.get("title")
        if not isinstance(title, str):
            continue
        owner = _owner_username(project)
        if owner is None:
            # Unresolved owner: only a canonical title matters — refuse to skip
            # it silently (that would risk creating a duplicate). Non-canonical
            # unknown-owner filters are irrelevant to this helper.
            if title in CANONICAL_TITLES:
                raise SavedFilterError(
                    f"Saved filter {title!r} (pseudo id {pseudo_id}) has an "
                    f"unresolved owner in GET /projects; cannot confirm it is "
                    f"kent's. Refusing to proceed (a silent skip could create a "
                    f"duplicate). Resolve manually."
                )
            continue
        if owner != KENT_USERNAME:
            continue
        filter_id = -pseudo_id - 1
        if title in existing and existing[title] != filter_id:
            raise SavedFilterError(
                f"Ambiguous existing saved filter {title!r}: filter ids "
                f"{existing[title]} and {filter_id} both present. Resolve "
                f"manually before reconciling."
            )
        existing[title] = filter_id
    return existing


def build_plan(
    client: Any, projects: list[dict], label_map: dict[str, int]
) -> FilterPlan:
    """Compute the create plan. Never mutates.

    For each canonical spec: resolve its query (label ids substituted). If a
    kent-owned saved filter with that title already exists, read back its stored
    query and require it to match the canonical query (fail loud on drift —
    never clobber). Otherwise queue it for creation.
    """
    plan = FilterPlan()
    existing = _existing_saved_filters(projects)

    for spec in FILTER_SPECS:
        resolved = resolve_query(spec.query_template, label_map)
        if spec.title in existing:
            filter_id = existing[spec.title]
            _assert_query_matches(client, spec.title, filter_id, resolved)
            plan.present[spec.title] = filter_id
        else:
            plan.to_create.append((spec, resolved))
    return plan


def _assert_query_matches(
    client: Any, title: str, filter_id: int, canonical_query: str
) -> None:
    """Read back an existing filter and require its query to be canonical.

    ``GET /filters/{id}`` returns the stored ``filters.filter`` string. A
    whitespace-normalised mismatch is a fail-loud error: the helper reconciles
    toward the canonical set but must never silently overwrite a filter a human
    deliberately edited. The operator deletes it and re-runs, or fixes it.
    """
    readback = client.get(f"/filters/{filter_id}")
    if not isinstance(readback, dict):
        raise SavedFilterError(
            f"Readback of existing filter {title!r} (id {filter_id}) returned a "
            f"non-object response; refusing to proceed."
        )
    stored = readback.get("filters")
    stored_query = stored.get("filter") if isinstance(stored, dict) else None
    if not isinstance(stored_query, str):
        raise SavedFilterError(
            f"Existing filter {title!r} (id {filter_id}) has no readable query; "
            f"refusing to proceed."
        )
    if _normalise_query(stored_query) != _normalise_query(canonical_query):
        raise SavedFilterError(
            f"Filter {title!r} (id {filter_id}) exists with query "
            f"{stored_query!r} but the canonical query is {canonical_query!r}. "
            f"Refusing to clobber a manual edit — delete it and re-run, or "
            f"reconcile manually."
        )


# ---------------------------------------------------------------------------
# Execute
# ---------------------------------------------------------------------------


def create_filters(
    client: Any,
    *,
    dry_run: bool = False,
) -> tuple[list[FilterOutcome], FilterPlan]:
    """Read live state, build the plan, create missing filters.

    Returns ``(outcomes, plan)``. In ``dry_run`` no filter is created and no
    verification query runs. Any :class:`VikunjaError`, :class:`SavedFilterError`,
    or unexpected exception propagates (mapped to a non-zero exit by
    :func:`main`); outcomes accumulated before the failure — plus the
    ``skipped`` remainder — are attached to the error for the summary.
    """
    outcomes: list[FilterOutcome] = []
    try:
        projects = list_projects(client)
        label_map = build_label_map(client)
        plan = build_plan(client, projects, label_map)

        for title, filter_id in plan.present.items():
            outcomes.append(
                FilterOutcome(title, "already-present", filter_id=filter_id)
            )

        _create_pass(client, plan, outcomes, dry_run=dry_run)
    except Exception as exc:  # noqa: BLE001 - attach partial progress, re-raise
        exc.filter_outcomes = list(outcomes)  # type: ignore[attr-defined]
        raise

    return outcomes, plan


def _create_pass(
    client: Any,
    plan: FilterPlan,
    outcomes: list[FilterOutcome],
    *,
    dry_run: bool,
) -> None:
    """Create each queued filter via ``PUT /filters``; verify counts best-effort.

    On any error the already-created filters are reported and the remaining
    ones marked ``skipped`` so the summary shows completed vs skipped. In
    ``dry_run`` each is reported ``created`` with no id and no HTTP call.
    """
    to_create = list(plan.to_create)

    def _remaining_skipped(from_index: int) -> None:
        for spec, query in to_create[from_index:]:
            outcomes.append(FilterOutcome(spec.title, "skipped", query=query))

    for index, (spec, query) in enumerate(to_create):
        if dry_run:
            outcomes.append(FilterOutcome(spec.title, "created", query=query))
            continue

        body = {
            "title": spec.title,
            "description": spec.description,
            "filters": {"filter": query, "filter_include_nulls": False},
        }
        try:
            response = client.put("/filters", json=body)
        except Exception:
            _remaining_skipped(index)
            raise
        if not isinstance(response, dict):
            _remaining_skipped(index)
            raise SavedFilterError(
                f"Create of filter {spec.title!r} returned a non-object "
                f"response; refusing to proceed."
            )
        filter_id = _project_id(response)
        if filter_id is None:
            # A create with no integer id is an API contract break: we cannot
            # verify the result set or derive its pseudo-project. Fail loud
            # rather than report a hollow success (post-review MEDIUM).
            _remaining_skipped(index)
            raise SavedFilterError(
                f"Create of filter {spec.title!r} returned no integer id "
                f"({response.get('id')!r}); cannot verify. Aborting fail-loud."
            )
        count = _verify_count(client, filter_id)
        outcomes.append(
            FilterOutcome(
                spec.title,
                "created",
                filter_id=filter_id,
                query=query,
                task_count=count,
            )
        )


def _verify_count(client: Any, filter_id: int | None) -> int | None:
    """Best-effort result-set size for a just-created filter.

    A saved filter with id ``N`` is queryable as pseudo-project ``-N - 1``. A
    count of ``0`` is a legitimate result (e.g. no task carries f:3-edge yet),
    NOT a failure — it is printed so the operator can distinguish genuine-empty
    from broken. Any error here is swallowed (returns ``None``): verification
    must never fail a successful create.
    """
    if filter_id is None:
        return None
    pseudo_id = -filter_id - 1
    try:
        tasks = client.get(
            f"/projects/{pseudo_id}/tasks", params={"per_page": str(_PAGE_SIZE)}
        )
    except Exception:  # noqa: BLE001 - verification is best-effort
        return None
    if tasks is None:
        return 0
    if isinstance(tasks, list):
        return len(tasks)
    return None


# ---------------------------------------------------------------------------
# Summary rendering
# ---------------------------------------------------------------------------


def _outcome_to_dict(outcome: FilterOutcome) -> dict[str, Any]:
    record: dict[str, Any] = {"title": outcome.title, "action": outcome.action}
    if outcome.filter_id is not None:
        record["filter_id"] = outcome.filter_id
    if outcome.query is not None:
        record["query"] = outcome.query
    if outcome.task_count is not None:
        record["task_count"] = outcome.task_count
    return record


def _summarize(outcomes: list[FilterOutcome]) -> dict[str, list[str]]:
    buckets: dict[str, list[str]] = {"created": [], "verified": [], "skipped": []}
    for outcome in outcomes:
        if outcome.action == "created":
            buckets["created"].append(outcome.title)
        elif outcome.action == "already-present":
            buckets["verified"].append(outcome.title)
        elif outcome.action == "skipped":
            buckets["skipped"].append(outcome.title)
    return buckets


def _print_human(
    outcomes: list[FilterOutcome], *, dry_run: bool, failed: bool
) -> None:
    header = "PLAN (dry-run)" if dry_run else "CREATE SAVED FILTERS"
    if failed:
        header += " (ABORTED mid-run)"
    print(f"--- {header} ---")
    width = max((len(o.title) for o in outcomes), default=0)
    for outcome in outcomes:
        detail = []
        if outcome.filter_id is not None:
            detail.append(f"filter_id={outcome.filter_id}")
        if outcome.task_count is not None:
            detail.append(f"tasks={outcome.task_count}")
        if outcome.query is not None:
            detail.append(f"query={outcome.query!r}")
        print(
            f"  {outcome.title.ljust(width)}  {outcome.action.ljust(16)}  "
            f"{'  '.join(detail)}"
        )
    buckets = _summarize(outcomes)
    print("--- summary ---")
    for name in ("created", "verified", "skipped"):
        titles = buckets[name]
        print(f"  {name.ljust(9)} ({len(titles)}): {', '.join(titles) or '-'}")
    print(
        "note: a task count of 0 is legitimate (e.g. no task carries "
        "f:3-edge/q:schedule yet); it is not a failure."
    )


def _emit_json(outcomes: list[FilterOutcome], *, failed: bool) -> None:
    print(
        json.dumps(
            {
                "outcomes": [_outcome_to_dict(o) for o in outcomes],
                "summary": _summarize(outcomes),
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
        prog="scripts.vikunja.create_saved_filters",
        description=(
            "Create the five canonical Vikunja saved filters as kent (#718): "
            "Today, Habits, Upcoming, High Priority, Edge + Schedule. Idempotent "
            "(matches by title). Someday is deferred to #725 (is-null date "
            "filtering unsupported in v0.24.6). Dashboard default is a manual "
            "web-UI step. Defaults to --dry-run; pass --apply to mutate."
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
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument(
        "--dry-run",
        action="store_true",
        help="compute and print the plan without creating anything (default)",
    )
    mode.add_argument(
        "--apply",
        action="store_true",
        help="actually create the missing saved filters",
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
    """Read the kent token from ``path``; abort if missing, blank, or felix-bot.

    Reads ONLY this file — never the VikunjaClient felix-bot default. The known
    felix-bot token path is refused outright (pre-mutation guard). A
    missing/unreadable/blank file is a hard error naming the credential so the
    operator can provision/refresh ``vikunja-api-kent``.
    """
    # Compare on realpath (not abspath) so a symlink pointing at the felix-bot
    # token cannot slip past the guard (post-review HIGH). realpath resolves
    # symlinks and ``..`` on both sides.
    if os.path.realpath(path) == os.path.realpath(FELIX_BOT_TOKEN_FILE):
        raise SavedFilterError(
            f"refusing to use the felix-bot token file {path!r}: saved filters "
            f"are per-user and must be created with the kent-owned "
            f"'vikunja-api-kent' credential (a felix-bot run would create "
            f"kent-invisible filters, #715)."
        )
    try:
        with open(path, encoding="utf-8") as handle:
            token = handle.read()
    except OSError as exc:
        raise SavedFilterError(
            f"kent token file {path!r} could not be read: {exc}. This helper "
            f"requires the kent-owned 'vikunja-api-kent' credential and never "
            f"falls back to the felix-bot token."
        ) from exc
    if not token.strip():
        raise SavedFilterError(
            f"kent token file {path!r} is empty. Provision the kent-owned "
            f"'vikunja-api-kent' credential before running."
        )
    return token


def _build_client(args: argparse.Namespace) -> Any:
    from scripts.common.vikunja_client import VikunjaClient

    token = _read_token_file(args.token_file)
    return VikunjaClient(base_url=args.base_url, token=token)


def main(argv: list[str] | None = None, *, client: Any | None = None) -> int:
    """CLI entrypoint. Returns 0 on success/dry-run, 1 on any failure.

    Defaults to dry-run: mutation happens only with ``--apply``. Exit ``1`` on
    any API error / missing-label / drift / inconsistency (a partial run never
    reports success).
    """
    args = _build_parser().parse_args(argv)
    dry_run = not args.apply

    try:
        active_client = client if client is not None else _build_client(args)
        outcomes, _plan = create_filters(active_client, dry_run=dry_run)
    except (VikunjaError, SavedFilterError, ValueError) as exc:
        _report_failure(exc, args, dry_run=dry_run)
        return 1
    except Exception as exc:  # noqa: BLE001 - CLI boundary: report, exit 1
        _report_failure(exc, args, dry_run=dry_run)
        return 1

    if args.json:
        _emit_json(outcomes, failed=False)
    else:
        _print_human(outcomes, dry_run=dry_run, failed=False)
    return 0


def _report_failure(
    exc: Exception, args: argparse.Namespace, *, dry_run: bool
) -> None:
    partial = getattr(exc, "filter_outcomes", None)
    if partial:
        if args.json:
            _emit_json(partial, failed=True)
        else:
            _print_human(partial, dry_run=dry_run, failed=True)
    print(f"ERROR: {type(exc).__name__}: {exc}", file=sys.stderr)


if __name__ == "__main__":  # pragma: no cover - CLI entry
    sys.exit(main())
