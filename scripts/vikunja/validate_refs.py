#!/usr/bin/env python3
"""On-demand Vikunja registry honesty check (WP02, mission
``vikunja-reference-seam-01KXK68Z``, kentonium3/kg-automation#748/#745).

The operator-facing CLI wrapper around the pure
``scripts.common.vikunja_refs_validate.validate`` core. It lists live Vikunja
**once per resource** (≤2 list round trips total — NFR-002), compares every
declared reference in ``vikunja_refs.json`` against that reality, prints the
findings, and **fails loud** (non-zero exit) on any drift so a rotted id can
never pass silently (the #743 regression guard, FR-004).

Three exit states, deliberately distinct:

- ``0`` — registry clean (no findings).
- ``1`` — one or more findings (``missing`` / ``id_drift`` / ``title_drift`` /
  ``unprovisioned``): the registry disagrees with live Vikunja.
- ``2`` — **unreachable**: the live list could not be fetched (network/auth). A
  single ``unreachable`` finding is emitted and the exit is non-zero — a state
  the operator must read as *"could not validate"*, NOT as *"registry clean"*
  (never folded into exit 0).

Only the **kent** token is needed today: every declared project is kent-owned and
the sole declared label namespace (``felix:ignore``) is ``owner_token: kent``.
Labels are per-user (#715), so they are read in kent's namespace. This is a
**read-only** check — it never mutates Vikunja.

Run it (``-m`` invocation form is mandatory — a bare script path breaks the
``scripts.*`` package imports, per ``[[feedback_helper_m_invocation_form]]``)::

    python3 -m scripts.vikunja.validate_refs
    python3 -m scripts.vikunja.validate_refs --json

Wraps the deterministic ``scripts.common.vikunja_client.VikunjaClient`` — the
canonical stdlib HTTP boundary. No new HTTP path, no ``requests`` dependency.
"""
from __future__ import annotations

import argparse
import json
import sys
from typing import Any

from scripts.common.vikunja_client import VikunjaError
from scripts.common.vikunja_refs_validate import ValidationFinding, validate

__all__ = [
    "DEFAULT_KENT_TOKEN_FILE",
    "KENT_TOKEN",
    "collect_and_validate",
    "main",
]

# The kent-owned API token (#715 two-token model). Projects are kent-owned and
# the declared label namespace is kent's, so this is the token that sees the
# references the registry declares.
DEFAULT_KENT_TOKEN_FILE = "/data/services/openclaw/secrets/vikunja-api-kent"

# The single token whose namespace we validate today (felix:ignore is
# owner_token: kent). Used as the key into ``live_labels_by_token``.
KENT_TOKEN = "kent"

# Vikunja caps ``per_page`` at 50 on this instance, but the declared registry is
# tiny (≈9 projects / 2 labels). A single high-``per_page`` list keeps us within
# the ≤2-round-trip NFR-002 budget (a pagination loop would blow it); the value
# comfortably covers the live set with headroom.
_PAGE_SIZE = "250"


def collect_and_validate(client: Any) -> list[ValidationFinding]:
    """List live Vikunja in ≤2 round trips and run the pure validator.

    Exactly two ``client.get`` list calls: ``GET /projects`` and ``GET /labels``
    (kent namespace). Any listing failure propagates to the caller, which maps it
    to the ``unreachable`` state — it is **never** swallowed into a clean result.
    """
    live_projects = _as_list(client.get("/projects", params={"per_page": _PAGE_SIZE}))
    live_labels = _as_list(client.get("/labels", params={"per_page": _PAGE_SIZE}))
    return validate(live_projects, {KENT_TOKEN: live_labels})


def _as_list(result: Any) -> list[dict]:
    """Normalize a list endpoint result to a list of dicts.

    Vikunja returns ``null`` for an empty collection; ``None``/non-list
    normalizes to ``[]``. Non-dict elements are dropped defensively.
    """
    if not isinstance(result, list):
        return []
    return [item for item in result if isinstance(item, dict)]


# ---------------------------------------------------------------------------
# Rendering
# ---------------------------------------------------------------------------


def _print_findings(findings: list[ValidationFinding]) -> None:
    """Human-readable report: one line per finding, then a one-line summary."""
    print(f"--- validate vikunja registry: {len(findings)} finding(s) ---")
    width = max((len(f.kind) for f in findings), default=0)
    for finding in findings:
        print(
            f"  {finding.kind.ljust(width)}  {finding.ref_type:<7}  "
            f"{finding.name}: {finding.detail}"
        )
    print(
        "--- registry OK ---"
        if not findings
        else f"--- registry DRIFT: {len(findings)} finding(s), fail-loud ---"
    )


def _emit_json(findings: list[ValidationFinding], *, unreachable: bool) -> None:
    print(
        json.dumps(
            {
                "unreachable": unreachable,
                "findings": [
                    {
                        "kind": f.kind,
                        "ref_type": f.ref_type,
                        "name": f.name,
                        "detail": f.detail,
                    }
                    for f in findings
                ],
            },
            ensure_ascii=False,
        )
    )


def _emit_error_envelope(detail: str) -> None:
    """Structured stderr envelope for the unreachable state (matches the
    ``{"error": ..., "detail": ...}`` convention used across ``scripts/``)."""
    print(
        json.dumps({"error": "unreachable", "detail": detail}),
        file=sys.stderr,
    )


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="scripts.vikunja.validate_refs",
        description=(
            "Validate the declared Vikunja reference registry against live "
            "Vikunja (drift/missing/unprovisioned honesty check, FR-004). "
            "Read-only; ≤2 list calls. Exit 0=clean, 1=findings, "
            "2=unreachable."
        ),
    )
    parser.add_argument(
        "--token-file",
        default=DEFAULT_KENT_TOKEN_FILE,
        metavar="PATH",
        help=(
            "read the kent-owned API token from this file (default: "
            f"{DEFAULT_KENT_TOKEN_FILE}). Labels are validated in this token's "
            "namespace (#715)."
        ),
    )
    parser.add_argument(
        "--base-url",
        default=None,
        help="override Vikunja base URL (else canonical config)",
    )
    parser.add_argument(
        "--json",
        action="store_true",
        help="emit findings as JSON on stdout",
    )
    return parser


def _read_token_file(path: str) -> str:
    with open(path, encoding="utf-8") as handle:
        token = handle.read()
    if not token.strip():
        raise ValueError(f"kent token file {path!r} is empty")
    return token


def _build_client(args: argparse.Namespace) -> Any:
    from scripts.common.vikunja_client import VikunjaClient

    token = _read_token_file(args.token_file)
    return VikunjaClient(base_url=args.base_url, token=token)


def main(argv: list[str] | None = None, *, client: Any | None = None) -> int:
    """CLI entrypoint.

    Returns ``0`` when the registry is clean, ``1`` when any finding is present,
    and ``2`` when live Vikunja could not be listed (unreachable — a single
    ``unreachable`` finding is emitted and the exit is non-zero, distinct from
    clean). ``client`` is injectable for tests (no real network).
    """
    args = _build_parser().parse_args(argv)

    try:
        active_client = client if client is not None else _build_client(args)
        findings = collect_and_validate(active_client)
    except (VikunjaError, OSError, ValueError) as exc:
        return _report_unreachable(exc, args)
    except Exception as exc:  # noqa: BLE001 - CLI boundary: any listing failure
        return _report_unreachable(exc, args)

    if args.json:
        _emit_json(findings, unreachable=False)
    else:
        _print_findings(findings)
    return 1 if findings else 0


def _report_unreachable(exc: Exception, args: argparse.Namespace) -> int:
    """Emit the single ``unreachable`` finding + non-zero exit (never exit 0)."""
    detail = f"could not list live Vikunja: {type(exc).__name__}: {exc}"
    finding = ValidationFinding(
        kind="unreachable", ref_type="", name="", detail=detail
    )
    if args.json:
        _emit_json([finding], unreachable=True)
    else:
        _print_findings([finding])
    _emit_error_envelope(detail)
    return 2


if __name__ == "__main__":  # pragma: no cover - CLI entry
    sys.exit(main())
