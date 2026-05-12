"""CLI entry point for the credential expiry health check.

Invoked by `python3 -m credential_health_check` from the systemd unit
(see scripts/office2/credential-health-check.service).
"""
from __future__ import annotations

import argparse
import logging
import sys
from datetime import date, datetime, timezone

from .manifest import ManifestUnreadableError
from .orchestrator import run_cycle


DEFAULT_MANIFEST = (
    "/home/claude/kg-automation/docs/design/architecture/data/credential-manifest.json"
)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="credential_health_check",
        description="Daily credential expiry + activity-signal audit (R-003).",
    )
    parser.add_argument(
        "--manifest",
        default=DEFAULT_MANIFEST,
        help="Path to credential-manifest.json. Default: the deployed repo copy on office2.",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Evaluate and log but do not file GitHub issues or Vikunja tasks.",
    )
    parser.add_argument(
        "--today",
        default=None,
        help="Override 'today' for testing (ISO-8601 date). Production runs always use UTC today.",
    )
    args = parser.parse_args(argv)

    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s %(message)s",
        stream=sys.stdout,
    )
    logger = logging.getLogger("credential_health_check")

    today = (
        date.fromisoformat(args.today)
        if args.today
        else datetime.now(timezone.utc).date()
    )

    try:
        result = run_cycle(args.manifest, today, dry_run=args.dry_run, logger=logger)
    except ManifestUnreadableError as e:
        logger.error("manifest_unreadable path=%s error=%s", args.manifest, e)
        return 1
    except Exception:
        logger.exception("unhandled_exception")
        return 2

    # Non-fatal per-credential errors do NOT cause a non-zero exit;
    # they are logged and counted. The systemd journal is the audit trail.
    return 0


if __name__ == "__main__":
    sys.exit(main())
