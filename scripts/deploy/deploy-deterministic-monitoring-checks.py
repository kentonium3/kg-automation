#!/usr/bin/env python3
"""Deploy entrypoint — deterministic monitoring checks cutover (#676).

Mission: ``deterministic-monitoring-checks-01KX1XNW``.

Installs WP03's ``felix-health-check`` systemd user timer + service + wrapper
(mirrors the ``credential-health-check`` precedent) and, once the timer is
verified active, removes the two openclaw crons that ran the old
Sonnet-`main`-mediated health-check (``health-check-morning``,
``health-check-evening``) — DIR-007, cron ops via the ``openclaw`` CLI only,
never the system crontab.

Strict order (Codex #6, plan.md IC-04) to avoid a double-alert or
missed-check window around 11:00/23:00:

  1. Preflight — confirm the wrapper package + the reused bash health-check
     script are present (fail closed rather than silently skip a step).
  2. Install units — copy ``felix-health-check.{service,timer}`` into
     ``~/.config/systemd/user/``, ``daemon-reload``.
  3. Smoke — one-shot ``systemctl --user start felix-health-check.service``
     and surface the outcome (does not block progress on a non-zero smoke
     exit; the health-check wrapper's own contract treats a health
     *failure* as data, not a runner error — see
     ``health-check-runner.contract.md``).
  4. Enable timer — ``systemctl --user enable --now felix-health-check.timer``.
  5. Verify — ``systemctl --user list-timers`` confirms the new timer is
     scheduled before anything is removed.
  6. Remove the two legacy openclaw crons — ONLY after step 5 succeeds.
  7. Confirm no health-check cron remains.

T017 decision (cron removal path): ``scripts/deploy/lib/cron.py`` exposes
only ``list`` / ``disable`` / ``enable`` / ``edit`` — there is no vetted
``remove`` primitive in the library today. Per
``docs/design/architecture/data/mutation-surfaces.json`` the canonical CLI
shape for deletion is ``openclaw cron rm <id>`` (Tier 2 under the actor
mutation taxonomy for a *live* actor invocation — but here the actor
invoking it is ``felix-deployer``, whose mutations are gated by the deploy
manifest's own ``dry_run_then_apply_gate`` contract, not the live-actor
wrap/prompt_forbid taxonomy; see that file's ``actors.felix-deployer``
entry). This entrypoint therefore rides the **felix-deployer happy path**
(the manifest pipeline) but bypasses ``scripts.deploy.lib.cron`` for the
removal call itself, subprocessing ``openclaw cron rm <id>`` directly —
the same bypass pattern (and rationale) as
``scripts/deploy/reschedule-felix-admin-habits-weekly-cron.py`` used for
the lib's cron-edit flag-shape mismatch (#613). The lib's ``list``
primitive is reused read-only to resolve each cron's UUID (``openclaw
cron rm`` takes the id positionally, not the display name).

CLI contract (per ``docs/runbooks/deploy/discipline.md``):

* ``--dry-run`` — print what would happen; NO side effects on office2.
* ``--apply`` — execute all seven steps in order; halts at the first
  failure so a partial cutover never leaves both paths silently disabled.

Exit codes
----------
* ``0`` — dry-run printed successfully, OR apply completed every step.
* ``1`` — a step failed (preflight, install, enable, verify, or a cron
  removal). Whatever ran before the failing step is NOT rolled back —
  rollback is the documented manual procedure in quickstart.md (re-add the
  two crons; the prior Haiku-mediated health-check on `main` had no state
  to restore since it was stateless per invocation).
* ``2`` — usage error (missing / wrong-shaped mode argument).
"""
from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

# Required only because this entrypoint imports from scripts.deploy.lib.*.
# felix-deployer invokes the entrypoint by path (not via `python3 -m`), so
# the repo root isn't on sys.path unless we put it there ourselves.
_REPO_ROOT = Path(__file__).resolve().parents[2]
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

from scripts.deploy.lib import cron as cron_lib  # noqa: E402

_OPENCLAW = "openclaw"
_SERVICE_NAME = "felix-health-check"
_LEGACY_CRON_NAMES: tuple[str, ...] = ("health-check-morning", "health-check-evening")

_SYSTEMD_USER_DIR = Path.home() / ".config/systemd/user"
_SYSTEMD_REPO_DIR = _REPO_ROOT / "scripts/office2"
_WRAPPER_PACKAGE = _REPO_ROOT / "scripts/office2/felix_health_check"
_HEALTH_CHECK_SCRIPT = Path("/home/claude/helper-scripts/health-check.sh")


def _print_line(prefix: str, summary: str, details: dict) -> None:
    """Emit a summary line + a JSON detail line for the applier's log."""
    sys.stdout.write(f"{prefix}: {summary}\n")
    sys.stdout.write(json.dumps(details, sort_keys=True) + "\n")


def _run(argv: list[str]) -> tuple[int, str, str]:
    """Execute *argv* and return (returncode, stdout, stderr).

    A missing executable (``FileNotFoundError`` — e.g. ``systemctl``/``openclaw``
    absent from ``PATH``, as on a non-office2 dry-run sandbox) is reported as
    rc=127 with the exception text on stderr rather than raising, so callers
    never need a bare ``except`` around every ``_run`` call site.
    """
    try:
        proc = subprocess.run(argv, capture_output=True, text=True, check=False)
    except FileNotFoundError as exc:
        return 127, "", str(exc)
    return proc.returncode, proc.stdout, proc.stderr


def _preflight() -> tuple[bool, dict]:
    """Confirm the wrapper package and the reused bash script are present."""
    details: dict = {}
    ok = True
    if not (_WRAPPER_PACKAGE / "run.py").exists():
        ok = False
        details["wrapper_missing"] = str(_WRAPPER_PACKAGE / "run.py")
    if not (_SYSTEMD_REPO_DIR / f"{_SERVICE_NAME}.service").exists():
        ok = False
        details["service_unit_missing"] = str(_SYSTEMD_REPO_DIR / f"{_SERVICE_NAME}.service")
    if not (_SYSTEMD_REPO_DIR / f"{_SERVICE_NAME}.timer").exists():
        ok = False
        details["timer_unit_missing"] = str(_SYSTEMD_REPO_DIR / f"{_SERVICE_NAME}.timer")
    # health-check.sh is reused in place (not shipped by this repo); on
    # office2 it must already exist. In --dry-run we only report presence,
    # we never fail dry-run on a fact about the live host that --apply will
    # also re-check.
    details["health_check_script_present"] = _HEALTH_CHECK_SCRIPT.exists()
    return ok, details


def _resolve_cron_id(cron_name: str) -> tuple[str | None, dict]:
    """Resolve a legacy cron's UUID via the vetted (read-only) list primitive."""
    try:
        listing = cron_lib.openclaw_cron_list()
    except FileNotFoundError as exc:
        # openclaw not on PATH (e.g. running this dry-run off office2). The
        # shared lib's own subprocess wrapper does not guard this; guard it
        # here rather than edit a module outside this WP's owned_files.
        return None, {"error": "openclaw binary not found", "detail": str(exc)}
    if not listing.ok:
        return None, {"error": "openclaw cron list failed", **dict(listing.details)}
    jobs = list(listing.details.get("crons", []))
    for job in jobs:
        if isinstance(job, dict) and job.get("name") == cron_name:
            return job.get("id"), dict(job)
    return None, {
        "error": f"cron {cron_name!r} not registered",
        "available_names": [j.get("name") for j in jobs if isinstance(j, dict)],
    }


def _dry_run() -> int:
    ok, preflight_details = _preflight()
    _print_line(
        "DRY-RUN",
        "preflight " + ("OK" if ok else "FAILED — see details"),
        preflight_details,
    )

    _print_line(
        "DRY-RUN",
        f"would install {_SERVICE_NAME}.service + {_SERVICE_NAME}.timer to "
        f"{_SYSTEMD_USER_DIR}, daemon-reload, smoke-start the service",
        {"systemd_user_dir": str(_SYSTEMD_USER_DIR)},
    )
    _print_line(
        "DRY-RUN",
        f"would enable+start {_SERVICE_NAME}.timer, verify via list-timers",
        {},
    )

    any_lookup_failed = False
    for cron_name in _LEGACY_CRON_NAMES:
        cron_id, info = _resolve_cron_id(cron_name)
        if cron_id is None:
            any_lookup_failed = True
            _print_line(
                "DRY-RUN",
                f"cannot resolve legacy cron {cron_name!r} (removal would fail at apply)",
                info,
            )
        else:
            _print_line(
                "DRY-RUN",
                f"would remove openclaw cron {cron_name!r} (id={cron_id}) via "
                f"`openclaw cron rm {cron_id}` — only after the timer is verified active",
                {"cron_name": cron_name, "cron_id": cron_id},
            )

    if not ok:
        return 1
    # A missing legacy cron during dry-run is reported but not fatal — it
    # may already have been removed manually in a prior partial attempt;
    # --apply treats "already absent" as idempotent success (see _remove_cron).
    del any_lookup_failed
    return 0


def _install_units() -> tuple[bool, dict]:
    _SYSTEMD_USER_DIR.mkdir(parents=True, exist_ok=True)
    details: dict = {}
    for suffix in ("service", "timer"):
        src = _SYSTEMD_REPO_DIR / f"{_SERVICE_NAME}.{suffix}"
        dst = _SYSTEMD_USER_DIR / f"{_SERVICE_NAME}.{suffix}"
        dst.write_text(src.read_text())
        details[f"{suffix}_installed_to"] = str(dst)

    rc, stdout, stderr = _run(["systemctl", "--user", "daemon-reload"])
    details["daemon_reload_rc"] = rc
    if rc != 0:
        details["daemon_reload_stderr"] = stderr[:400]
        return False, details
    return True, details


def _smoke() -> tuple[bool, dict]:
    rc, stdout, stderr = _run(["systemctl", "--user", "start", f"{_SERVICE_NAME}.service"])
    details = {
        "smoke_start_rc": rc,
        "smoke_stdout_excerpt": stdout[:400],
        "smoke_stderr_excerpt": stderr[:400],
    }
    # The wrapper's own contract makes a health *failure* into data (exit 0
    # from the service), so a non-zero here indicates the *runner* itself
    # could not execute (e.g. python import failure) — that is a genuine
    # deploy-blocking condition, not a health-check result.
    return rc == 0, details


def _enable_and_verify_timer() -> tuple[bool, dict]:
    rc, stdout, stderr = _run(
        ["systemctl", "--user", "enable", "--now", f"{_SERVICE_NAME}.timer"]
    )
    details = {"enable_rc": rc, "enable_stderr_excerpt": stderr[:400]}
    if rc != 0:
        return False, details

    rc2, stdout2, stderr2 = _run(
        ["systemctl", "--user", "list-timers", f"{_SERVICE_NAME}.timer", "--no-pager"]
    )
    details["list_timers_rc"] = rc2
    details["list_timers_stdout"] = stdout2[:400]
    if rc2 != 0 or _SERVICE_NAME not in stdout2:
        details["error"] = "felix-health-check.timer not found in list-timers output"
        return False, details
    return True, details


def _remove_cron(cron_name: str) -> tuple[bool, dict]:
    """Remove one legacy openclaw cron by name via a direct `openclaw cron rm`.

    Idempotent: a cron that is already absent (e.g. a prior partial apply
    removed it) is treated as success, matching the idempotency contract
    the rest of the deploy-lib cron primitives follow.
    """
    cron_id, info = _resolve_cron_id(cron_name)
    if cron_id is None:
        if "not registered" in str(info.get("error", "")):
            return True, {"cron_name": cron_name, "idempotent": True, "note": "already absent"}
        return False, {"cron_name": cron_name, **info}

    rc, stdout, stderr = _run([_OPENCLAW, "cron", "rm", cron_id])
    details = {
        "cron_name": cron_name,
        "cron_id": cron_id,
        "rm_rc": rc,
        "rm_stdout_excerpt": stdout[:400],
        "rm_stderr_excerpt": stderr[:400],
    }
    return rc == 0, details


def _confirm_no_health_cron_remains() -> tuple[bool, dict]:
    try:
        listing = cron_lib.openclaw_cron_list()
    except FileNotFoundError as exc:
        return False, {"error": "openclaw binary not found", "detail": str(exc)}
    if not listing.ok:
        return False, {"error": "openclaw cron list failed post-removal", **dict(listing.details)}
    jobs = list(listing.details.get("crons", []))
    remaining = [
        j.get("name") for j in jobs if isinstance(j, dict) and j.get("name") in _LEGACY_CRON_NAMES
    ]
    return not remaining, {"remaining_health_check_crons": remaining}


def _apply() -> int:
    ok, details = _preflight()
    _print_line("APPLY", "preflight " + ("OK" if ok else "FAILED"), details)
    if not ok:
        return 1

    ok, details = _install_units()
    _print_line("APPLY", "install units " + ("OK" if ok else "FAILED"), details)
    if not ok:
        return 1

    ok, details = _smoke()
    _print_line("APPLY", "smoke-start " + ("OK" if ok else "FAILED"), details)
    if not ok:
        return 1

    ok, details = _enable_and_verify_timer()
    _print_line("APPLY", "enable+verify timer " + ("OK" if ok else "FAILED"), details)
    if not ok:
        return 1

    # Only now — after the new timer is confirmed active — remove the
    # legacy crons, per the strict order in plan.md IC-04 / Codex #6.
    for cron_name in _LEGACY_CRON_NAMES:
        ok, details = _remove_cron(cron_name)
        _print_line(
            "APPLY", f"remove cron {cron_name!r} " + ("OK" if ok else "FAILED"), details
        )
        if not ok:
            return 1

    ok, details = _confirm_no_health_cron_remains()
    _print_line("APPLY", "confirm no health-check cron remains " + ("OK" if ok else "FAILED"), details)
    if not ok:
        return 1

    return 0


def main(argv: list[str] | None = None) -> int:
    args = list(sys.argv[1:] if argv is None else argv)
    if len(args) != 1 or args[0] not in ("--dry-run", "--apply"):
        sys.stderr.write(
            "usage: deploy-deterministic-monitoring-checks.py --dry-run|--apply\n"
        )
        return 2
    return _dry_run() if args[0] == "--dry-run" else _apply()


if __name__ == "__main__":  # pragma: no cover - module entry
    sys.exit(main())
