#!/usr/bin/env python3
"""Compatibility alias for the inbox intake completeness scan.

``scripts.inbox.intake_scan`` is the exact module path the capture agent was
observed to hallucinate for Step 1b (kentonium3/kg-automation#809). The canonical
name is :mod:`scripts.inbox.scan_inbox` (which itself re-exports
:mod:`scripts.intake.scan_inbox`); this alias exists purely as a belt-and-suspenders
safety net so that the transposed invocation resolves instead of erroring the tick.

``python3 -m scripts.inbox.intake_scan`` is fully equivalent to
``python3 -m scripts.inbox.scan_inbox``.
"""
from __future__ import annotations

import sys

from scripts.intake.scan_inbox import main

if __name__ == "__main__":  # pragma: no cover - CLI entry
    sys.exit(main())
