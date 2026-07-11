"""Canary registry loader — service-inventory.json → runner work list.

Pure and offline. This module reads the architecture service inventory and
produces the canary runner's work list:

* one :class:`CanaryTarget` per **service-type** entry (code records such as
  ``python-module`` / ``library`` / ``cli-integration`` are exempt), and
* a **coverage-gap set** (:class:`CoverageGap`) for alert-eligible entries that
  declare no usable ``health_check`` (FR-006).

It never probes anything, never touches the network, and never calls an LLM
(INV-E). The only I/O in the module is the single file read in
:func:`load_inventory`; :func:`load_targets` is pure and accepts a parsed dict.
Probing is WP03 (``probes.py``); orchestration/emission is WP04 (``run.py``).

References: data-model.md (CanaryTarget / CoverageGap), contracts §1–§2
(pointer-path resolution F4, method vocabulary), research.md R3 (real method
heterogeneity) + R9 (coverage-gap set), plan.md IC-02, ADR-0006 (status gate).
"""
from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path

# --------------------------------------------------------------------------- #
# Type-set constants.
#
# Source of truth: ``tooling/scripts/validate_architecture_data.py``
# (``SERVICE_TYPES`` / ``NON_SERVICE_TYPES``). These are **duplicated** here on
# purpose — the runtime ``scripts/canary`` package must not import from
# ``tooling/`` (keeps the runtime package free of the tooling dependency). If
# the validator's sets change, update these to match (drift here silently drops
# or mis-classifies components — see the WP02 reviewer guidance).
# --------------------------------------------------------------------------- #
SERVICE_TYPES: frozenset[str] = frozenset(
    {
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
)

# Code/integration records, NOT running services. Exempt from health checks by
# design — they never become targets and are never coverage gaps.
NON_SERVICE_TYPES: frozenset[str] = frozenset(
    {
        "python-module",
        "cli-integration",
        "library",
    }
)

# --------------------------------------------------------------------------- #
# Health-check method vocabulary.
#
# The real inventory declares a heterogeneous method vocabulary (research R3);
# it is NOT normalized in the inventory data. We classify here; WP03's
# ``probes.py`` dispatch actually runs the probes. Keep ``HANDLED_METHODS``
# aligned with WP03's dispatch table (contracts §2) — a method absent from this
# set on an alert-eligible entry becomes an ``unhandled-method`` coverage gap
# rather than being silently skipped (INV-002, no-silent-fallback).
# --------------------------------------------------------------------------- #

# Freshness-pointer methods: the probe reads a pointer JSON and checks its
# authoritative timestamp against ``max_age_seconds``. For these, the loader
# resolves ``pointer_path`` (F4). All other methods carry ``pointer_path=None``.
FRESHNESS_METHODS: frozenset[str] = frozenset(
    {
        "tick-signal-file",
        "signal-file",
        "state-file",
    }
)

# Every method WP03 knows how to dispatch (contracts §2). ``none`` is
# deliberately excluded: it means "no evaluable check" ⇒ coverage gap.
HANDLED_METHODS: frozenset[str] = frozenset(
    FRESHNESS_METHODS
    | {
        "http",
        "shell",
        "systemd-status",
        "log-tail",
        "journal",
        "self-check-command",
        "self-test",
    }
)

# Declared statuses that make a component alert-eligible (ADR-0006 §4). Every
# other status (suspended / deprecated / planned / retired) is intentionally
# off: not probed, never a coverage gap.
ALERT_ELIGIBLE_STATUSES: frozenset[str] = frozenset({"active", "running"})

DEFAULT_INVENTORY_PATH = Path(
    "docs/design/architecture/data/service-inventory.json"
)


@dataclass(frozen=True)
class CanaryTarget:
    """One evaluable component derived from a service-inventory entry.

    Fields per data-model.md. ``component_id`` is the stable identity used as
    the alert ``source`` and the dedup key downstream. ``alert_eligible`` is the
    ADR-0006 status gate (WP03 returns ``suppressed`` without probing when it is
    false). ``pointer_path`` is resolved only for freshness methods (F4).
    """

    component_id: str
    type: str
    status: str
    alert_eligible: bool
    health_check: dict | None
    pointer_path: str | None


@dataclass(frozen=True)
class CoverageGap:
    """An alert-eligible service that declares no usable health_check (FR-006).

    ``reason`` is one of ``"no-health-check"``, ``"method-none"``, or
    ``"unhandled-method:<method>"``. The loader returns gaps as a separate list;
    it does NOT emit them (WP04 emits them as WARN, deduped).
    """

    component_id: str
    type: str
    reason: str


def _component_id(entry: dict) -> str:
    """Stable identity for an inventory entry: ``name`` if present, else ``id``."""
    name = entry.get("name")
    if name:
        return name
    return entry["id"]


def _resolve_pointer_path(health_check: dict) -> str | None:
    """Resolve the freshness pointer path for a freshness-method health_check.

    F4: ``state_path`` first, then ``endpoint`` (restic sets ``state_path``;
    agent-prompt-sync et al. put the path in ``endpoint``). Returns ``None`` for
    non-freshness methods.
    """
    if health_check.get("method") not in FRESHNESS_METHODS:
        return None
    return health_check.get("state_path") or health_check.get("endpoint")


def _coverage_gap_reason(
    alert_eligible: bool, health_check: dict | None
) -> str | None:
    """Return the coverage-gap reason for an entry, or ``None`` if it is covered.

    A gap arises only for an **alert-eligible** entry (ADR-0006 — suspended-class
    components are intentionally off and never gaps) whose ``health_check`` is
    missing/empty, declares ``method: none``, or declares a method WP03 does not
    handle (FR-006, INV-B no-silent-drop).
    """
    if not alert_eligible:
        return None
    if not health_check:
        return "no-health-check"
    method = health_check.get("method")
    if method == "none" or not method:
        return "method-none"
    if method not in HANDLED_METHODS:
        return f"unhandled-method:{method}"
    return None


def load_targets(
    inventory: dict,
) -> tuple[list[CanaryTarget], list[CoverageGap]]:
    """Turn a parsed inventory dict into (targets, coverage_gaps).

    Pure: accepts the already-parsed inventory dict; no I/O. Yields exactly one
    :class:`CanaryTarget` for every entry whose ``type`` is a service type;
    ``NON_SERVICE_TYPES`` entries are skipped silently (code records, exempt by
    design — not a gap). A :class:`CoverageGap` is produced for every
    alert-eligible entry with no usable ``health_check``.
    """
    targets: list[CanaryTarget] = []
    gaps: list[CoverageGap] = []

    for entry in inventory.get("services", []):
        etype = entry.get("type")
        if etype not in SERVICE_TYPES:
            # Code records (NON_SERVICE_TYPES) and any unknown type are not
            # evaluable services — skip silently. Only service types become work.
            continue

        component_id = _component_id(entry)
        status = entry.get("status", "")
        alert_eligible = status in ALERT_ELIGIBLE_STATUSES
        health_check = entry.get("health_check")
        pointer_path = (
            _resolve_pointer_path(health_check) if health_check else None
        )

        targets.append(
            CanaryTarget(
                component_id=component_id,
                type=etype,
                status=status,
                alert_eligible=alert_eligible,
                health_check=health_check,
                pointer_path=pointer_path,
            )
        )

        reason = _coverage_gap_reason(alert_eligible, health_check)
        if reason is not None:
            gaps.append(
                CoverageGap(
                    component_id=component_id,
                    type=etype,
                    reason=reason,
                )
            )

    return targets, gaps


def load_inventory(path: Path = DEFAULT_INVENTORY_PATH) -> dict:
    """Read and parse the service inventory JSON.

    The only I/O in this module. Thin wrapper so callers (and WP04's runner) can
    inject a path; the pure work is in :func:`load_targets`.
    """
    with Path(path).open(encoding="utf-8") as fh:
        return json.load(fh)
