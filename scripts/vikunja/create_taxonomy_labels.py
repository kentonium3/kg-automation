#!/usr/bin/env python3
"""Reconcile the live Vikunja label set toward the canonical taxonomy (#715).

Deterministic, idempotent helper (Felix Constitution Directive 6): no LLM, no
global state, no caching. It creates any missing taxonomy label (with color),
optionally deletes the 3 legacy labels behind an explicit backup-gated flag,
and reports outcomes plus the title->id map.

Create is ``PUT /labels`` (Vikunja uses PUT, not POST, to create a label) with
body ``{"title", "hex_color"}``; list is a paginated ``GET /labels``
(``per_page`` caps at 50 on this instance); delete is ``DELETE /labels/{id}``.
Titles are matched **exactly** (case-sensitive) — ``Duplicate`` stays
capitalized. Colors are normalized (strip a leading ``#``, lower-case) on
compare so the stored bare-hex form never triggers a false mismatch.

The **live run is operator-invoked post-merge** — this module ships the code +
tests + the design-doc color column only. Run it on office2 where
``VikunjaClient`` resolves its base-URL/token defaults:

    python3 -m scripts.vikunja.create_taxonomy_labels [options]

Wraps the deterministic ``scripts.common.vikunja_client.VikunjaClient`` — the
canonical stdlib HTTP boundary. No new HTTP path, no ``requests`` dependency.
"""
from __future__ import annotations

import argparse
import json
import sys
from dataclasses import dataclass
from typing import Any

from scripts.common.vikunja_client import VikunjaError

__all__ = [
    "TAXONOMY_LABELS",
    "LEGACY_TITLES",
    "TaxonomyLabel",
    "ReconcileOutcome",
    "normalize_color",
    "list_labels",
    "duplicate_titles",
    "reconcile",
    "main",
]

# Vikunja caps ``per_page`` at 50 on this instance (Felix gotcha, R-02); a
# ``len < 100`` stop condition would be wrong.
_PAGE_SIZE = 50


@dataclass(frozen=True)
class TaxonomyLabel:
    """A label the helper intends to exist. Pure declared data."""

    title: str
    hex_color: str  # bare 6-hex, no leading '#', lower-case
    dimension: str  # friction | eisenhower | type | loe


# The single in-code source of truth for the canonical taxonomy. Titles +
# colors are locked to data-model.md / vikunja-configuration-design.md; the
# fidelity test asserts all three agree so drift fails loudly (INV-1).
TAXONOMY_LABELS: tuple[TaxonomyLabel, ...] = (
    # Friction (gradient)
    TaxonomyLabel("f:1-flow", "4caf50", "friction"),
    TaxonomyLabel("f:2-growth", "fbc02d", "friction"),
    TaxonomyLabel("f:3-edge", "fb8c00", "friction"),
    TaxonomyLabel("f:4-overload", "e53935", "friction"),
    # Eisenhower (blue)
    TaxonomyLabel("q:do", "1565c0", "eisenhower"),
    TaxonomyLabel("q:schedule", "1e88e5", "eisenhower"),
    TaxonomyLabel("q:delegate", "42a5f5", "eisenhower"),
    TaxonomyLabel("q:eliminate", "90caf9", "eisenhower"),
    # Type
    TaxonomyLabel("t:habit", "8e24aa", "type"),
    # LOE (gray)
    TaxonomyLabel("loe:s", "bdbdbd", "loe"),
    TaxonomyLabel("loe:m", "757575", "loe"),
    TaxonomyLabel("loe:l", "424242", "loe"),
)

# Legacy labels deleted only under --delete-legacy (matched by exact title,
# deleted by resolved id). ``Duplicate`` is capitalized — exact match.
LEGACY_TITLES: tuple[str, ...] = ("personal", "intentional", "Duplicate")


@dataclass(frozen=True)
class ReconcileOutcome:
    """One emitted per label acted on."""

    title: str
    action: str  # created | already-present | color-mismatch | deleted
    #            | already-absent | skipped-no-flag | duplicate-title
    #            | delete-inconsistent
    id: int | None = None
    ids: tuple[int, ...] | None = None  # populated for duplicate-title


def normalize_color(value: str) -> str:
    """Normalize a hex color: strip a leading ``#``, lower-case (R-04).

    Makes the declared-vs-server comparison form-independent — the live API
    returns ``hex_color`` without a leading ``#`` but Vikunja tolerates both
    on input.
    """
    return value.lstrip("#").lower()


def list_labels(client: Any) -> dict[str, list[dict]]:
    """Return ``{title: [label, ...]}`` from a paginated ``GET /labels``.

    Pages ``per_page=50`` starting at page 1, accumulating until a page
    returns fewer than 50 items (or empty). A **list** is kept per title so
    duplicates are surfaced, never silently collapsed (FR-009/FR-010, INV-6).
    Each label dict retains at least ``id``, ``title``, ``hex_color``.
    """
    by_title: dict[str, list[dict]] = {}
    page = 1
    while True:
        batch = client.get(
            "/labels",
            params={"per_page": str(_PAGE_SIZE), "page": str(page)},
        )
        if not isinstance(batch, list):
            # A non-list body from a 200 is a contract violation; surface it
            # as a server error rather than silently treating it as empty.
            raise VikunjaError(path="/labels", status=200)
        for label in batch:
            if not isinstance(label, dict):
                continue
            title = label.get("title")
            if not isinstance(title, str):
                continue
            by_title.setdefault(title, []).append(label)
        if len(batch) < _PAGE_SIZE:
            break
        page += 1
    return by_title


def duplicate_titles(by_title: dict[str, list[dict]]) -> set[str]:
    """Titles that map to more than one live label."""
    return {title for title, labels in by_title.items() if len(labels) > 1}


def _create_pass(
    client: Any,
    by_title: dict[str, list[dict]],
    *,
    dry_run: bool,
) -> tuple[list[ReconcileOutcome], dict[str, int], bool]:
    """Reconcile the 12 taxonomy labels. Returns (outcomes, id_map, failed).

    ``failed`` is set on any duplicate-title or color-mismatch. In ``dry_run``
    no ``put`` is issued (would-create is still reported as ``created`` for the
    plan, but with a null id).
    """
    outcomes: list[ReconcileOutcome] = []
    id_map: dict[str, int] = {}
    failed = False

    for entry in TAXONOMY_LABELS:
        matches = by_title.get(entry.title, [])
        if len(matches) > 1:
            ids = tuple(
                int(m["id"]) for m in matches if isinstance(m.get("id"), int)
            )
            outcomes.append(
                ReconcileOutcome(entry.title, "duplicate-title", ids=ids)
            )
            failed = True
            continue
        if not matches:
            if dry_run:
                outcomes.append(ReconcileOutcome(entry.title, "created", None))
                continue
            created = client.put(
                "/labels",
                json={"title": entry.title, "hex_color": entry.hex_color},
            )
            new_id = created.get("id") if isinstance(created, dict) else None
            if not isinstance(new_id, int):
                # Create returned an unexpected shape — surface it.
                raise VikunjaError(path="/labels", status=200)
            id_map[entry.title] = new_id
            outcomes.append(ReconcileOutcome(entry.title, "created", new_id))
            continue

        existing = matches[0]
        existing_id = existing.get("id")
        existing_id = existing_id if isinstance(existing_id, int) else None
        server_color = str(existing.get("hex_color", ""))
        if normalize_color(server_color) == normalize_color(entry.hex_color):
            outcomes.append(
                ReconcileOutcome(entry.title, "already-present", existing_id)
            )
        else:
            outcomes.append(
                ReconcileOutcome(entry.title, "color-mismatch", existing_id)
            )
            failed = True
        if existing_id is not None:
            id_map[entry.title] = existing_id

    return outcomes, id_map, failed


def _delete_pass(
    client: Any,
    by_title: dict[str, list[dict]],
    *,
    delete_legacy: bool,
    dry_run: bool,
) -> tuple[list[ReconcileOutcome], bool]:
    """Handle the 3 legacy labels. Returns (outcomes, failed).

    Without ``--delete-legacy`` any present legacy label is ``skipped-no-flag``.
    With the flag (and a backup ref already validated by the caller) every
    exact-title match is deleted by id.
    """
    outcomes: list[ReconcileOutcome] = []
    failed = False

    for title in LEGACY_TITLES:
        matches = by_title.get(title, [])
        if not matches:
            outcomes.append(ReconcileOutcome(title, "already-absent"))
            continue
        if not delete_legacy:
            for match in matches:
                mid = match.get("id")
                outcomes.append(
                    ReconcileOutcome(
                        title,
                        "skipped-no-flag",
                        mid if isinstance(mid, int) else None,
                    )
                )
            continue
        # Delete every exact-title match (handles duplicate legacy labels).
        for match in matches:
            mid = match.get("id")
            if not isinstance(mid, int):
                continue
            if dry_run:
                outcomes.append(ReconcileOutcome(title, "deleted", mid))
                continue
            try:
                client.delete(f"/labels/{mid}")
            except VikunjaError as exc:
                # A 404 mid-delete (concurrent/stale). Re-list and reconcile.
                from scripts.common.vikunja_client import VikunjaNotFoundError

                if not isinstance(exc, VikunjaNotFoundError):
                    raise
                fresh = list_labels(client)
                if fresh.get(title):
                    # Still present under a different id — inconsistent view
                    # (INV-8). Distinct action so a legacy label is never
                    # mislabeled with the taxonomy-color concept.
                    outcomes.append(
                        ReconcileOutcome(title, "delete-inconsistent", mid)
                    )
                    failed = True
                else:
                    outcomes.append(ReconcileOutcome(title, "already-absent", mid))
                continue
            outcomes.append(ReconcileOutcome(title, "deleted", mid))

    return outcomes, failed


def reconcile(
    client: Any,
    *,
    delete_legacy: bool = False,
    backup_confirmed: str | None = None,
    dry_run: bool = False,
) -> tuple[list[ReconcileOutcome], dict[str, int], bool]:
    """Run the create pass and (optionally) the delete pass.

    Returns ``(outcomes, id_map, failed)``. ``failed`` is True on any
    duplicate-title, color-mismatch, or delete-404 inconsistency. The
    delete-refused-without-backup case is enforced in :func:`main` before this
    is called, so a caller passing ``delete_legacy=True`` here has already
    satisfied the backup gate.
    """
    by_title = list_labels(client)
    outcomes, id_map, failed = _create_pass(client, by_title, dry_run=dry_run)

    if delete_legacy:
        del_outcomes, del_failed = _delete_pass(
            client,
            by_title,
            delete_legacy=True,
            dry_run=dry_run,
        )
        failed = failed or del_failed
    else:
        del_outcomes, _ = _delete_pass(
            client,
            by_title,
            delete_legacy=False,
            dry_run=dry_run,
        )
    outcomes.extend(del_outcomes)
    return outcomes, id_map, failed


def _outcome_to_dict(outcome: ReconcileOutcome) -> dict[str, Any]:
    record: dict[str, Any] = {"title": outcome.title, "action": outcome.action}
    if outcome.ids is not None:
        record["ids"] = list(outcome.ids)
    else:
        record["id"] = outcome.id
    return record


def _print_human(
    outcomes: list[ReconcileOutcome],
    id_map: dict[str, int],
    backup_confirmed: str | None,
    *,
    dry_run: bool,
) -> None:
    header = "PLAN (dry-run)" if dry_run else "RECONCILE"
    print(f"--- {header} ---")
    width = max((len(o.title) for o in outcomes), default=0)
    for outcome in outcomes:
        if outcome.ids is not None:
            detail = f"ids={list(outcome.ids)}"
        elif outcome.id is not None:
            detail = f"id={outcome.id}"
        else:
            detail = "id=-"
        print(f"  {outcome.title.ljust(width)}  {outcome.action.ljust(16)}  {detail}")
    print("--- title->id map ---")
    for title, label_id in id_map.items():
        print(f"  {title.ljust(width)}  {label_id}")
    if backup_confirmed is not None:
        print(f"backup_confirmed: {backup_confirmed}")


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="scripts.vikunja.create_taxonomy_labels",
        description=(
            "Reconcile Vikunja labels toward the canonical taxonomy (#715). "
            "Create-only by default; --delete-legacy (backup-gated) removes "
            "the 3 legacy labels."
        ),
    )
    parser.add_argument(
        "--delete-legacy",
        action="store_true",
        help="also delete legacy labels (personal, intentional, Duplicate); "
        "requires --backup-confirmed",
    )
    parser.add_argument(
        "--backup-confirmed",
        default=None,
        metavar="REF",
        help="Restic snapshot id / ISO timestamp asserting a recent backup; "
        "mandatory companion to --delete-legacy",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="compute and print the plan without any put/delete",
    )
    parser.add_argument(
        "--json",
        action="store_true",
        help="emit outcomes + title->id map as JSON on stdout",
    )
    parser.add_argument(
        "--base-url",
        default=None,
        help="override Vikunja base URL (else canonical config)",
    )
    parser.add_argument(
        "--token",
        default=None,
        help="override API token (else canonical secret path)",
    )
    parser.add_argument(
        "--token-file",
        default=None,
        help="read the API token from this file (overrides --token)",
    )
    return parser


def _resolve_token(args: argparse.Namespace) -> str | None:
    if args.token_file:
        with open(args.token_file, encoding="utf-8") as handle:
            return handle.read()
    return args.token


def _build_client(args: argparse.Namespace) -> Any:
    from scripts.common.vikunja_client import VikunjaClient

    return VikunjaClient(base_url=args.base_url, token=_resolve_token(args))


def main(argv: list[str] | None = None, *, client: Any | None = None) -> int:
    """CLI entrypoint. Returns 0 on full success, non-zero otherwise."""
    args = _build_parser().parse_args(argv)

    # Delete pass is gated on BOTH --delete-legacy AND --backup-confirmed —
    # refuse before any mutation (C-002).
    if args.delete_legacy and not args.backup_confirmed:
        print(
            "ERROR: --delete-legacy requires --backup-confirmed <ref> "
            "(a Restic snapshot id or ISO timestamp). Refusing to delete.",
            file=sys.stderr,
        )
        return 2

    try:
        active_client = client if client is not None else _build_client(args)
        outcomes, id_map, failed = reconcile(
            active_client,
            delete_legacy=args.delete_legacy,
            backup_confirmed=args.backup_confirmed,
            dry_run=args.dry_run,
        )
    except VikunjaError as exc:
        print(f"ERROR: {type(exc).__name__}: {exc}", file=sys.stderr)
        return 1
    except Exception as exc:  # noqa: BLE001 - CLI boundary: report, exit 1
        print(f"ERROR: {type(exc).__name__}: {exc}", file=sys.stderr)
        return 1

    backup_ref = args.backup_confirmed if args.delete_legacy else None

    if args.json:
        print(
            json.dumps(
                {
                    "outcomes": [_outcome_to_dict(o) for o in outcomes],
                    "label_id_map": id_map,
                    "backup_confirmed": backup_ref,
                },
                ensure_ascii=False,
            )
        )
    else:
        _print_human(outcomes, id_map, backup_ref, dry_run=args.dry_run)

    # Dry-run always exits 0 (it made no mutation); a real run exits non-zero
    # on any duplicate-title / color-mismatch / delete inconsistency.
    if args.dry_run:
        return 0
    return 1 if failed else 0


if __name__ == "__main__":  # pragma: no cover - CLI entry
    sys.exit(main())
