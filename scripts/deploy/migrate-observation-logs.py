#!/usr/bin/env python3
"""Phase-1 (non-destructive) observation-log migration entrypoint.

Thin executable wrapper for felix-deployer.  All logic lives in the importable
underscore module ``scripts.deploy.observation_migration`` (Codex Major 4:
hyphenated filenames are not importable).  This file only adds the repo root to
``sys.path`` — felix-deployer runs the entrypoint via its shebang, so the repo
root is not otherwise importable — and delegates to ``main()``.

**Non-destructive**: this entrypoint copies / union-merges only.  No deletion
happens here; the destructive decommission is a separate Phase-2 entrypoint.

Usage:
  migrate-observation-logs.py [--dry-run] [--apply]
                              [--source-root DIR] [--vault-logs-dir DIR]
"""
from __future__ import annotations

import sys
from pathlib import Path

# sys.path shim — felix-deployer invokes this via the shebang, so scripts/deploy/
# is on sys.path but the repo root is NOT. Add the repo root so the
# `from scripts.deploy...` imports resolve regardless of how it is invoked
# (matches the convention in the other deploy entrypoints).
_REPO_ROOT = Path(__file__).resolve().parents[2]
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

from scripts.deploy.observation_migration import main  # noqa: E402

if __name__ == "__main__":
    sys.exit(main())
