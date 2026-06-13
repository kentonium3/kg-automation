"""Module entry point: ``python3 -m anthropic_verify [--check | --repair]``."""

from __future__ import annotations

import sys

from . import main


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
