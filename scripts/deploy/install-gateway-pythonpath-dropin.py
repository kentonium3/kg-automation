#!/usr/bin/env python3
"""Deploy entrypoint — install PYTHONPATH systemd drop-in for openclaw-gateway.

Mission: ``felix-admin-cron-path-fix-01KWQTY3`` (issue kentonium3/kg-automation#656).

Ships FR-001/FR-002: exports ``PYTHONPATH=/home/claude/kg-automation`` into the
``openclaw-gateway.service`` process environment via a systemd **drop-in** rather
than an edit to the base unit (avoids collision with #653's in-flight ExecStart
relocation).

The drop-in propagates to all agent subprocesses (Node ``child_process`` inherits
``process.env``), so ``python3 -m scripts.*`` resolves from **any** working directory
for every OpenClaw agent without per-agent cwd discipline.

CLI contract (per docs/runbooks/deploy/discipline.md):

* ``--dry-run`` — print planned operations; NO side effects on office2.
* ``--apply``   — install drop-in, reload daemon, restart gateway, verify env.

Exit codes
----------
* 0 — dry-run printed; OR apply succeeded (drop-in installed + env verified).
* 1 — apply failed (copy, systemctl, or verification failure).
* 2 — usage error (missing / wrong-shaped mode argument).

Invocation note: felix-deployer invokes entrypoints by file path
(``subprocess.run([path, "--dry-run"], shell=False)``), NOT via ``python3 -m``.
The sys.path shim below is not strictly needed for this script (it imports only
stdlib), but is included for consistency with the project convention.

SC-10 verification strategy
----------------------------
* SC-10a (declared-value sanity): ``systemctl --user show -p Environment`` confirms
  the value the unit will export to new processes.
* SC-10b (live-process gate): reads ``/proc/<MainPID>/environ`` of the running
  gateway (``systemctl --user show -p MainPID --value``).  The gateway is a
  ``systemctl --user`` service whose children — the Node ``child_process``
  subprocesses that run agent tool calls — inherit ``process.env`` by default.
  Confirming ``PYTHONPATH`` in the gateway's own /proc/environ is the
  deterministic, side-effect-free proof that agent subprocesses will carry it.
  **Do NOT** use ``openclaw cron run`` / ``openclaw agent`` in this gate — that
  would launch a full billed LLM turn with side effects.
* The DEFINITIVE real-agent confirmation (belt) is the operator's post-deploy
  step: run ``openclaw cron runs`` and observe status=success with no
  ModuleNotFoundError.  That step is documented in quickstart.md SC-1/SC-2 and
  is intentionally outside this automated gate.
"""
from __future__ import annotations

import shutil
import subprocess
import sys
from pathlib import Path

# sys.path shim — kept for convention consistency; this script imports stdlib only.
_REPO_ROOT = Path(__file__).resolve().parents[2]

# Source drop-in (repo-relative; tracked in git).
_SOURCE_CONF = _REPO_ROOT / "scripts" / "openclaw" / "openclaw-gateway.service.d" / "pythonpath.conf"

# Target systemd user drop-in directory for the claude user on office2.
# HOME=/home/claude is set in the gateway unit; Path.home() reads from $HOME or
# /etc/passwd — in the deployer context (running as claude) this yields /home/claude.
_TARGET_DIR = Path.home() / ".config" / "systemd" / "user" / "openclaw-gateway.service.d"
_TARGET_CONF = _TARGET_DIR / "pythonpath.conf"

_UNIT = "openclaw-gateway.service"
_EXPECTED_PYTHONPATH = "/home/claude/kg-automation"


def _print_line(prefix: str, summary: str) -> None:
    """Emit a single tagged output line for the applier's log."""
    sys.stdout.write(f"{prefix}: {summary}\n")


def _dry_run() -> int:
    """Report planned operations without executing any."""
    _print_line("DRY-RUN", f"source: {_SOURCE_CONF}")
    _print_line("DRY-RUN", f"source exists: {_SOURCE_CONF.exists()}")
    _print_line("DRY-RUN", f"target dir: {_TARGET_DIR}")
    _print_line("DRY-RUN", f"target file: {_TARGET_CONF}")
    _print_line("DRY-RUN", f"target already installed: {_TARGET_CONF.exists()}")
    _print_line("DRY-RUN", "would run: systemctl --user daemon-reload")
    _print_line("DRY-RUN", f"would run: systemctl --user restart {_UNIT}")
    _print_line(
        "DRY-RUN",
        f"would verify (SC-10a): systemctl --user show {_UNIT} -p Environment"
        f" contains PYTHONPATH={_EXPECTED_PYTHONPATH}",
    )
    _print_line(
        "DRY-RUN",
        f"would get gateway MainPID: systemctl --user show -p MainPID --value {_UNIT}",
    )
    _print_line(
        "DRY-RUN",
        f"would verify (SC-10b): /proc/<MainPID>/environ contains"
        f" PYTHONPATH={_EXPECTED_PYTHONPATH} (live gateway process env,"
        " proves agent subprocess inheritance)",
    )
    return 0


def _run_systemctl(*args: str) -> tuple[int, str, str]:
    """Run a ``systemctl --user <args>`` command; return (returncode, stdout, stderr)."""
    argv = ["systemctl", "--user", *args]
    proc = subprocess.run(argv, capture_output=True, text=True, check=False)
    return proc.returncode, proc.stdout, proc.stderr


def _apply() -> int:
    """Install the drop-in, reload daemon, restart gateway, and verify."""
    # 1. Validate source exists.
    if not _SOURCE_CONF.exists():
        _print_line("APPLY", f"FAILED: source drop-in not found: {_SOURCE_CONF}")
        return 1

    # 2. Create target directory (idempotent).
    _TARGET_DIR.mkdir(parents=True, exist_ok=True)
    _print_line("APPLY", f"target dir ensured: {_TARGET_DIR}")

    # 3. Copy drop-in (idempotent — overwrites identical content harmlessly).
    shutil.copy2(str(_SOURCE_CONF), str(_TARGET_CONF))
    _print_line("APPLY", f"installed: {_TARGET_CONF}")

    # 4. Reload systemd user daemon so it picks up the new drop-in.
    rc, _, stderr = _run_systemctl("daemon-reload")
    if rc != 0:
        _print_line("APPLY", f"FAILED: daemon-reload returned rc={rc}: {stderr[:200]}")
        return 1
    _print_line("APPLY", "daemon-reload ok")

    # 5. Restart the gateway to apply the new environment.
    rc, _, stderr = _run_systemctl("restart", _UNIT)
    if rc != 0:
        _print_line("APPLY", f"FAILED: restart {_UNIT} returned rc={rc}: {stderr[:200]}")
        return 1
    _print_line("APPLY", f"restarted: {_UNIT}")

    # 6. SC-10a: Verify PYTHONPATH appears in the unit's active environment.
    rc, stdout, stderr = _run_systemctl("show", _UNIT, "-p", "Environment")
    if rc != 0:
        _print_line("APPLY", f"FAILED: systemctl show returned rc={rc}: {stderr[:200]}")
        return 1
    if f"PYTHONPATH={_EXPECTED_PYTHONPATH}" not in stdout:
        _print_line(
            "APPLY",
            f"FAILED (SC-10a): PYTHONPATH={_EXPECTED_PYTHONPATH!r} not found in unit environment. "
            f"Got: {stdout[:300]}",
        )
        return 1
    _print_line("APPLY", f"SC-10a ok: PYTHONPATH={_EXPECTED_PYTHONPATH} confirmed in unit env")

    # 7. SC-10b: Verify PYTHONPATH is in the live gateway process's own environment.
    #    The gateway is a systemctl --user service.  OpenClaw spawns agent tool-call
    #    subprocesses as Node child_process children of the gateway, which inherit
    #    process.env by default.  Reading /proc/<MainPID>/environ of the running
    #    gateway is the deterministic, side-effect-free proof that agent subprocesses
    #    will carry PYTHONPATH — it proves the running gateway actually has the value,
    #    not just that the unit declares it.
    #    NOTE: running `openclaw cron run` / `openclaw agent` here is NOT appropriate —
    #    that launches a full billed LLM turn with side effects.  The DEFINITIVE
    #    real-agent confirmation is the operator's post-deploy step (quickstart.md SC-1/SC-2).

    # 7a. Get the gateway's MainPID.
    rc, pid_stdout, pid_stderr = _run_systemctl("show", "-p", "MainPID", "--value", _UNIT)
    if rc != 0:
        _print_line(
            "APPLY",
            f"FAILED (SC-10b): could not get MainPID from systemctl: {pid_stderr[:200]}",
        )
        return 1
    main_pid = pid_stdout.strip()
    if not main_pid or main_pid == "0":
        _print_line(
            "APPLY",
            f"FAILED (SC-10b): gateway not running — MainPID={main_pid!r}. "
            f"Ensure {_UNIT} is active before verifying.",
        )
        return 1
    _print_line("APPLY", f"SC-10b: gateway MainPID={main_pid}")

    # 7b. Read the live process environment and assert the exact PYTHONPATH entry.
    proc_environ_path = Path(f"/proc/{main_pid}/environ")
    try:
        raw = proc_environ_path.read_bytes()
    except OSError as exc:
        _print_line(
            "APPLY",
            f"FAILED (SC-10b): cannot read {proc_environ_path}: {exc}",
        )
        return 1

    entries = raw.split(b"\x00")
    target_entry = f"PYTHONPATH={_EXPECTED_PYTHONPATH}".encode()
    if target_entry not in entries:
        pythonpath_entries = [
            e.decode(errors="replace")
            for e in entries
            if e.startswith(b"PYTHONPATH")
        ]
        _print_line(
            "APPLY",
            f"FAILED (SC-10b): PYTHONPATH={_EXPECTED_PYTHONPATH!r} not found in "
            f"/proc/{main_pid}/environ. "
            f"PYTHONPATH entries present: {pythonpath_entries!r}. "
            "Drop-in may not have taken effect — check daemon-reload and restart.",
        )
        return 1
    _print_line(
        "APPLY",
        f"SC-10b ok: PYTHONPATH={_EXPECTED_PYTHONPATH} confirmed in "
        f"/proc/{main_pid}/environ (live gateway process env — agent subprocesses inherit this)",
    )

    _print_line("APPLY", "ALL OK: drop-in installed, gateway restarted, PYTHONPATH verified")
    return 0


def main(argv: list[str] | None = None) -> int:
    args = list(sys.argv[1:] if argv is None else argv)
    if len(args) != 1 or args[0] not in ("--dry-run", "--apply"):
        sys.stderr.write(
            "usage: install-gateway-pythonpath-dropin.py --dry-run|--apply\n"
        )
        return 2
    return _dry_run() if args[0] == "--dry-run" else _apply()


if __name__ == "__main__":  # pragma: no cover - module entry
    sys.exit(main())
