"""Unit tests for scripts.canary.registry.

All fixtures are built inline as dicts — the live ``service-inventory.json`` is
never read. Per the charter "fixtures mirror real inputs" standard, the
``health_check`` shapes below are copied from real inventory entries:

* ``restic-backup``     — ``shell`` method with ``state_path`` (freshness pointer
                          in ``state_path``), ``cron`` / ``active``.
* ``agent-prompt-sync`` — ``tick-signal-file`` with the path in ``endpoint`` (no
                          ``state_path``), ``systemd-timer`` / ``active``.
* ``vikunja``           — ``http``, ``docker-compose`` / ``running``.
* ``felix-trust-scan``  — ``state-file`` with the path in ``endpoint``,
                          ``systemd-timer`` / ``active``.
* ``inbox-processing``  — ``openclaw-cron``, ``method: none``, ``active``.
* ``drift_interpretation`` — ``python-module`` (NON_SERVICE_TYPE), no
                          ``health_check``.
"""
from __future__ import annotations

from scripts.canary.registry import (
    HANDLED_METHODS,
    NON_SERVICE_TYPES,
    SERVICE_TYPES,
    CanaryTarget,
    CoverageGap,
    load_inventory,
    load_targets,
)

# --------------------------------------------------------------------------- #
# Real-shape inventory entries (inline fixtures).
# --------------------------------------------------------------------------- #

RESTIC = {
    "name": "restic-backup",
    "type": "cron",
    "status": "active",
    "health_check": {
        "method": "shell",
        "endpoint": "jq -er '...' /data/services/backup/state/last-backup.json",
        "expected": "exit 0 with an 'OK …' line",
        "timeout_seconds": 5,
        "state_path": "/data/services/backup/state/last-backup.json",
        "note": "Pointer file written on every run.",
    },
}

AGENT_PROMPT_SYNC = {
    "name": "agent-prompt-sync",
    "type": "systemd-timer",
    "status": "active",
    "health_check": {
        "method": "tick-signal-file",
        "endpoint": "/data/services/openclaw/deploy/agent-prompt-sync.jsonl",
        "expected": "tick_summary entry with exit_code=0 within the last 10 minutes",
        "timeout_seconds": 5,
        "note": "Append-only JSONL audit log.",
    },
}

VIKUNJA = {
    "name": "vikunja",
    "type": "docker-compose",
    "status": "running",
    "health_check": {
        "method": "http",
        "endpoint": "http://100.92.197.90:3456/api/v1/info",
        "expected": 200,
        "timeout_seconds": 5,
    },
}

FELIX_TRUST_SCAN = {
    "name": "felix-trust-scan",
    "type": "systemd-timer",
    "status": "active",
    "health_check": {
        "method": "state-file",
        "endpoint": "/data/services/trust/state/seen-findings.json",
        "expected": "Seen-findings state map written atomically each tick.",
        "timeout_seconds": 5,
    },
}

INBOX_PROCESSING = {
    "name": "inbox-processing",
    "type": "openclaw-cron",
    "status": "active",
    "health_check": {
        "method": "none",
        "note": "Scheduled job — health inferred from agent activity logs",
    },
}

DRIFT_INTERPRETATION = {
    "name": "drift_interpretation",
    "type": "python-module",
    "status": "active",
    # No health_check — code records are exempt.
}


def _inventory(*entries: dict) -> dict:
    """Wrap entries in the real top-level inventory envelope."""
    return {
        "schema_version": "1.0",
        "last_updated": "2026-07-11",
        "updated_by": "test",
        "services": list(entries),
    }


def _by_id(targets: list[CanaryTarget]) -> dict[str, CanaryTarget]:
    return {t.component_id: t for t in targets}


# --------------------------------------------------------------------------- #
# Type-set constants must match the validator's (source of truth).
# --------------------------------------------------------------------------- #


def test_service_type_sets_match_validator() -> None:
    # Guards against silent drift from validate_architecture_data.py.
    assert SERVICE_TYPES == frozenset(
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
    assert NON_SERVICE_TYPES == frozenset(
        {"python-module", "cli-integration", "library"}
    )
    assert SERVICE_TYPES.isdisjoint(NON_SERVICE_TYPES)


# --------------------------------------------------------------------------- #
# Targets: service types become targets; code records do not.
# --------------------------------------------------------------------------- #


def test_service_type_entry_becomes_target() -> None:
    targets, _gaps = load_targets(_inventory(VIKUNJA))
    assert [t.component_id for t in targets] == ["vikunja"]
    assert targets[0].type == "docker-compose"


def test_python_module_is_skipped_not_a_target() -> None:
    targets, gaps = load_targets(_inventory(DRIFT_INTERPRETATION))
    assert targets == []
    # Skipped silently by design — not a coverage gap.
    assert gaps == []


def test_one_target_per_service_type_entry() -> None:
    inv = _inventory(
        RESTIC,
        AGENT_PROMPT_SYNC,
        VIKUNJA,
        FELIX_TRUST_SCAN,
        INBOX_PROCESSING,
        DRIFT_INTERPRETATION,  # skipped
    )
    targets, _gaps = load_targets(inv)
    # Five service-type entries → five targets; the python-module is excluded.
    assert len(targets) == 5
    assert "drift_interpretation" not in _by_id(targets)


def test_component_id_falls_back_to_id_when_no_name() -> None:
    entry = {"id": "some-cron-id", "type": "cron", "status": "active"}
    targets, _gaps = load_targets(_inventory(entry))
    assert targets[0].component_id == "some-cron-id"


# --------------------------------------------------------------------------- #
# Alert-eligibility (ADR-0006).
# --------------------------------------------------------------------------- #


def test_active_status_is_alert_eligible() -> None:
    targets, _gaps = load_targets(_inventory(RESTIC))
    assert targets[0].alert_eligible is True


def test_running_status_is_alert_eligible() -> None:
    targets, _gaps = load_targets(_inventory(VIKUNJA))
    assert targets[0].alert_eligible is True


def test_suspended_status_is_not_alert_eligible() -> None:
    suspended = {**FELIX_TRUST_SCAN, "status": "suspended"}
    targets, _gaps = load_targets(_inventory(suspended))
    assert targets[0].alert_eligible is False


def test_other_lifecycle_statuses_are_not_eligible() -> None:
    for status in ("deprecated", "planned", "retired"):
        entry = {**VIKUNJA, "status": status}
        targets, _gaps = load_targets(_inventory(entry))
        assert targets[0].alert_eligible is False, status


# --------------------------------------------------------------------------- #
# Pointer-path resolution (F4): state_path first, then endpoint; None otherwise.
# --------------------------------------------------------------------------- #


def test_pointer_path_prefers_state_path() -> None:
    # restic-backup: freshness method carries the path in state_path.
    entry = {**RESTIC, "health_check": {**RESTIC["health_check"], "method": "state-file"}}
    targets, _gaps = load_targets(_inventory(entry))
    assert targets[0].pointer_path == "/data/services/backup/state/last-backup.json"


def test_pointer_path_falls_back_to_endpoint() -> None:
    # agent-prompt-sync: freshness method with the path only in endpoint.
    targets, _gaps = load_targets(_inventory(AGENT_PROMPT_SYNC))
    assert (
        targets[0].pointer_path
        == "/data/services/openclaw/deploy/agent-prompt-sync.jsonl"
    )


def test_pointer_path_state_file_uses_endpoint_when_no_state_path() -> None:
    # felix-trust-scan: state-file method, path in endpoint, no state_path key.
    targets, _gaps = load_targets(_inventory(FELIX_TRUST_SCAN))
    assert (
        targets[0].pointer_path
        == "/data/services/trust/state/seen-findings.json"
    )


def test_pointer_path_none_for_non_freshness_method() -> None:
    # http (vikunja) and shell (restic as-is) are not freshness methods.
    targets, _gaps = load_targets(_inventory(VIKUNJA, RESTIC))
    by_id = _by_id(targets)
    assert by_id["vikunja"].pointer_path is None
    assert by_id["restic-backup"].pointer_path is None


# --------------------------------------------------------------------------- #
# Coverage gaps (FR-006): only alert-eligible entries with no usable check.
# --------------------------------------------------------------------------- #


def test_active_method_none_is_a_gap() -> None:
    _targets, gaps = load_targets(_inventory(INBOX_PROCESSING))
    assert gaps == [
        CoverageGap(
            component_id="inbox-processing",
            type="openclaw-cron",
            reason="method-none",
        )
    ]


def test_suspended_method_none_is_not_a_gap() -> None:
    suspended = {**INBOX_PROCESSING, "status": "suspended"}
    targets, gaps = load_targets(_inventory(suspended))
    # Still a target, but intentionally off — never a coverage gap.
    assert targets[0].alert_eligible is False
    assert gaps == []


def test_unhandled_method_on_active_entry_is_a_gap() -> None:
    entry = {
        "name": "weird-service",
        "type": "native",
        "status": "active",
        "health_check": {"method": "quantum-ping", "endpoint": "x"},
    }
    _targets, gaps = load_targets(_inventory(entry))
    assert gaps == [
        CoverageGap(
            component_id="weird-service",
            type="native",
            reason="unhandled-method:quantum-ping",
        )
    ]


def test_missing_health_check_on_active_service_is_a_gap() -> None:
    entry = {"name": "no-hc", "type": "cron", "status": "active"}
    _targets, gaps = load_targets(_inventory(entry))
    assert gaps == [
        CoverageGap(component_id="no-hc", type="cron", reason="no-health-check")
    ]


def test_handled_method_active_entry_is_not_a_gap() -> None:
    _targets, gaps = load_targets(
        _inventory(RESTIC, AGENT_PROMPT_SYNC, VIKUNJA, FELIX_TRUST_SCAN)
    )
    assert gaps == []


def test_all_handled_methods_recognized() -> None:
    # Every freshness/liveness method is handled; none of them is a gap.
    for method in HANDLED_METHODS:
        entry = {
            "name": f"svc-{method}",
            "type": "native",
            "status": "active",
            "health_check": {"method": method, "endpoint": "/x"},
        }
        _targets, gaps = load_targets(_inventory(entry))
        assert gaps == [], method


# --------------------------------------------------------------------------- #
# load_inventory thin wrapper (the module's only I/O).
# --------------------------------------------------------------------------- #


def test_load_inventory_reads_and_parses(tmp_path) -> None:
    inv = _inventory(VIKUNJA)
    path = tmp_path / "inv.json"
    path.write_text(__import__("json").dumps(inv), encoding="utf-8")
    loaded = load_inventory(path)
    assert loaded == inv
    # And it round-trips through load_targets.
    targets, _gaps = load_targets(loaded)
    assert [t.component_id for t in targets] == ["vikunja"]
