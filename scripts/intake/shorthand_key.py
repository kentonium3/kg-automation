"""Intake shorthand reference card (#755).

Deterministic, LLM-free helper that renders the compact-shorthand reference for
the #749 task-intake loop. The card is **derived from the ``shorthand`` alias
tables** (`FRICTION_ALIASES`, `QUADRANT_ALIASES`, `LOE_ALIASES`,
`PROJECT_ALIASES`), so it can never drift from what the parser actually accepts —
add a token to the parser and it appears here automatically.

Two surfaces:

- ``render_card()`` — the full multi-line reference card; the main agent returns
  it verbatim on an "intake key" WhatsApp DM trigger.
- ``render_hint()`` — a single-line format hint for the digest footer
  (`scripts.intake.scan_inbox`), so the syntax is visible at reply time.

CLI: ``python3 -m scripts.intake.shorthand_key [--hint] [--json]``.
"""

from __future__ import annotations

import argparse
import json
import sys

from scripts.intake.shorthand import (
    FRICTION_ALIASES,
    LOE_ALIASES,
    PROJECT_ALIASES,
    QUADRANT_ALIASES,
)

# Preferred display order for the Eisenhower quadrants (importance × urgency);
# any quadrant the parser gains that is not listed here is appended after.
_QUADRANT_ORDER = ["q:do", "q:schedule", "q:delegate", "q:eliminate"]


def _project_display_names() -> list[str]:
    """User-facing project short-names, one per distinct canonical project.

    `PROJECT_ALIASES` maps several keys to the same canonical value (e.g.
    ``spec-kitty`` and ``spec_kitty``). Keep the first-listed key per value so
    the card shows the friendly form the user types.
    """
    seen: set[str] = set()
    names: list[str] = []
    for key, value in PROJECT_ALIASES.items():
        if value in seen:
            continue
        seen.add(value)
        names.append(key)
    return names


def _friction_pairs() -> list[str]:
    """``f<n>=<descriptor>`` for each friction token, in token order."""
    pairs: list[str] = []
    for token in sorted(FRICTION_ALIASES):  # f1, f2, f3, f4
        canonical = FRICTION_ALIASES[token]  # e.g. "f:3-edge"
        descriptor = canonical.split("-", 1)[1] if "-" in canonical else canonical
        pairs.append(f"{token}={descriptor}")
    return pairs


def _quadrant_names() -> list[str]:
    """Distinct quadrant names (``q:`` prefix stripped), preferred order first."""
    values = list(dict.fromkeys(QUADRANT_ALIASES.values()))
    ordered = [q for q in _QUADRANT_ORDER if q in values]
    ordered += [q for q in values if q not in _QUADRANT_ORDER]
    return [q.split(":", 1)[1] for q in ordered]


def _loe_sizes() -> list[str]:
    """LOE size letters (``loe:`` prefix stripped), in table order."""
    return [v.split(":", 1)[1] for v in dict.fromkeys(LOE_ALIASES.values())]


def render_hint() -> str:
    """One-line format hint for the digest footer (no newline)."""
    return (
        "reply: <n> <project> f1-3 <do|schedule|delegate|eliminate> "
        "[due:] [habit] [loe:s|m|l] — or 'intake key' for the full list"
    )


def render_card() -> str:
    """The full multi-line shorthand reference card (one WhatsApp block)."""
    projects = " · ".join(_project_display_names())
    friction = "  ".join(_friction_pairs())
    quadrant = " · ".join(_quadrant_names())
    loe = "/".join(_loe_sizes())
    return "\n".join(
        [
            "Intake shorthand — one line per numbered task (supply only what's missing):",
            "  <n> <project> f<1-3> <quadrant> [due:<date>] [habit] [loe:s|m|l]",
            f"Projects : {projects}",
            f"Friction : {friction}   (f4 → decompose, not scheduled)",
            f"Quadrant : {quadrant}",
            f'Tier-2   : due:2026-07-22 (or "fri") · habit · loe:{loe}',
            "e.g.  1 personal f2 schedule  ·  2 clients f3 do due:fri  ·  3 personal  (project only)",
        ]
    )


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="scripts.intake.shorthand_key",
        description="Render the intake compact-shorthand reference (derived from the parser).",
    )
    parser.add_argument(
        "--hint",
        action="store_true",
        help="emit the one-line digest-footer hint instead of the full card",
    )
    parser.add_argument("--json", action="store_true", help="emit JSON {\"text\": ...}")
    args = parser.parse_args(argv)

    text = render_hint() if args.hint else render_card()
    if args.json:
        print(json.dumps({"text": text}))
    else:
        print(text)
    return 0


if __name__ == "__main__":
    sys.exit(main())
