#!/usr/bin/env python3
"""Felix Observation Intelligence Layer.

Centralized summarization script that reads agent activity logs,
applies autonomy-level-based filtering, and produces consolidated
digests for the Obsidian vault. Sends WhatsApp critical alerts
when errors or security items are detected.

Standardized log format:
  Each agent writes a markdown log to ~/second-brain/agents/logs/ after
  every run. Action lines are tagged with categories:
    [routine]  — normal successful operations
    [flagged]  — items requiring Kent's attention
    [error]    — operation failures (critical alert)
    [security] — security concerns (critical alert)

Usage:
  python summarize.py                    # Normal run (today's logs)
  python summarize.py --date 2026-04-01  # Specific date
  python summarize.py --dry-run          # Parse and print, don't write files
"""

import argparse
import re
import sys
from datetime import datetime, date
from pathlib import Path

from scripts.openclaw.observation.config import ObservationConfig

CATEGORY_PATTERN = re.compile(r"^\s*-\s*\[(\w+)\]\s*(.*)")
AGENT_PATTERN = re.compile(r"\*\*Agent\*\*:\s*(.+)")
RUN_TIME_PATTERN = re.compile(r"\*\*Run time\*\*:\s*(.+)")
SUMMARY_LINE_PATTERN = re.compile(r"^\s*-\s*(.+?):\s*(\d+)")


def parse_log_file(path):
    """Parse a structured agent activity log file.

    Returns a dict with agent_name, run_time, actions (list of
    {category, text}), and summary (dict of counts).
    """
    path = Path(path)
    content = path.read_text()

    agent_name = "unknown"
    run_time = "unknown"
    actions = []
    summary = {}

    in_actions = False
    in_summary = False

    for line in content.split("\n"):
        agent_match = AGENT_PATTERN.search(line)
        if agent_match:
            agent_name = agent_match.group(1).strip()
            continue

        run_match = RUN_TIME_PATTERN.search(line)
        if run_match:
            run_time = run_match.group(1).strip()
            continue

        if line.strip().startswith("## Actions taken"):
            in_actions = True
            in_summary = False
            continue

        if line.strip().startswith("## Summary"):
            in_actions = False
            in_summary = True
            continue

        if line.strip().startswith("## ") and line.strip() != "## Actions taken" and line.strip() != "## Summary":
            in_actions = False
            in_summary = False
            continue

        if in_actions and line.strip().startswith("-"):
            cat_match = CATEGORY_PATTERN.match(line)
            if cat_match:
                actions.append({
                    "category": cat_match.group(1),
                    "text": cat_match.group(2).strip(),
                })
            elif line.strip().startswith("- "):
                actions.append({
                    "category": "routine",
                    "text": line.strip()[2:],
                })

        if in_summary:
            sum_match = SUMMARY_LINE_PATTERN.match(line)
            if sum_match:
                summary[sum_match.group(1).strip()] = int(sum_match.group(2))

    return {
        "agent_name": agent_name,
        "run_time": run_time,
        "actions": actions,
        "summary": summary,
        "source_file": str(path.name),
    }


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
                icon = "🚨" if item["category"] in ("error", "security") else "⚠"
                lines.append(f"- {icon} {item['text']}")
            lines.append("")

        if digest.get("critical"):
            has_critical = True

        lines.append(f"**Full log**: `{digest['log_ref']}`")
        lines.append("")
        lines.append("---")
        lines.append("")

    if has_critical:
        lines.append("🚨 **Critical alerts detected** — see details above.")
    else:
        lines.append("*No critical alerts today.*")
    lines.append("")

    return "\n".join(lines)


def generate_agent_detail(agent_name, parsed_logs, autonomy_level, target_date):
    """Generate per-agent detail file content."""
    level = autonomy_level.capitalize()
    lines = [
        f"# {agent_name} — {target_date}",
        "",
        f"*Autonomy Level: {level} | Runs today: {len(parsed_logs)}*",
        "",
    ]

    flagged_items = []

    for i, log in enumerate(parsed_logs, 1):
        lines.append(f"## Run {i} — {log['run_time']}")

        routine_count = sum(1 for a in log["actions"] if a["category"] == "routine")
        if routine_count:
            lines.append(f"**Routine**: {routine_count} actions completed")

        elevated = [a for a in log["actions"] if a["category"] in ("flagged", "error", "security")]
        for item in elevated:
            icon = "🚨" if item["category"] in ("error", "security") else "⚠"
            lines.append(f"**{item['category'].capitalize()}**: {icon} {item['text']}")
            flagged_items.append(item)

        lines.append("")

    if flagged_items:
        lines.append("## Flagged Items")
        lines.append("")
        for item in flagged_items:
            icon = "🚨" if item["category"] in ("error", "security") else "⚠"
            lines.append(f"- {icon} {item['text']}")
        lines.append("")

    if parsed_logs:
        lines.append("## Full Log")
        lines.append("")
        lines.append(f"`{parsed_logs[0]['source_file']}`")
        lines.append("")

    return "\n".join(lines)


def format_whatsapp_alert(critical_items, target_date):
    """Format a brief WhatsApp critical alert message.

    Kept under 5 lines for WhatsApp readability.
    """
    lines = [f"🚨 Felix Alert — {target_date}", ""]

    for agent_name, items in critical_items.items():
        count = len(items)
        label = "error" if count == 1 else "errors"
        lines.append(f"{agent_name}: {count} {label}")
        if items:
            lines.append(f'  "{items[0]["text"]}"')

    lines.append("")
    lines.append("Check Obsidian: 00-System/agent-activity/overview.md")

    return "\n".join(lines)


def find_log_files(log_dir, target_date):
    """Find all log files for the target date."""
    log_dir = Path(log_dir)
    if not log_dir.exists():
        return []

    date_str = target_date if isinstance(target_date, str) else target_date.isoformat()
    return sorted(log_dir.glob(f"*{date_str}*"))


def run(config, target_date, dry_run=False):
    """Main execution flow.

    Returns a dict with the digest content and critical alert status.
    """
    log_files = find_log_files(config.log_dir, target_date)

    if not log_files:
        overview = (
            f"# Agent Activity — {target_date}\n\n"
            f"*Generated: {datetime.now().strftime('%Y-%m-%d %H:%M')} ET*\n\n"
            "No agent activity recorded today.\n"
        )
        if not dry_run:
            config.output_dir.mkdir(parents=True, exist_ok=True)
            (config.output_dir / "overview.md").write_text(overview)
        return {"overview": overview, "critical": False, "alert_message": None}

    # Group parsed logs by agent
    agent_logs = {}
    for log_file in log_files:
        try:
            parsed = parse_log_file(log_file)
            agent_name = parsed["agent_name"]
            if agent_name not in agent_logs:
                agent_logs[agent_name] = []
            agent_logs[agent_name].append(parsed)
        except Exception as e:
            print(f"Warning: Failed to parse {log_file}: {e}", file=sys.stderr)

    # Build digests per agent
    agent_digests = {}
    critical_items = {}

    for agent_name, logs in agent_logs.items():
        try:
            level = config.autonomy_level(agent_name)
        except KeyError:
            level = "assisted"  # default for unregistered agents

        all_actions = []
        for log in logs:
            all_actions.extend(log["actions"])

        filtered = filter_actions_by_autonomy(all_actions, level)
        routine = [a for a in filtered if a["category"] == "routine"]
        elevated = [a for a in filtered if a["category"] != "routine"]
        is_critical = detect_critical_alerts(all_actions)

        routine_summary = summarize_routine_actions(routine) if routine else None

        agent_digests[agent_name] = {
            "autonomy_level": level,
            "runs": len(logs),
            "routine_summary": routine_summary,
            "elevated": elevated,
            "critical": is_critical,
            "log_ref": f"agents/logs/{logs[0]['source_file']}",
        }

        if is_critical:
            critical_items[agent_name] = [
                a for a in all_actions if a["category"] in ("error", "security")
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
        for agent_name, logs in agent_logs.items():
            level = agent_digests[agent_name]["autonomy_level"]
            detail = generate_agent_detail(agent_name, logs, level, target_date)
            print(f"\n=== {agent_name.upper()} DETAIL ===")
            print(detail)
    else:
        config.output_dir.mkdir(parents=True, exist_ok=True)
        (config.output_dir / "overview.md").write_text(overview)
        for agent_name, logs in agent_logs.items():
            level = agent_digests[agent_name]["autonomy_level"]
            detail = generate_agent_detail(agent_name, logs, level, target_date)
            safe_name = agent_name.replace("/", "-")
            (config.output_dir / f"{safe_name}.md").write_text(detail)

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
