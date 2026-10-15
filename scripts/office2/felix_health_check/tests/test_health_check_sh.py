"""health-check.sh, executed with stubbed systemctl and curl (#1068).

A timer's health is its producer's freshness, which the canary owns. The
``is-active`` check cannot judge a timer: a monotonic timer stuck in the #1062
dormant state still reports ``active (elapsed)``, so ``is-active`` passes
while the timer never fires again. These tests run the real script and record
the arguments ``systemctl`` actually receives. They do not grep the script
text, so a ``.timer`` reached through a variable or a loop is still caught.
"""
from __future__ import annotations

import json
import os
import subprocess
from pathlib import Path

import pytest

SCRIPT = Path(__file__).resolve().parents[1] / "health-check.sh"
REPO_ROOT = Path(__file__).resolve().parents[4]
INVENTORY = REPO_ROOT / "docs" / "design" / "architecture" / "data" / "service-inventory.json"


def _stub(bin_dir: Path, name: str, body: str) -> None:
    path = bin_dir / name
    path.write_text("#!/usr/bin/env bash\n" + body + "\n")
    path.chmod(0o755)


def _run(tmp_path: Path, script: Path = SCRIPT, **env_overrides):
    """Run ``script`` with stubs; return (stdout, recorded systemctl calls)."""
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir(exist_ok=True)
    calls = tmp_path / "systemctl-calls.log"
    # Records every invocation, one line per call. A unit named in
    # STUB_DOWN_UNIT reports "inactive"; everything else reports "active".
    _stub(bin_dir, "systemctl", f'''
echo "$*" >> "{calls}"
unit="${{@: -1}}"
if [ "$unit" = "$STUB_DOWN_UNIT" ]; then echo inactive; exit 3; fi
echo active''')
    # Both HTTP probes answer 200 unless STUB_HTTP overrides it, so the happy
    # path reaches ALL_HEALTHY on purpose, not by accident.
    _stub(bin_dir, "curl", 'echo -n "${STUB_HTTP:-200}"')
    env = dict(os.environ)
    env["PATH"] = f"{bin_dir}:{env['PATH']}"
    env.update(env_overrides)
    proc = subprocess.run(["bash", str(script)], env=env, capture_output=True, text=True, check=False)
    recorded = calls.read_text().splitlines() if calls.exists() else []
    return proc.stdout, recorded


def _is_active_units(calls: list[str]) -> list[str]:
    """Every unit argument of every is-active call, not just the last one, so
    `is-active b.timer a.service` is caught too (pre-merge review)."""
    units: list[str] = []
    for call in calls:
        tokens = call.split()
        if "is-active" not in tokens:
            continue
        after = tokens[tokens.index("is-active") + 1:]
        units.extend(t for t in after if not t.startswith("-"))
    return units


def test_no_timer_is_ever_judged_by_is_active(tmp_path):
    """The #1068 guard. is-active cannot see a dormant timer, so no .timer
    may be checked with it; the canary's freshness check owns timers."""
    _, calls = _run(tmp_path)
    units = _is_active_units(calls)
    assert units, "the stub recorded no is-active calls; the guard would be vacuous"
    timers = [u for u in units if u.endswith(".timer")]
    assert not timers, f"is-active cannot see a #1062-dormant timer: {timers}"


def test_guard_goes_red_when_a_timer_is_added(tmp_path):
    """The guard can fail: the same assertion against a copy of the script
    that checks a timer must find it."""
    variant = tmp_path / "health-check-variant.sh"
    text = SCRIPT.read_text()
    marker = "for unit in openclaw-gateway.service"
    assert marker in text, "user-unit loop not found; update this self-test"
    variant.write_text(text.replace(marker, marker + " some-thing.timer", 1))
    _, calls = _run(tmp_path, script=variant)
    assert "some-thing.timer" in _is_active_units(calls)


def test_all_up_reports_all_healthy(tmp_path):
    out, calls = _run(tmp_path)
    assert out.strip() == "ALL_HEALTHY"
    assert {"obsidian-sync.service", "vikunja.service", "openclaw-gateway.service"} <= set(
        _is_active_units(calls)
    )


def test_gateway_down_line_format_is_unchanged(tmp_path):
    """run.py parses these tokens; the DOWN line format is part of the contract."""
    out, _ = _run(tmp_path, STUB_DOWN_UNIT="openclaw-gateway.service")
    lines = out.splitlines()
    assert lines[0] == "FAILURES_DETECTED"
    assert "DOWN: openclaw-gateway.service (inactive)" in lines


def test_system_unit_down_is_still_reported(tmp_path):
    out, _ = _run(tmp_path, STUB_DOWN_UNIT="vikunja.service")
    assert out.splitlines()[0] == "FAILURES_DETECTED"
    assert "DOWN: vikunja.service (inactive)" in out.splitlines()


@pytest.mark.parametrize("http", ["000", "500"])
def test_http_probes_still_report(tmp_path, http):
    out, _ = _run(tmp_path, STUB_HTTP=http)
    assert out.splitlines()[0] == "FAILURES_DETECTED"
    assert f"DOWN: vikunja-api (HTTP {http})" in out.splitlines()


def test_core_digest_stays_covered_by_canary_freshness():
    """Dropping the is-active check loses no coverage only while the canary
    judges felix-core-digest by its tick's freshness, bounded, on the
    producer's last-tick.json. A dormant timer stops the tick, so the canary
    reads it stale within max_age_seconds."""
    doc = json.loads(INVENTORY.read_text())
    (entry,) = [s for s in doc["services"] if s.get("name") == "felix-core-digest"]
    assert entry["status"] == "active"
    hc = entry["health_check"]
    assert hc["method"] == "tick-signal-file"
    assert hc["endpoint"].endswith("/felix-core-digest-signals/last-tick.json")
    bound = hc["max_age_seconds"]
    assert isinstance(bound, (int, float)) and not isinstance(bound, bool)
    assert 0 < bound <= 3600


def test_guard_sees_a_timer_that_is_not_the_last_argument(tmp_path):
    variant = tmp_path / "health-check-multi.sh"
    text = SCRIPT.read_text()
    old = 'status=$(systemctl --user is-active $unit 2>/dev/null)'
    assert old in text, "user-unit is-active call not found; update this self-test"
    variant.write_text(text.replace(
        old, 'status=$(systemctl --user is-active other.timer $unit 2>/dev/null)', 1))
    _, calls = _run(tmp_path, script=variant)
    assert "other.timer" in _is_active_units(calls)
