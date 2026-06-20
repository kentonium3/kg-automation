#!/usr/bin/env python3
"""Semantic validator for the architecture data store.

The JSON files under ``docs/design/architecture/data/`` are policy-authoritative:
Felix agents read them to reason about the running system. ``jq`` only proves a
file *parses* — it says nothing about whether the content is *semantically
possible*. This validator adds that second layer of checks:

  * Date sanity — any field whose value parses as an ISO date is treated as a
    past-event date and must not be later than the file's ``last_updated``,
    UNLESS its name is forward-looking (``expires_at`` and friends, see
    ``FORWARD_DATE_FIELDS``) or is the ``last_updated`` anchor itself. Checking
    by exclusion covers every past-event field name in the store
    (``created_date``, ``added_at``, ``introduced_at``, ``deployed_on``,
    ``last_reviewed``, ...) without enumerating them. Unparseable values
    (``"unknown"``, an issue ref) are skipped, not flagged.
  * Required fields by entity type — an inventory entry whose ``type`` denotes a
    runtime service (see ``SERVICE_TYPES``) must carry a ``health_check`` field.
    Module-like entries (``python-module``, ``cli-integration``, ``library``)
    are exempt. An entry whose ``type`` is unrecognised is flagged so new types
    get an explicit classification decision.
  * Status enum — an inventory entry's ``status`` must be a member of the
    canonical lifecycle set. That set is **stubbed** here pending the #538
    lifecycle-status contract; it lives in one place (``STATUS_ENUM``) so #538
    can replace it without touching validator logic.
  * Status contradiction — an entry marked ``operational_status: suspended``
    while its ``status`` still claims a live value (``active``/``running``) is
    flagged as impossible content (the #545 felix-doc-auditor case).

Schema-definition files (a top-level ``$schema`` and no ``last_updated`` — e.g.
``capabilities-schema.json``, ``catalog-schema.json``) describe the *shape* of
other files and are exempt from every data-entity rule.

This is the "validator is the schema" approach (no separate JSON-Schema
framework): the rules are encoded here as documented constants.

Posture: **warn-only**. Findings are reported but the process exits 0, so wiring
this into CI cannot turn the build red. The current data already has known
violations (a future-dated credential, the doc-auditor status contradiction);
those are corrected under issue #545, after which ``--strict`` flips this to a
blocking gate.

Usage::

    python tooling/scripts/validate_architecture_data.py            # warn-only (exit 0)
    python tooling/scripts/validate_architecture_data.py --strict   # exit 1 if findings
    python tooling/scripts/validate_architecture_data.py --json     # machine-readable
    python tooling/scripts/validate_architecture_data.py --data-dir <path>

Issue #544 (Epic #532). Architecture review finding F-005.
"""
from __future__ import annotations

import argparse
import json
import sys
from dataclasses import dataclass
from datetime import date
from pathlib import Path
from typing import Any, Iterable

# --------------------------------------------------------------------------- #
# Rules-as-code (the "schema"). Edit these to change validator behaviour.
# --------------------------------------------------------------------------- #

DEFAULT_DATA_DIR = Path("docs/design/architecture/data")

# Date sanity works by exclusion: ANY field whose value parses as an ISO date is
# treated as a past-event date (must be <= the file's last_updated) UNLESS its
# name is forward-looking or is the comparison anchor itself. This catches the
# full spread of past-event field names actually used in the store
# (created_date, added_at, introduced_at, deployed_on, enabled_on, installed,
# last_reviewed, last_rotated, deprecated_at, since, updated_at, date, ...)
# without having to enumerate and maintain every one.
#
# Forward-looking fields are *supposed* to be in the future (an expiry, a
# renewal) — never flagged. last_updated is the anchor we compare against.
FORWARD_DATE_FIELDS = {
    "expires_at",
    "expiry_date",
    "valid_until",
    "not_after",
    "renews_at",
    "renewal_date",
    "next_review",
    "next_run",
}
DATE_REFERENCE_FIELDS = {"last_updated"}

# Inventory entry types that ARE independently-running, monitorable services and
# therefore must declare a health_check.
SERVICE_TYPES = {
    "cron",
    "docker",
    "docker-compose",
    "host-binary",
    "native",
    "npm-global",
    "openclaw-cron",
    "scheduled",
    "systemd-timer",
    "systemd_user_timer",
}

# Inventory entry types that are code/integration records, NOT running services.
# They are exempt from the health_check requirement.
NON_SERVICE_TYPES = {
    "python-module",
    "cli-integration",
    "library",
}

KNOWN_ENTITY_TYPES = SERVICE_TYPES | NON_SERVICE_TYPES

# Canonical lifecycle status values. STUB pending the #538 lifecycle-status
# contract — this is the single definition #538 will replace.
STATUS_ENUM = {
    "active",
    "running",
    "suspended",
    "planned",
    "deprecated",
    "retired",
}

# status values that assert the entity is live; contradicted by
# operational_status == "suspended".
LIVE_STATUS_VALUES = {"active", "running"}


@dataclass(frozen=True, order=True)
class Finding:
    """A single semantic problem. Ordered for deterministic, stable output."""

    file: str
    entity: str
    rule: str
    detail: str


# --------------------------------------------------------------------------- #
# File classification
# --------------------------------------------------------------------------- #

def is_schema_definition(doc: dict) -> bool:
    """A schema-definition file describes the shape of other files.

    Detected structurally: a top-level ``$schema`` key and no ``last_updated``.
    These are exempt from every data-entity rule.
    """
    return "$schema" in doc and "last_updated" not in doc


# --------------------------------------------------------------------------- #
# Individual rules. Each takes a single inventory entry (dict) plus context and
# yields Finding objects. Pure functions — no I/O — so they unit-test cleanly.
# --------------------------------------------------------------------------- #

def _entity_label(entry: dict) -> str:
    """Best-effort human label for an entry in findings output."""
    for key in ("name", "id", "identifier", "slug"):
        val = entry.get(key)
        if isinstance(val, str) and val:
            return val
    return "<unnamed>"


def _parse_iso_date(value: Any) -> date | None:
    """Parse an ISO ``YYYY-MM-DD`` date, or return None if not a real date.

    Non-strings and any unparseable string (``"unknown"``, an issue ref like
    ``"#371"``, free text) return None and are silently skipped — date.fromisoformat
    raises ValueError for them, so no separate sentinel list is needed.
    """
    if not isinstance(value, str):
        return None
    try:
        return date.fromisoformat(value.strip())
    except ValueError:
        return None


def check_dates(entry: dict, last_updated: date | None, file: str) -> Iterable[Finding]:
    """Every date-valued field except forward-looking ones must be <= last_updated."""
    if last_updated is None:
        return
    label = _entity_label(entry)
    for field, value in entry.items():
        if field in FORWARD_DATE_FIELDS or field in DATE_REFERENCE_FIELDS:
            continue
        parsed = _parse_iso_date(value)
        if parsed is None or parsed <= last_updated:
            continue
        yield Finding(
            file=file,
            entity=label,
            rule="date-sanity",
            detail=(
                f"{field}={value} is later than the file's "
                f"last_updated={last_updated.isoformat()} "
                f"(a past-event date cannot be in the future)"
            ),
        )


def check_health(entry: dict, file: str) -> Iterable[Finding]:
    """A runtime-service entry must declare a health_check.

    Applied by deep traversal, gated on ``type`` being an unambiguous service
    type — so it catches service records nested under a parent entry, and never
    fires on the differently-vocabularied ``type`` fields of credentials or
    dependency descriptors.
    """
    etype = entry.get("type")
    if isinstance(etype, str) and etype in SERVICE_TYPES and "health_check" not in entry:
        yield Finding(
            file=file,
            entity=_entity_label(entry),
            rule="missing-health-check",
            detail=f"type={etype!r} is a runtime service but has no health_check field",
        )


def check_status(entry: dict, file: str) -> Iterable[Finding]:
    """Inventory entries' status must be in the canonical enum; flag contradictions.

    Gated on a recognised entity ``type`` so it only judges genuine inventory
    entries (service-inventory's own vocabulary), not unrelated ``status`` fields
    elsewhere. ``status`` is treated as invalid if absent-of-type-safety: a
    non-string value is itself a malformed status, not a crash.
    """
    etype = entry.get("type")
    if not isinstance(etype, str) or etype not in KNOWN_ENTITY_TYPES:
        return
    label = _entity_label(entry)
    status = entry.get("status")
    if status is not None and (not isinstance(status, str) or status not in STATUS_ENUM):
        yield Finding(
            file=file,
            entity=label,
            rule="status-enum",
            detail=(
                f"status={status!r} is not in the canonical lifecycle set "
                f"({', '.join(sorted(STATUS_ENUM))})"
            ),
        )
    if entry.get("operational_status") == "suspended" and status in LIVE_STATUS_VALUES:
        yield Finding(
            file=file,
            entity=label,
            rule="status-contradiction",
            detail=f"operational_status=suspended contradicts status={status!r}",
        )


def check_unknown_type(entry: dict, file: str) -> Iterable[Finding]:
    """Flag a service-inventory entry whose ``type`` is unrecognised.

    Scoped by the caller to genuine service-inventory entries (the top-level
    ``services`` array): only there does an unknown ``type`` mean a
    classification gap, rather than a different schema's vocabulary
    (credentials, dependency edges, etc.).
    """
    if "type" not in entry:
        return
    etype = entry["type"]
    if not isinstance(etype, str) or etype not in KNOWN_ENTITY_TYPES:
        yield Finding(
            file=file,
            entity=_entity_label(entry),
            rule="unknown-entity-type",
            detail=(
                f"type={etype!r} is not a recognised entity type; classify it "
                f"as a service type or a non-service type in the validator"
            ),
        )


# --------------------------------------------------------------------------- #
# Traversal
# --------------------------------------------------------------------------- #

def _iter_objects(node: Any) -> Iterable[dict]:
    """Yield every dict in a nested JSON structure (depth-first)."""
    if isinstance(node, dict):
        yield node
        for value in node.values():
            yield from _iter_objects(value)
    elif isinstance(node, list):
        for item in node:
            yield from _iter_objects(item)


def validate_document(doc: dict, file: str) -> list[Finding]:
    """Apply all rules to a single parsed data document."""
    if is_schema_definition(doc):
        return []

    findings: list[Finding] = []
    last_updated = _parse_iso_date(doc.get("last_updated"))
    if last_updated is None:
        detail = (
            f"last_updated={doc.get('last_updated')!r} is not a valid ISO date"
            if "last_updated" in doc
            else "data file has no top-level last_updated field"
        )
        findings.append(Finding(file=file, entity="<file>", rule="missing-last-updated", detail=detail))

    # Date, health-check and status rules apply by deep traversal so a service
    # or dated record nested under a parent entry is still validated. Each rule
    # is gated on field/type identity, so foreign ``type``/``status``
    # vocabularies (credentials, dependency edges) are skipped, not mis-flagged.
    for entry in _iter_objects(doc):
        findings.extend(check_dates(entry, last_updated, file))
        findings.extend(check_health(entry, file))
        findings.extend(check_status(entry, file))

    # An *unrecognised* type only signals a classification gap inside the service
    # inventory's own entries (the top-level ``services`` array). Elsewhere a
    # foreign ``type`` is another schema's vocabulary, not an error — so this one
    # rule stays scoped rather than deep.
    services = doc.get("services")
    if isinstance(services, list):
        for entry in services:
            if isinstance(entry, dict):
                findings.extend(check_unknown_type(entry, file))

    return findings


def validate_tree(data_dir: Path) -> list[Finding]:
    """Validate every ``*.json`` file under ``data_dir``. Deterministic order."""
    findings: list[Finding] = []
    for path in sorted(data_dir.glob("*.json")):
        rel = path.as_posix()
        try:
            doc = json.loads(path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError) as exc:
            findings.append(
                Finding(file=rel, entity="<file>", rule="parse-error", detail=str(exc))
            )
            continue
        if not isinstance(doc, dict):
            continue
        findings.extend(validate_document(doc, rel))
    # Sort for deterministic, stable output. No set()-dedup: distinct violations
    # that happen to share a label + detail must each be reported, not collapsed.
    return sorted(findings)


# --------------------------------------------------------------------------- #
# CLI
# --------------------------------------------------------------------------- #

def _format_text(findings: list[Finding]) -> str:
    lines = []
    for f in findings:
        lines.append(f"  [{f.rule}] {f.file} :: {f.entity}: {f.detail}")
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument(
        "--data-dir",
        type=Path,
        default=DEFAULT_DATA_DIR,
        help="directory of architecture data JSON files (default: %(default)s)",
    )
    parser.add_argument(
        "--strict",
        action="store_true",
        help="exit non-zero when findings exist (blocking gate; default is warn-only)",
    )
    parser.add_argument("--json", action="store_true", help="emit findings as JSON")
    parser.add_argument(
        "--github",
        action="store_true",
        help="also emit GitHub Actions ::warning:: annotations (non-blocking)",
    )
    args = parser.parse_args(argv)

    if not args.data_dir.is_dir():
        print(f"validate_architecture_data: data dir not found: {args.data_dir}", file=sys.stderr)
        return 2

    findings = validate_tree(args.data_dir)

    if args.github and not args.json:
        for f in findings:
            # GitHub Actions annotation: shows in the Checks/PR UI, non-blocking.
            # Suppressed under --json so stdout stays a single parseable document.
            print(f"::warning file={f.file}::[{f.rule}] {f.entity}: {f.detail}")

    if args.json:
        print(json.dumps([f.__dict__ for f in findings], indent=2, sort_keys=True))
    elif findings:
        print(f"validate_architecture_data: {len(findings)} finding(s) "
              f"[{'STRICT' if args.strict else 'warn-only'}]:")
        print(_format_text(findings))
    else:
        print("validate_architecture_data: OK (0 findings)")

    if findings and args.strict:
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
