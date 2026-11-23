"""Cron-drift detector (WP02, felix-truthful-reporting-01KX6MN5).

Compares live OpenClaw crons (``openclaw cron list --all --json`` — ``--all``
so disabled jobs are enumerated, #1127) against the
committed approved-cron baseline (:mod:`scripts.trust.cron_baseline`) and
produces structured findings for FR-003/FR-004/FR-006(b) — the "unrequested
infrastructure" incident class. This module deliberately does **not** emit
alerts, maintain seen-findings state, or run a timer loop; that layering
belongs to WP04 (see contract C3 /
``kitty-specs/felix-truthful-reporting-01KX6MN5/contracts/detector-cli.md``).

Two halves, kept strictly separate:

- :func:`detect_cron_drift` — the pure, I/O-free diff. No subprocess, no
  file read, no network, no bus call. This is what makes the detector
  unit-testable against canned JSON.
- :func:`enumerate_live_crons` — the one impure step (runs ``openclaw cron
  list --all --json`` via ``subprocess.run``), isolated behind a small function so
  the fail-safe rule (NFR-001) is enforced at a single boundary: a CLI
  failure or non-JSON output must never be silently treated as "no crons".
"""

from __future__ import annotations

import json
import subprocess
from dataclasses import dataclass

from scripts.common.openclaw_bin import openclaw_argv
from scripts.trust.cron_baseline import ApprovedCron

# Closed set of finding kinds (mirrors the token-constant pattern in
# scripts/office2/felix_health_check/run.py).
KIND_UNAPPROVED_PRESENT = "unapproved_present"
KIND_APPROVED_MISSING = "approved_missing"
KIND_SCHEDULE_MISMATCH = "schedule_mismatch"
KIND_ENABLED_MISMATCH = "enabled_mismatch"
# A second (third, ...) live copy of the same (name, agent_id) key (#1126).
KIND_DUPLICATE_PRESENT = "duplicate_present"

# Normalised ``enabled`` states (#1127). Only ``ENABLED_TRUE`` counts as
# enabled; every other state of an approved cron is an ``enabled_mismatch``
# (default-deny).
ENABLED_TRUE = "true"
ENABLED_FALSE = "false"
ENABLED_ABSENT = "absent"
ENABLED_MALFORMED = "malformed"
_ENABLED_RAW_MAX = 64

# Fixed argv for the live-enumeration subprocess (no shell, never `exec` —
# matches the felix-health-check runner style). The binary path is resolved by
# the seam (scripts/common/openclaw_bin.py): felix-trust-scan.service has no
# PATH override, so the systemd-user default PATH lacks ~/.local/bin and a bare
# `openclaw` would raise FileNotFoundError → the scan would fail (#653/#811).
# `--all` (#1127): without it OpenClaw omits disabled jobs, so a disabled
# approved cron read as approved_missing and a disabled unapproved cron was
# invisible.
OPENCLAW_CRON_LIST_ARGV = openclaw_argv("cron", "list", "--all", "--json")
_CRON_LIST_CMD = "openclaw cron list --all --json"
SUBPROCESS_TIMEOUT_SECONDS = 30


class CronEnumerationError(Exception):
    """Raised when live cron enumeration cannot be trusted.

    Covers a non-zero exit, a timeout, non-JSON stdout, a missing ``jobs``
    key, or a paginated (``hasMore: true``) payload. Deliberately distinct from returning ``[]`` — an empty
    list is a valid "genuinely no crons" answer and must never be produced
    as a side effect of a read/parse failure (NFR-001, the fail-safe
    inversion risk called out in the WP02 spec).
    """


@dataclass
class CronDriftFinding:
    """A single drift finding produced by :func:`detect_cron_drift`.

    Field set mirrors ``CronDriftFinding`` in data-model.md. Optional
    fields default to ``None`` and are populated only when relevant to the
    finding's ``kind`` (e.g. ``expected_schedule_expr`` for
    ``schedule_mismatch``/``approved_missing``).
    """

    kind: str
    name: str
    # ``None`` is truthful, not a gap: OpenClaw plugin-managed crons (e.g. the
    # memory-core "Memory Dreaming Promotion" job, 2026.11.7+) carry
    # ``agentId: null`` — no agent owns them (#1124). The approved-cron
    # baseline requires a non-blank agent_id, so ``(name, None)`` can never
    # match an approved entry and always fails closed as unapproved_present.
    agent_id: str | None
    cron_id: str | None = None
    schedule_expr: str | None = None
    expected_schedule_expr: str | None = None
    enabled: bool | None = None
    created_at_ms: int | None = None
    # Forensic only (rendered into alert details): which plugin declared a
    # plugin-managed cron. Deliberately NOT part of the fingerprint identity,
    # so adding it changed no existing fingerprint (#1124).
    declaration_key: str | None = None
    # Forensic only, NOT fingerprinted (#1127): the normalised enabled state
    # (``true``/``false``/``absent``/``malformed``) and, only when malformed,
    # the truncated ``repr`` of the raw value.
    enabled_state: str | None = None
    enabled_raw: str | None = None
    # duplicate_present only (#1126), NOT fingerprinted: the id and enabled
    # state of the group's primary copy.
    primary_cron_id: str | None = None
    primary_enabled_state: str | None = None


def _sort_key(finding: CronDriftFinding) -> tuple[str, str, bool, str, str]:
    # None-safe on agent_id: two findings sharing kind+name with agents None
    # and "x" must not raise TypeError inside sorted() (which would lose the
    # whole cron sub-scan). Ordering of all-str findings is unchanged; a None
    # agent sorts after every str agent.
    return (
        finding.kind,
        finding.name,
        finding.agent_id is None,
        finding.agent_id or "",
        # Separates duplicate_present copies of one key (#1126). Not part of
        # the fingerprint, so safe to add.
        finding.cron_id or "",
    )


def _normalize_name(value: object) -> str:
    """Parse-boundary normalisation: a cron ``name`` is always a ``str``."""
    if value is None:
        return ""
    return value if isinstance(value, str) else str(value)


def _normalize_optional_str(value: object) -> str | None:
    """Parse-boundary normalisation for an optional field: ``str | None``.

    ``None`` (or an absent key) stays ``None`` — for ``agentId`` that is
    truthful: the cron has no owning agent (#1124). Any other non-str value is
    coerced with ``str()``, mirroring ``assertion_verifier``'s coercion of raw
    JSON fields.
    """
    if value is None:
        return None
    return value if isinstance(value, str) else str(value)


def _normalize_created_at_ms(value: object) -> int | None:
    """Parse-boundary normalisation: ``createdAtMs`` is ``int | None``.

    Only a real ``int`` survives; ``bool`` (an ``int`` subclass), ``str`` and
    ``float`` are rejected to ``None`` so the primary-copy sort key is always
    comparable (#1126).
    """
    if isinstance(value, int) and not isinstance(value, bool):
        return value
    return None


def _normalize_enabled(value: object, present: bool) -> tuple[bool | None, str, str | None]:
    """Normalise raw ``enabled`` into ``(enabled, enabled_state, enabled_raw)`` (#1127).

    Identity checks only — ``1``/``0``/``"true"``/``"false"`` are NOT
    booleans here — and no hashing or lookup of the raw value, so an
    unhashable list/dict cannot raise. A missing key or ``null`` is
    ``absent``; any other non-bool is ``malformed`` with its ``repr``
    truncated to 64 chars kept for forensics.
    """
    if value is True:
        return True, ENABLED_TRUE, None
    if value is False:
        return False, ENABLED_FALSE, None
    if not present or value is None:
        return None, ENABLED_ABSENT, None
    return None, ENABLED_MALFORMED, repr(value)[:_ENABLED_RAW_MAX]


def _parse_live_job(job: dict) -> dict:
    """Defensively pull the fields the detector cares about from a raw job dict.

    Tolerant of extra/unknown fields and a missing ``schedule`` object or
    missing ``schedule.tz`` (contract C1) — this is where "unknown OpenClaw
    JSON shape drift" is absorbed so :func:`detect_cron_drift` can assume a
    clean, minimal shape. Type normalisation happens HERE, once: ``name`` is
    always ``str`` and ``agent_id`` is ``str | None`` (#1124), so no
    downstream consumer (sort, fingerprint, render) has to re-guard raw JSON.
    ``cron_id`` is ``str | None``, ``created_at_ms`` is ``int | None`` and
    ``enabled`` is folded into ``enabled_state`` (#1126/#1127).
    """
    schedule = job.get("schedule")
    if not isinstance(schedule, dict):
        schedule = {}
    enabled, enabled_state, enabled_raw = _normalize_enabled(
        job.get("enabled"), "enabled" in job
    )
    return {
        "name": _normalize_name(job.get("name")),
        "agent_id": _normalize_optional_str(job.get("agentId")),
        "declaration_key": _normalize_optional_str(job.get("declarationKey")),
        "enabled": enabled,
        "enabled_state": enabled_state,
        "enabled_raw": enabled_raw,
        "schedule_expr": schedule.get("expr"),
        "tz": schedule.get("tz"),
        "cron_id": _normalize_optional_str(job.get("id")),
        "created_at_ms": _normalize_created_at_ms(job.get("createdAtMs")),
    }


def _primary_sort_key(job: dict) -> tuple[bool, bool, int, bool, str]:
    """Total order over the copies of one ``(name, agent_id)`` group (#1126).

    The running copy is preferred, then the oldest (``created_at_ms``; None
    last), then ``cron_id`` (None last). All inputs are already normalised, so
    every element is comparable and the choice is independent of input order.
    """
    created = job["created_at_ms"]
    cron_id = job["cron_id"]
    return (
        job["enabled_state"] != ENABLED_TRUE,
        created is None,
        created or 0,
        cron_id is None,
        cron_id or "",
    )


def detect_cron_drift(
    live_jobs: list[dict], baseline: list[ApprovedCron]
) -> list[CronDriftFinding]:
    """Diff parsed live OpenClaw jobs against the approved-cron baseline.

    Pure function — **no I/O** (no subprocess, no file read, no network, no
    bus call). Match key is ``(name, agent_id)`` (contract C3): a live
    ``(name, agent_id)`` absent from the baseline is ``unapproved_present``,
    which also covers the owner-mismatch case (an approved ``name`` running
    under a *different* ``agent_id`` is unapproved under this key, which is
    the incident-relevant signal — the alternative of matching on ``name``
    alone would silently miss a hijacked/re-owned cron).

    Several live jobs sharing one key (#1126) are grouped: a deterministic
    **primary** (see :func:`_primary_sort_key`) is evaluated exactly as a
    single job would be, and every other copy is a ``duplicate_present``
    finding, whether or not the key is approved. Id-less extra copies share
    one identity, so they collapse to a single finding (a degraded shape
    OpenClaw does not emit).

    Findings are returned sorted by ``(kind, name, agent_id, cron_id)`` for
    deterministic, test-stable ordering (a ``None`` agent sorts last).
    """
    parsed_live = [_parse_live_job(job) for job in live_jobs]
    live_groups: dict[tuple[str, str | None], list[dict]] = {}
    for job in parsed_live:
        live_groups.setdefault((job["name"], job["agent_id"]), []).append(job)
    baseline_by_key = {(entry.name, entry.agent_id): entry for entry in baseline}

    findings: list[CronDriftFinding] = []

    for key, group in live_groups.items():
        name, agent_id = key
        live, *extra_copies = sorted(group, key=_primary_sort_key)
        seen_copy_ids: set[str | None] = set()
        for copy in extra_copies:
            if copy["cron_id"] in seen_copy_ids:
                # Same identity as a copy already reported (e.g. two id-less
                # copies): one finding per identity (A2).
                continue
            seen_copy_ids.add(copy["cron_id"])
            findings.append(
                CronDriftFinding(
                    kind=KIND_DUPLICATE_PRESENT,
                    name=name,
                    agent_id=agent_id,
                    cron_id=copy["cron_id"],
                    schedule_expr=copy["schedule_expr"],
                    enabled=copy["enabled"],
                    created_at_ms=copy["created_at_ms"],
                    declaration_key=copy["declaration_key"],
                    enabled_state=copy["enabled_state"],
                    enabled_raw=copy["enabled_raw"],
                    primary_cron_id=live["cron_id"],
                    primary_enabled_state=live["enabled_state"],
                )
            )

        baseline_entry = baseline_by_key.get(key)

        if baseline_entry is None:
            findings.append(
                CronDriftFinding(
                    kind=KIND_UNAPPROVED_PRESENT,
                    name=name,
                    agent_id=agent_id,
                    cron_id=live["cron_id"],
                    schedule_expr=live["schedule_expr"],
                    enabled=live["enabled"],
                    created_at_ms=live["created_at_ms"],
                    declaration_key=live["declaration_key"],
                    enabled_state=live["enabled_state"],
                    enabled_raw=live["enabled_raw"],
                )
            )
            continue

        # Matched pair: evaluate schedule and enabled independently — a
        # single pair may legitimately produce both a schedule_mismatch and
        # an enabled_mismatch finding.
        # Normalize tz: the live payload omits schedule.tz (→ None) for crons
        # running in the host default timezone, and the baseline records "" for
        # the same case — treat absent/empty as equal so that case is NOT a
        # spurious schedule_mismatch (a genuine tz change, e.g. NY→UTC, still
        # differs and is flagged). #683 deploy fix.
        schedule_changed = (
            live["schedule_expr"] != baseline_entry.schedule_expr
            or (live["tz"] or "") != (baseline_entry.tz or "")
        )
        if schedule_changed:
            findings.append(
                CronDriftFinding(
                    kind=KIND_SCHEDULE_MISMATCH,
                    name=name,
                    agent_id=agent_id,
                    cron_id=live["cron_id"],
                    schedule_expr=live["schedule_expr"],
                    expected_schedule_expr=baseline_entry.schedule_expr,
                    declaration_key=live["declaration_key"],
                )
            )

        # Default-deny (#1127): only a literal True is enabled. False, a
        # missing/null key, or any non-bool value is an enabled_mismatch; the
        # state is forensic detail and does NOT enter the fingerprint, so a
        # genuine False keeps its pre-#1127 fingerprint.
        if live["enabled_state"] != ENABLED_TRUE:
            findings.append(
                CronDriftFinding(
                    kind=KIND_ENABLED_MISMATCH,
                    name=name,
                    agent_id=agent_id,
                    cron_id=live["cron_id"],
                    enabled=live["enabled"],
                    declaration_key=live["declaration_key"],
                    enabled_state=live["enabled_state"],
                    enabled_raw=live["enabled_raw"],
                )
            )

    for key, baseline_entry in baseline_by_key.items():
        if key not in live_groups:
            findings.append(
                CronDriftFinding(
                    kind=KIND_APPROVED_MISSING,
                    name=baseline_entry.name,
                    agent_id=baseline_entry.agent_id,
                    expected_schedule_expr=baseline_entry.schedule_expr,
                )
            )

    return sorted(findings, key=_sort_key)


def enumerate_live_crons() -> list[dict]:
    """Run ``openclaw cron list --all --json`` and return the raw job dicts.

    The single impure boundary in this module: ``subprocess.run`` (never
    ``exec`` — an ``exec`` would replace this process and make it
    impossible to return/parse the result) with a fixed argv, no shell, and
    a hard timeout, matching the ``felix_health_check`` runner style.

    Fail-safe (NFR-001): raises :class:`CronEnumerationError` on a non-zero
    exit, a timeout, non-JSON stdout, a missing ``jobs`` key, or a paginated
    payload (``hasMore`` literally ``true`` — the scan must never read a
    truncated page as the complete set) — it never returns ``[]`` on failure. An empty list is reserved for a genuinely
    empty ``jobs: []`` payload. The caller (WP04) catches
    ``CronEnumerationError`` and fails safe (no alert, ``ok:false``).
    """
    try:
        completed = subprocess.run(  # noqa: S603 - fixed argv, no shell
            OPENCLAW_CRON_LIST_ARGV,
            capture_output=True,
            text=True,
            timeout=SUBPROCESS_TIMEOUT_SECONDS,
            check=False,
        )
    except subprocess.TimeoutExpired as exc:
        raise CronEnumerationError(
            f"{_CRON_LIST_CMD} timed out after {SUBPROCESS_TIMEOUT_SECONDS}s"
        ) from exc
    except OSError as exc:
        raise CronEnumerationError(f"failed to run {_CRON_LIST_CMD}: {exc}") from exc

    if completed.returncode != 0:
        raise CronEnumerationError(
            f"{_CRON_LIST_CMD} exited "
            f"{completed.returncode}: {completed.stderr.strip()}"
        )

    try:
        payload = json.loads(completed.stdout)
    except json.JSONDecodeError as exc:
        raise CronEnumerationError(
            f"{_CRON_LIST_CMD} returned non-JSON output: {exc}"
        ) from exc

    if not isinstance(payload, dict) or "jobs" not in payload:
        raise CronEnumerationError(f"{_CRON_LIST_CMD} response missing 'jobs' key")

    if payload.get("hasMore") is True:
        raise CronEnumerationError(
            f"{_CRON_LIST_CMD} returned a paginated payload (hasMore: true); "
            "refusing to diff a truncated job list"
        )

    jobs = payload["jobs"]
    if not isinstance(jobs, list):
        raise CronEnumerationError(f"{_CRON_LIST_CMD} 'jobs' field is not a list")

    return jobs


__all__ = [
    "KIND_UNAPPROVED_PRESENT",
    "KIND_APPROVED_MISSING",
    "KIND_SCHEDULE_MISMATCH",
    "KIND_ENABLED_MISMATCH",
    "KIND_DUPLICATE_PRESENT",
    "ENABLED_TRUE",
    "ENABLED_FALSE",
    "ENABLED_ABSENT",
    "ENABLED_MALFORMED",
    "CronDriftFinding",
    "CronEnumerationError",
    "detect_cron_drift",
    "enumerate_live_crons",
]
