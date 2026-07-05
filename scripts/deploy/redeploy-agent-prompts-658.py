#!/usr/bin/env python3
"""Redeploy converted OpenClaw agent prompts to office2 (#658, WP06).

Thin felix-deployer entrypoint for mission ``agent-runtime-env-guardrails``.
All prompt-sync logic already lives in the importable helper
``scripts.openclaw.deploy.deploy_agent_prompts`` (WP01 of #567). This file
only:

  1. Self-bootstraps ``sys.path`` with the repo root — felix-deployer runs
     the entrypoint via its shebang, so ``scripts/deploy/`` is on ``sys.path``
     but the repo root is NOT; adding it makes ``from scripts...`` resolve
     regardless of launch context (the exact bug class this mission kills).
  2. ``chdir``s to that same repo root so the underlying helper's
     ``Path.cwd()``-based repo-root resolution is deterministic and
     cwd-independent (not reliant on the applier's cwd).
  3. Maps the applier's ``--dry-run`` / ``--apply`` protocol onto the
     helper's CLI and exits with the helper's return code.

felix-deployer invokes ``<entrypoint> --dry-run`` and then
``<entrypoint> --apply`` (see scripts/deploy/lib/apply.py). Both must exit 0.

Underlying helper exit codes (see deploy_agent_prompts.py):
    0 success | 1 partial failure | 2 git pull failed | 3 validation error.

Stdlib only. This entrypoint is itself free of the runtime-env-assumption
bug — self-bootstrapping sys.path + chdir to the __file__-anchored repo root
is the correct, launch-context-independent pattern.

Usage:
  redeploy-agent-prompts-658.py [--dry-run] [--apply]
"""
from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

# sys.path shim — felix-deployer invokes this via the shebang, so
# scripts/deploy/ is on sys.path but the repo root is NOT. Add the repo root
# so `from scripts.openclaw...` resolves (matches the other deploy entrypoints).
_REPO_ROOT = Path(__file__).resolve().parents[2]
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

from scripts.openclaw.deploy import deploy_agent_prompts  # noqa: E402


def main(argv: list[str] | None = None) -> int:
    if argv is None:
        argv = sys.argv[1:]
    parser = argparse.ArgumentParser(
        prog="redeploy-agent-prompts-658",
        description="Redeploy converted Felix agent prompts (full fleet sync).",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Compute drift only; no file writes, no git pull, no audit writes.",
    )
    parser.add_argument(
        "--apply",
        action="store_true",
        help="Execute the full-fleet prompt sync (all agents).",
    )
    args = parser.parse_args(argv)

    # Deterministic, cwd-independent repo root for the underlying helper,
    # which resolves its repo root from Path.cwd().
    os.chdir(_REPO_ROOT)

    # Full sync of every agent; pass through only the dry-run flag.
    inner_argv = ["--dry-run"] if args.dry_run else []
    return deploy_agent_prompts.main(inner_argv)


if __name__ == "__main__":
    sys.exit(main())
