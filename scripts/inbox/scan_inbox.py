#!/usr/bin/env python3
"""Inbox-pipeline entry point for the Tier-1 intake completeness scan (Step 1b).

The canonical implementation lives in :mod:`scripts.intake.scan_inbox` (it is
shared with the intake reply flow). This thin re-export gives the inbox
processing pipeline a ``scripts.inbox.*`` entry point that is consistent with
every other pipeline command the capture agent runs (``scripts.inbox.prescan``,
``scripts.inbox.classify_content``, ``scripts.inbox.route_and_finalize``,
``scripts.inbox.clarification_sweep_finalize``).

Why this exists: ``scripts.intake.scan_inbox`` was the lone ``scripts.intake.*``
outlier in an otherwise ``scripts.inbox.*`` pipeline, and the capture agent
reliably transposed it to the non-existent ``scripts.inbox.intake_scan`` — a
prompt-following failure that errored every inbox tick (kentonium3/kg-automation#809).
Keeping the whole pipeline under ``scripts.inbox.*`` removes the trap at the root.

``python3 -m scripts.inbox.scan_inbox`` is fully equivalent to
``python3 -m scripts.intake.scan_inbox`` — same CLI surface, flags, and exit codes.
"""
from __future__ import annotations

import sys

from scripts.intake.scan_inbox import main

if __name__ == "__main__":  # pragma: no cover - CLI entry
    sys.exit(main())
