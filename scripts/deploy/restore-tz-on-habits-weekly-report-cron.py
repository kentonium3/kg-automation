#!/usr/bin/env python3
"""Deploy entrypoint — restore the America/New_York TZ on habits-weekly-report.

Mission follow-up: kentonium3/kg-automation#605 +
``trustworthy-weekly-habit-report-01KV4GZ7`` shipped the cron reschedule
in commit ``290a36d2`` / applied at ``7eba774b``, but the
``openclaw cron edit <id> --cron <expr>`` call (without ``--tz``) reset
the cron's timezone to openclaw's default (UTC). The original cron had
``tz: America/New_York`` so it fired at Sunday 22:00 ET (= 02:00 UTC
Mon EDT). The new cron fires at 06:00 UTC = 02:00 ET Mon, four hours
earlier than the intended 06:00 ET wall clock.

This entrypoint patches just the ``tz`` field. The cron expression is
left alone so the openclaw layer sees an idempotent edit-tz-only call.

CLI contract (per docs/runbooks/deploy/discipline.md):

* ``--dry-run`` — print what would happen; NO side effects on office2.
* ``--apply`` — invoke ``openclaw cron edit <uuid> --tz America/New_York``.

Exit codes
----------
* ``0`` — dry-run reported; OR apply set the tz (idempotent at openclaw
  layer if already at target).
* ``1`` — apply failed.
* ``2`` — usage error.
"""
from __future__ import annotations

import json
import subprocess
import sys


CRON_NAME: str = "habits-weekly-report"
TARGET_TZ: str = "America/New_York"
_OPENCLAW: str = "openclaw"


def _print_line(prefix: str, summary: str, details: dict) -> None:
    sys.stdout.write(f"{prefix}: {summary}\n")
    sys.stdout.write(json.dumps(details, sort_keys=True) + "\n")


def _resolve_cron_id(cron_name: str) -> tuple[str | None, dict | None]:
    """Return (cron_id, full_job_dict) for ``cron_name``, or (None, None)."""
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
    cron_id, info = _resolve_cron_id(CRON_NAME)
    if cron_id is None:
        _print_line("DRY-RUN", f"cannot resolve cron {CRON_NAME!r}", info or {})
        return 1
    current_tz = (info or {}).get("schedule", {}).get("tz")
    current_expr = (info or {}).get("schedule", {}).get("expr")
    _print_line(
        prefix="DRY-RUN",
        summary=(
            f"would edit openclaw cron {CRON_NAME!r} (id={cron_id}): "
            f"--tz {TARGET_TZ!r} (current tz: {current_tz!r}; expr unchanged at {current_expr!r})"
        ),
        details={
            "cron_name": CRON_NAME,
            "cron_id": cron_id,
            "current_tz": current_tz,
            "current_expr": current_expr,
            "target_tz": TARGET_TZ,
            "mode": "dry-run",
        },
    )
    return 0


def _apply() -> int:
    cron_id, info = _resolve_cron_id(CRON_NAME)
    if cron_id is None:
        _print_line("APPLY", f"cannot resolve cron {CRON_NAME!r}", info or {})
        return 1
    argv = [_OPENCLAW, "cron", "edit", cron_id, "--tz", TARGET_TZ]
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
        f"openclaw cron {CRON_NAME!r} (id={cron_id}) edited: --tz {TARGET_TZ!r}",
        details,
    )
    return 0


def main(argv: list[str] | None = None) -> int:
    args = list(sys.argv[1:] if argv is None else argv)
    if len(args) != 1 or args[0] not in ("--dry-run", "--apply"):
        sys.stderr.write(
            "usage: restore-tz-on-habits-weekly-report-cron.py --dry-run|--apply\n"
        )
        return 2
    if args[0] == "--dry-run":
        return _dry_run()
    return _apply()


if __name__ == "__main__":  # pragma: no cover - module entry
    sys.exit(main())
