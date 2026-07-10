"""Cron-drift detector (WP02, felix-truthful-reporting-01KX6MN5).

Compares live OpenClaw crons (``openclaw cron list --json``) against the
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
  list --json`` via ``subprocess.run``), isolated behind a small function so
  the fail-safe rule (NFR-001) is enforced at a single boundary: a CLI
  failure or non-JSON output must never be silently treated as "no crons".
"""

from __future__ import annotations

import json
import subprocess
from dataclasses import dataclass

from scripts.trust.cron_baseline import ApprovedCron

# Closed set of finding kinds (mirrors the token-constant pattern in
# scripts/office2/felix_health_check/run.py).
KIND_UNAPPROVED_PRESENT = "unapproved_present"
KIND_APPROVED_MISSING = "approved_missing"
KIND_SCHEDULE_MISMATCH = "schedule_mismatch"
KIND_ENABLED_MISMATCH = "enabled_mismatch"

# Fixed argv for the live-enumeration subprocess (no shell, never `exec` —
# matches the felix-health-check runner style).
OPENCLAW_CRON_LIST_ARGV = ["openclaw", "cron", "list", "--json"]
SUBPROCESS_TIMEOUT_SECONDS = 30


class CronEnumerationError(Exception):
    """Raised when live cron enumeration cannot be trusted.

    Covers a non-zero exit, a timeout, non-JSON stdout, or a missing
    ``jobs`` key. Deliberately distinct from returning ``[]`` — an empty
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
    agent_id: str
    cron_id: str | None = None
    schedule_expr: str | None = None
    expected_schedule_expr: str | None = None
    enabled: bool | None = None
    created_at_ms: int | None = None


def _sort_key(finding: CronDriftFinding) -> tuple[str, str, str]:
    return (finding.kind, finding.name, finding.agent_id)


def _parse_live_job(job: dict) -> dict:
    """Defensively pull the fields the detector cares about from a raw job dict.

    Tolerant of extra/unknown fields and a missing ``schedule`` object or
    missing ``schedule.tz`` (contract C1) — this is where "unknown OpenClaw
    JSON shape drift" is absorbed so :func:`detect_cron_drift` can assume a
    clean, minimal shape.
    """
    schedule = job.get("schedule")
    if not isinstance(schedule, dict):
        schedule = {}
    return {
        "name": job.get("name"),
        "agent_id": job.get("agentId"),
        "enabled": job.get("enabled"),
        "schedule_expr": schedule.get("expr"),
        "tz": schedule.get("tz"),
        "cron_id": job.get("id"),
        "created_at_ms": job.get("createdAtMs"),
    }


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

    Findings are returned sorted by ``(kind, name, agent_id)`` for
    deterministic, test-stable ordering.
    """
    parsed_live = [_parse_live_job(job) for job in live_jobs]
    live_by_key = {(job["name"], job["agent_id"]): job for job in parsed_live}
    baseline_by_key = {(entry.name, entry.agent_id): entry for entry in baseline}

    findings: list[CronDriftFinding] = []

    for key, live in live_by_key.items():
        name, agent_id = key
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
                )
            )

        if live["enabled"] is False:
            findings.append(
                CronDriftFinding(
                    kind=KIND_ENABLED_MISMATCH,
                    name=name,
                    agent_id=agent_id,
                    cron_id=live["cron_id"],
                    enabled=False,
                )
            )

    for key, baseline_entry in baseline_by_key.items():
        if key not in live_by_key:
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
    """Run ``openclaw cron list --json`` and return the raw job dicts.

    The single impure boundary in this module: ``subprocess.run`` (never
    ``exec`` — an ``exec`` would replace this process and make it
    impossible to return/parse the result) with a fixed argv, no shell, and
    a hard timeout, matching the ``felix_health_check`` runner style.

    Fail-safe (NFR-001): raises :class:`CronEnumerationError` on a non-zero
    exit, a timeout, non-JSON stdout, or a missing ``jobs`` key — it never
    returns ``[]`` on failure. An empty list is reserved for a genuinely
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
            f"openclaw cron list --json timed out after {SUBPROCESS_TIMEOUT_SECONDS}s"
        ) from exc
    except OSError as exc:
        raise CronEnumerationError(f"failed to run openclaw cron list --json: {exc}") from exc

    if completed.returncode != 0:
        raise CronEnumerationError(
            "openclaw cron list --json exited "
            f"{completed.returncode}: {completed.stderr.strip()}"
        )

    try:
        payload = json.loads(completed.stdout)
    except json.JSONDecodeError as exc:
        raise CronEnumerationError(
            f"openclaw cron list --json returned non-JSON output: {exc}"
        ) from exc

    if not isinstance(payload, dict) or "jobs" not in payload:
        raise CronEnumerationError(
            "openclaw cron list --json response missing 'jobs' key"
        )

    jobs = payload["jobs"]
    if not isinstance(jobs, list):
        raise CronEnumerationError(
            "openclaw cron list --json 'jobs' field is not a list"
        )

    return jobs


__all__ = [
    "KIND_UNAPPROVED_PRESENT",
    "KIND_APPROVED_MISSING",
    "KIND_SCHEDULE_MISMATCH",
    "KIND_ENABLED_MISMATCH",
    "CronDriftFinding",
    "CronEnumerationError",
    "detect_cron_drift",
    "enumerate_live_crons",
]
