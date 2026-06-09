"""CLI entry point for the credential expiry health check.

Invoked by `python3 -m credential_health_check` from the systemd unit
(see scripts/office2/credential-health-check.service).
"""
from __future__ import annotations

import argparse
import logging
import sys
from datetime import date, datetime, timezone

from .listing import list_credentials
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
        "--list",
        action="store_true",
        dest="list_only",
        help=(
            "Print the current credential state as a terminal table and exit. "
            "Read-only: no GitHub or Vikunja calls; orchestrator is not invoked."
        ),
    )
    parser.add_argument(
        "--liveness",
        action="store_true",
        help=(
            "With --list: print an additional table of OAuth liveness state "
            "per oauth2-typed credential. Read-only; no probes issued. "
            "For fresh classification, run with --dry-run --liveness-only."
        ),
    )
    parser.add_argument(
        "--liveness-only",
        action="store_true",
        help=(
            "Run only the OAuth liveness probe pass for credentials with "
            "liveness_probe.enabled. Skips cadence, staleness, and "
            "manifest-quality passes. Used by credential-liveness-probe.timer (6h cadence)."
        ),
    )
    parser.add_argument(
        "--today",
        default=None,
        help="Override 'today' for testing (ISO-8601 date). Production runs always use UTC today.",
    )
    args = parser.parse_args(argv)

    today = (
        date.fromisoformat(args.today)
        if args.today
        else datetime.now(timezone.utc).date()
    )

    if args.list_only:
        # --list is read-only and prints directly to stdout. No structured logging
        # noise; suitable for ad-hoc terminal use and copy-paste.
        try:
            return list_credentials(args.manifest, today, stream=sys.stdout, liveness=args.liveness)
        except ManifestUnreadableError as e:
            print(f"ERROR: manifest unreadable at {args.manifest}: {e}", file=sys.stderr)
            return 1

    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s %(message)s",
        stream=sys.stdout,
    )
    logger = logging.getLogger("credential_health_check")

    try:
        result = run_cycle(
            args.manifest, today,
            dry_run=args.dry_run,
            logger=logger,
            liveness_only=args.liveness_only,
        )
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
