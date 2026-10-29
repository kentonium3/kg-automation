"""Coverage checks for felix-health-check: the canary's dead-man's switch and
an independent backup check (kentonium3/kg-automation#1063).

From 2026-09-27 to 2026-10-14 every nightly backup failed and nothing said
so. The canary, the only component that judged backup health, had stopped
ticking (#1062), and this health check reported ``ALL_HEALTHY`` 34 times
because it looked at neither the canary nor the backup.

This module closes both gaps by *observing* the two components through the
canary's own code path: the ``service-inventory.json`` declaration of each,
evaluated by :func:`scripts.canary.health.evaluate`. It restates no bound,
good-set or freshness rule (C-001); a changed declaration changes both
watchers at once, and there is one definition of "healthy". It reads only
the two declared pointer files and the inventory, and never depends on the
canary *process* running (C-002).

Every inability to evaluate is an ``unknown`` finding, never a healthy one
(engineering principle 14), and :func:`evaluate_coverage` never raises.
"""

from __future__ import annotations

import importlib
import json
import math
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any, Callable, Literal

#: The components this health check vouches for, in report order. Hard-coded
#: on purpose: two dead-man targets do not justify a declarative inventory
#: flag; a third one is the trigger to add one (rule of three, research R11/
#: paula-4). CI pins that both exist, are alert-eligible and carry the
#: declaration shape the evaluator needs (``test_coverage.py``).
COVERAGE_COMPONENTS: tuple[str, ...] = ("felix-canary", "restic-backup")

INVENTORY_PATH = (
    Path(__file__).resolve().parents[3]
    / "docs" / "design" / "architecture" / "data" / "service-inventory.json"
)

Finding = Literal["ok", "failure", "unknown"]

# Canary outcome -> finding (research R2). An allow-list: any outcome not
# named here, including one the canary invents later, is unknown, never ok.
_FINDING_BY_OUTCOME: dict[str, Finding] = {
    "healthy": "ok",
    "stale": "failure",
    "failed": "failure",
    "degraded": "failure",
    "unknown": "unknown",
}

OUTCOME_UNAVAILABLE = "unavailable"


@dataclass(frozen=True)
class CoverageFinding:
    component: str
    outcome: str
    finding: Finding
    evidence: str

    def to_record(self) -> dict[str, str]:
        return {
            "component": self.component,
            "outcome": self.outcome,
            "finding": self.finding,
            "evidence": self.evidence,
        }


def _read_json(path: str) -> Any:
    with open(path, encoding="utf-8") as fh:
        return json.load(fh)


def _host_uptime() -> float | None:
    try:
        with open("/proc/uptime", encoding="ascii") as fh:
            return float(fh.read().split()[0])
    except (OSError, ValueError, IndexError):
        return None


def _refuse(*_args: Any, **_kwargs: Any) -> Any:
    # Coverage checks are file reads. A declaration repointed to an http or
    # shell method fails closed as unknown instead of executing (research R4).
    raise RuntimeError("coverage checks are file-read only; declaration needs a network or shell probe")


def _is_positive_bound(value: Any) -> bool:
    return (
        isinstance(value, (int, float))
        and not isinstance(value, bool)
        and math.isfinite(value)
        and value > 0
    )


def declaration_problems(health_check: Any) -> list[str]:
    """Shape checks the evaluator needs to judge freshness at all (R12).

    Not a health rule: no value is compared against data here. Without a
    bound the canary's freshness path silently degrades to liveness-only,
    and without exactly one anchor there is no freshness verdict.
    """
    if not isinstance(health_check, dict):
        return ["no health_check declared"]
    problems: list[str] = []
    if not _is_positive_bound(health_check.get("max_age_seconds")):
        problems.append(
            f"max_age_seconds={health_check.get('max_age_seconds')!r} is not a finite positive number"
        )
    ledger = health_check.get("key_ledger")
    if not isinstance(ledger, dict) or not isinstance(ledger.get("adjudicated"), dict):
        problems.append("no key_ledger with an adjudicated map")
        return problems
    anchors = []
    for key, predicate in ledger["adjudicated"].items():
        if not isinstance(predicate, dict) or "freshness" not in predicate:
            continue
        if predicate.get("anchor") is True:
            anchors.append(key)
        if "max_age_seconds" in predicate and not _is_positive_bound(predicate["max_age_seconds"]):
            problems.append(
                f"{key}.max_age_seconds={predicate['max_age_seconds']!r} is not a finite positive number"
            )
    if len(anchors) != 1:
        problems.append(f"expected exactly one freshness anchor, found {anchors or 'none'}")
    return problems


def _unknown(component: str, evidence: str, outcome: str = OUTCOME_UNAVAILABLE) -> CoverageFinding:
    return CoverageFinding(component=component, outcome=outcome, finding="unknown", evidence=evidence)


def _all_unknown(evidence: str) -> list[CoverageFinding]:
    return [_unknown(c, evidence) for c in COVERAGE_COMPONENTS]


def evaluate_coverage(
    now: datetime,
    *,
    inventory_path: Path = INVENTORY_PATH,
    read_state: Callable[[str], Any] = _read_json,
    uptime_seconds: Callable[[], float | None] = _host_uptime,
) -> list[CoverageFinding]:
    """Return one finding per :data:`COVERAGE_COMPONENTS` entry, in order.

    Never raises: an import, inventory or per-component fault becomes an
    ``unknown`` finding that names it.
    """
    try:
        # import_module, not `from scripts.canary import ...`: the latter is
        # satisfied by an attribute already set on the package and would not
        # see a module that failed to load (sys.modules entry None).
        health = importlib.import_module("scripts.canary.health")
        registry = importlib.import_module("scripts.canary.registry")

        targets, _gaps = registry.load_targets(registry.load_inventory(inventory_path))
        by_id = {t.component_id: t for t in targets}
    except Exception as exc:  # noqa: BLE001 - fail closed, never crash the run
        return _all_unknown(f"coverage could not start: {type(exc).__name__}: {exc}")

    findings: list[CoverageFinding] = []
    for component in COVERAGE_COMPONENTS:
        try:
            findings.append(
                _evaluate_one(component, by_id.get(component), now, health, read_state, uptime_seconds)
            )
        except Exception as exc:  # noqa: BLE001 - health.evaluate is total; belt and braces
            findings.append(_unknown(component, f"{type(exc).__name__}: {exc}"))
    return findings


def _evaluate_one(component, target, now, health, read_state, uptime_seconds) -> CoverageFinding:
    if target is None:
        return _unknown(component, "component not declared in the service inventory")
    problems = declaration_problems(target.health_check)
    if problems:
        return _unknown(component, "declaration invalid: " + "; ".join(problems))

    result = health.evaluate(target, now, http_get=_refuse, run_cmd=_refuse, read_state=read_state)

    if result.outcome == "suppressed":
        return _unknown(
            component,
            f"status {target.status!r} not alert-eligible: coverage withheld",
            outcome="suppressed",
        )
    finding = _FINDING_BY_OUTCOME.get(result.outcome, "unknown")
    evidence = result.evidence
    if component == "felix-canary" and result.outcome == "stale":
        evidence += _post_boot_note(target.health_check, uptime_seconds)
    return CoverageFinding(component=component, outcome=result.outcome, finding=finding, evidence=evidence)


def _post_boot_note(health_check: dict, uptime_seconds: Callable[[], float | None]) -> str:
    """Informative only (research R9): a catch-up run right after boot can
    see a canary that has not ticked yet. The finding stays a failure."""
    try:
        up = uptime_seconds()
    except Exception:  # noqa: BLE001
        return ""
    bound = health_check.get("max_age_seconds")
    if up is None or not _is_positive_bound(bound) or up >= bound:
        return ""
    return f" (host up {int(up // 60)} min: may be a post-boot catch-up)"
