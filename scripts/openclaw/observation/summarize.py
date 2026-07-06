#!/usr/bin/env python3
"""Felix Observation Intelligence Layer.

Centralized summarization script that reads agent activity logs (JSONL format),
applies autonomy-level-based filtering, and produces consolidated digests for
the Obsidian vault. Sends WhatsApp critical alerts when errors or security
items are detected.

JSONL log format:
  Each agent writes a JSONL log to /home/kgale/second-brain/agents/logs/{agent-name}/
  after every run. Each line is a JSON object with fields:
    ts, run_id, agent, autonomy_level, category, action, target, outcome
  Optional fields: context (object), trace (object)

  Categories:
    routine  - normal successful operations
    flagged  - items requiring Kent's attention
    error    - operation failures (critical alert)
    security - security concerns (critical alert)

Usage:
  python summarize.py                    # Normal run (today's logs)
  python summarize.py --date 2026-04-01  # Specific date
  python summarize.py --dry-run          # Parse and print, don't write files
"""

import argparse
import json
import os
import re
import sys
from datetime import datetime, date, timedelta
from pathlib import Path

try:
    from scripts.openclaw.observation.config import ObservationConfig
except ImportError:
    from config import ObservationConfig

# Required fields in each JSONL log entry
REQUIRED_FIELDS = {"agent", "category", "action", "target", "outcome"}

# Retention window: digest files older than this many days are deleted
RETENTION_DAYS = 5

# Pattern to extract date from digest filenames like YYYY-MM-DD-log.md
DIGEST_DATE_PATTERN = re.compile(r"^(\d{4}-\d{2}-\d{2})-log\.md$")


def parse_jsonl_log(path):
    """Parse a JSONL log file and return a list of action dicts.

    Each returned dict has at minimum: category, text, agent_name, run_id, ts.
    The 'category' and 'text' keys are compatible with the processing layer
    (filter_actions_by_autonomy, detect_critical_alerts, summarize_routine_actions).

    Invalid lines are logged to stderr and skipped.
    Empty lines are skipped silently.
    """
    path = Path(path)
    entries = []

    with open(path) as f:
        for line_num, raw_line in enumerate(f, 1):
            line = raw_line.strip()
            if not line:
                continue

            try:
                entry = json.loads(line)
            except json.JSONDecodeError as e:
                print(
                    f"WARNING: Skipping malformed line {line_num} in {path}: {e}",
                    file=sys.stderr,
                )
                continue

            if not isinstance(entry, dict):
                print(
                    f"WARNING: Skipping malformed line {line_num} in {path}: "
                    f"expected object, got {type(entry).__name__}",
                    file=sys.stderr,
                )
                continue

            missing = REQUIRED_FIELDS - set(entry.keys())
            if missing:
                print(
                    f"WARNING: Skipping malformed line {line_num} in {path}: "
                    f"missing required fields: {sorted(missing)}",
                    file=sys.stderr,
                )
                continue

            # Build processing-layer compatible dict
            action_dict = {
                "category": entry["category"],
                "text": f"{entry['action']}: {entry['target']}",
                "agent_name": entry["agent"],
                "run_id": entry.get("run_id", "unknown"),
                "ts": entry.get("ts", ""),
                "outcome": entry["outcome"],
            }

            # Preserve optional fields
            if "context" in entry:
                action_dict["context"] = entry["context"]
            if "trace" in entry:
                action_dict["trace"] = entry["trace"]
            if "autonomy_level" in entry:
                action_dict["autonomy_level"] = entry["autonomy_level"]

            entries.append(action_dict)

    return entries


def filter_actions_by_autonomy(actions, autonomy_level):
    """Filter actions based on agent's autonomy level.

    Assisted/Observed: all categories surfaced.
    Autonomous: only flagged, error, security (routine omitted).
    """
    if autonomy_level in ("assisted", "observed"):
        return actions
    elif autonomy_level == "autonomous":
        return [a for a in actions if a["category"] != "routine"]
    else:
        return actions


def detect_critical_alerts(actions):
    """Return True if any action is an error or security concern."""
    return any(a["category"] in ("error", "security") for a in actions)


def summarize_routine_actions(actions):
    """Summarize routine actions as a count string."""
    routine = [a for a in actions if a["category"] == "routine"]
    if not routine:
        return "No routine actions"
    return f"{len(routine)} routine actions completed"


def generate_digest(agent_digests, target_date):
    """Generate the overview.md digest content.

    Args:
        agent_digests: dict of agent_name -> digest info
        target_date: date string (YYYY-MM-DD)

    Returns:
        Markdown string for overview.md
    """
    lines = [
        f"# Agent Activity — {target_date}",
        "",
        f"*Generated: {datetime.now().strftime('%Y-%m-%d %H:%M')} ET | Window: last 24 hours*",
        "",
    ]

    has_critical = False

    for agent_name, digest in sorted(agent_digests.items()):
        level = digest["autonomy_level"].capitalize()
        lines.append(f"## {agent_name} ({level})")
        lines.append("")

        if digest.get("routine_summary"):
            lines.append(f"**Routine**: {digest['routine_summary']} ({digest['runs']} run{'s' if digest['runs'] != 1 else ''})")
            lines.append("")

        if digest.get("elevated"):
            lines.append("**Attention needed:**")
            for item in digest["elevated"]:
                icon = "\U0001f6a8" if item["category"] in ("error", "security") else "\u26a0"
                lines.append(f"- {icon} {item['text']}")
            lines.append("")

        if digest.get("critical"):
            has_critical = True

        lines.append(f"**Full log**: `{digest['log_ref']}`")
        lines.append("")
        lines.append("---")
        lines.append("")

    if has_critical:
        lines.append("\U0001f6a8 **Critical alerts detected** \u2014 see details above.")
    else:
        lines.append("*No critical alerts today.*")
    lines.append("")

    return "\n".join(lines)


def generate_agent_detail(agent_name, run_groups, autonomy_level, target_date):
    """Generate per-agent detail file content.

    Args:
        agent_name: Name of the agent.
        run_groups: List of (run_id, actions_list) tuples, one per run.
        autonomy_level: The agent's autonomy level string.
        target_date: Date string (YYYY-MM-DD) for the filename.

    Returns:
        Markdown string for the per-agent detail file.
    """
    level = autonomy_level.capitalize()
    lines = [
        f"# {agent_name} — {target_date}",
        "",
        f"*Autonomy Level: {level} | Runs today: {len(run_groups)}*",
        "",
    ]

    flagged_items = []

    for i, (run_id, actions) in enumerate(run_groups, 1):
        # Use the first entry's ts as run time if available
        run_time = actions[0].get("ts", "unknown") if actions else "unknown"
        lines.append(f"## Run {i} — {run_time}")

        routine_count = sum(1 for a in actions if a["category"] == "routine")
        if routine_count:
            lines.append(f"**Routine**: {routine_count} actions completed")

        elevated = [a for a in actions if a["category"] in ("flagged", "error", "security")]
        for item in elevated:
            icon = "\U0001f6a8" if item["category"] in ("error", "security") else "\u26a0"
            lines.append(f"**{item['category'].capitalize()}**: {icon} {item['text']}")
            flagged_items.append(item)

        lines.append("")

    if flagged_items:
        lines.append("## Flagged Items")
        lines.append("")
        for item in flagged_items:
            icon = "\U0001f6a8" if item["category"] in ("error", "security") else "\u26a0"
            lines.append(f"- {icon} {item['text']}")
        lines.append("")

    return "\n".join(lines)


def format_whatsapp_alert(critical_items, target_date):
    """Format a brief WhatsApp critical alert message.

    Kept under 5 lines for WhatsApp readability.
    """
    lines = [f"\U0001f6a8 Felix Alert — {target_date}", ""]

    for agent_name, items in critical_items.items():
        count = len(items)
        label = "error" if count == 1 else "errors"
        lines.append(f"{agent_name}: {count} {label}")
        if items:
            lines.append(f'  "{items[0]["text"]}"')

    lines.append("")
    lines.append("Check Obsidian: Agent-Logs/overview.md")

    return "\n".join(lines)


def find_log_files(log_dir, target_date):
    """Find JSONL log files for target_date across all agent subdirectories.

    Walks log_dir looking for subdirectories (each is an agent name).
    In each subdirectory, looks for {target_date}.jsonl.

    Returns dict: {agent_name: Path} mapping agent names to their daily log files.
    """
    log_dir = Path(log_dir)
    if not log_dir.exists():
        return {}

    date_str = target_date if isinstance(target_date, str) else target_date.isoformat()
    result = {}

    for entry in sorted(log_dir.iterdir()):
        if not entry.is_dir():
            continue
        agent_name = entry.name
        log_file = entry / f"{date_str}.jsonl"
        if log_file.exists():
            result[agent_name] = log_file

    return result


def _group_by_run_id(actions):
    """Group a list of action dicts by run_id, preserving order.

    Returns a list of (run_id, [actions]) tuples.
    """
    seen = {}
    order = []
    for action in actions:
        rid = action.get("run_id", "unknown")
        if rid not in seen:
            seen[rid] = []
            order.append(rid)
        seen[rid].append(action)
    return [(rid, seen[rid]) for rid in order]


def _apply_retention(agent_logs_dir, target_date):
    """Delete digest files with filename dates > RETENTION_DAYS old.

    Scans each agent subdirectory under agent_logs_dir for files matching
    YYYY-MM-DD-log.md. Files with dates more than RETENTION_DAYS before
    target_date are deleted.

    overview.md is never subject to retention.
    """
    if not agent_logs_dir.exists():
        return

    if isinstance(target_date, str):
        target_dt = date.fromisoformat(target_date)
    else:
        target_dt = target_date

    cutoff = target_dt - timedelta(days=RETENTION_DAYS)

    for entry in agent_logs_dir.iterdir():
        if not entry.is_dir():
            continue
        for file in entry.iterdir():
            match = DIGEST_DATE_PATTERN.match(file.name)
            if not match:
                continue
            try:
                file_date = date.fromisoformat(match.group(1))
            except ValueError:
                print(
                    f"WARNING: Could not parse date from filename {file}: skipping retention",
                    file=sys.stderr,
                )
                continue
            if file_date < cutoff:
                file.unlink()


def run(config, target_date, dry_run=False):
    """Main execution flow.

    Returns a dict with the digest content and critical alert status.
    """
    agent_logs_dir = config.output_dir / "Agent-Logs"
    agent_log_files = find_log_files(config.log_dir, target_date)

    if not agent_log_files:
        overview = (
            f"# Agent Activity — {target_date}\n\n"
            f"*Generated: {datetime.now().strftime('%Y-%m-%d %H:%M')} ET*\n\n"
            "No agent activity recorded today.\n"
        )
        if not dry_run:
            agent_logs_dir.mkdir(parents=True, exist_ok=True)
            (agent_logs_dir / "overview.md").write_text(overview)
        return {"overview": overview, "critical": False, "alert_message": None}

    # Check idempotency: skip agents whose JSONL hasn't changed since last digest
    agents_to_process = {}
    any_processed = False

    for agent_name, log_path in agent_log_files.items():
        digest_path = agent_logs_dir / agent_name / f"{target_date}-log.md"
        if digest_path.exists():
            log_mtime = os.path.getmtime(log_path)
            digest_mtime = os.path.getmtime(digest_path)
            if log_mtime <= digest_mtime:
                continue  # Skip — no new content
        agents_to_process[agent_name] = log_path
        any_processed = True

    if not any_processed:
        # All agents skipped — no new content
        # Read existing overview if available
        overview_path = agent_logs_dir / "overview.md"
        if overview_path.exists():
            overview = overview_path.read_text()
        else:
            overview = ""
        return {"overview": overview, "critical": False, "alert_message": None}

    # Parse all agent logs (including skipped ones for complete overview)
    all_agent_actions = {}
    for agent_name, log_path in agent_log_files.items():
        try:
            actions = parse_jsonl_log(log_path)
            if actions:
                all_agent_actions[agent_name] = actions
        except Exception as e:
            print(f"Warning: Failed to parse {log_path}: {e}", file=sys.stderr)

    # Build digests per agent
    agent_digests = {}
    critical_items = {}

    for agent_name, actions in all_agent_actions.items():
        try:
            level = config.autonomy_level(agent_name)
        except KeyError:
            level = "assisted"  # default for unregistered agents

        run_groups = _group_by_run_id(actions)

        filtered = filter_actions_by_autonomy(actions, level)
        routine = [a for a in filtered if a["category"] == "routine"]
        elevated = [a for a in filtered if a["category"] != "routine"]
        is_critical = detect_critical_alerts(actions)

        routine_summary = summarize_routine_actions(routine) if routine else None

        agent_digests[agent_name] = {
            "autonomy_level": level,
            "runs": len(run_groups),
            "routine_summary": routine_summary,
            "elevated": elevated,
            "critical": is_critical,
            "log_ref": f"Agent-Logs/{agent_name}/{target_date}-log.md",
            "run_groups": run_groups,
        }

        if is_critical:
            critical_items[agent_name] = [
                a for a in actions if a["category"] in ("error", "security")
            ]

    # Generate outputs
    overview = generate_digest(agent_digests, target_date)

    alert_message = None
    if critical_items:
        alert_message = format_whatsapp_alert(critical_items, target_date)

    if dry_run:
        print("=== OVERVIEW ===")
        print(overview)
        if alert_message:
            print("\n=== WHATSAPP ALERT ===")
            print(alert_message)
        for agent_name, digest in agent_digests.items():
            detail = generate_agent_detail(
                agent_name, digest["run_groups"],
                digest["autonomy_level"], target_date,
            )
            print(f"\n=== {agent_name.upper()} DETAIL ===")
            print(detail)
    else:
        agent_logs_dir.mkdir(parents=True, exist_ok=True)
        (agent_logs_dir / "overview.md").write_text(overview)

        for agent_name, digest in agent_digests.items():
            if agent_name not in agents_to_process:
                continue  # Skip writing for idempotent agents
            agent_dir = agent_logs_dir / agent_name
            agent_dir.mkdir(parents=True, exist_ok=True)
            detail = generate_agent_detail(
                agent_name, digest["run_groups"],
                digest["autonomy_level"], target_date,
            )
            (agent_dir / f"{target_date}-log.md").write_text(detail)

        # Retention: clean up old digest files
        _apply_retention(agent_logs_dir, target_date)

        # WhatsApp critical alert (T009)
        if alert_message:
            _send_whatsapp_alert(alert_message)

    return {
        "overview": overview,
        "critical": bool(critical_items),
        "alert_message": alert_message,
    }


def _send_whatsapp_alert(message):
    """Send a WhatsApp critical alert via OpenClaw.

    Conditional on WhatsApp DM policy being enabled.
    If sending fails, log the failure but do not fail the overall run.
    """
    try:
        # Check if WhatsApp is available by looking for the OpenClaw config
        # This is a placeholder — the actual send mechanism depends on
        # OpenClaw's WhatsApp channel integration.
        # For F012, we log the alert. Full WhatsApp integration activates
        # when DM policy is re-enabled.
        print(f"[WhatsApp Alert] Would send:\n{message}", file=sys.stderr)
        print("[WhatsApp Alert] Skipped — DM policy currently disabled. "
              "Alert is marked in Obsidian digest.", file=sys.stderr)
    except Exception as e:
        print(f"[WhatsApp Alert] Failed to send: {e}. "
              "Critical alert is still in Obsidian digest.", file=sys.stderr)


def main():
    parser = argparse.ArgumentParser(
        description="Felix Observation Intelligence Layer"
    )
    parser.add_argument(
        "--date",
        help="Target date (YYYY-MM-DD). Defaults to today.",
        default=None,
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Parse and print digest without writing files.",
    )
    parser.add_argument(
        "--registry",
        help="Path to agent-registry.json (default: auto-detect).",
        default=None,
    )
    parser.add_argument(
        "--log-dir",
        help="Path to agent log directory.",
        default=None,
    )
    parser.add_argument(
        "--output-dir",
        help="Path to Obsidian digest output directory.",
        default=None,
    )
    args = parser.parse_args()

    target_date = args.date or date.today().isoformat()

    try:
        config = ObservationConfig(
            registry_path=args.registry,
            log_dir=args.log_dir,
            output_dir=args.output_dir,
        )
    except (FileNotFoundError, ValueError) as e:
        print(f"Configuration error: {e}", file=sys.stderr)
        sys.exit(1)

    result = run(config, target_date, dry_run=args.dry_run)

    if result["critical"]:
        print(f"Critical alerts detected for {target_date}.", file=sys.stderr)
        sys.exit(0)  # success — alerts are informational, not failures


if __name__ == "__main__":
    main()
