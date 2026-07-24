#!/usr/bin/env python3
"""Deterministic verification helper for the attended Tier-2 token cutover (FR-007).

Phase 2 of the ``vikunja-token-seam-kent-cutover-01KY8XQ0`` mission flips the
Felix runtime's Vikunja identity from ``felix-bot`` to ``kent`` by changing a
single credential file on office2 (the seam — see
:mod:`scripts.common.vikunja_config`). The cutover itself (merge → office2 pull
→ verify) is an *operator* action; this module is the deterministic, testable
tool the operator runs BEFORE the flip (still felix-bot on office2) and AFTER
the flip (kent), so the go/no-go decision is a repeatable command rather than
ad-hoc SSH (Constitution Directive 6).

**Strictly read-only.** This helper only issues ``GET`` requests through
:class:`~scripts.common.vikunja_client.VikunjaClient`; it never writes to
Vikunja. There is no ``--dry-run`` because there is nothing to mutate.

Token resolution
----------------
The credential is resolved through the mission's single seam,
:func:`scripts.common.vikunja_config.get_vikunja_token_path` — never a
hardcoded path. That is the whole point: "BEFORE (felix-bot)" vs
"AFTER (kent)" is just the office2 token-file state (or a ``VIKUNJA_TOKEN_PATH``
override), so the *same* command reports each identity's view without a code
change.

Capabilities (run individually via flags, or all three by default)
------------------------------------------------------------------
``--inverse-probe``
    List the projects visible to the resolved token and assert the expected
    topic projects (``16,17,18,19,20``) **and** ``Inbox`` (``1``) + ``Habits``
    (``13``) are present. Fails loud (non-zero exit) if any expected project is
    missing — the #860 visibility gap the cutover closes. Parameterize the id
    set with ``--expect-projects``.

``--connectivity``
    A lightweight read per Felix→Vikunja consumer surface (projects list, a task
    page, labels) confirming the resolved token authenticates and reads. This is
    the before/after connectivity check; a client error on any surface maps to a
    non-zero result.

``--task-delta``
    Count the tasks the resolved token sees across the newly-visible projects
    (``16–20`` by default; parameterize with ``--delta-projects``) so the
    operator can size the first-observation burst that the ~5-min poll sync will
    process post-cutover.

Output contract
---------------
``--json`` emits a single JSON object on stdout (the summary the operator
captures BEFORE and AFTER). Without ``--json`` a human-readable report plus a
final ``SUMMARY:`` line (helper-script convention §3) is printed. Errors go to
stderr prefixed ``ERROR:``.

Exit codes
----------
``0`` all requested checks passed; ``1`` a verification failure (missing
expected project, a connectivity surface unreadable, or any API error) or the
token could not be resolved; ``2`` a usage error (bad ``--expect-projects`` /
``--delta-projects`` value).

Usage (operator, on office2, post-merge)::

    python3 -m scripts.vikunja.cutover_verify --json          # all checks
    python3 -m scripts.vikunja.cutover_verify --inverse-probe # one check
"""
from __future__ import annotations

import argparse
import json
import sys
from dataclasses import dataclass
from typing import Any

from scripts.common.vikunja_client import VikunjaError
from scripts.common.vikunja_config import get_vikunja_token_path

__all__ = [
    "DEFAULT_EXPECT_PROJECTS",
    "DEFAULT_DELTA_PROJECTS",
    "InverseProbeResult",
    "SurfaceRead",
    "ConnectivityResult",
    "TaskDeltaResult",
    "list_project_ids",
    "inverse_probe",
    "connectivity_check",
    "task_delta",
    "count_project_tasks",
    "main",
]

# Vikunja caps ``per_page`` at 50 on this instance; a larger stop threshold
# would page incorrectly. Mirrors scripts/vikunja/reconcile_projects.py.
_PAGE_SIZE = 50

# Runaway-loop guard for per-collection pagination.
_MAX_PAGES = 200

#: Expected-visible project ids the cutover must prove kent can see: the five
#: newly-visible topic projects (16–20) PLUS Inbox (1) and Habits (13), the two
#: pre-existing runtime-critical projects. A missing id here is the #860 gap.
DEFAULT_EXPECT_PROJECTS: tuple[int, ...] = (1, 13, 16, 17, 18, 19, 20)

#: The newly-visible projects whose first-observation task burst the operator
#: sizes with ``--task-delta``.
DEFAULT_DELTA_PROJECTS: tuple[int, ...] = (16, 17, 18, 19, 20)


# ---------------------------------------------------------------------------
# Result types
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class InverseProbeResult:
    """Outcome of ``--inverse-probe``: which expected projects are visible."""

    expected: list[int]
    visible: list[int]
    present: list[int]
    missing: list[int]
    ok: bool

    def to_dict(self) -> dict[str, Any]:
        return {
            "expected": self.expected,
            "visible": self.visible,
            "present": self.present,
            "missing": self.missing,
            "ok": self.ok,
        }


@dataclass(frozen=True)
class SurfaceRead:
    """One connectivity surface read (projects / tasks / labels)."""

    surface: str
    ok: bool
    error: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {"surface": self.surface, "ok": self.ok, "error": self.error}


@dataclass(frozen=True)
class ConnectivityResult:
    """Outcome of ``--connectivity``: per-surface reads + overall ok."""

    surfaces: list[SurfaceRead]
    ok: bool

    def to_dict(self) -> dict[str, Any]:
        return {
            "surfaces": [s.to_dict() for s in self.surfaces],
            "ok": self.ok,
        }


@dataclass(frozen=True)
class TaskDeltaResult:
    """Outcome of ``--task-delta``: task counts across the target projects."""

    projects: list[int]
    per_project: dict[int, int]
    total: int

    def to_dict(self) -> dict[str, Any]:
        # JSON object keys must be strings.
        return {
            "projects": self.projects,
            "per_project": {str(k): v for k, v in self.per_project.items()},
            "total": self.total,
        }


# ---------------------------------------------------------------------------
# Read primitives (all GET; strictly read-only)
# ---------------------------------------------------------------------------


def list_project_ids(client: Any) -> list[int]:
    """Return the sorted, de-duplicated int ids of every visible project.

    Pages ``GET /projects`` (``per_page=50``) until a short/empty page. Vikunja
    returns JSON ``null`` for an exhausted/empty collection — treated as a stop,
    never an error. Non-list, non-null 200 bodies are a contract violation and
    surface as :class:`VikunjaError`. Negative pseudo-project ids (saved-filter
    / Favorites shims) are excluded; only real projects (id > 0) are returned.
    """
    ids: set[int] = set()
    for page in range(1, _MAX_PAGES + 1):
        batch = client.get(
            "/projects",
            params={"per_page": str(_PAGE_SIZE), "page": str(page)},
        )
        if batch is None:
            break
        if not isinstance(batch, list):
            raise VikunjaError(path="/projects", status=200)
        for element in batch:
            if not isinstance(element, dict):
                continue
            pid = element.get("id")
            if isinstance(pid, int) and not isinstance(pid, bool) and pid > 0:
                ids.add(pid)
        if len(batch) < _PAGE_SIZE:
            break
    else:
        raise VikunjaError(path="/projects", status=None)
    return sorted(ids)


def count_project_tasks(client: Any, project_id: int) -> int:
    """Count tasks in one project via paged ``GET /projects/{id}/tasks``.

    Done-inclusive (no ``filter`` sent), matching the sync driver's view. Stops
    on a short/empty/``null`` page; a non-list 200 body surfaces as
    :class:`VikunjaError`; the page loop is bounded by ``_MAX_PAGES``.
    """
    path = f"/projects/{project_id}/tasks"
    total = 0
    for page in range(1, _MAX_PAGES + 1):
        batch = client.get(
            path, params={"per_page": str(_PAGE_SIZE), "page": str(page)}
        )
        if batch is None:
            break
        if not isinstance(batch, list):
            raise VikunjaError(path=path, status=200)
        total += len(batch)
        if len(batch) < _PAGE_SIZE:
            break
    else:
        raise VikunjaError(path=path, status=None)
    return total


# ---------------------------------------------------------------------------
# Capabilities
# ---------------------------------------------------------------------------


def inverse_probe(client: Any, expect_projects: list[int]) -> InverseProbeResult:
    """Assert every expected project id is visible to the resolved token.

    "Inverse" because it verifies the credential can *see* the projects the
    cutover makes visible, rather than probing the credential's write scope.
    ``ok`` is ``False`` (fail loud) when any expected id is missing.
    """
    visible = list_project_ids(client)
    visible_set = set(visible)
    expected_sorted = sorted(set(expect_projects))
    present = [pid for pid in expected_sorted if pid in visible_set]
    missing = [pid for pid in expected_sorted if pid not in visible_set]
    return InverseProbeResult(
        expected=expected_sorted,
        visible=visible,
        present=present,
        missing=missing,
        ok=not missing,
    )


def connectivity_check(client: Any) -> ConnectivityResult:
    """Read each Felix→Vikunja consumer surface once; map errors to ``ok=False``.

    Surfaces: the projects list, a single task page (from the first visible
    project), and the labels list. Any :class:`VikunjaError` on a surface is
    captured as that surface's ``error`` and drops overall ``ok`` — the
    before/after "does this credential authenticate and read" gate.
    """
    surfaces: list[SurfaceRead] = []

    # Projects surface — also yields a project id for the task-page read.
    project_ids: list[int] = []
    try:
        batch = client.get(
            "/projects", params={"per_page": str(_PAGE_SIZE), "page": "1"}
        )
        if batch is None:
            batch = []
        if not isinstance(batch, list):
            raise VikunjaError(path="/projects", status=200)
        project_ids = [
            element["id"]
            for element in batch
            if isinstance(element, dict)
            and isinstance(element.get("id"), int)
            and not isinstance(element.get("id"), bool)
            and element["id"] > 0
        ]
        surfaces.append(SurfaceRead("projects", True))
    except VikunjaError as exc:
        surfaces.append(SurfaceRead("projects", False, _format_error(exc)))

    # Task-page surface — a lightweight read of one project's tasks.
    if project_ids:
        pid = project_ids[0]
        path = f"/projects/{pid}/tasks"
        try:
            client.get(path, params={"per_page": "1", "page": "1"})
            surfaces.append(SurfaceRead("tasks", True))
        except VikunjaError as exc:
            surfaces.append(SurfaceRead("tasks", False, _format_error(exc)))
    else:
        surfaces.append(
            SurfaceRead(
                "tasks", False, "no project visible to read a task page"
            )
        )

    # Labels surface.
    try:
        client.get("/labels", params={"per_page": "1", "page": "1"})
        surfaces.append(SurfaceRead("labels", True))
    except VikunjaError as exc:
        surfaces.append(SurfaceRead("labels", False, _format_error(exc)))

    return ConnectivityResult(surfaces=surfaces, ok=all(s.ok for s in surfaces))


def task_delta(client: Any, delta_projects: list[int]) -> TaskDeltaResult:
    """Count tasks across each target project so the operator sizes the burst."""
    project_ids = sorted(set(delta_projects))
    per_project: dict[int, int] = {}
    for pid in project_ids:
        per_project[pid] = count_project_tasks(client, pid)
    return TaskDeltaResult(
        projects=project_ids,
        per_project=per_project,
        total=sum(per_project.values()),
    )


def _format_error(exc: VikunjaError) -> str:
    return f"{type(exc).__name__}: {exc}"


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


def _parse_id_set(raw: str, *, flag: str) -> list[int]:
    """Parse a comma-separated int id set; raise ``ValueError`` on bad input."""
    ids: list[int] = []
    for chunk in raw.split(","):
        token = chunk.strip()
        if not token:
            continue
        try:
            ids.append(int(token))
        except ValueError as exc:
            raise ValueError(
                f"{flag}: {token!r} is not an integer project id"
            ) from exc
    if not ids:
        raise ValueError(f"{flag}: no project ids provided")
    return sorted(set(ids))


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="scripts.vikunja.cutover_verify",
        description=(
            "Deterministic, read-only verification for the attended Tier-2 "
            "Vikunja token cutover (FR-007). Resolves the credential through "
            "the token seam (get_vikunja_token_path) and reports the resolved "
            "identity's view. Run BEFORE (felix-bot) and AFTER (kent) the flip."
        ),
    )
    parser.add_argument(
        "--inverse-probe",
        action="store_true",
        help=(
            "assert the expected projects (Inbox 1, Habits 13, topics 16-20) "
            "are visible to the resolved token; fail loud if any is missing"
        ),
    )
    parser.add_argument(
        "--connectivity",
        action="store_true",
        help="read each consumer surface (projects, a task page, labels) once",
    )
    parser.add_argument(
        "--task-delta",
        action="store_true",
        help="count tasks across the newly-visible projects (16-20 default)",
    )
    parser.add_argument(
        "--expect-projects",
        default=None,
        metavar="IDS",
        help=(
            "comma-separated project ids --inverse-probe requires "
            f"(default: {','.join(str(i) for i in DEFAULT_EXPECT_PROJECTS)})"
        ),
    )
    parser.add_argument(
        "--delta-projects",
        default=None,
        metavar="IDS",
        help=(
            "comma-separated project ids --task-delta counts "
            f"(default: {','.join(str(i) for i in DEFAULT_DELTA_PROJECTS)})"
        ),
    )
    parser.add_argument(
        "--json",
        action="store_true",
        help="emit the summary as a single JSON object on stdout",
    )
    parser.add_argument(
        "--base-url",
        default=None,
        help="override the Vikunja base URL (else the canonical config)",
    )
    return parser


def _build_client(base_url: str | None) -> tuple[Any, str]:
    """Construct a VikunjaClient whose token is resolved via the seam.

    Returns the client and the string form of the resolved token path (for the
    summary). The token path comes from
    :func:`scripts.common.vikunja_config.get_vikunja_token_path` — the single
    resolution point — so BEFORE/AFTER is just the office2 file state or a
    ``VIKUNJA_TOKEN_PATH`` override, never a code change.
    """
    from scripts.common.vikunja_client import VikunjaClient

    token_path = get_vikunja_token_path()
    token = token_path.read_text(encoding="utf-8")
    client = VikunjaClient(base_url=base_url, token=token)
    return client, str(token_path)


def _emit_json(summary: dict[str, Any]) -> None:
    print(json.dumps(summary, ensure_ascii=False))


def _emit_human(summary: dict[str, Any]) -> None:
    token_path = summary.get("token_path")
    print(f"INFO: token_path={token_path}")

    inv = summary.get("inverse_probe")
    if inv is not None:
        state = "OK" if inv["ok"] else "FAIL"
        print(
            f"INFO: inverse-probe [{state}] "
            f"present={inv['present']} missing={inv['missing']}"
        )

    conn = summary.get("connectivity")
    if conn is not None:
        state = "OK" if conn["ok"] else "FAIL"
        detail = " ".join(
            f"{s['surface']}={'ok' if s['ok'] else 'FAIL'}"
            for s in conn["surfaces"]
        )
        print(f"INFO: connectivity [{state}] {detail}")

    delta = summary.get("task_delta")
    if delta is not None:
        print(
            f"INFO: task-delta total={delta['total']} "
            f"per_project={delta['per_project']}"
        )

    overall = "ok" if summary["ok"] else "FAIL"
    checks = ",".join(summary["checks"]) or "-"
    print(f"SUMMARY: checks={checks} ok={summary['ok']} result={overall}")


def main(argv: list[str] | None = None, *, client: Any | None = None) -> int:
    """CLI entrypoint. Returns 0 when every requested check passes, else 1/2.

    When no client is injected, the client is built through the token seam;
    tests inject a mocked client so no network or credential file is touched.
    """
    args = _build_parser().parse_args(argv)

    # Resolve the parameterized id sets first (usage errors before any I/O).
    try:
        expect_projects = (
            _parse_id_set(args.expect_projects, flag="--expect-projects")
            if args.expect_projects is not None
            else list(DEFAULT_EXPECT_PROJECTS)
        )
        delta_projects = (
            _parse_id_set(args.delta_projects, flag="--delta-projects")
            if args.delta_projects is not None
            else list(DEFAULT_DELTA_PROJECTS)
        )
    except ValueError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 2

    # No capability flag → run all three (the default operator summary).
    do_inverse = args.inverse_probe
    do_conn = args.connectivity
    do_delta = args.task_delta
    if not (do_inverse or do_conn or do_delta):
        do_inverse = do_conn = do_delta = True

    checks: list[str] = []
    if do_inverse:
        checks.append("inverse-probe")
    if do_conn:
        checks.append("connectivity")
    if do_delta:
        checks.append("task-delta")

    token_path: str | None = None
    try:
        if client is None:
            client, token_path = _build_client(args.base_url)

        inv_result = inverse_probe(client, expect_projects) if do_inverse else None
        conn_result = connectivity_check(client) if do_conn else None
        delta_result = task_delta(client, delta_projects) if do_delta else None
    except VikunjaError as exc:
        print(f"ERROR: {_format_error(exc)}", file=sys.stderr)
        return 1
    except Exception as exc:  # noqa: BLE001 - CLI boundary: report, exit 1
        # Includes VikunjaConfigError from an unresolved/unreadable token file.
        print(f"ERROR: {type(exc).__name__}: {exc}", file=sys.stderr)
        return 1

    ok = True
    if inv_result is not None and not inv_result.ok:
        ok = False
    if conn_result is not None and not conn_result.ok:
        ok = False

    summary: dict[str, Any] = {
        "token_path": token_path,
        "checks": checks,
        "inverse_probe": inv_result.to_dict() if inv_result else None,
        "connectivity": conn_result.to_dict() if conn_result else None,
        "task_delta": delta_result.to_dict() if delta_result else None,
        "ok": ok,
    }

    if args.json:
        _emit_json(summary)
    else:
        _emit_human(summary)

    if not ok:
        if inv_result is not None and inv_result.missing:
            print(
                "ERROR: inverse-probe FAILED — expected projects not visible "
                f"to the resolved token: {inv_result.missing}",
                file=sys.stderr,
            )
        if conn_result is not None and not conn_result.ok:
            broken = [s.surface for s in conn_result.surfaces if not s.ok]
            print(
                f"ERROR: connectivity FAILED — unreadable surface(s): {broken}",
                file=sys.stderr,
            )
        return 1

    return 0


if __name__ == "__main__":  # pragma: no cover - CLI entry
    sys.exit(main())
