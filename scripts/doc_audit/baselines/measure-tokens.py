#!/usr/bin/env python3
"""Measure per-tick token consumption from an OpenClaw session JSONL.

The OpenClaw felix-doc-auditor agent writes a session JSONL at:

    /home/claude/.openclaw/agents/felix-doc-auditor/sessions/<uuid>.jsonl

Each tick begins with a user message whose text matches the cron-tick
preamble (default regex: ``\\[.*UTC\\] Cron tick\\.``). Between two
consecutive user-tick messages, every assistant message carries a
``usage`` field with input / output / cacheRead / cacheWrite token
counts. This script sums those numbers per tick and emits one
record per tick in the schema consumed by
``docs/design/architecture/baselines/felix-doc-auditor-pre-rework.json``.

The same script is reused in WP09 to compute the post-rework
measurement against an analogous session JSONL emitted by the new
driver (or its activity log) — keeping the pre/post comparison
apples-to-apples per NFR-001's repeatability requirement.

Usage
-----

    python3 scripts/doc_audit/baselines/measure-tokens.py \\
        --session /path/to/session.jsonl \\
        --tick-marker '[.*UTC] Cron tick.' \\
        [--first-n 10] [--from-tick N] [--to-tick N] \\
        [--out per-tick.json]

Outcome classification is heuristic — derived from the FINAL assistant
message of each tick (the closing status report). Operators can
override classifications by editing the emitted JSON before promoting
it into the baseline file.

Exit codes:
- 0 — at least one tick measured
- 1 — invalid input (file missing, malformed)
- 2 — no ticks matched the marker
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any, Iterable, Iterator, Optional


DEFAULT_TICK_MARKER = r"\[.*UTC\] Cron tick\."


# ---------------------------------------------------------------------------
# Data shapes
# ---------------------------------------------------------------------------


@dataclass
class Tick:
    """One tick worth of data extracted from a session JSONL."""

    tick_index: int
    started_utc: str
    ended_utc: str
    input_tokens: int = 0
    output_tokens: int = 0
    cache_read_input_tokens: int = 0
    cache_write_input_tokens: int = 0
    llm_calls: int = 0
    duration_seconds: float = 0.0
    outcome: str = "unknown"
    closing_text: str = ""
    user_text: str = ""

    def to_sample(self) -> dict[str, Any]:
        """Render in the baseline-sample schema."""
        return {
            "tick_id": f"tick-{self.tick_index:04d}",
            "started_utc": self.started_utc,
            "ended_utc": self.ended_utc,
            "outcome": self.outcome,
            "input_tokens": self.input_tokens,
            "output_tokens": self.output_tokens,
            "cache_read_input_tokens": self.cache_read_input_tokens,
            "cache_write_input_tokens": self.cache_write_input_tokens,
            "total_input_tokens_billable": self.input_tokens
            + self.cache_read_input_tokens
            + self.cache_write_input_tokens,
            "llm_calls": self.llm_calls,
            "duration_seconds": round(self.duration_seconds, 3),
        }


# ---------------------------------------------------------------------------
# Parsing
# ---------------------------------------------------------------------------


def _iter_messages(path: Path) -> Iterator[dict[str, Any]]:
    """Yield each parsed ``message``-typed record from a JSONL file."""
    with path.open("r", encoding="utf-8") as fh:
        for raw in fh:
            raw = raw.strip()
            if not raw:
                continue
            try:
                rec = json.loads(raw)
            except json.JSONDecodeError:
                continue
            if rec.get("type") == "message":
                yield rec


def _user_text(rec: dict[str, Any]) -> str:
    msg = rec.get("message") or {}
    if msg.get("role") != "user":
        return ""
    parts = msg.get("content") or []
    out = []
    for part in parts:
        if isinstance(part, dict) and part.get("type") == "text":
            out.append(part.get("text", ""))
    return "\n".join(out)


def _assistant_text(rec: dict[str, Any]) -> str:
    msg = rec.get("message") or {}
    if msg.get("role") != "assistant":
        return ""
    parts = msg.get("content") or []
    out = []
    for part in parts:
        if isinstance(part, dict) and part.get("type") == "text":
            out.append(part.get("text", ""))
    return "\n".join(out)


def _usage(rec: dict[str, Any]) -> Optional[dict[str, Any]]:
    msg = rec.get("message") or {}
    if msg.get("role") != "assistant":
        return None
    return msg.get("usage")


def _ts(rec: dict[str, Any]) -> str:
    """Best-effort ISO timestamp string."""
    return rec.get("timestamp") or ""


def _parse_iso(ts: str) -> Optional[datetime]:
    if not ts:
        return None
    try:
        return datetime.fromisoformat(ts.replace("Z", "+00:00"))
    except ValueError:
        return None


# ---------------------------------------------------------------------------
# Outcome classification (heuristic)
# ---------------------------------------------------------------------------


_OUTCOME_PATTERNS: list[tuple[str, re.Pattern[str]]] = [
    # Tier-A apply ticks → commit hash referenced in closing report
    (
        "tier_a_apply",
        re.compile(
            r"(?:tier[- ]a|auto-?apply|frontmatter[- ]bump|committed|"
            r"`?[0-9a-f]{7,40}`?\s+(?:on|to)\s+main)",
            re.IGNORECASE,
        ),
    ),
    # Debt-filed ticks
    ("debt_only", re.compile(r"(?:debt[- ]issue|filed.*debt|docs-debt)", re.IGNORECASE)),
    # Empty-queue / no-work ticks
    (
        "empty",
        re.compile(
            r"(?:no\s+work|exit(?:ed)?\s+cleanly|clean\s+exit|"
            r"all\s+audits\s+blocked|no\s+(?:audits|signals)\s+available|"
            r"NO_REPLY)",
            re.IGNORECASE,
        ),
    ),
]


def _classify(closing_text: str) -> str:
    for label, pat in _OUTCOME_PATTERNS:
        if pat.search(closing_text):
            return label
    return "unknown"


# ---------------------------------------------------------------------------
# Tick extraction
# ---------------------------------------------------------------------------


def iter_ticks(
    session_path: Path,
    tick_marker: re.Pattern[str],
) -> Iterator[Tick]:
    """Yield one :class:`Tick` per cron-tick boundary in ``session_path``.

    Boundary definition: a user-role message whose text matches
    ``tick_marker``. All assistant ``usage`` records between two
    consecutive markers belong to the prior tick.
    """
    current: Optional[Tick] = None
    tick_count = 0

    for rec in _iter_messages(session_path):
        utext = _user_text(rec)
        if utext and tick_marker.search(utext):
            if current is not None:
                yield current
            tick_count += 1
            current = Tick(
                tick_index=tick_count,
                started_utc=_ts(rec),
                ended_utc=_ts(rec),
                user_text=utext,
            )
            continue

        if current is None:
            # Assistant traffic before the first tick marker (e.g. a session
            # warmup); ignore.
            continue

        usage = _usage(rec)
        if usage:
            current.llm_calls += 1
            current.input_tokens += int(usage.get("input", 0) or 0)
            current.output_tokens += int(usage.get("output", 0) or 0)
            current.cache_read_input_tokens += int(usage.get("cacheRead", 0) or 0)
            current.cache_write_input_tokens += int(usage.get("cacheWrite", 0) or 0)

        atext = _assistant_text(rec)
        if atext:
            current.closing_text = atext  # last assistant message wins
            current.ended_utc = _ts(rec)

    if current is not None:
        yield current


def finalize_tick(tick: Tick) -> Tick:
    """Compute derived fields (duration, outcome)."""
    start = _parse_iso(tick.started_utc)
    end = _parse_iso(tick.ended_utc)
    if start and end:
        tick.duration_seconds = max(0.0, (end - start).total_seconds())
    tick.outcome = _classify(tick.closing_text)
    return tick


# ---------------------------------------------------------------------------
# Aggregation
# ---------------------------------------------------------------------------


def aggregate_by_outcome(ticks: Iterable[Tick]) -> list[dict[str, Any]]:
    """Group per-tick samples by outcome and compute averages."""
    buckets: dict[str, list[Tick]] = {}
    for t in ticks:
        buckets.setdefault(t.outcome, []).append(t)

    out: list[dict[str, Any]] = []
    for outcome, ts in buckets.items():
        n = len(ts)
        out.append(
            {
                "outcome": outcome,
                "sample_count": n,
                "samples": [t.to_sample() for t in ts],
                "average_input_tokens": round(sum(t.input_tokens for t in ts) / n, 1),
                "average_output_tokens": round(sum(t.output_tokens for t in ts) / n, 1),
                "average_cache_read_input_tokens": round(
                    sum(t.cache_read_input_tokens for t in ts) / n, 1
                ),
                "average_cache_write_input_tokens": round(
                    sum(t.cache_write_input_tokens for t in ts) / n, 1
                ),
                "average_total_input_tokens_billable": round(
                    sum(
                        t.input_tokens
                        + t.cache_read_input_tokens
                        + t.cache_write_input_tokens
                        for t in ts
                    )
                    / n,
                    1,
                ),
                "average_duration_seconds": round(
                    sum(t.duration_seconds for t in ts) / n, 3
                ),
                "average_llm_calls": round(sum(t.llm_calls for t in ts) / n, 2),
            }
        )
    # Sort by canonical outcome order
    canonical = {"empty": 0, "debt_only": 1, "tier_a_apply": 2, "unknown": 9}
    out.sort(key=lambda d: canonical.get(d["outcome"], 99))
    return out


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


def _build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        description=(
            "Measure per-tick token consumption from an OpenClaw session "
            "JSONL and emit the per-outcome aggregation used by the "
            "felix-doc-auditor baseline JSON."
        )
    )
    p.add_argument(
        "--session",
        type=Path,
        required=True,
        help="Path to the agent session JSONL.",
    )
    p.add_argument(
        "--tick-marker",
        type=str,
        default=DEFAULT_TICK_MARKER,
        help="Regex (re.search) identifying the user-role tick boundary message.",
    )
    p.add_argument(
        "--from-tick",
        type=int,
        default=1,
        help="Skip ticks before this 1-based index.",
    )
    p.add_argument(
        "--to-tick",
        type=int,
        default=None,
        help="Skip ticks after this 1-based index (inclusive).",
    )
    p.add_argument(
        "--first-n",
        type=int,
        default=None,
        help="Convenience: equivalent to --to-tick (from-tick + first-n - 1).",
    )
    p.add_argument(
        "--out",
        type=Path,
        default=None,
        help="If given, write the JSON output here (else stdout).",
    )
    p.add_argument(
        "--per-tick",
        action="store_true",
        help="Emit per-tick records instead of the per-outcome aggregation.",
    )
    return p


def main(argv: Optional[list[str]] = None) -> int:
    args = _build_parser().parse_args(argv)

    session = args.session
    if not session.is_file():
        print(f"ERROR: session file not found: {session}", file=sys.stderr)
        return 1

    try:
        marker = re.compile(args.tick_marker)
    except re.error as exc:
        print(f"ERROR: invalid --tick-marker regex: {exc}", file=sys.stderr)
        return 1

    ticks: list[Tick] = []
    for tick in iter_ticks(session, marker):
        ticks.append(finalize_tick(tick))

    if not ticks:
        print(
            f"ERROR: no ticks matched marker {args.tick_marker!r} in {session}",
            file=sys.stderr,
        )
        return 2

    lo = max(1, args.from_tick)
    if args.first_n is not None:
        hi = lo + args.first_n - 1
    elif args.to_tick is not None:
        hi = args.to_tick
    else:
        hi = len(ticks)
    selected = [t for t in ticks if lo <= t.tick_index <= hi]

    if not selected:
        print(
            f"ERROR: --from-tick/--to-tick selected zero of {len(ticks)} ticks",
            file=sys.stderr,
        )
        return 2

    if args.per_tick:
        payload: Any = [t.to_sample() for t in selected]
    else:
        payload = {
            "tick_count": len(selected),
            "tick_range": {"from": selected[0].tick_index, "to": selected[-1].tick_index},
            "by_outcome": aggregate_by_outcome(selected),
        }

    output = json.dumps(payload, indent=2)
    if args.out:
        args.out.parent.mkdir(parents=True, exist_ok=True)
        args.out.write_text(output + "\n", encoding="utf-8")
    else:
        print(output)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
