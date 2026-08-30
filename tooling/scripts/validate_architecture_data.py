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
from datetime import date, datetime
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

# Canonical lifecycle *declared-status* values, defined by ADR-0006 (the #538
# lifecycle-status contract) — the single authoritative definition. These are the
# declared-intention axis only; observed *health* (healthy/stale/failed/degraded/
# unknown) is computed by the canary registry and never stored here (see ADR-0006 §1).
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

# health_check methods whose probe is freshness- or log-scan-based: they read an
# authoritative timestamp / most-recent-event and compare it to now, so they need
# a ``max_age_seconds`` freshness bound to be evaluable. Pure-liveness methods
# (http/systemd-status/command/self-test/none) legitimately omit it. WP02/WP03
# keep their own copy of this set — this constant is not a shared import surface
# (scripts/ must not import from tooling/).
FRESHNESS_METHODS = {
    "tick-signal-file",
    "signal-file",
    "state-file",
    "log-tail",
    "journal",
}

# Rules that are informational during a warn→strict rollout: reported in every
# mode but NOT blocking under --strict, so a not-yet-adopted field doesn't break
# commits (cf. the STATUS_ENUM #538 / #545 warn→strict pattern). max-age-missing
# flips to strict-blocking in a future "close freshness coverage gaps" issue once
# all live freshness/log-scan services declare max_age_seconds. A malformed value
# (max-age-type) is a real error and is intentionally NOT advisory.
ADVISORY_RULES: frozenset[str] = frozenset({"max-age-missing"})

# --------------------------------------------------------------------------- #
# health_check.key_ledger structural rules (pointer-key-ledger-01M189P6 WP02).
# Authority: kitty-specs/pointer-key-ledger-01M189P6/contracts/key-ledger.md
# § "Structural rules". `key_ledger` is optional (Placement); only its
# *contents*, when present, are constrained here.
# --------------------------------------------------------------------------- #

# The three predicate fields a `key_ledger.adjudicated` entry may carry.
# Contract rule 4: exactly one per adjudicated key.
KEY_LEDGER_PREDICATE_FIELDS: frozenset[str] = frozenset({"good_values", "minimum", "freshness"})

# The allow-list of modifier fields permitted alongside each predicate
# (contract "Predicate modifiers" table). A field on an adjudicated key's
# predicate object that is neither the chosen predicate itself nor on this
# list is a structural error — the vocabulary cannot be silently extended.
KEY_LEDGER_MODIFIER_ALLOWLIST: dict[str, frozenset[str]] = {
    "good_values": frozenset(),
    "minimum": frozenset({"unmeasured_is_unknown", "suppress_until_utc"}),
    "freshness": frozenset({"anchor", "max_age_seconds"}),
}

# Contract rule 6: a key_ledger may only appear on a health_check whose
# method reads a JSON document.
KEY_LEDGER_ELIGIBLE_METHODS: frozenset[str] = frozenset({"state-file", "tick-signal-file", "signal-file"})

# The members a key_ledger object may declare (contract rule 1).
KEY_LEDGER_MEMBERS: frozenset[str] = frozenset({"adjudicated", "diagnostic_only", "reconciliation_harness"})


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


def _parse_iso_instant(value: Any) -> datetime | None:
    """Parse an ISO-8601 instant (a full timestamp, not just a date).

    Used only by ``check_key_ledger`` to validate ``suppress_until_utc``.
    Mirrors ``scripts/canary/ledger.py``'s ``_parse_iso`` (reimplemented
    locally rather than imported so this validator stays dependency-free of
    the canary package): a trailing ``Z`` is normalized to ``+00:00``;
    anything non-string or unparseable returns ``None`` rather than raising.
    """
    if not isinstance(value, str):
        return None
    text = value.strip()
    if text.endswith("Z"):
        text = text[:-1] + "+00:00"
    try:
        return datetime.fromisoformat(text)
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


def check_max_age_seconds(entry: dict, file: str) -> Iterable[Finding]:
    """Validate the optional ``health_check.max_age_seconds`` freshness bound.

    When a ``health_check`` dict carries ``max_age_seconds``, it MUST be a
    positive int. ``bool`` is rejected even though it is an ``int`` subclass in
    Python (``True``/``False`` are never a valid duration). Absence is legal —
    pure-liveness checks omit the field entirely (see ``check_max_age_missing``
    for the alert-eligible-omission *warning*, which is a separate rule).
    """
    hc = entry.get("health_check")
    if not isinstance(hc, dict) or "max_age_seconds" not in hc:
        return
    value = hc["max_age_seconds"]
    if not (isinstance(value, int) and not isinstance(value, bool)) or value <= 0:
        yield Finding(
            file=file,
            entity=_entity_label(entry),
            rule="max-age-type",
            detail=(
                f"health_check.max_age_seconds={value!r} must be a positive int "
                f"(got {type(value).__name__})"
            ),
        )


def check_max_age_missing(entry: dict, file: str) -> Iterable[Finding]:
    """Warn when an alert-eligible freshness/log-scan check omits max_age_seconds.

    Alert-eligibility here is: a recognised runtime-service ``type`` **and** a
    live ``status`` (``LIVE_STATUS_VALUES``) **and** a freshness/log-scan
    ``health_check.method`` (``FRESHNESS_METHODS``). Such a check reads a
    timestamp but has no bound to compare it against, so freshness cannot be
    evaluated. A suspended/planned entry or a pure-liveness method does not warn.

    This is a *warning* (surfaces under warn-only, only fails under ``--strict``),
    matching the STATUS_ENUM/health-check posture.
    """
    etype = entry.get("type")
    if not (isinstance(etype, str) and etype in SERVICE_TYPES):
        return
    if entry.get("status") not in LIVE_STATUS_VALUES:
        return
    hc = entry.get("health_check")
    if not isinstance(hc, dict) or hc.get("method") not in FRESHNESS_METHODS:
        return
    if "max_age_seconds" in hc:
        return
    yield Finding(
        file=file,
        entity=_entity_label(entry),
        rule="max-age-missing",
        detail=(
            "alert-eligible freshness/log-scan health_check omits "
            "max_age_seconds; freshness cannot be evaluated"
        ),
    )


def check_key_ledger(entry: dict, file: str) -> Iterable[Finding]:
    """Validate an optional ``health_check.key_ledger`` (contract rules 1-8).

    Gated on ``entry.get("health_check")``, **never** on ``"key_ledger" in
    entry``: the traversal in ``_iter_objects`` yields every nested dict, so
    each adjudicated key's own predicate object (e.g. ``{"good_values": [0,
    3]}``) is visited as its own "entry". Such a fragment has no
    ``health_check`` field of its own, so gating here means it is never
    mistaken for a component carrying a ledger. Absence of ``key_ledger`` is
    always legal (contract "Placement") and yields nothing.
    """
    hc = entry.get("health_check")
    if not isinstance(hc, dict):
        return
    if "key_ledger" not in hc:
        return
    ledger = hc["key_ledger"]
    label = _entity_label(entry)

    if not isinstance(ledger, dict):
        yield Finding(
            file=file, entity=label, rule="key-ledger-shape",
            detail=f"health_check.key_ledger must be an object, got {type(ledger).__name__}",
        )
        return

    # Rule 1 — key_ledger contains only recognised members.
    for member in ledger:
        if member not in KEY_LEDGER_MEMBERS:
            yield Finding(
                file=file, entity=label, rule="key-ledger-unknown-member",
                detail=f"key_ledger has unrecognised member {member!r}; allowed: {sorted(KEY_LEDGER_MEMBERS)}",
            )

    # Rule 6 — eligible health_check method only.
    method = hc.get("method")
    if method not in KEY_LEDGER_ELIGIBLE_METHODS:
        yield Finding(
            file=file, entity=label, rule="key-ledger-ineligible-method",
            detail=(
                f"key_ledger present on health_check.method={method!r}; only "
                f"{sorted(KEY_LEDGER_ELIGIBLE_METHODS)} may carry a ledger"
            ),
        )

    # Rule 8 — reconciliation_harness is required and must be a non-empty,
    # repo-relative path string. Presence and shape ONLY: the validator does
    # NOT check that the file exists on disk.
    #
    # Revised 2026-08-30 (contract e9df2666): an existence check here created
    # a deadlock — the harness is WP05's, WP05 depends on WP02, and the
    # harness must reconcile against a ledger that already exists, so the
    # window cannot be closed by reordering. It was also the wrong layer: a
    # file existing proves nothing about whether it reconciles anything. That
    # binding — the named harness actually produced the document it
    # reconciles against — is Obligation 2's job (WP05's reconciliation
    # test), which cannot pass without genuinely doing it. Structure is the
    # validator's job; truth is the test's.
    harness = ledger.get("reconciliation_harness")
    if not isinstance(harness, str) or not harness.strip() or harness.startswith("/"):
        yield Finding(
            file=file, entity=label, rule="key-ledger-missing-harness",
            detail=(
                "key_ledger.reconciliation_harness is required and must be a non-empty, "
                f"repo-relative path string, got {harness!r}"
            ),
        )

    adjudicated = ledger.get("adjudicated", {})
    diagnostic_only = ledger.get("diagnostic_only", {})

    # Rule 2a — adjudicated must be an object.
    if not isinstance(adjudicated, dict):
        yield Finding(
            file=file, entity=label, rule="key-ledger-adjudicated-shape",
            detail=f"key_ledger.adjudicated must be an object, got {type(adjudicated).__name__}",
        )
        adjudicated = {}

    # Rule 2b — diagnostic_only maps key -> {"reason": non-empty string}.
    if not isinstance(diagnostic_only, dict):
        yield Finding(
            file=file, entity=label, rule="key-ledger-diagnostic-shape",
            detail=f"key_ledger.diagnostic_only must be an object, got {type(diagnostic_only).__name__}",
        )
        diagnostic_only = {}
    else:
        for dkey, dval in diagnostic_only.items():
            reason = dval.get("reason") if isinstance(dval, dict) else None
            if not isinstance(dval, dict) or not isinstance(reason, str) or not reason.strip():
                yield Finding(
                    file=file, entity=label, rule="key-ledger-diagnostic-missing-reason",
                    detail=f"diagnostic_only key {dkey!r} must be an object with a non-empty 'reason'",
                )

    # Rule 3 — no key appears in both lists. A hard error, never resolved by
    # precedence: precedence silently picks a winner, and the point of the
    # contract is that placement is a stated decision.
    for dupe in sorted(set(adjudicated) & set(diagnostic_only)):
        yield Finding(
            file=file, entity=label, rule="key-ledger-key-in-both-lists",
            detail=(
                f"{dupe!r} appears in both adjudicated and diagnostic_only; "
                "placement must be a single stated decision, not resolved by precedence"
            ),
        )

    # Rules 4, 5, 7 — per-key predicate structure.
    anchor_count = 0
    for akey, predicate in adjudicated.items():
        if not isinstance(predicate, dict):
            yield Finding(
                file=file, entity=label, rule="key-ledger-predicate-shape",
                detail=f"adjudicated key {akey!r} must map to a predicate object, got {type(predicate).__name__}",
            )
            continue

        present_predicates = [f for f in predicate if f in KEY_LEDGER_PREDICATE_FIELDS]
        if len(present_predicates) != 1:
            yield Finding(
                file=file, entity=label, rule="key-ledger-predicate-count",
                detail=(
                    f"adjudicated key {akey!r} must have exactly one predicate field "
                    f"({sorted(KEY_LEDGER_PREDICATE_FIELDS)}); found {sorted(present_predicates)}"
                ),
            )
            continue

        chosen = present_predicates[0]
        allowed_modifiers = KEY_LEDGER_MODIFIER_ALLOWLIST[chosen]
        for field in predicate:
            if field == chosen or field in allowed_modifiers:
                continue
            yield Finding(
                file=file, entity=label, rule="key-ledger-unrecognised-modifier",
                detail=(
                    f"adjudicated key {akey!r} predicate {chosen!r} carries field {field!r}, "
                    f"not on its modifier allow-list {sorted(allowed_modifiers)}"
                ),
            )

        # Rule 5 — malformed predicate value shape. This validates the
        # predicate FIELDS' values, not just their names/presence: a modifier
        # allow-list check alone lets `"anchor": "true"` (a string) through,
        # which the runtime treats as "no anchor" — a declared freshness
        # obligation with no bound that silently accepts any timestamp
        # (post-merge review of #934, Finding 1). Every branch below checks
        # value, not just key membership.
        if chosen == "good_values":
            value = predicate["good_values"]
            if not isinstance(value, list) or not value or not all(
                v is None or isinstance(v, (str, int, float, bool)) for v in value
            ):
                yield Finding(
                    file=file, entity=label, rule="key-ledger-good-values-malformed",
                    detail=(
                        f"adjudicated key {akey!r} good_values must be a non-empty array "
                        f"of scalars/null, got {value!r}"
                    ),
                )
        elif chosen == "minimum":
            value = predicate["minimum"]
            if isinstance(value, bool) or not isinstance(value, (int, float)):
                yield Finding(
                    file=file, entity=label, rule="key-ledger-minimum-malformed",
                    detail=f"adjudicated key {akey!r} minimum must be a number, got {value!r}",
                )

            if "unmeasured_is_unknown" in predicate:
                unmeasured = predicate["unmeasured_is_unknown"]
                if not isinstance(unmeasured, bool):
                    yield Finding(
                        file=file, entity=label, rule="key-ledger-unmeasured-is-unknown-malformed",
                        detail=(
                            f"adjudicated key {akey!r} unmeasured_is_unknown must be a boolean, "
                            f"got {unmeasured!r}"
                        ),
                    )

            if "suppress_until_utc" in predicate:
                suppress = predicate["suppress_until_utc"]
                if not isinstance(suppress, str) or _parse_iso_instant(suppress) is None:
                    yield Finding(
                        file=file, entity=label, rule="key-ledger-suppress-until-malformed",
                        detail=(
                            f"adjudicated key {akey!r} suppress_until_utc must be a string that "
                            f"parses as an ISO-8601 instant, got {suppress!r}"
                        ),
                    )

        elif chosen == "freshness":
            fvalue = predicate["freshness"]
            if fvalue is not True:
                yield Finding(
                    file=file, entity=label, rule="key-ledger-freshness-malformed",
                    detail=(
                        f"adjudicated key {akey!r} freshness must be the literal boolean "
                        f"true, got {fvalue!r}"
                    ),
                )

            if "anchor" in predicate:
                anchor_value = predicate["anchor"]
                if not isinstance(anchor_value, bool):
                    yield Finding(
                        file=file, entity=label, rule="key-ledger-anchor-malformed",
                        detail=(
                            f"adjudicated key {akey!r} anchor must be a boolean (True or "
                            f"False, never a string); got {anchor_value!r}"
                        ),
                    )
                elif anchor_value is True:
                    anchor_count += 1

            own_max_age = predicate.get("max_age_seconds")
            own_max_age_usable = False
            if "max_age_seconds" in predicate:
                if (
                    isinstance(own_max_age, bool)
                    or not isinstance(own_max_age, (int, float))
                    or own_max_age <= 0
                ):
                    yield Finding(
                        file=file, entity=label, rule="key-ledger-freshness-max-age-malformed",
                        detail=(
                            f"adjudicated key {akey!r} max_age_seconds must be a positive "
                            f"number and not a bool, got {own_max_age!r}"
                        ),
                    )
                else:
                    own_max_age_usable = True

            # Effective-bound check: a freshness predicate must resolve to a
            # bound from SOMEWHERE — its own max_age_seconds or the
            # health_check's — or it accepts any parseable timestamp as
            # fresh forever (runtime's `_ledger_freshness_result` "no
            # freshness anchor declared" / unbounded-obligation path). A
            # legitimate liveness-only ledger key must be declared as such
            # explicitly, not arrived at by omission; today's contract has
            # no such declaration, so omission is always a finding.
            hc_max_age = hc.get("max_age_seconds")
            hc_max_age_usable = (
                isinstance(hc_max_age, (int, float))
                and not isinstance(hc_max_age, bool)
                and hc_max_age > 0
            )
            if not own_max_age_usable and not hc_max_age_usable:
                yield Finding(
                    file=file, entity=label, rule="key-ledger-freshness-no-bound",
                    detail=(
                        f"adjudicated key {akey!r} freshness predicate resolves to no "
                        "effective bound (no usable own max_age_seconds and "
                        "health_check.max_age_seconds is absent or malformed); this "
                        "silently accepts any parseable timestamp as fresh"
                    ),
                )

    # Rule 7 — at most one key declares freshness with anchor: true. Any
    # number of keys may carry freshness with their own max_age_seconds;
    # only the anchor must be unique.
    if anchor_count > 1:
        yield Finding(
            file=file, entity=label, rule="key-ledger-multiple-anchors",
            detail=(
                f"{anchor_count} adjudicated keys declare freshness with anchor: true; "
                "at most one is permitted"
            ),
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
        findings.extend(check_max_age_seconds(entry, file))
        findings.extend(check_max_age_missing(entry, file))
        findings.extend(check_key_ledger(entry, file))
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

    # Advisory findings (warn→strict rollout signals) are reported in every mode
    # but do not gate the --strict exit code, so a not-yet-adopted field can't
    # break commits/CI. Only genuine errors (non-advisory rules) block.
    blocking = [f for f in findings if f.rule not in ADVISORY_RULES]
    if args.strict and blocking:
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
