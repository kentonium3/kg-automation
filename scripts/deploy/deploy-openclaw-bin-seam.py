#!/usr/bin/env python3
"""Deploy entrypoint — sync the seam-migrated ``audit.sh`` to its office2 copy (#811).

The OpenClaw binary-path seam (``scripts/common/openclaw_bin.py``) migration is
otherwise **checkout-resident**: the 4 systemd Python services and the deploy
helpers run ``python3 -m scripts.*`` from ``WorkingDirectory=/home/claude/
kg-automation`` (the felix-deployer origin/main checkout), so they go live on the
next ``git pull`` with no deploy action. The one exception is
``scripts/office2/security-monitor/audit.sh``, which runs from a **standalone
copy** at ``/data/services/security-monitor/scripts/audit.sh`` — a ``git pull``
does not refresh it.

This entrypoint copies the checkout's ``audit.sh`` to that deployed path and
verifies the copy is byte-identical. The change is path-resolution only (adopting
the ``: "${OPENCLAW_BIN:=…}"`` seam convention in place of a hardcoded literal), so
``openclaw cron list`` output — and thus the ``openclaw-cron.txt`` baseline — is
unchanged. It mirrors the #653 precedent (commit ``c163c3be``) that last updated
this file, but records the copy through the manifest pipeline rather than by hand.

Tier 3 (a file copy into a claude-owned dir — no sudo, no Tier 0/1/2 action).

CLI contract (per docs/runbooks/deploy/discipline.md):

* ``--dry-run`` — print the planned copy (source, target, exists/differs). NO
  side effects on office2.
* ``--apply``   — copy + verify byte-identical. Idempotent in effect (a re-run
  re-copies the identical bytes and re-verifies — same success outcome).

Exit codes
----------
* 0 — dry-run printed; OR apply succeeded (target byte-identical to source).
* 1 — apply failed (source missing, copy error, or post-copy mismatch).
* 2 — usage error (missing / wrong-shaped mode argument).

Invocation note: felix-deployer invokes entrypoints by file path
(``subprocess.run([path, "--dry-run"], shell=False)``), NOT via ``python3 -m``.
This script imports only stdlib, so no sys.path shim is required.
"""
from __future__ import annotations

import argparse
import filecmp
import json
import os
import shutil
import stat
import sys
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parents[2]
_SOURCE = _REPO_ROOT / "scripts" / "office2" / "security-monitor" / "audit.sh"
_TARGET = Path("/data/services/security-monitor/scripts/audit.sh")


def _emit(outcome: str, **fields: object) -> None:
    """Print one structured line for the felix-deployer log."""
    payload = {"entrypoint": "deploy-openclaw-bin-seam", "outcome": outcome, **fields}
    sys.stdout.write(json.dumps(payload, sort_keys=True) + "\n")


def _dry_run() -> int:
    if not _SOURCE.is_file():
        _emit("dry_run_error", error=f"source not found: {_SOURCE}")
        return 1
    target_exists = _TARGET.exists()
    differs = not (target_exists and filecmp.cmp(_SOURCE, _TARGET, shallow=False))
    _emit(
        "dry_run",
        source=str(_SOURCE),
        target=str(_TARGET),
        target_exists=target_exists,
        would_copy=differs,
    )
    return 0


def _apply() -> int:
    if not _SOURCE.is_file():
        _emit("apply_error", error=f"source not found: {_SOURCE}")
        return 1
    try:
        _TARGET.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(_SOURCE, _TARGET)
        # audit.sh is invoked directly (`sg docker -c .../audit.sh`), so it MUST
        # stay executable. copy2 only preserves the *source* mode, so ensure +x
        # on the target explicitly rather than trusting the checkout's bits.
        current = _TARGET.stat().st_mode
        _TARGET.chmod(current | stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH)
    except OSError as exc:
        _emit("apply_error", error=f"copy failed: {exc}", target=str(_TARGET))
        return 1
    # Verify byte-identical + executable (the deterministic post-conditions).
    if not filecmp.cmp(_SOURCE, _TARGET, shallow=False):
        _emit("apply_error", error="post-copy mismatch", target=str(_TARGET))
        return 1
    if not os.access(_TARGET, os.X_OK):
        _emit("apply_error", error="target not executable after copy", target=str(_TARGET))
        return 1
    _emit("applied", source=str(_SOURCE), target=str(_TARGET))
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--dry-run", action="store_true", help="print planned copy; no side effects")
    mode.add_argument("--apply", action="store_true", help="copy + verify audit.sh")
    try:
        args = parser.parse_args(argv)
    except SystemExit:
        return 2
    return _apply() if args.apply else _dry_run()


if __name__ == "__main__":
    raise SystemExit(main())
