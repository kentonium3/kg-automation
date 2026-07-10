#!/usr/bin/env python3
"""Deploy entrypoint — Felix Truthful Reporting trust-scan timer (#683, WP04).

Mission: ``felix-truthful-reporting-01KX6MN5`` (WP04).

Installs the ``felix-trust-scan.{service,timer}`` systemd **user** units
under the ``claude`` account on office2, self-tests the scan runner WITHOUT
emitting, enables the timer only if that self-test is clean, and triggers a
prompt-sync tick to verify the fleet doctrine (WP01) landed in the deployed
``AGENTS.md`` files — all before declaring success. Tier 3 (Logic/Workflow —
installs a user timer; no Tier 0/1/2 action). Rebaseline is **not required**
(gap `#621` — agent prompts are an *unmonitored* audited surface; ``audit.sh``
does not hash deployed ``AGENTS.md``, and the detector/systemd code is not a
hashed baseline either).

Strict, halt-on-error order:

  1. **Install units** — copy ``felix-trust-scan.service`` +
     ``felix-trust-scan.timer`` into ``~/.config/systemd/user/``.
  2. **``daemon-reload``** — install the unit definitions (does NOT start
     anything; a repo unit file does nothing until installed + daemon-reloaded,
     #701/#699/#706 deploy lessons).
  3. **Dry-run self-test + baseline gate (#711)** — ``python3 -m
     scripts.trust.run_trust_scan --dry-run --json``. ``--dry-run`` EMITS
     NOTHING (a self-test must never page the operator), and the deploy gates
     ``enable --now`` on a clean result: if the dry-run reports any
     drift/assertion finding, the seeded baseline does not match live reality —
     the deploy FAILS here with the timer left un-started, so no false-positive
     alert ever fires. Reconcile the baseline, then re-deploy.
  4. **``enable --now``** — start the timer, reached ONLY after a clean dry-run.
  5. **Prompt-sync verification (Codex finding 10 + F4)** — trigger
     ``systemctl --user start agent-prompt-sync.service`` (rather than waiting
     for the 5-minute prompt-sync timer), then verify the **exact canonical**
     truthful-reporting + mechanism-fidelity doctrine block is present in
     **every deployed fleet prompt** and the no-unrequested-infra block in
     deployed ``main`` **only** — reusing the same canonical-block source as
     the repo-source fleet-guard test
     (``scripts/openclaw/agents/truthful_doctrine.py``) so the deploy check and
     the test can never drift apart. Deployed prompt paths are resolved from
     ``service-inventory.json`` (agents.<slug>.workspace); agents with no
     deployed workspace (the retired ``felix-doc-auditor`` driver) have no
     prompt to verify and are skipped.
  6. **Report via the ``#701`` bus** — outcome (success/failure) is emitted
     through ``scripts.common.alert_bus.emit``; no parallel channel.

No auto-rollback — on any failure the script prints recovery instructions
and exits non-zero.

CLI contract (per ``docs/runbooks/deploy/discipline.md``):

* ``--dry-run`` — print each planned step; **no side effects** on office2.
  Safe to run anywhere (off-office2 too).
* ``--apply`` — execute all steps in order; halt at the first failure.

Exit codes
----------
* ``0`` — dry-run printed successfully, OR apply completed every step.
* ``1`` — a step failed (install / enable / self-test / prompt-sync-verify).
  Nothing is rolled back; recovery instructions are printed to stderr.
* ``2`` — usage error (missing / wrong-shaped mode argument).
"""
from __future__ import annotations

import json
import shutil
import subprocess
import sys
from pathlib import Path

# felix-deployer invokes the entrypoint by path (not via `python3 -m`), so the
# repo root is not on sys.path unless we put it there ourselves.
_REPO_ROOT = Path(__file__).resolve().parents[2]
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

from scripts.common.alert_bus import emit  # noqa: E402
from scripts.common.alert_bus.model import Alert, Severity  # noqa: E402
from scripts.openclaw.agents.truthful_doctrine import (  # noqa: E402
    FLEET_AGENTS,
    check_deployed_doctrine,
)
from scripts.openclaw.deploy.deploy_agent_prompts import iter_agents  # noqa: E402

# --------------------------------------------------------------------------- #
# Grounded constants.
# --------------------------------------------------------------------------- #

_UNIT_SOURCE_DIR = _REPO_ROOT / "scripts" / "office2"
_UNIT_NAMES = ("felix-trust-scan.service", "felix-trust-scan.timer")
_SYSTEMD_USER_DIR = Path.home() / ".config/systemd/user"

_TIMER_UNIT = "felix-trust-scan.timer"

# The deploy self-test uses --dry-run (NOT --preflight): --dry-run computes
# findings but EMITS NOTHING and mutates no state, so the self-test can never
# page the operator. --preflight is a real scan that emits — using it here
# pinged Kent's phone with deploy-time false-positives (#711).
_SELF_TEST_ARGV = [
    sys.executable,
    "-m",
    "scripts.trust.run_trust_scan",
    "--dry-run",
    "--json",
]

# The canonical operational-state source for each agent's deployed prompt
# location: service-inventory.json services[openclaw].agents.<slug>.workspace.
# The prompt-sync pipeline (scripts.openclaw.deploy.deploy_agent_prompts) copies
# each repo-source AGENTS.md to <workspace>/AGENTS.md; we resolve the same
# mapping here so the deploy verification checks exactly what prompt-sync
# deploys.
_SERVICE_INVENTORY = (
    _REPO_ROOT / "docs" / "design" / "architecture" / "data" / "service-inventory.json"
)


def _print_line(prefix: str, summary: str, details: dict) -> None:
    """Emit a summary line + a JSON detail line for the applier's log."""
    sys.stdout.write(f"{prefix}: {summary}\n")
    sys.stdout.write(json.dumps(details, sort_keys=True) + "\n")


def _print_recovery(lines: list[str]) -> None:
    """Print manual-recovery guidance to stderr (no auto-rollback)."""
    sys.stderr.write("RECOVERY (manual — this deploy does not roll back):\n")
    for line in lines:
        sys.stderr.write(f"  - {line}\n")


def _run(argv: list[str], cwd: Path | None = None) -> tuple[int, str, str]:
    """Execute *argv* and return (returncode, stdout, stderr).

    A missing executable (``FileNotFoundError`` — e.g. ``systemctl`` absent
    from a non-office2 dry-run sandbox) is reported as rc=127 with the
    exception text on stderr rather than raising.
    """
    try:
        proc = subprocess.run(
            argv,
            capture_output=True,
            text=True,
            check=False,
            cwd=str(cwd) if cwd is not None else None,
        )
    except FileNotFoundError as exc:
        return 127, "", str(exc)
    return proc.returncode, proc.stdout, proc.stderr


# --------------------------------------------------------------------------- #
# Step 1 — install the systemd user units.
# --------------------------------------------------------------------------- #


def _step_install_units() -> tuple[bool, dict]:
    details: dict = {"dest_dir": str(_SYSTEMD_USER_DIR)}
    try:
        _SYSTEMD_USER_DIR.mkdir(parents=True, exist_ok=True)
        installed = []
        for unit_name in _UNIT_NAMES:
            src = _UNIT_SOURCE_DIR / unit_name
            dest = _SYSTEMD_USER_DIR / unit_name
            shutil.copyfile(src, dest)
            installed.append(str(dest))
        details["installed"] = installed
        return True, details
    except OSError as exc:
        details["error"] = str(exc)
        return False, details


# --------------------------------------------------------------------------- #
# Step 2 — daemon-reload (install the unit definitions; does NOT start anything).
# --------------------------------------------------------------------------- #


def _step_daemon_reload() -> tuple[bool, dict]:
    rc, stdout, stderr = _run(["systemctl", "--user", "daemon-reload"])
    details: dict = {"daemon_reload_rc": rc}
    if rc != 0:
        details["daemon_reload_stderr"] = stderr[:400]
        return False, details
    return True, details


# --------------------------------------------------------------------------- #
# Step 3 — dry-run self-test (no emit, no state mutation) + baseline gate.
#
# This runs BEFORE the timer is enabled (#711). A fresh detector must not go
# live emitting against an unverified baseline: if the dry-run reports ANY
# drift/assertion finding, that is a deploy-time signal the seeded baseline
# does not match live reality (e.g. the tz mismatch of #683) — the deploy
# fails here and the timer is left un-started so no false-positive ever pages
# the operator. Reconcile the baseline, then re-deploy.
# --------------------------------------------------------------------------- #


def _step_dry_run_self_test() -> tuple[bool, dict]:
    rc, stdout, stderr = _run(_SELF_TEST_ARGV, cwd=_REPO_ROOT)
    details: dict = {
        "self_test_rc": rc,
        "self_test_stdout_excerpt": stdout[:400],
        "self_test_stderr_excerpt": stderr[:400],
    }
    if rc != 0:
        details["self_test_fault"] = "scan could not run (see stderr excerpt)"
        return False, details

    # Parse the --json summary and gate on a clean baseline (0 findings).
    try:
        summary = json.loads(stdout.strip().splitlines()[-1])
    except (ValueError, IndexError) as exc:
        details["self_test_parse_error"] = str(exc)
        return False, details

    drift = summary.get("drift_findings")
    assertion = summary.get("assertion_findings")
    details["drift_findings"] = drift
    details["assertion_findings"] = assertion
    if not summary.get("ok") or drift or assertion:
        details["baseline_mismatch"] = (
            "dry-run reported findings against a fresh deploy — the approved-cron "
            "baseline (or assertion ledger) does not match live reality; reconcile "
            "before enabling the timer so no false-positive alerts fire"
        )
        return False, details

    return True, details


# --------------------------------------------------------------------------- #
# Step 4 — enable --now (ONLY after a clean dry-run self-test).
# --------------------------------------------------------------------------- #


def _step_enable_timer() -> tuple[bool, dict]:
    rc, stdout, stderr = _run(["systemctl", "--user", "enable", "--now", _TIMER_UNIT])
    details: dict = {"enable_now_rc": rc}
    if rc != 0:
        details["enable_now_stderr"] = stderr[:400]
        return False, details
    return True, details


# --------------------------------------------------------------------------- #
# Step 4 — prompt-sync trigger + deployed AGENTS.md verification.
# --------------------------------------------------------------------------- #


def _deployed_fleet_prompts() -> dict:
    """Resolve ``agent_slug -> deployed AGENTS.md Path`` for the doctrine fleet.

    Reads the canonical workspace mapping from service-inventory.json (the same
    source the prompt-sync pipeline uses) and restricts to the fleet agents
    that carry the doctrine block (:data:`FLEET_AGENTS`). Agents with no
    deployed workspace target (e.g. the retired ``felix-doc-auditor``
    scripts-first driver, absent from the inventory's agents map) are simply
    not present in the returned mapping — they have no deployed prompt to
    verify, so the deploy checks the subset that is actually deployed.
    """
    fleet = set(FLEET_AGENTS)
    resolved: dict = {}
    for agent in iter_agents(_SERVICE_INVENTORY):
        if agent.slug in fleet:
            resolved[agent.slug] = agent.workspace / "AGENTS.md"
    return resolved


def _step_prompt_sync_and_verify() -> tuple[bool, dict]:
    details: dict = {}

    rc, stdout, stderr = _run(
        ["systemctl", "--user", "start", "agent-prompt-sync.service"]
    )
    details["prompt_sync_start_rc"] = rc
    if rc != 0:
        details["prompt_sync_start_stderr"] = stderr[:400]
        return False, details

    # Verify the exact canonical doctrine block landed in EVERY deployed fleet
    # prompt (not a loose "truthful" substring on main only — Codex F4), and
    # the no-unrequested-infra block in main only. Reuses the same canonical
    # block source as the repo-source fleet-guard test so they cannot drift.
    deployed = _deployed_fleet_prompts()
    if not deployed:
        # Could not resolve any deployed prompt from the inventory — treat as a
        # verification failure rather than a silent pass.
        details["error"] = "no deployed fleet prompts resolved from service-inventory.json"
        details["inventory"] = str(_SERVICE_INVENTORY)
        return False, details

    check = check_deployed_doctrine(deployed)
    details["checked"] = check.checked
    details["missing_block"] = check.missing_block
    details["missing_main_only"] = check.missing_main_only
    return check.ok, details


# --------------------------------------------------------------------------- #
# dry-run / apply orchestration.
# --------------------------------------------------------------------------- #


def _dry_run() -> int:
    _print_line(
        "DRY-RUN",
        f"would install {', '.join(_UNIT_NAMES)} into {_SYSTEMD_USER_DIR}",
        {"units": list(_UNIT_NAMES)},
    )
    _print_line(
        "DRY-RUN",
        "would run `systemctl --user daemon-reload`",
        {},
    )
    _print_line(
        "DRY-RUN",
        "would run `python3 -m scripts.trust.run_trust_scan --dry-run --json` as a "
        "no-emit self-test and gate on 0 findings BEFORE enabling the timer",
        {"argv": _SELF_TEST_ARGV},
    )
    _print_line(
        "DRY-RUN",
        f"would (only if the self-test is clean) run `systemctl --user enable "
        f"--now {_TIMER_UNIT}`",
        {},
    )
    deployed = _deployed_fleet_prompts()
    _print_line(
        "DRY-RUN",
        "would trigger `systemctl --user start agent-prompt-sync.service` and "
        "verify the exact canonical truthful-reporting doctrine block is present "
        "in every deployed fleet prompt, plus the no-unrequested-infra block in "
        "main only",
        {
            "deployed_prompts": {slug: str(p) for slug, p in sorted(deployed.items())},
        },
    )
    return 0


def _report(*, ok: bool, phase: str, details: dict) -> None:
    """Best-effort outcome report via the #701 bus; never raises."""
    try:
        severity = Severity.INFO if ok else Severity.ERROR
        title = (
            "felix-trust-scan deploy succeeded"
            if ok
            else f"felix-trust-scan deploy failed: {phase}"
        )
        emit(
            Alert(
                source="felix-deployer/deploy-truthful-reporting",
                severity=severity,
                title=title,
                description=(
                    "Deployed the felix-trust-scan timer (clean dry-run self-test "
                    "gated the enable) + prompt-sync verification."
                    if ok
                    else f"Deploy halted at phase {phase!r}."
                ),
                details={key: str(value) for key, value in details.items()},
            )
        )
    except Exception:  # noqa: BLE001 - fail-safe: reporting must never break the deploy
        pass


def _apply() -> int:
    ok, details = _step_install_units()
    _print_line("APPLY", "install units " + ("OK" if ok else "FAILED"), details)
    if not ok:
        _print_recovery(
            [
                f"Confirm {_UNIT_SOURCE_DIR} contains {', '.join(_UNIT_NAMES)}.",
                f"Confirm {_SYSTEMD_USER_DIR} is writable by the claude user.",
            ]
        )
        _report(ok=False, phase="install_units", details=details)
        return 1

    ok, details = _step_daemon_reload()
    _print_line("APPLY", "daemon-reload " + ("OK" if ok else "FAILED"), details)
    if not ok:
        _print_recovery(
            [
                "Inspect the systemctl output above.",
                "Manually: systemctl --user daemon-reload",
            ]
        )
        _report(ok=False, phase="daemon_reload", details=details)
        return 1

    # Dry-run self-test BEFORE enabling the timer: no emit, and a gate on a
    # clean baseline so a fresh deploy never pages the operator (#711).
    ok, details = _step_dry_run_self_test()
    _print_line("APPLY", "dry-run self-test " + ("OK" if ok else "FAILED"), details)
    if not ok:
        _print_recovery(
            [
                "The dry-run self-test failed. Either the scan could not run "
                "(unreadable baseline — see self_test_stderr_excerpt) OR it "
                "reported findings against a fresh deploy (see baseline_mismatch).",
                "If baseline_mismatch: reconcile docs/design/architecture/data/"
                "approved-crons.json with `openclaw cron list --json`, push, let "
                "felix-deployer sync, then re-deploy. The timer was NOT started, "
                "so no false-positive alerts fired.",
                "Verify locally: python3 -m scripts.trust.run_trust_scan --dry-run --json",
            ]
        )
        _report(ok=False, phase="dry_run_self_test", details=details)
        return 1

    ok, details = _step_enable_timer()
    _print_line("APPLY", "enable timer " + ("OK" if ok else "FAILED"), details)
    if not ok:
        _print_recovery(
            [
                "Inspect the systemctl output above.",
                f"Manually: systemctl --user enable --now {_TIMER_UNIT}",
            ]
        )
        _report(ok=False, phase="enable_timer", details=details)
        return 1

    ok, details = _step_prompt_sync_and_verify()
    _print_line(
        "APPLY", "prompt-sync + AGENTS.md verify " + ("OK" if ok else "FAILED"), details
    )
    if not ok:
        _print_recovery(
            [
                "Confirm agent-prompt-sync.service ran successfully:",
                "  systemctl --user status agent-prompt-sync.service",
                "Confirm the canonical doctrine block landed in every deployed "
                "fleet prompt (see 'missing_block' above) and the "
                "no-unrequested-infra block in main (see 'missing_main_only').",
                "This may indicate WP01's doctrine commit has not reached main yet.",
            ]
        )
        _report(ok=False, phase="prompt_sync_verify", details=details)
        return 1

    _report(ok=True, phase="complete", details=details)
    return 0


def main(argv: list[str] | None = None) -> int:
    args = list(sys.argv[1:] if argv is None else argv)

    if len(args) != 1 or args[0] not in ("--dry-run", "--apply"):
        sys.stderr.write(
            "usage: deploy-truthful-reporting.py --dry-run|--apply\n"
        )
        return 2

    if args[0] == "--dry-run":
        return _dry_run()
    return _apply()


if __name__ == "__main__":  # pragma: no cover - module entry
    sys.exit(main())
