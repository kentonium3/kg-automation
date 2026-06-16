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

Exit codes
----------
* ``0`` — cron edited (or already at the target schedule; primitive is
  idempotent at the openclaw layer).
* ``1`` — primitive failed (LibResult.summary printed on stderr, details
  emitted as JSON for the applier to log).
"""
from __future__ import annotations

import json
import sys

from scripts.deploy.lib.cron import openclaw_cron_edit


# Identifiers — keep stable so the manifest can reference them.
CRON_NAME: str = "habits-weekly-report"
NEW_SCHEDULE: str = "0 6 * * 1"  # Monday 06:00 office2-local (ET)


def main() -> int:
    result = openclaw_cron_edit(cron_name=CRON_NAME, schedule=NEW_SCHEDULE)
    sys.stdout.write(result.summary + "\n")
    sys.stdout.write(json.dumps(result.details, sort_keys=True) + "\n")
    return 0 if result.ok else 1


if __name__ == "__main__":  # pragma: no cover - module entry
    sys.exit(main())
