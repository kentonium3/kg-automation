"""Reality-vs-registry drift validator (WP02, mission
``vikunja-reference-seam-01KXK68Z``, kentonium3/kg-automation#748/#745).

This module is the **deterministic core** of the "honesty check" that keeps the
committed Vikunja ids (declared in ``vikunja_refs.json``) from silently rotting —
the #743 regression class. It answers one question: *does every declared
reference still match the live Vikunja reality?*

Two layers:

- :func:`validate` — a **pure** function over *injected* live data. It performs
  **no** network I/O; all live projects/labels are parameters. This is what makes
  the drift taxonomy unit-testable with fixtures. It returns
  ``list[ValidationFinding]`` (empty == clean).
- The operator-facing CLI that actually lists live Vikunja lives in
  ``scripts/vikunja/validate_refs.py`` (it owns the ≤2 live-list round trips of
  NFR-002 and the ``unreachable`` state). This module never touches the network.

The declared entries are read **through WP01's loader**
(``scripts.common.vikunja_refs``) — the single source of truth — never by
re-parsing ``vikunja_refs.json`` here. That keeps one authority for the registry
shape and honors WP01's test-injection seam (``set_registry_for_test``).

Finding taxonomy (see
``kitty-specs/vikunja-reference-seam-01KXK68Z/data-model.md`` and
``contracts/vikunja-refs.contract.md``):

- ``missing`` — a declared, provisioned name whose title *and* id are both absent
  from live Vikunja.
- ``id_drift`` — a live entity carries the declared title, but its id no longer
  matches the declared value (the id moved).
- ``title_drift`` — a live entity carries the declared id, but its title no longer
  matches the declared value (the title was renamed).
- ``unprovisioned`` — the reference is declared with ``value: null`` (or
  ``provisioned: false``); it has no live id yet. This is a *distinct* state from
  ``missing`` (a declared-but-not-yet-created ref is expected, FR-009).
- ``unreachable`` — emitted **only** by the CLI when the live list cannot be
  fetched; never produced by :func:`validate` (which is given live data).

Per Felix Constitution Directive 6 / ``docs/design/helper-script-conventions.md``
this is a library-tier module: pure, importable, no I/O on the hot path.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Iterable, Mapping

from scripts.common import vikunja_refs

__all__ = [
    "ValidationFinding",
    "validate",
    "validate_declarations",
]


@dataclass(frozen=True)
class ValidationFinding:
    """One drift/absence observation about a declared reference.

    Matches the ``ValidationFinding`` shape in ``data-model.md``:

    - ``kind`` — one of ``missing`` | ``id_drift`` | ``title_drift`` |
      ``unprovisioned`` | ``unreachable``.
    - ``ref_type`` — ``project`` | ``label`` (empty string for the global
      ``unreachable`` finding, which is not tied to a single ref).
    - ``name`` — the logical registry name affected (empty/global for
      ``unreachable``).
    - ``detail`` — a human-readable "expected vs live" string for the operator.
    """

    kind: str
    ref_type: str
    name: str
    detail: str


def _as_items(live: Iterable[Mapping[str, Any]] | None) -> list[dict[str, Any]]:
    """Coerce a live list endpoint result into a list of ``{id, title}`` dicts.

    Vikunja returns ``null`` for an empty collection; a non-iterable or ``None``
    normalizes to ``[]``. Non-dict elements are dropped defensively so a
    malformed row cannot crash the pure comparison.
    """
    if not live:
        return []
    return [dict(item) for item in live if isinstance(item, Mapping)]


def _drift_finding(
    ref_type: str,
    name: str,
    declared_id: int,
    declared_title: str,
    live_items: list[dict[str, Any]],
) -> ValidationFinding | None:
    """Compare one provisioned declared ref against the live list.

    Returns ``None`` when the declared ``(title, id)`` pair still matches a live
    entity (clean), else the single most-specific finding:

    - title present but id changed → ``id_drift``;
    - id present but title changed → ``title_drift``;
    - neither present → ``missing``.
    """
    by_title = [item for item in live_items if item.get("title") == declared_title]
    if by_title:
        if any(item.get("id") == declared_id for item in by_title):
            return None  # title + id both match → clean
        live_id = by_title[0].get("id")
        return ValidationFinding(
            kind="id_drift",
            ref_type=ref_type,
            name=name,
            detail=(
                f"declared id {declared_id} but live {ref_type} titled "
                f"{declared_title!r} now has id {live_id!r}"
            ),
        )

    by_id = [item for item in live_items if item.get("id") == declared_id]
    if by_id:
        live_title = by_id[0].get("title")
        return ValidationFinding(
            kind="title_drift",
            ref_type=ref_type,
            name=name,
            detail=(
                f"declared title {declared_title!r} but live {ref_type} with id "
                f"{declared_id} now has title {live_title!r}"
            ),
        )

    return ValidationFinding(
        kind="missing",
        ref_type=ref_type,
        name=name,
        detail=(
            f"no live {ref_type} with title {declared_title!r} or id "
            f"{declared_id} (declared but absent)"
        ),
    )


def validate(
    live_projects: Iterable[Mapping[str, Any]] | None,
    live_labels_by_token: Mapping[str, Iterable[Mapping[str, Any]] | None],
) -> list[ValidationFinding]:
    """Compare every declared reference against injected live data.

    Pure: performs **no** network I/O — all live data is supplied by the caller
    (the CLI does the listing). Reads the declared registry through WP01's
    memoized loader (``scripts.common.vikunja_refs``), never by re-parsing the
    JSON file, so there is a single source of registry truth and the WP01 test
    override is honored.

    Parameters
    ----------
    live_projects:
        Iterable of ``{"id": int, "title": str}`` as returned by
        ``GET /projects`` (``None`` / empty tolerated).
    live_labels_by_token:
        ``{token: [{"id": int, "title": str}, ...]}`` — the live labels visible
        in each token's namespace (#715 per-token label ownership).

    Returns
    -------
    list[ValidationFinding]
        Every finding across all declared refs (does not stop at the first).
        An empty list means the registry matches live reality (clean).
    """
    projects = _as_items(live_projects)
    labels_by_token = {
        token: _as_items(items) for token, items in live_labels_by_token.items()
    }

    findings: list[ValidationFinding] = []

    for entry in vikunja_refs.declared_projects():
        name = entry["name"]
        declared_id = entry["selector"]["value"]
        if not entry.get("provisioned", True) or declared_id is None:
            findings.append(
                ValidationFinding(
                    kind="unprovisioned",
                    ref_type="project",
                    name=name,
                    detail=(
                        f"declared with value:null (unprovisioned); no live id "
                        f"yet for title {entry['title']!r}"
                    ),
                )
            )
            continue
        finding = _drift_finding(
            "project", name, declared_id, entry["title"], projects
        )
        if finding is not None:
            findings.append(finding)

    for entry in vikunja_refs.declared_labels():
        name = entry["name"]
        declared_id = entry["selector"]["value"]
        owner_token = entry["owner_token"]
        if declared_id is None:
            findings.append(
                ValidationFinding(
                    kind="unprovisioned",
                    ref_type="label",
                    name=name,
                    detail=(
                        f"declared with value:null (unprovisioned) for token "
                        f"{owner_token!r}; no live id yet for title "
                        f"{entry['title']!r}"
                    ),
                )
            )
            continue
        finding = _drift_finding(
            "label",
            name,
            declared_id,
            entry["title"],
            labels_by_token.get(owner_token, []),
        )
        if finding is not None:
            findings.append(finding)

    return findings


def _duplicate_id_findings(
    ref_type: str,
    id_to_names: Mapping[Any, list[str]],
    namespace: str = "",
) -> list[ValidationFinding]:
    """Emit one ``duplicate_id`` finding per collided id in one id-space.

    ``id_to_names`` maps a declared provisioned id to every logical name that
    claims it. Any id claimed by more than one name is a collision: two refs
    resolving to the same live entity is a latent mis-routing bug (a caller
    asking for ``f:3-edge`` and ``q:schedule`` must never get the same id).
    ``namespace`` names the owning token for labels (labels are per-token,
    #715), empty for projects.
    """
    findings: list[ValidationFinding] = []
    for declared_id, names in id_to_names.items():
        if len(names) > 1:
            where = f" in token {namespace!r}" if namespace else ""
            findings.append(
                ValidationFinding(
                    kind="duplicate_id",
                    ref_type=ref_type,
                    name=", ".join(sorted(names)),
                    detail=(
                        f"declared id {declared_id} is claimed by "
                        f"{len(names)} {ref_type}s{where}: "
                        f"{sorted(names)} (ids must be unique per id-space)"
                    ),
                )
            )
    return findings


def validate_declarations() -> list[ValidationFinding]:
    """Structural, live-data-free drift gate over the declared registry alone.

    Complements :func:`validate` (which compares declared refs against injected
    live data) by checking invariants that hold **independent of Vikunja** and
    that the WP01 loader does not already enforce:

    - **No duplicate provisioned ids.** ``vikunja_refs._normalize`` rejects
      duplicate *names* at load, but nothing catches two distinct names
      declaring the same live *id*. That is exactly the mis-routing hazard the
      seam exists to prevent, so it is surfaced here as a ``duplicate_id``
      finding. Projects and labels are separate Vikunja id-spaces, and labels
      are per-token (#715), so collisions are detected **within** each space /
      token namespace, never across them.

    Unprovisioned refs (``value: null``) are skipped — a not-yet-reconciled id
    cannot collide. Returns ``list[ValidationFinding]`` (empty == clean), so a
    caller can fold these findings into the same report as :func:`validate`.
    Reads the registry through WP01's memoized loader — never by re-parsing the
    JSON — so it honors the ``set_registry_for_test`` seam and performs no I/O
    on the hot path.
    """
    findings: list[ValidationFinding] = []

    project_ids: dict[Any, list[str]] = {}
    for entry in vikunja_refs.declared_projects():
        if not entry.get("provisioned", True):
            continue
        declared_id = entry["selector"]["value"]
        if declared_id is None:
            continue
        project_ids.setdefault(declared_id, []).append(entry["name"])
    findings.extend(_duplicate_id_findings("project", project_ids))

    label_ids_by_token: dict[str, dict[Any, list[str]]] = {}
    for entry in vikunja_refs.declared_labels():
        declared_id = entry["selector"]["value"]
        if declared_id is None:
            continue
        token = entry["owner_token"]
        label_ids_by_token.setdefault(token, {}).setdefault(
            declared_id, []
        ).append(entry["name"])
    for token, id_to_names in label_ids_by_token.items():
        findings.extend(_duplicate_id_findings("label", id_to_names, token))

    return findings


def main(argv: list[str] | None = None) -> int:
    """Run the live-data-free declaration gate over the shipped registry.

    Loads the committed ``vikunja_refs.json`` through WP01's loader (file + JSON
    only, no network) and runs :func:`validate_declarations`. Prints any
    structural finding to stderr and returns a nonzero exit code so
    ``python3 -m scripts.common.vikunja_refs_validate`` is a real CI/pre-deploy
    gate (exit ``0`` == clean). The reality-vs-registry drift comparison that
    needs live Vikunja stays in the operator CLI at
    ``scripts/vikunja/validate_refs.py`` — this entry point never touches the
    network.
    """
    import sys

    del argv  # no options today; declared for a stable signature
    findings = validate_declarations()
    if not findings:
        print("vikunja_refs declarations OK: no duplicate ids", file=sys.stderr)
        return 0
    print(
        f"vikunja_refs declaration gate found {len(findings)} issue(s):",
        file=sys.stderr,
    )
    for finding in findings:
        print(f"  [{finding.kind}] {finding.ref_type} {finding.name}: {finding.detail}", file=sys.stderr)
    return 1


if __name__ == "__main__":  # pragma: no cover - thin CLI shim
    raise SystemExit(main())
