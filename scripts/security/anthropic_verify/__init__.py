"""anthropic-verify: detect per-agent SQLite shadow + plaintext/SQLite drift.

Origin: kentonium3/kg-automation#597 (preventive follow-up to #596).

This package implements the `--check` (WP01) and `--repair` (WP02) surfaces
behind the `scripts/security/anthropic-verify.sh` bash entry. The `--repair`
implementation lives in a separate module that is imported lazily so the
WP01 build can ship and tests can run without `repair.py` being present.

Public entry point: :func:`main(argv)`. Used by `python3 -m anthropic_verify`.
"""

from __future__ import annotations

import sys
from typing import List

from . import core

__all__ = ["main", "core"]


def main(argv: List[str]) -> int:
    """Dispatch on `--check` / `--repair`. No state side-effects in this layer.

    Returns the exit code per spec FR-011:
      0 green, 1 unexpected error, 2 shadow, 3 drift, 4 anthropic_rejected,
      5 network, 6 substrate-gap.
    """
    if argv == ["--check"]:
        return core.run_check()
    if argv == ["--repair"]:
        # Lazy import: WP02 lands `repair.py`. Until then, surface a clean
        # message rather than crashing with an opaque ImportError.
        try:
            from . import repair  # type: ignore[attr-defined]
        except ImportError:
            print(
                "anthropic-verify --repair: not available in this build "
                "(WP02 lands repair.py). Run --check to inspect findings.",
                file=sys.stderr,
            )
            return 1
        return repair.run_repair()
    # Unknown / missing argv: treat as usage error per CLI contract (exit 1).
    print(
        "anthropic-verify: usage: python3 -m anthropic_verify [--check | --repair]",
        file=sys.stderr,
    )
    return 1


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
