"""Deploy entrypoint — move felix-admin-habits weekly cron to Mon 06:00 ET.

Mission: ``trustworthy-weekly-habit-report-01KV4GZ7`` (issue
kentonium3/kg-automation#605).

Invoked by the felix-deployer applier from the corresponding manifest at
``deploys/queued/reschedule-felix-admin-habits-weekly-cron.yaml``. The
entrypoint is intentionally a thin wrapper over
:func:`scripts.deploy.lib.cron.openclaw_cron_edit`; all the heavy lifting
(idempotency, NOT_FOUND refusal, openclaw subprocess wrangling) lives in
the library primitive.

The schedule string is passed through verbatim to ``openclaw cron edit``,
which is the canonical scheduler on office2. The cron primitive does NOT
support a separate TZ field — openclaw interprets the cron string in its
own configured timezone (office2's host TZ). The companion AGENTS.md edit
in WP04 and the architecture-doc edits in WP06 document the target wall
clock as **Monday 06:00 America/New_York**.

CLI contract (per docs/runbooks/deploy/discipline.md):

* ``--dry-run`` — print what would happen; NO side effects on office2.
* ``--apply`` — invoke ``openclaw_cron_edit`` and report the result.

Exit codes
----------
* ``0`` — dry-run reported successfully, OR apply edited the cron (the
  openclaw primitive is idempotent at the openclaw layer, so re-runs after
  the cron is already at the target schedule still exit 0).
* ``1`` — apply failed (LibResult.summary on stderr; details on stdout as
  JSON for the applier to log).
* ``2`` — usage error (missing / wrong-shaped mode argument).
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

# The felix-deployer applier invokes this entrypoint by path
# (``scripts/deploy/reschedule-felix-admin-habits-weekly-cron.py --dry-run``),
# NOT via ``python3 -m``. Without this shim, ``from scripts.deploy.lib...``
# raises ModuleNotFoundError because the repo root isn't on sys.path. Adding
# it here (instead of relying on the runner to set PYTHONPATH) keeps the
# entrypoint self-contained and matches what the runbook example does for
# bash entrypoints.
_REPO_ROOT = Path(__file__).resolve().parents[2]
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

from scripts.deploy.lib.cron import openclaw_cron_edit  # noqa: E402  (after sys.path shim)


# Identifiers — keep stable so the manifest can reference them.
CRON_NAME: str = "habits-weekly-report"
NEW_SCHEDULE: str = "0 6 * * 1"  # Monday 06:00 office2-local (ET)


def _print_libresult(prefix: str, summary: str, details: dict) -> None:
    """Emit summary + JSON-details lines for the applier's log."""
    sys.stdout.write(f"{prefix}: {summary}\n")
    sys.stdout.write(json.dumps(details, sort_keys=True) + "\n")


def _dry_run() -> int:
    """Report the intended edit without invoking the openclaw primitive."""
    _print_libresult(
        prefix="DRY-RUN",
        summary=(
            f"would edit openclaw cron {CRON_NAME!r}: "
            f"schedule -> {NEW_SCHEDULE!r}"
        ),
        details={
            "cron_name": CRON_NAME,
            "target_schedule": NEW_SCHEDULE,
            "primitive": "scripts.deploy.lib.cron.openclaw_cron_edit",
            "mode": "dry-run",
        },
    )
    return 0


def _apply() -> int:
    """Invoke the openclaw primitive; print summary + details."""
    result = openclaw_cron_edit(cron_name=CRON_NAME, schedule=NEW_SCHEDULE)
    _print_libresult(
        prefix="APPLY",
        summary=result.summary,
        details=result.details,
    )
    return 0 if result.ok else 1


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
