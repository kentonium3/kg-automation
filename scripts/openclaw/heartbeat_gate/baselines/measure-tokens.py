#!/usr/bin/env python3
"""Measure pre-rollout heartbeat-gate token consumption (WP-03 T022).

Captures the current Sonnet heartbeat cost as a baseline JSON file so
NFR-001's ≥80% reduction can be measured post-deploy. The output
matches the shape of
``docs/design/architecture/baselines/felix-doc-auditor-pre-rework.json``.

Modes
-----

- ``--mode historical``: read OpenClaw's main-agent session JSONL(s) on
  office2 and aggregate per-heartbeat usage records. Mirrors the
  doc_audit measure-tokens.py approach. Accepts either a single session
  via ``--session`` or a directory of session files via ``--session-dir``
  (each ``*.jsonl*`` file in the directory is walked; reset/deleted
  variants are included because their content is the historical record).
- ``--mode sample``: emit a placeholder baseline with a methodology
  string explaining that historical data isn't available; the operator
  is expected to instrument the current heartbeat for N days, then
  re-run this script in ``historical`` mode against the instrumented log.

Why two modes
-------------
OpenClaw's main-agent session log on office2 carries per-turn ``usage``
records but a single session can span dozens of heartbeats AND
WhatsApp-triage events. Discriminating "heartbeat" from "event" turns
needs the heartbeat preamble regex. The default
``DEFAULT_TICK_MARKER`` matches the literal preamble OpenClaw injects
into the main-agent prompt at each ~30-minute heartbeat tick (the
"Read HEARTBEAT.md if it exists (workspace context)..." line). If that
preamble is absent (e.g. the heartbeat is disabled, or the session log
is missing), the script does not fabricate numbers — historical mode
exits non-zero and the operator falls back to sample mode.

Historical mode also accepts optional ``--window-start`` and
``--window-end`` ISO-8601 UTC bounds so an operator can pull a clean
N-day window out of a multi-month session corpus (e.g. excluding the
days the Anthropic API spend cap was hit).

This is intentional: the WP prompt's reviewer-style note (T022 baseline
methodology honesty) calls out that an unavailable measurement must be
documented as such, not papered over.

Usage
-----

    # Single session (legacy):
    python3 scripts/openclaw/heartbeat_gate/baselines/measure-tokens.py \\
        --mode historical \\
        --session /home/claude/.openclaw/agents/main/sessions/<uuid>.jsonl \\
        --window-days 7 \\
        --out /tmp/baseline.json

    # Directory walk across all session files (preferred for the
    # office2 main-agent corpus where heartbeats span many sessions):
    python3 scripts/openclaw/heartbeat_gate/baselines/measure-tokens.py \\
        --mode historical \\
        --session-dir /home/claude/.openclaw/agents/main/sessions \\
        --window-start 2026-05-05T00:00:00Z \\
        --window-end   2026-05-19T00:00:00Z \\
        --window-days 14 \\
        --out /tmp/baseline.json

    # Fallback (when historical data isn't extractable at all):
    python3 scripts/openclaw/heartbeat_gate/baselines/measure-tokens.py \\
        --mode sample \\
        --out /tmp/baseline.json

Exit codes:
- 0  -- baseline written.
- 1  -- input parsing error (invalid session path, bad JSON).
- 2  -- historical mode found zero ticks matching the preamble regex.
"""
from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterator, Optional


__all__ = [
    "DEFAULT_TICK_MARKER",
    "DEFAULT_HAIKU_INPUT_USD_PER_MTOK",
    "DEFAULT_HAIKU_OUTPUT_USD_PER_MTOK",
    "DEFAULT_SONNET_INPUT_USD_PER_MTOK",
    "DEFAULT_SONNET_OUTPUT_USD_PER_MTOK",
    "aggregate_session",
    "aggregate_session_dir",
    "build_historical_baseline",
    "build_sample_placeholder",
    "main",
]


# Heartbeat preamble substring -- OpenClaw injects this into the main
# agent's user prompt at each ~30-minute heartbeat tick (verified by
# sampling /home/claude/.openclaw/agents/main/sessions/*.jsonl* on
# office2 on 2026-06-01). The marker is a substring (not anchored at
# line start) because OpenClaw prefixes it with a system block carrying
# gateway connection info on session resume.
DEFAULT_TICK_MARKER = r"Read HEARTBEAT\.md if it exists"

# Pricing constants (Anthropic public list price, May 2026). The numbers
# in the baseline JSON are honest estimates; precise billing comes from
# Anthropic console. Sonnet 4.6 list price: $3/MTok input, $15/MTok output.
DEFAULT_HAIKU_INPUT_USD_PER_MTOK = 0.80
DEFAULT_HAIKU_OUTPUT_USD_PER_MTOK = 4.00
DEFAULT_SONNET_INPUT_USD_PER_MTOK = 3.00
DEFAULT_SONNET_OUTPUT_USD_PER_MTOK = 15.00


# ---------------------------------------------------------------------------
# Historical-mode aggregation
# ---------------------------------------------------------------------------


def aggregate_session(
    session_path: Path,
    *,
    tick_marker: str = DEFAULT_TICK_MARKER,
    window_start: Optional[str] = None,
    window_end: Optional[str] = None,
) -> dict[str, Any]:
    """Walk a session JSONL once and aggregate per-heartbeat totals.

    ``window_start`` / ``window_end`` are inclusive-of-start, exclusive-of-end
    ISO-8601 UTC strings. A heartbeat is included iff its preamble
    timestamp falls inside the window. Both bounds are optional; with
    none supplied the whole session is aggregated.

    Returns a dict carrying:
    - ``tick_count``: how many heartbeats matched the preamble (within
      the optional window).
    - ``earliest_tick_utc`` / ``latest_tick_utc``: ISO strings or None.
    - ``total_input_tokens``, ``total_cache_read_input_tokens``,
      ``total_cache_write_input_tokens``, ``total_output_tokens``: sums
      across assistant messages within matched ticks.
    - ``total_cost_usd``: sum of per-message ``usage.cost.total`` where
      the OpenClaw session log carries it. Real observed cost — more
      reliable than re-applying list-price math to token counts when
      OpenClaw already records the priced value. Falls back to zero if
      no record carries a cost block.
    """
    pattern = re.compile(tick_marker)
    in_tick = False
    tick_count = 0
    earliest: Optional[str] = None
    latest: Optional[str] = None

    totals = {
        "input_tokens": 0,
        "cache_read_input_tokens": 0,
        "cache_write_input_tokens": 0,
        "output_tokens": 0,
    }
    total_cost_usd = 0.0

    for record in _iter_jsonl(session_path):
        role = (
            record.get("role")
            or (record.get("message") or {}).get("role")
            or ""
        )
        text = _extract_user_text(record)

        if role == "user" and pattern.search(text or ""):
            ts = _extract_timestamp(record)
            if not _in_window(ts, window_start, window_end):
                in_tick = False
                continue
            in_tick = True
            tick_count += 1
            if ts:
                if earliest is None or ts < earliest:
                    earliest = ts
                if latest is None or ts > latest:
                    latest = ts
            continue

        if role == "user" and in_tick:
            # A subsequent user message NOT matching the preamble means
            # the prior heartbeat ended. Mark out-of-tick until the
            # next preamble match.
            in_tick = False
            continue

        if role == "assistant" and in_tick:
            usage = _extract_usage(record)
            for tkey, ukeys in _USAGE_KEY_ALIASES.items():
                totals[tkey] += _coerce_int(usage, ukeys)
            cost_block = usage.get("cost") if isinstance(usage, dict) else None
            if isinstance(cost_block, dict):
                try:
                    total_cost_usd += float(cost_block.get("total", 0) or 0)
                except (TypeError, ValueError):
                    pass

    return {
        "tick_count": tick_count,
        "earliest_tick_utc": earliest,
        "latest_tick_utc": latest,
        "total_input_tokens": totals["input_tokens"],
        "total_cache_read_input_tokens": totals["cache_read_input_tokens"],
        "total_cache_write_input_tokens": totals["cache_write_input_tokens"],
        "total_output_tokens": totals["output_tokens"],
        "total_cost_usd_observed": round(total_cost_usd, 6),
    }


# Mapping of canonical aggregate-key -> tuple of usage-key aliases
# accepted in the session JSONL. OpenClaw on office2 emits the short
# form (``input`` / ``output`` / ``cacheRead`` / ``cacheWrite``);
# Anthropic SDK's raw responses use the long form
# (``input_tokens`` / ``cache_read_input_tokens`` / etc.). Tolerate both.
_USAGE_KEY_ALIASES: dict[str, tuple[str, ...]] = {
    "input_tokens": ("input_tokens", "input"),
    "cache_read_input_tokens": (
        "cache_read_input_tokens",
        "cacheRead",
        "cache_read",
    ),
    "cache_write_input_tokens": (
        "cache_creation_input_tokens",
        "cache_write_input_tokens",
        "cacheWrite",
        "cache_write",
    ),
    "output_tokens": ("output_tokens", "output"),
}


def _coerce_int(usage: dict[str, Any], aliases: tuple[str, ...]) -> int:
    """Return the first present alias from ``usage`` coerced to int, or 0."""
    for alias in aliases:
        if alias in usage:
            try:
                return int(usage.get(alias) or 0)
            except (TypeError, ValueError):
                continue
    return 0


def _in_window(
    ts: Optional[str],
    start: Optional[str],
    end: Optional[str],
) -> bool:
    """Half-open window test ``start <= ts < end`` on ISO-8601 strings.

    With no timestamp on the record the tick is treated as in-window only
    when no bounds are set. Bounds are compared lexicographically because
    ISO-8601 UTC strings sort correctly under string comparison.
    """
    if start is None and end is None:
        return True
    if not ts:
        return False
    if start is not None and ts < start:
        return False
    if end is not None and ts >= end:
        return False
    return True


def aggregate_session_dir(
    session_dir: Path,
    *,
    tick_marker: str = DEFAULT_TICK_MARKER,
    window_start: Optional[str] = None,
    window_end: Optional[str] = None,
) -> dict[str, Any]:
    """Aggregate ``aggregate_session`` over every ``*.jsonl*`` in a dir.

    OpenClaw rotates the main-agent session daily (``*.jsonl.reset.*``
    and ``*.jsonl.deleted.*`` suffixes). Heartbeat ticks live in all of
    them, so the historical baseline needs the whole directory.

    Returns the same shape as :func:`aggregate_session` plus
    ``files_walked`` (count of session files inspected).
    """
    agg = {
        "tick_count": 0,
        "earliest_tick_utc": None,
        "latest_tick_utc": None,
        "total_input_tokens": 0,
        "total_cache_read_input_tokens": 0,
        "total_cache_write_input_tokens": 0,
        "total_output_tokens": 0,
        "total_cost_usd_observed": 0.0,
        "files_walked": 0,
    }

    # ``Path.glob`` is non-recursive; sessions all live in the directory
    # root, so a single-level glob is the right scope.
    paths = sorted(
        p
        for p in session_dir.iterdir()
        if p.is_file() and ".jsonl" in p.name
    )
    for path in paths:
        agg["files_walked"] += 1
        sub = aggregate_session(
            path,
            tick_marker=tick_marker,
            window_start=window_start,
            window_end=window_end,
        )
        agg["tick_count"] += sub["tick_count"]
        agg["total_input_tokens"] += sub["total_input_tokens"]
        agg["total_cache_read_input_tokens"] += sub[
            "total_cache_read_input_tokens"
        ]
        agg["total_cache_write_input_tokens"] += sub[
            "total_cache_write_input_tokens"
        ]
        agg["total_output_tokens"] += sub["total_output_tokens"]
        agg["total_cost_usd_observed"] += sub["total_cost_usd_observed"]
        sub_e = sub["earliest_tick_utc"]
        sub_l = sub["latest_tick_utc"]
        if sub_e is not None:
            if agg["earliest_tick_utc"] is None or sub_e < agg["earliest_tick_utc"]:
                agg["earliest_tick_utc"] = sub_e
        if sub_l is not None:
            if agg["latest_tick_utc"] is None or sub_l > agg["latest_tick_utc"]:
                agg["latest_tick_utc"] = sub_l

    agg["total_cost_usd_observed"] = round(agg["total_cost_usd_observed"], 6)
    return agg


def _iter_jsonl(path: Path) -> Iterator[dict[str, Any]]:
    """Yield each JSON-decoded line in a JSONL file."""
    with path.open("r", encoding="utf-8") as fp:
        for line_no, line in enumerate(fp, start=1):
            line = line.strip()
            if not line:
                continue
            try:
                yield json.loads(line)
            except json.JSONDecodeError:
                # Skip malformed lines but record their presence so the
                # operator knows the session log had garbage.
                sys.stderr.write(
                    f"WARN: malformed line {line_no} in {path}\n"
                )


def _extract_user_text(record: dict[str, Any]) -> str:
    """Pull the user-message text out of an OpenClaw record."""
    content = (
        record.get("content")
        or (record.get("message") or {}).get("content")
        or ""
    )
    if isinstance(content, list):
        parts = []
        for block in content:
            if isinstance(block, dict):
                parts.append(str(block.get("text", "")))
        return "\n".join(parts)
    if isinstance(content, str):
        return content
    return ""


def _extract_timestamp(record: dict[str, Any]) -> Optional[str]:
    """Pull a UTC timestamp string from a record (best-effort)."""
    for key in ("timestamp", "ts", "started_at"):
        value = record.get(key)
        if isinstance(value, str) and value:
            return value
    msg = record.get("message")
    if isinstance(msg, dict):
        for key in ("timestamp", "ts"):
            value = msg.get(key)
            if isinstance(value, str) and value:
                return value
    return None


def _extract_usage(record: dict[str, Any]) -> dict[str, Any]:
    """Pull the per-message ``usage`` object from an assistant record."""
    msg = record.get("message")
    if isinstance(msg, dict):
        usage = msg.get("usage")
        if isinstance(usage, dict):
            return usage
    usage = record.get("usage")
    if isinstance(usage, dict):
        return usage
    return {}


# ---------------------------------------------------------------------------
# Baseline assembly
# ---------------------------------------------------------------------------


def build_historical_baseline(
    aggregate: dict[str, Any],
    *,
    window_days: int,
    git_sha: str,
    git_branch: str,
    source_path: Path,
    source_kind: str = "session",
    tick_marker: str = DEFAULT_TICK_MARKER,
    window_start: Optional[str] = None,
    window_end: Optional[str] = None,
) -> dict[str, Any]:
    """Build the baseline JSON from a historical aggregate.

    ``source_kind`` is either ``"session"`` (single JSONL) or
    ``"session-dir"`` (a directory walked for all session files).
    ``window_start`` / ``window_end`` echo the operator-supplied window
    bounds into the methodology so future readers can reproduce the
    cut.
    """
    captured_at = datetime.now(tz=timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    total_in = aggregate["total_input_tokens"]
    total_cache_r = aggregate["total_cache_read_input_tokens"]
    total_cache_w = aggregate["total_cache_write_input_tokens"]
    total_out = aggregate["total_output_tokens"]
    tick_count = aggregate["tick_count"]
    observed_cost = float(aggregate.get("total_cost_usd_observed", 0.0) or 0.0)

    # Sonnet pricing applied to billable input + output (fallback when
    # the session log does not carry an observed ``cost.total`` block).
    # Anthropic bills (input + cache_read) at input rate; cache_write
    # at the standard input rate today (the legacy 25% cache-write
    # surcharge has been retired).
    billable_input = total_in + total_cache_r + total_cache_w
    sonnet_input_usd = (
        billable_input / 1_000_000
    ) * DEFAULT_SONNET_INPUT_USD_PER_MTOK
    sonnet_output_usd = (
        total_out / 1_000_000
    ) * DEFAULT_SONNET_OUTPUT_USD_PER_MTOK
    estimated_cost_usd = sonnet_input_usd + sonnet_output_usd
    # Prefer the directly-observed cost (OpenClaw records the priced
    # value per turn) over re-derived list-price math when present.
    measured_cost_usd = observed_cost if observed_cost > 0 else estimated_cost_usd
    cost_source = (
        "observed-from-session-log"
        if observed_cost > 0
        else "computed-from-list-pricing"
    )
    ticks_per_day = tick_count / window_days if window_days > 0 else 0
    daily_cost_usd = (
        (measured_cost_usd / window_days) if window_days > 0 else 0
    )
    monthly_cost_usd = daily_cost_usd * 30

    return {
        "schema_version": "1.0",
        "name": "felix-heartbeat-gate-pre-rollout",
        "captured_at_utc": captured_at,
        "captured_at": captured_at,
        "captured_by": "#490-WP03",
        "captured_via": (
            "scripts/openclaw/heartbeat_gate/baselines/measure-tokens.py "
            f"--mode historical --{source_kind} {source_path} on office2"
        ),
        "subject": {
            "service": "openclaw-main-heartbeat",
            "implementation": (
                "Pre-rollout: OpenClaw heartbeat invokes main agent "
                "(Sonnet 4.6) directly every ~30 minutes when "
                "HEARTBEAT.md has tasks; otherwise emits a silent "
                "ok-token without an LLM call."
            ),
            "host": "office2",
            "model": "anthropic/claude-sonnet-4-6",
            "git_sha": git_sha,
            "git_branch": git_branch,
            "source_kind": source_kind,
            "source_path": str(source_path),
            "files_walked": aggregate.get("files_walked"),
        },
        "window_days": window_days,
        "measurement_window": {
            "tick_count": tick_count,
            "earliest_tick_utc": aggregate["earliest_tick_utc"],
            "latest_tick_utc": aggregate["latest_tick_utc"],
            "window_start_filter_utc": window_start,
            "window_end_filter_utc": window_end,
            "spans_hours": window_days * 24,
        },
        "total_heartbeats": tick_count,
        "total_input_tokens": total_in,
        "total_cache_hit_tokens": total_cache_r,
        "total_cache_write_tokens": total_cache_w,
        "total_output_tokens": total_out,
        "ticks_per_day": ticks_per_day,
        "observed_total_cost_usd": round(observed_cost, 6),
        "estimated_total_cost_usd_from_list_pricing": round(
            estimated_cost_usd, 6
        ),
        "estimated_monthly_cost_usd": round(monthly_cost_usd, 2),
        "cost_source": cost_source,
        "methodology": {
            "summary": (
                "Walk the OpenClaw main-agent session JSONL(s) on "
                "office2, identify each heartbeat tick by the literal "
                "preamble OpenClaw injects ('Read HEARTBEAT.md if it "
                "exists (workspace context)...'), then sum the per-turn "
                "`usage` records WITHIN each tick. OpenClaw records the "
                "Anthropic-priced cost per turn in `usage.cost.total`; "
                "the baseline prefers that observed value over "
                "re-applying list-price math. Sonnet 4.6 list price is "
                "retained for fallback and for the post-rollout Haiku "
                "comparison. The measurement reflects only main-agent "
                "heartbeats — WhatsApp-triage turns and ESCALATE events "
                "from other paths are excluded by the preamble filter."
            ),
            "tick_marker_regex": tick_marker,
            "window_start_filter_utc": window_start,
            "window_end_filter_utc": window_end,
            "pricing": {
                "sonnet_input_usd_per_mtok": DEFAULT_SONNET_INPUT_USD_PER_MTOK,
                "sonnet_output_usd_per_mtok": DEFAULT_SONNET_OUTPUT_USD_PER_MTOK,
                "haiku_input_usd_per_mtok": DEFAULT_HAIKU_INPUT_USD_PER_MTOK,
                "haiku_output_usd_per_mtok": DEFAULT_HAIKU_OUTPUT_USD_PER_MTOK,
            },
            "billing_model_note": (
                "We treat total_input_tokens_billable = input + cache_read "
                "+ cache_write (cache-read and cache-write are charged at "
                "different per-token rates but all consume the input-side "
                "quota). When OpenClaw's `usage.cost.total` field is "
                "present on the assistant turn, that priced value is "
                "summed directly and `cost_source = "
                "observed-from-session-log`."
            ),
            "reproduction_steps": [
                "1. SSH to office2 (`ssh office2-claude`).",
                "2. Locate the main-agent session directory: "
                "`/home/claude/.openclaw/agents/main/sessions/`.",
                "3. Run: `python3 scripts/openclaw/heartbeat_gate/baselines/"
                "measure-tokens.py --mode historical --session-dir "
                "/home/claude/.openclaw/agents/main/sessions "
                "--window-start <ISO> --window-end <ISO> "
                "--window-days <N> --out /tmp/baseline.json`.",
                "4. Spot-check the tick_count against the OpenClaw "
                "heartbeat cadence and HEARTBEAT.md fill rate (only "
                "ticks with non-template HEARTBEAT.md content produce "
                "an LLM call; the empty-skip rule short-circuits most "
                "ticks to silent ok-token).",
                "5. Promote into the baselines directory: "
                "`cp /tmp/baseline.json docs/design/architecture/baselines/"
                "felix-heartbeat-gate-pre-rollout.json` and commit.",
            ],
        },
    }


def build_sample_placeholder(
    *,
    git_sha: str,
    git_branch: str,
    note: str,
) -> dict[str, Any]:
    """Build a placeholder baseline when historical data isn't extractable.

    Used when:
    - The OpenClaw heartbeat session JSONL isn't accessible on office2.
    - The session log doesn't have a reliable per-tick preamble.
    - The operator wants to sample fresh data before cutover.

    The placeholder is honest: ``total_heartbeats`` and token counts
    are zero, and ``methodology`` explains that the measurement is
    deferred pending a sample-collection window.
    """
    captured_at = datetime.now(tz=timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    return {
        "schema_version": "1.0",
        "name": "felix-heartbeat-gate-pre-rollout",
        "captured_at_utc": captured_at,
        "captured_at": captured_at,
        "captured_by": "#490-WP03",
        "captured_via": (
            "scripts/openclaw/heartbeat_gate/baselines/measure-tokens.py "
            "--mode sample (placeholder; awaiting sample-collection window)"
        ),
        "subject": {
            "service": "openclaw-main-heartbeat",
            "implementation": (
                "Pre-rollout: OpenClaw heartbeat invokes main agent "
                "(Sonnet 4.6) directly every ~30 minutes."
            ),
            "host": "office2",
            "model": "anthropic/claude-sonnet-4-6",
            "git_sha": git_sha,
            "git_branch": git_branch,
        },
        "window_days": 0,
        "measurement_window": {
            "tick_count": 0,
            "earliest_tick_utc": None,
            "latest_tick_utc": None,
            "spans_hours": 0,
        },
        "total_heartbeats": 0,
        "total_input_tokens": 0,
        "total_cache_hit_tokens": 0,
        "total_cache_write_tokens": 0,
        "total_output_tokens": 0,
        "ticks_per_day": 0,
        "estimated_monthly_cost_usd": 0,
        "methodology": {
            "summary": (
                "DEFERRED -- historical sampling deferred to the "
                "post-rollout window. The pre-rollout baseline is "
                "captured by re-running this script in `--mode historical` "
                "against an OpenClaw main-agent session JSONL covering "
                "≥7 days of heartbeats. At T022 time the historical "
                "JSONL was not extractable from outside office2 (the "
                "WP03 implementing agent is running on the Mac lane-c "
                "worktree), so this placeholder marks the measurement "
                "as pending."
            ),
            "deferred_reason": note,
            "tick_marker_regex": DEFAULT_TICK_MARKER,
            "pricing": {
                "sonnet_input_usd_per_mtok": DEFAULT_SONNET_INPUT_USD_PER_MTOK,
                "sonnet_output_usd_per_mtok": DEFAULT_SONNET_OUTPUT_USD_PER_MTOK,
                "haiku_input_usd_per_mtok": DEFAULT_HAIKU_INPUT_USD_PER_MTOK,
                "haiku_output_usd_per_mtok": DEFAULT_HAIKU_OUTPUT_USD_PER_MTOK,
            },
            "reproduction_steps": [
                "1. SSH to office2 (`ssh office2-claude`).",
                "2. Locate the active main-agent session JSONL: "
                "`ls -la /home/claude/.openclaw/agents/main/sessions/`.",
                "3. Run: `python3 scripts/openclaw/heartbeat_gate/baselines/"
                "measure-tokens.py --mode historical --session <path> "
                "--window-days 7 --out /tmp/baseline.json`.",
                "4. Replace this placeholder with the historical output.",
            ],
            "future_use": (
                "Post-rollout WP-04 reads ``gate-ledger.jsonl`` and "
                "any Sonnet escalation cost from the OpenClaw session "
                "log; the ratio (post-rollout daily cost) / (this "
                "baseline daily cost) must be ≤0.20 for NFR-001 to "
                "pass. With a 0-cost placeholder the ratio is "
                "undefined and the comparison defers to the captured "
                "historical baseline."
            ),
        },
        "open_caveats": [
            (
                "Placeholder baseline. Re-run in --mode historical against "
                "an office2 session JSONL before declaring NFR-001 "
                "satisfied."
            ),
        ],
    }


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


def _git_sha(repo_root: Optional[Path] = None) -> str:
    """Best-effort ``git rev-parse HEAD``. Returns empty string on failure."""
    try:
        out = subprocess.run(
            ["git", "rev-parse", "HEAD"],
            cwd=str(repo_root) if repo_root else None,
            capture_output=True,
            text=True,
            timeout=5,
            check=False,
        )
        return (out.stdout or "").strip()
    except (OSError, subprocess.TimeoutExpired):
        return ""


def _git_branch(repo_root: Optional[Path] = None) -> str:
    """Best-effort ``git rev-parse --abbrev-ref HEAD``."""
    try:
        out = subprocess.run(
            ["git", "rev-parse", "--abbrev-ref", "HEAD"],
            cwd=str(repo_root) if repo_root else None,
            capture_output=True,
            text=True,
            timeout=5,
            check=False,
        )
        return (out.stdout or "").strip()
    except (OSError, subprocess.TimeoutExpired):
        return ""


def main(argv: Optional[list[str]] = None) -> int:
    parser = argparse.ArgumentParser(
        prog="measure-tokens",
        description=(
            "Capture pre-rollout heartbeat-gate token baseline. See "
            "docs/design/architecture/baselines/README.md for the schema."
        ),
    )
    parser.add_argument(
        "--mode",
        choices=("historical", "sample"),
        required=True,
        help=(
            "historical = read OpenClaw session JSONL; "
            "sample = emit placeholder baseline with deferred methodology"
        ),
    )
    parser.add_argument(
        "--session",
        type=Path,
        help=(
            "(historical mode) Path to one OpenClaw main-agent session "
            "JSONL. Mutually exclusive with --session-dir."
        ),
    )
    parser.add_argument(
        "--session-dir",
        type=Path,
        help=(
            "(historical mode) Path to the OpenClaw main-agent sessions "
            "directory. Walks every `*.jsonl*` file (including reset / "
            "deleted variants). Use this for the multi-month corpus on "
            "office2 where heartbeats span many session files."
        ),
    )
    parser.add_argument(
        "--window-days",
        type=int,
        default=7,
        help="(historical mode) Window width for daily-rate normalization.",
    )
    parser.add_argument(
        "--window-start",
        default=None,
        help=(
            "(historical mode, optional) ISO-8601 UTC lower bound on "
            "tick timestamps (inclusive). Use to exclude pre-cutover or "
            "API-spend-cap days from the aggregate."
        ),
    )
    parser.add_argument(
        "--window-end",
        default=None,
        help=(
            "(historical mode, optional) ISO-8601 UTC upper bound on "
            "tick timestamps (exclusive)."
        ),
    )
    parser.add_argument(
        "--tick-marker",
        default=DEFAULT_TICK_MARKER,
        help="(historical mode) Override the heartbeat preamble regex.",
    )
    parser.add_argument(
        "--note",
        default=(
            "WP03 implementer ran from Mac lane-c worktree; office2 "
            "session log not reachable from this execution context. "
            "Defer historical extraction to a pre-cutover operator run."
        ),
        help="(sample mode) Free-form reason populated into methodology.",
    )
    parser.add_argument(
        "--out",
        type=Path,
        required=True,
        help="Output path for the baseline JSON.",
    )
    args = parser.parse_args(argv)

    git_sha = _git_sha()
    git_branch = _git_branch()

    if args.mode == "historical":
        if (args.session is None) == (args.session_dir is None):
            sys.stderr.write(
                "ERROR: --mode historical requires exactly one of "
                "--session <path> or --session-dir <path>.\n"
            )
            return 1
        if args.session is not None:
            if not args.session.is_file():
                sys.stderr.write(
                    f"ERROR: --session must be a file; got: {args.session}\n"
                )
                return 1
            aggregate = aggregate_session(
                args.session,
                tick_marker=args.tick_marker,
                window_start=args.window_start,
                window_end=args.window_end,
            )
            source_path = args.session
            source_kind = "session"
        else:
            if not args.session_dir.is_dir():
                sys.stderr.write(
                    "ERROR: --session-dir must be a directory; "
                    f"got: {args.session_dir}\n"
                )
                return 1
            aggregate = aggregate_session_dir(
                args.session_dir,
                tick_marker=args.tick_marker,
                window_start=args.window_start,
                window_end=args.window_end,
            )
            source_path = args.session_dir
            source_kind = "session-dir"
        if aggregate["tick_count"] == 0:
            sys.stderr.write(
                "ERROR: no ticks matched the preamble regex in "
                f"{source_path}. Use --tick-marker to override, widen the "
                "--window-start/--window-end bounds, or run in --mode "
                "sample to emit a placeholder.\n"
            )
            return 2
        payload = build_historical_baseline(
            aggregate,
            window_days=args.window_days,
            git_sha=git_sha,
            git_branch=git_branch,
            source_path=source_path,
            source_kind=source_kind,
            tick_marker=args.tick_marker,
            window_start=args.window_start,
            window_end=args.window_end,
        )
    else:
        payload = build_sample_placeholder(
            git_sha=git_sha, git_branch=git_branch, note=args.note
        )

    args.out.parent.mkdir(parents=True, exist_ok=True)
    _atomic_write_json(args.out, payload)
    print(f"wrote {args.out}")
    return 0


def _atomic_write_json(path: Path, payload: dict[str, Any]) -> None:
    """Write ``payload`` to ``path`` atomically (write tmp + rename)."""
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(
        json.dumps(payload, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
    tmp.replace(path)


if __name__ == "__main__":  # pragma: no cover - CLI entry
    sys.exit(main())
