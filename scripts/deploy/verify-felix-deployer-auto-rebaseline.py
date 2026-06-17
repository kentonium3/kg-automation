#!/usr/bin/env python3
"""Deploy entrypoint — verify auto-rebaseline modules are present and importable.

Mission: ``auto-rebaseline-on-deploy-01KVAYJN`` (issue kentonium3/kg-automation#618).

This is a verification-only entrypoint with NO state mutation. felix-deployer
self-updates by ``git pull`` each oneshot tick, so the new
``scripts/deploy/felix-deployer/rebaseline.py`` and
``tooling/scripts/audited_surfaces.py`` modules go live on office2 on the
next tick after merge — no explicit copy step is needed.

The sole job of this script is to confirm that the expected files landed and
are importable under the path-bootstrap convention used by felix-deployer.

CLI contract (per docs/runbooks/deploy/discipline.md):
  --dry-run   report what would be verified; no side effects.
  --apply     run the module-presence checks and exit non-zero on any failure.

Exit codes:
  0   dry-run printed; OR apply confirmed all modules present and importable.
  1   apply: at least one expected file is missing or fails to import.
  2   usage error.

Invocation note: felix-deployer invokes entrypoints by file path
(``subprocess.run([path, "--dry-run"], shell=False)``), NOT via
``python3 -m``. The repo root is NOT on sys.path by default; we add it
via the sys.path shim below so imports from ``tooling.scripts`` resolve.
"""
from __future__ import annotations

import importlib
import sys
from pathlib import Path

# sys.path shim — repo root must be on sys.path so tooling.scripts resolves.
# felix-deployer invokes this by file path, not via python3 -m, so the repo
# root is not automatically on sys.path.
_REPO_ROOT = Path(__file__).resolve().parents[2]
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

# The felix-deployer directory itself must also be on sys.path so that
# ``import rebaseline`` resolves (same bootstrap as deployer.py).
_FELIX_DIR = _REPO_ROOT / "scripts" / "deploy" / "felix-deployer"
if str(_FELIX_DIR) not in sys.path:
    sys.path.insert(0, str(_FELIX_DIR))

# ── Expected artifacts ──────────────────────────────────────────────────────
# Each entry is (description, repo-relative path, import name or None).
# import_name=None means file-presence only (not a Python import).
EXPECTED: list[tuple[str, str, str | None]] = [
    (
        "shared audited-surface matcher",
        "tooling/scripts/audited_surfaces.py",
        "tooling.scripts.audited_surfaces",
    ),
    (
        "felix-deployer rebaseline engine",
        "scripts/deploy/felix-deployer/rebaseline.py",
        "rebaseline",
    ),
]


def _print_line(prefix: str, summary: str) -> None:
    sys.stdout.write(f"{prefix}: {summary}\n")


def _dry_run() -> int:
    _print_line("DRY-RUN", "would verify presence + importability of auto-rebaseline modules:")
    for desc, rel_path, import_name in EXPECTED:
        abs_path = _REPO_ROOT / rel_path
        _print_line("DRY-RUN", f"  [{desc}] {rel_path} — present={abs_path.exists()}")
        if import_name:
            _print_line("DRY-RUN", f"    import {import_name}")
    return 0


def _apply() -> int:
    failures: list[str] = []
    for desc, rel_path, import_name in EXPECTED:
        abs_path = _REPO_ROOT / rel_path
        if not abs_path.exists():
            msg = f"MISSING: {rel_path} ({desc})"
            _print_line("APPLY", msg)
            failures.append(msg)
            continue
        _print_line("APPLY", f"OK file: {rel_path}")
        if import_name:
            try:
                importlib.import_module(import_name)
                _print_line("APPLY", f"OK import: {import_name}")
            except ImportError as exc:
                msg = f"IMPORT-FAILED: {import_name} — {exc}"
                _print_line("APPLY", msg)
                failures.append(msg)
    if failures:
        _print_line("APPLY", f"FAILED: {len(failures)} check(s) did not pass")
        return 1
    _print_line("APPLY", f"ALL OK: {len(EXPECTED)} module(s) present and importable")
    return 0


def main(argv: list[str] | None = None) -> int:
    args = list(sys.argv[1:] if argv is None else argv)
    if len(args) != 1 or args[0] not in ("--dry-run", "--apply"):
        sys.stderr.write(
            "usage: verify-felix-deployer-auto-rebaseline.py --dry-run|--apply\n"
        )
        return 2
    return _dry_run() if args[0] == "--dry-run" else _apply()


if __name__ == "__main__":  # pragma: no cover
    sys.exit(main())
