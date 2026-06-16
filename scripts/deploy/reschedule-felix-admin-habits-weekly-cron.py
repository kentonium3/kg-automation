#!/usr/bin/env python3
"""Deploy entrypoint — move felix-admin-habits weekly cron to Mon 06:00 ET.

Mission: ``trustworthy-weekly-habit-report-01KV4GZ7`` (issue
kentonium3/kg-automation#605).

Invoked by the felix-deployer applier from the corresponding manifest at
``deploys/queued/reschedule-felix-admin-habits-weekly-cron.yaml``.

This entrypoint does NOT use ``scripts.deploy.lib.cron.openclaw_cron_edit``.
That primitive invokes ``openclaw cron edit --name <name> --schedule <expr>``,
but OpenClaw 2026.6.5 wants ``openclaw cron edit <uuid> --cron <expr>`` —
positional UUID, ``--cron`` not ``--schedule``. The library's cron primitives
(disable/enable/edit) all share the same wrong-flag-shape defect. Tracked as
a follow-up internal P3-bug; bypassed here with a direct subprocess to keep
the WP05 deploy moving.

CLI contract (per docs/runbooks/deploy/discipline.md):

* ``--dry-run`` — print what would happen; NO side effects on office2.
* ``--apply`` — invoke ``openclaw cron edit`` and report the result.

Exit codes
----------
* ``0`` — dry-run printed; OR apply edited the cron (or it was already at
  the target schedule — idempotency caught by the openclaw layer).
* ``1`` — apply failed (openclaw subprocess non-zero, or the named cron is
  not registered).
* ``2`` — usage error (missing / wrong-shaped mode argument).
"""
from __future__ import annotations

import json
import subprocess
import sys


# Identifiers — keep stable so the manifest can reference them.
CRON_NAME: str = "habits-weekly-report"
NEW_SCHEDULE: str = "0 6 * * 1"  # Monday 06:00 office2-local (ET)
_OPENCLAW: str = "openclaw"


def _print_line(prefix: str, summary: str, details: dict) -> None:
    """Emit summary + JSON-details lines for the applier's log."""
    sys.stdout.write(f"{prefix}: {summary}\n")
    sys.stdout.write(json.dumps(details, sort_keys=True) + "\n")


def _resolve_cron_id(cron_name: str) -> tuple[str | None, dict | None]:
    """Return (cron_id, full_job_dict) for ``cron_name``, or (None, None).

    Lists openclaw crons as JSON and finds the job whose ``name`` matches.
    OpenClaw's CLI takes the UUID (``id``) positionally; ``name`` is purely
    a display field, so we have to look it up.
    """
    proc = subprocess.run(
        [_OPENCLAW, "cron", "list", "--json"],
        capture_output=True,
        text=True,
        check=False,
    )
    if proc.returncode != 0:
        return None, {
            "error": "openclaw cron list failed",
            "returncode": proc.returncode,
            "stderr_excerpt": proc.stderr[:400],
        }
    try:
        payload = json.loads(proc.stdout)
    except json.JSONDecodeError as exc:
        return None, {
            "error": f"openclaw cron list returned non-JSON: {exc}",
            "stdout_excerpt": proc.stdout[:400],
        }
    jobs = payload.get("jobs") if isinstance(payload, dict) else None
    if not isinstance(jobs, list):
        return None, {
            "error": "openclaw cron list payload missing 'jobs' array",
            "keys": list(payload.keys()) if isinstance(payload, dict) else None,
        }
    for job in jobs:
        if isinstance(job, dict) and job.get("name") == cron_name:
            return job.get("id"), job
    return None, {
        "error": f"cron {cron_name!r} not registered",
        "available_names": [j.get("name") for j in jobs if isinstance(j, dict)],
    }


def _dry_run() -> int:
    """Report the intended edit without invoking ``openclaw cron edit``."""
    cron_id, info = _resolve_cron_id(CRON_NAME)
    if cron_id is None:
        # Same failure surface as apply would hit; surface it in dry-run too
        # so the operator catches misconfiguration before --apply runs.
        _print_line("DRY-RUN", f"cannot resolve cron {CRON_NAME!r}", info or {})
        return 1
    current_schedule = (info or {}).get("schedule", {}).get("expr")
    _print_line(
        prefix="DRY-RUN",
        summary=(
            f"would edit openclaw cron {CRON_NAME!r} (id={cron_id}): "
            f"--cron {NEW_SCHEDULE!r} (current: {current_schedule!r})"
        ),
        details={
            "cron_name": CRON_NAME,
            "cron_id": cron_id,
            "current_schedule": current_schedule,
            "target_schedule": NEW_SCHEDULE,
            "mode": "dry-run",
        },
    )
    return 0


def _apply() -> int:
    """Subprocess ``openclaw cron edit <uuid> --cron <expr>`` and report."""
    cron_id, info = _resolve_cron_id(CRON_NAME)
    if cron_id is None:
        _print_line("APPLY", f"cannot resolve cron {CRON_NAME!r}", info or {})
        return 1
    argv = [_OPENCLAW, "cron", "edit", cron_id, "--cron", NEW_SCHEDULE]
    proc = subprocess.run(
        argv,
        capture_output=True,
        text=True,
        check=False,
    )
    details = {
        "argv": argv,
        "returncode": proc.returncode,
        "stdout_excerpt": proc.stdout[:400],
        "stderr_excerpt": proc.stderr[:400],
    }
    if proc.returncode != 0:
        _print_line(
            "APPLY",
            f"openclaw cron edit failed (rc={proc.returncode})",
            details,
        )
        return 1
    _print_line(
        "APPLY",
        f"openclaw cron {CRON_NAME!r} (id={cron_id}) edited: --cron {NEW_SCHEDULE!r}",
        details,
    )
    return 0


def main(argv: list[str] | None = None) -> int:
    args = list(sys.argv[1:] if argv is None else argv)
    if len(args) != 1 or args[0] not in ("--dry-run", "--apply"):
        sys.stderr.write(
            "usage: reschedule-felix-admin-habits-weekly-cron.py --dry-run|--apply\n"
        )
        return 2
    if args[0] == "--dry-run":
        return _dry_run()
    return _apply()


if __name__ == "__main__":  # pragma: no cover - module entry
    sys.exit(main())
