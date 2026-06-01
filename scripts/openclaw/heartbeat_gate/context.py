"""Gate context assembler (WP-03 T015).

Reads the two deterministic inputs the heartbeat gate needs to decide
routing for one tick:

1. ``last-tick.json`` -- the most recent signal-extraction cycle record
   produced by ``scripts/openclaw/observation/tick.py``. Schema is
   ``contracts/tick-signal.contract.md`` (E3 cycle record).
2. ``HEARTBEAT.md`` -- the operator's heartbeat contract file. Empty,
   missing, or template-only files mean "no scheduled task this tick";
   anything else means "operator wants the agent to read it."

The novelty-marker derivation is purely deterministic: each signal in
``signals_evaluated`` whose ``threshold_status`` is anything other than
``"below"`` contributes its ``signal_id`` to ``novelty_markers``. The
gate prompt sees only the IDs; the gate cannot expand its scope to
look at signals it was not given.

This module never raises on a malformed ``last-tick.json`` body --
``json.JSONDecodeError`` propagates so the orchestrator (``run.py``)
can record the error and fall back per FR-011. The only sentinel
raised here is ``MissingTickError`` when ``last_tick_path`` does not
exist, because that is a deployment-state problem distinct from a
parse error.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path


__all__ = [
    "GateContext",
    "MissingTickError",
    "classify_heartbeat_md",
    "load_context",
]


class MissingTickError(FileNotFoundError):
    """Raised when ``last_tick_path`` does not exist on disk.

    Distinct from ``FileNotFoundError`` so the orchestrator can branch
    on "no signal-extraction tick has happened yet" vs. other I/O
    errors (corrupt JSON, permission denied, etc.). Inherits from
    ``FileNotFoundError`` for ``except FileNotFoundError`` compatibility.
    """


@dataclass(frozen=True)
class GateContext:
    """Per-tick inputs assembled for the routing prompt.

    All fields are derived deterministically from ``last-tick.json`` and
    ``HEARTBEAT.md`` -- no LLM call is made to construct this struct.
    The gate prompt receives the dict serialization of this struct as
    the variable section of the user message.
    """

    tick_id: str
    digest_snapshot_at_utc: str
    signals_evaluated: list[dict] = field(default_factory=list)
    issues_filed: list[dict] = field(default_factory=list)
    errors: list[dict] = field(default_factory=list)
    heartbeat_md_state: str = "empty"
    novelty_markers: list[str] = field(default_factory=list)


# ---------------------------------------------------------------------------
# HEARTBEAT.md classification
# ---------------------------------------------------------------------------


# Lines starting with any of these prefixes are "template content" and do not
# constitute actionable tasks. The matcher is intentionally conservative -- a
# stray paragraph in the file should be treated as has_tasks (escalation),
# not silently swallowed.
_TEMPLATE_LINE_PREFIXES: tuple[str, ...] = (
    "# Keep this file empty",
    "<!-- Keep this file empty",
    "<!-- keep this file empty",
    "# When you want Felix",
    "<!--",
)

# Code-fence delimiters are noise; pure markdown horizontal rules / dividers
# are also noise. Whitespace-only lines are stripped before classification.
_NOISE_LINES: tuple[str, ...] = ("```", "---", "***", "___")


def classify_heartbeat_md(text: str) -> str:
    """Classify ``HEARTBEAT.md`` body as ``"empty"`` or ``"has_tasks"``.

    Returns ``"empty"`` when the file is whitespace-only, contains only
    template comments, or contains only markdown heading lines without
    accompanying content. Returns ``"has_tasks"`` when any actionable
    line is present.

    Rules:
    - Strip each line.
    - Drop blank lines.
    - Drop ``_NOISE_LINES`` matches (code fences, horizontal rules).
    - Drop lines whose stripped form starts with any of
      ``_TEMPLATE_LINE_PREFIXES`` (the project's documented "empty"
      sentinel comments).
    - If every remaining line starts with ``#`` (markdown heading), the
      file is heading-only and treated as ``"empty"``.
    - Otherwise ``"has_tasks"``.

    This matcher errs on the side of escalation: when in doubt, prefer
    ``"has_tasks"`` so the gate routes to Sonnet rather than silently
    ignoring an operator's instruction.
    """
    actionable = []
    for raw_line in text.splitlines():
        line = raw_line.strip()
        if not line:
            continue
        if line in _NOISE_LINES:
            continue
        # A line that begins with a noise prefix (e.g. ``---`` followed
        # by frontmatter content) we treat as noise too, but only for
        # exact-match -- substring matches would over-trigger.
        if any(line.startswith(prefix) for prefix in _TEMPLATE_LINE_PREFIXES):
            continue
        actionable.append(line)

    if not actionable:
        return "empty"
    # If everything that survived is a markdown heading, the file is a
    # scaffold (e.g. ``# Today``) with no work attached. Treat as empty.
    if all(line.startswith("#") for line in actionable):
        return "empty"
    return "has_tasks"


# ---------------------------------------------------------------------------
# Public loader
# ---------------------------------------------------------------------------


def load_context(
    last_tick_path: Path,
    heartbeat_md_path: Path,
    *,
    tick_id: str,
) -> GateContext:
    """Assemble a ``GateContext`` from the two deterministic inputs.

    Parameters
    ----------
    last_tick_path:
        Path to ``last-tick.json`` (produced by ``observation/tick.py``).
        Must exist; missing file raises :class:`MissingTickError`.
    heartbeat_md_path:
        Path to the operator's ``HEARTBEAT.md`` contract file. Missing
        or unreadable files are treated as ``"empty"`` (no escalation
        because of an absent contract).
    tick_id:
        ULID-shaped identifier for THIS gate tick (NOT the
        signal-extraction cycle id). The caller assigns this so the
        ledger ties together fallback writes with their successful
        sibling writes for the same systemd-invocation.

    Returns
    -------
    GateContext
        Frozen dataclass carrying everything the routing prompt needs.

    Raises
    ------
    MissingTickError
        If ``last_tick_path`` does not exist.
    json.JSONDecodeError
        If ``last_tick_path`` exists but is not valid JSON. The caller
        is expected to translate this to a fallback per FR-011.
    """
    if not last_tick_path.is_file():
        raise MissingTickError(f"last-tick.json not found at {last_tick_path}")

    payload = json.loads(last_tick_path.read_text(encoding="utf-8"))

    # The tick file's ``started_at_utc`` IS the digest snapshot the gate
    # consumed. We surface it in the context so the ledger can record
    # which extraction tick the gate decision was based on.
    digest_snapshot = str(payload.get("started_at_utc") or "")
    signals_evaluated = list(payload.get("signals_evaluated") or [])
    issues_filed = list(payload.get("issues_filed") or [])
    errors = list(payload.get("errors") or [])

    novelty_markers = [
        str(sig.get("signal_id"))
        for sig in signals_evaluated
        if isinstance(sig, dict) and sig.get("threshold_status") != "below"
    ]

    # HEARTBEAT.md: missing file is treated as empty (no escalation
    # because the operator never wrote a contract). Read errors fall
    # through to ``"empty"`` for the same reason -- the gate should
    # not escalate just because the file is unreachable.
    if heartbeat_md_path.is_file():
        try:
            heartbeat_text = heartbeat_md_path.read_text(encoding="utf-8")
            heartbeat_md_state = classify_heartbeat_md(heartbeat_text)
        except OSError:  # pragma: no cover - defensive; rare
            heartbeat_md_state = "empty"
    else:
        heartbeat_md_state = "empty"

    return GateContext(
        tick_id=tick_id,
        digest_snapshot_at_utc=digest_snapshot,
        signals_evaluated=signals_evaluated,
        issues_filed=issues_filed,
        errors=errors,
        heartbeat_md_state=heartbeat_md_state,
        novelty_markers=novelty_markers,
    )
