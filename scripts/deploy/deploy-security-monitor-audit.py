#!/usr/bin/env python3
"""Deploy entrypoint — sync the checkout's security-monitor ``audit.sh`` to its
standalone office2 copy.

``scripts/office2/security-monitor/audit.sh`` runs daily (3AM cron, ``sg docker``)
from a **standalone copy** at ``/data/services/security-monitor/scripts/audit.sh``
— a ``git pull`` of the felix-deployer checkout does NOT refresh it. Any change to
``audit.sh`` therefore needs an explicit sync of that deployed copy.

This is the **canonical** audit.sh syncer: use it (via a deploys/queued manifest)
for every change to ``audit.sh``, rather than minting a per-mission deploy script.
It supersedes the mission-named ``deploy-openclaw-bin-seam.py`` (#811), the first
instance of this same copy+verify operation, for future audit.sh syncs. The logic
is identical: copy the checkout's ``audit.sh`` to the deployed path, force the
executable bit (it is invoked directly), and verify byte-identity.

Tier 3 (a file copy into a claude-owned dir — no sudo, no Tier 0/1/2 action).

CLI contract (per docs/runbooks/deploy/discipline.md):

* ``--dry-run`` — print the planned copy (source, target, exists/differs). NO
  side effects on office2.
* ``--apply``   — copy + force +x + verify byte-identical. Idempotent in effect.

Exit codes
----------
* 0 — dry-run printed; OR apply succeeded (target byte-identical + executable).
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
    payload = {"entrypoint": "deploy-security-monitor-audit", "outcome": outcome, **fields}
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
