"""Tests for the ``max_age_seconds`` rules in
``tooling/scripts/validate_architecture_data.py`` (WP01, felix-canary-registry).

Two rules are exercised directly (they are pure functions):

* ``check_max_age_seconds`` — ``health_check.max_age_seconds``, when present, must
  be a positive int (``bool`` rejected).
* ``check_max_age_missing`` — an alert-eligible (live-status) freshness/log-scan
  check that omits ``max_age_seconds`` yields a *warning*; suspended or
  liveness-only entries do not.

The module is a standalone script (not an importable package), so it is loaded
from its file path via ``importlib`` — the same pattern as
``test_validate_architecture_data.py``. Health-check fixtures mirror the real
``service-inventory.json`` shapes (restic ``shell``; agent-prompt-sync
``tick-signal-file``; vikunja ``http``; an openclaw-cron ``method: none``) per
the charter testing standard.
"""

from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path

import pytest

_REPO_ROOT = Path(__file__).resolve().parents[2]
_SCRIPT = _REPO_ROOT / "tooling" / "scripts" / "validate_architecture_data.py"

_spec = importlib.util.spec_from_file_location("validate_architecture_data", _SCRIPT)
vad = importlib.util.module_from_spec(_spec)
sys.modules["validate_architecture_data"] = vad
assert _spec.loader is not None
_spec.loader.exec_module(vad)


def _type_rules(entry: dict) -> list[str]:
    return sorted(f.rule for f in vad.check_max_age_seconds(entry, "test.json"))


def _missing_rules(entry: dict) -> list[str]:
    return sorted(f.rule for f in vad.check_max_age_missing(entry, "test.json"))


# --------------------------------------------------------------------------- #
# Real-shaped health_check fixtures (mirroring service-inventory.json)
# --------------------------------------------------------------------------- #

def _freshness_entry(max_age=..., *, status="active"):
    """agent-prompt-sync tick-signal-file shape (a live freshness check)."""
    hc = {
        "method": "tick-signal-file",
        "endpoint": "/data/services/openclaw/deploy/agent-prompt-sync.jsonl",
        "expected": "tick_summary entry with exit_code=0 within the last 10 minutes",
        "timeout_seconds": 5,
    }
    if max_age is not ...:
        hc["max_age_seconds"] = max_age
    return {
        "name": "agent-prompt-sync",
        "type": "systemd-timer",
        "status": status,
        "health_check": hc,
    }


def _liveness_entry():
    """vikunja http shape (a pure-liveness check — no freshness bound)."""
    return {
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


def _restic_shell_entry(max_age=...):
    """restic-backup shell shape (a command/liveness check, not in FRESHNESS_METHODS)."""
    hc = {
        "method": "shell",
        "endpoint": "jq -er '...' /data/services/backup/state/last-backup.json",
        "expected": "exit 0 with an 'OK …' line",
        "timeout_seconds": 5,
        "state_path": "/data/services/backup/state/last-backup.json",
    }
    if max_age is not ...:
        hc["max_age_seconds"] = max_age
    return {
        "name": "restic-backup",
        "type": "cron",
        "status": "active",
        "health_check": hc,
    }


def _method_none_entry():
    """inbox-processing method:none shape (no probe, no freshness bound)."""
    return {
        "name": "inbox-processing",
        "type": "openclaw-cron",
        "status": "active",
        "health_check": {
            "method": "none",
            "note": "Scheduled job — health inferred from agent activity logs",
        },
    }


# --------------------------------------------------------------------------- #
# T001 — max_age_seconds type validation (check_max_age_seconds)
# --------------------------------------------------------------------------- #

def test_valid_positive_int_passes():
    assert _type_rules(_freshness_entry(600)) == []


def test_valid_positive_int_on_shell_check_passes():
    # A freshness bound on a non-freshness method is still type-valid.
    assert _type_rules(_restic_shell_entry(100800)) == []


def test_absent_max_age_is_legal():
    assert _type_rules(_freshness_entry()) == []
    assert _type_rules(_liveness_entry()) == []


def test_missing_health_check_does_not_crash():
    assert _type_rules({"name": "x", "type": "cron", "status": "active"}) == []


@pytest.mark.parametrize("bad_value", [0, -1, -100800])
def test_zero_and_negative_int_yield_max_age_type(bad_value):
    findings = list(vad.check_max_age_seconds(_freshness_entry(bad_value), "test.json"))
    assert [f.rule for f in findings] == ["max-age-type"]
    assert repr(bad_value) in findings[0].detail


def test_string_value_yields_max_age_type():
    findings = list(vad.check_max_age_seconds(_freshness_entry("100800"), "test.json"))
    assert [f.rule for f in findings] == ["max-age-type"]
    assert "str" in findings[0].detail


@pytest.mark.parametrize("bad_bool", [True, False])
def test_bool_value_yields_max_age_type(bad_bool):
    # bool is an int subclass in Python; it must still be rejected.
    findings = list(vad.check_max_age_seconds(_freshness_entry(bad_bool), "test.json"))
    assert [f.rule for f in findings] == ["max-age-type"]
    assert "bool" in findings[0].detail


# --------------------------------------------------------------------------- #
# T002 — alert-eligible omission warning (check_max_age_missing)
# --------------------------------------------------------------------------- #

def test_alert_eligible_freshness_without_max_age_warns():
    findings = list(vad.check_max_age_missing(_freshness_entry(), "test.json"))
    assert [f.rule for f in findings] == ["max-age-missing"]
    assert "freshness cannot be evaluated" in findings[0].detail
    assert findings[0].entity == "agent-prompt-sync"


def test_freshness_with_max_age_does_not_warn():
    assert _missing_rules(_freshness_entry(600)) == []


def test_suspended_freshness_entry_does_not_warn():
    # A non-live status is not alert-eligible → no warning even without the field.
    assert _missing_rules(_freshness_entry(status="suspended")) == []


def test_planned_freshness_entry_does_not_warn():
    assert _missing_rules(_freshness_entry(status="planned")) == []


def test_liveness_http_entry_without_max_age_does_not_warn():
    # http is a pure-liveness method — never expected to carry a freshness bound.
    assert _missing_rules(_liveness_entry()) == []


def test_method_none_entry_does_not_warn():
    assert _missing_rules(_method_none_entry()) == []


def test_shell_command_entry_without_max_age_does_not_warn():
    # shell is a command method, not in FRESHNESS_METHODS.
    assert _missing_rules(_restic_shell_entry()) == []


@pytest.mark.parametrize(
    "method",
    ["tick-signal-file", "signal-file", "state-file", "log-tail", "journal"],
)
def test_every_freshness_method_warns_when_omitted(method):
    entry = {
        "name": f"svc-{method}",
        "type": "systemd-timer",
        "status": "active",
        "health_check": {"method": method, "endpoint": "/x", "timeout_seconds": 5},
    }
    assert _missing_rules(entry) == ["max-age-missing"]


# --------------------------------------------------------------------------- #
# Integration through validate_document (both rules wired into the traversal)
# --------------------------------------------------------------------------- #

def test_rules_are_wired_into_validate_document():
    doc = {
        "last_updated": "2026-07-11",
        "services": [
            _freshness_entry(),          # → max-age-missing warning
            _freshness_entry("100800"),  # → max-age-type finding
            _liveness_entry(),           # → nothing
        ],
    }
    rules = sorted(f.rule for f in vad.validate_document(doc, "test.json"))
    assert rules == ["max-age-missing", "max-age-type"]


def test_clean_freshness_doc_has_no_max_age_findings():
    doc = {
        "last_updated": "2026-07-11",
        "services": [_freshness_entry(600), _liveness_entry(), _method_none_entry()],
    }
    rules = {f.rule for f in vad.validate_document(doc, "test.json")}
    assert "max-age-type" not in rules
    assert "max-age-missing" not in rules


# --------------------------------------------------------------------------- #
# --strict gate: max-age-missing is advisory (non-blocking); max-age-type blocks
# --------------------------------------------------------------------------- #

def test_max_age_missing_is_advisory():
    assert "max-age-missing" in vad.ADVISORY_RULES
    assert "max-age-type" not in vad.ADVISORY_RULES


def test_strict_gate_on_real_tree_does_not_block(capsys):
    # The pre-commit hook runs exactly `--strict`. The real tree currently has
    # only max-age-missing (advisory) findings for max_age — the gate must not
    # block on them. (Other non-advisory findings would fail; the live tree is
    # otherwise clean, which this asserts.)
    exit_code = vad.main(["--strict"])
    out = capsys.readouterr().out
    assert exit_code == 0
    # Advisory findings are still printed, not silently dropped.
    assert "max-age-missing" in out
    # And no genuine max_age validity error is present on the real tree.
    assert "max-age-type" not in out


def test_strict_gate_blocks_on_max_age_type(tmp_path, capsys):
    # A malformed max_age_seconds (non-advisory max-age-type) MUST block --strict.
    data_dir = tmp_path / "data"
    data_dir.mkdir()
    doc = {
        "last_updated": "2026-07-11",
        "services": [_freshness_entry("100800")],  # string → max-age-type
    }
    (data_dir / "inventory.json").write_text(json.dumps(doc), encoding="utf-8")
    exit_code = vad.main(["--strict", "--data-dir", str(data_dir)])
    out = capsys.readouterr().out
    assert exit_code == 1
    assert "max-age-type" in out


def test_warn_only_never_blocks_even_with_type_error(tmp_path):
    # Warn-only posture is unchanged: findings present, exit 0.
    data_dir = tmp_path / "data"
    data_dir.mkdir()
    doc = {
        "last_updated": "2026-07-11",
        "services": [_freshness_entry("100800"), _freshness_entry()],
    }
    (data_dir / "inventory.json").write_text(json.dumps(doc), encoding="utf-8")
    assert vad.main(["--data-dir", str(data_dir)]) == 0


def test_strict_gate_advisory_only_tree_does_not_block(tmp_path):
    # A synthetic tree whose only findings are advisory (max-age-missing) → exit 0.
    data_dir = tmp_path / "data"
    data_dir.mkdir()
    doc = {
        "last_updated": "2026-07-11",
        "services": [_freshness_entry()],  # live freshness, no field → max-age-missing
    }
    (data_dir / "inventory.json").write_text(json.dumps(doc), encoding="utf-8")
    assert vad.main(["--strict", "--data-dir", str(data_dir)]) == 0
