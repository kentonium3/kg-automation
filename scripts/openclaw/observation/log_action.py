#!/usr/bin/env python3
"""Deterministic log writer for Felix agent actions.

Receives structured CLI arguments from agents (via OpenClaw exec tool),
validates them, and appends a single JSONL entry to the correct daily
log file. Agents determine WHAT to log; this script owns HOW.

Added by F014 — Felix Core Digest.
"""

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

VALID_CATEGORIES = ("routine", "flagged", "error", "security")
MAX_STRING_LENGTH = 120
TRUNCATION_SUFFIX = "[truncated]"

# Fields that are controlled values — never truncated
NO_TRUNCATE_FIELDS = {"ts", "run_id", "agent", "category", "autonomy_level"}


def _truncate(value):
    """Truncate string to MAX_STRING_LENGTH and append suffix if exceeded."""
    if isinstance(value, str) and len(value) > MAX_STRING_LENGTH:
        return value[:MAX_STRING_LENGTH] + TRUNCATION_SUFFIX
    return value


def _truncate_dict(d):
    """Truncate all string values in a dict (non-recursive for top level)."""
    return {k: _truncate(v) if isinstance(v, str) else v for k, v in d.items()}


def _build_entry(args, config):
    """Build and return the JSONL entry dict."""
    now = datetime.now(timezone.utc)

    entry = {
        "ts": now.strftime("%Y-%m-%dT%H:%M:%SZ"),
        "run_id": f"{args.agent}-{now.strftime('%Y%m%d')}-{now.strftime('%H%M')}",
        "agent": args.agent,
        "autonomy_level": config.autonomy_level(args.agent),
        "category": args.category,
        "action": _truncate(args.action),
        "target": _truncate(args.target),
        "outcome": _truncate(args.outcome),
    }

    verbosity = config.log_verbosity(args.agent)

    # Context block: standard + verbose only
    if args.context and verbosity in ("standard", "verbose"):
        context = json.loads(args.context)
        entry["context"] = _truncate_dict(context)

    # Trace block: verbose only
    if args.trace and verbosity == "verbose":
        entry["trace"] = json.loads(args.trace)

    return entry, now


def _write_entry(entry, now, agent_name, log_dir):
    """Append JSONL entry to the correct daily log file."""
    agent_dir = log_dir / agent_name
    agent_dir.mkdir(parents=True, exist_ok=True)

    filename = now.strftime("%Y-%m-%d") + ".jsonl"
    log_file = agent_dir / filename

    with open(log_file, "a") as f:
        f.write(json.dumps(entry, ensure_ascii=False) + "\n")


def main():
    parser = argparse.ArgumentParser(
        description="Deterministic log writer for Felix agent actions."
    )
    parser.add_argument("--agent", required=True, help="Agent name")
    parser.add_argument("--category", required=True, help="Action category")
    parser.add_argument("--action", required=True, help="What the agent did")
    parser.add_argument("--target", required=True, help="What the action operated on")
    parser.add_argument("--outcome", required=True, help="Result of the action")
    parser.add_argument("--context", default=None, help="JSON string of context data")
    parser.add_argument("--trace", default=None, help="JSON string of trace/debug data")
    parser.add_argument("--registry", default=None, help="Path to agent-registry.json")
    parser.add_argument("--log-dir", default=None, help="Path to log directory")

    args = parser.parse_args()

    # Validate category
    if args.category not in VALID_CATEGORIES:
        print(
            f"Error: Invalid category '{args.category}'. "
            f"Must be one of: {', '.join(VALID_CATEGORIES)}",
            file=sys.stderr,
        )
        sys.exit(1)

    # Validate required fields are non-empty
    for field_name in ("agent", "action", "target", "outcome"):
        value = getattr(args, field_name)
        if not value or not value.strip():
            print(f"Error: --{field_name} must be non-empty", file=sys.stderr)
            sys.exit(1)

    # Validate JSON args if provided
    if args.context:
        try:
            json.loads(args.context)
        except json.JSONDecodeError as e:
            print(f"Error: Invalid JSON in --context: {e}", file=sys.stderr)
            sys.exit(1)

    if args.trace:
        try:
            json.loads(args.trace)
        except json.JSONDecodeError as e:
            print(f"Error: Invalid JSON in --trace: {e}", file=sys.stderr)
            sys.exit(1)

    # Load config
    from config import ObservationConfig

    registry_path = args.registry
    log_dir = Path(args.log_dir) if args.log_dir else None

    try:
        config = ObservationConfig(registry_path=registry_path)
    except (FileNotFoundError, ValueError) as e:
        print(f"Error: {e}", file=sys.stderr)
        sys.exit(1)

    if log_dir is None:
        log_dir = config.log_dir

    # Build and write entry
    try:
        entry, now = _build_entry(args, config)
        _write_entry(entry, now, args.agent, log_dir)
    except KeyError as e:
        print(f"Error: {e}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
