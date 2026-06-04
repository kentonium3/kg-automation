"""CLI entry point for the Felix-Vikunja reconciliation driver (WP05 / T019).

Run as:

    python3 -m scripts.sync.driver                # steady-state tick
    python3 -m scripts.sync.driver --bootstrap    # first-run seed
    python3 -m scripts.sync.driver --dry-run      # no state writes

Exit codes (per contracts/cycle-pipeline.md § Cycle entry point):
    0 — cycle succeeded; freshness pointer advanced
    1 — cycle failed in preamble/fetch/diff/classify; pointer NOT advanced
    2 — cycle failed in emit/update/complete; partial commit possible
    3 — validation error before any I/O; safe state
"""
from __future__ import annotations

import argparse
import os
import re
import sys
from pathlib import Path

from scripts.sync.cycle import CycleConfig, run_bootstrap, run_cycle
from scripts.sync.send_whatsapp import WHATSAPP_RECIPIENT_ENV_VAR, resolve_recipient
from scripts.sync.state import SECRETS_DIR_DEFAULT, STATE_DIR_DEFAULT


# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------


CADENCE_FLOOR = 180
CADENCE_CEILING = 600
CADENCE_DEFAULT = 300

ENV_CADENCE = "FELIX_SYNC_CADENCE_SECONDS"
ENV_STATE_DIR = "FELIX_SYNC_STATE_DIR"
ENV_SECRETS_DIR = "FELIX_SYNC_SECRETS_DIR"
ENV_API_BASE_URL = "FELIX_VIKUNJA_API_BASE_URL"

API_BASE_URL_DEFAULT = "https://office2.tail0f5f56.ts.net/api/v1/"

_E164_RE = re.compile(r"^\+\d{8,15}$")


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="scripts.sync.driver",
        description=(
            "Felix-Vikunja reconciliation driver. One-shot tick (default) "
            "or first-run bootstrap (--bootstrap)."
        ),
    )
    parser.add_argument(
        "--cadence-seconds",
        type=int,
        default=None,
        help=(
            f"Cycle cadence in seconds (floor {CADENCE_FLOOR}, ceiling "
            f"{CADENCE_CEILING}). Default: env {ENV_CADENCE} or {CADENCE_DEFAULT}."
        ),
    )
    parser.add_argument(
        "--state-dir",
        type=Path,
        default=None,
        help=f"Driver state directory. Default: env {ENV_STATE_DIR} or {STATE_DIR_DEFAULT}.",
    )
    parser.add_argument(
        "--secrets-dir",
        type=Path,
        default=None,
        help=f"Secrets directory (vikunja-api). Default: env {ENV_SECRETS_DIR} or {SECRETS_DIR_DEFAULT}.",
    )
    parser.add_argument(
        "--api-base-url",
        type=str,
        default=None,
        help=f"Vikunja API base URL. Default: env {ENV_API_BASE_URL} or {API_BASE_URL_DEFAULT}.",
    )
    parser.add_argument(
        "--whatsapp-recipient",
        type=str,
        default=None,
        help=(
            f"E.164 recipient phone number. Default: env "
            f"{WHATSAPP_RECIPIENT_ENV_VAR}. REQUIRED — driver exits 3 if unset."
        ),
    )
    parser.add_argument("--dry-run", action="store_true", help="Skip all state writes.")
    parser.add_argument(
        "--bootstrap",
        action="store_true",
        help="First-run mode: seed cache from full Vikunja state; do NOT classify/emit.",
    )
    return parser


# ---------------------------------------------------------------------------
# Config resolution
# ---------------------------------------------------------------------------


class ValidationError(Exception):
    """Validation failure during config resolution. Maps to exit code 3."""


def resolve_config(args: argparse.Namespace, env: dict[str, str]) -> CycleConfig:
    """Resolve CLI > env > default for each value; raise ValidationError on bad input."""
    cadence = _resolve_int(args.cadence_seconds, env.get(ENV_CADENCE), CADENCE_DEFAULT)
    if cadence < CADENCE_FLOOR or cadence > CADENCE_CEILING:
        raise ValidationError(
            f"cadence-seconds {cadence} out of range "
            f"[{CADENCE_FLOOR}, {CADENCE_CEILING}]"
        )

    state_dir = _resolve_path(args.state_dir, env.get(ENV_STATE_DIR), STATE_DIR_DEFAULT)
    secrets_dir = _resolve_path(
        args.secrets_dir, env.get(ENV_SECRETS_DIR), SECRETS_DIR_DEFAULT
    )
    api_base_url = (
        args.api_base_url
        or env.get(ENV_API_BASE_URL)
        or API_BASE_URL_DEFAULT
    )

    try:
        recipient = resolve_recipient(args.whatsapp_recipient)
    except OSError as e:
        raise ValidationError(str(e)) from e
    if not _E164_RE.match(recipient):
        raise ValidationError(
            f"whatsapp-recipient {recipient!r} is not E.164 format "
            f"(expected ^\\+\\d{{8,15}}$)"
        )

    return CycleConfig(
        state_dir=state_dir,
        secrets_dir=secrets_dir,
        api_base_url=api_base_url,
        cadence_seconds=cadence,
        whatsapp_recipient=recipient,
        dry_run=args.dry_run,
    )


def _resolve_int(cli: int | None, env: str | None, default: int) -> int:
    if cli is not None:
        return cli
    if env is not None:
        try:
            return int(env)
        except ValueError as e:
            raise ValidationError(f"env var must parse as int (got {env!r})") from e
    return default


def _resolve_path(cli: Path | None, env: str | None, default: Path) -> Path:
    if cli is not None:
        return cli
    if env:
        return Path(env)
    return default


# ---------------------------------------------------------------------------
# main
# ---------------------------------------------------------------------------


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    try:
        config = resolve_config(args, dict(os.environ))
    except ValidationError as e:
        sys.stderr.write(f"[sync] phase=preamble status=validation_error reason={e!r}\n")
        return 3

    if args.bootstrap:
        result = run_bootstrap(config)
    else:
        result = run_cycle(config)
    return result.exit_code


if __name__ == "__main__":  # pragma: no cover
    sys.exit(main())
