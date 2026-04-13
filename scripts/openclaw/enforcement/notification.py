"""Notification dispatch for agent workspace drift enforcement.

Sends WhatsApp alerts via openclaw agent --deliver and creates
GitHub issues for conflicts and factory-default transitions.
"""

import logging
import subprocess

from scripts.openclaw.enforcement.detection import DriftResult

logger = logging.getLogger(__name__)


def compose_alert_message(actions: dict) -> str:
    """Compose a consolidated WhatsApp alert message."""
    lines = ["Agent Workspace Drift Alert\n"]

    if actions["conflicts"]:
        lines.append("Conflicts (both sides changed):")
        for r in actions["conflicts"]:
            lines.append(f"  - {r.agent_id}/{r.filename}")
        lines.append("")

    if actions["factory_transitions"]:
        lines.append("Factory transitions (newly customized):")
        for r in actions["factory_transitions"]:
            lines.append(f"  - {r.agent_id}/{r.filename}")
        lines.append("")

    if actions["errors"]:
        lines.append("Errors (remediation failed):")
        for r in actions["errors"]:
            lines.append(f"  - {r.agent_id}/{r.filename}")
        lines.append("")

    summary_parts = []
    if actions["deployed"]:
        summary_parts.append(f"{len(actions['deployed'])} deployed (repo->office2)")
    if actions["captured"]:
        summary_parts.append(f"{len(actions['captured'])} captured (office2->repo)")
    if summary_parts:
        lines.append("Auto-remediated: " + ", ".join(summary_parts))

    if actions["conflicts"] or actions["factory_transitions"]:
        lines.append("\nAction required: review and resolve manually.")

    return "\n".join(lines)


def compose_issue_body(actions: dict) -> str:
    """Compose a GitHub issue body with drift details."""
    lines = ["## Agent Workspace Drift Report\n"]
    lines.append("Detected by the automated drift enforcement script.\n")

    if actions["conflicts"]:
        lines.append("### Conflicts (both sides changed since last baseline)\n")
        for r in actions["conflicts"]:
            lines.append(f"- **{r.agent_id}/{r.filename}**")
            lines.append(f"  - Repo hash: `{r.current_repo_hash}`")
            lines.append(f"  - Office2 hash: `{r.current_office2_hash}`")
            lines.append(f"  - Baseline repo: `{r.baseline_repo_hash}`")
            lines.append(f"  - Baseline office2: `{r.baseline_office2_hash}`")
        lines.append("")

    if actions["factory_transitions"]:
        lines.append("### Factory-Default Transitions (newly customized)\n")
        for r in actions["factory_transitions"]:
            lines.append(f"- **{r.agent_id}/{r.filename}** — was factory default, now customized")
            lines.append(f"  - Current hash: `{r.current_office2_hash}`")
        lines.append("")

    lines.append("### Resolution\n")
    if actions["conflicts"]:
        lines.append("For conflicts: compare both versions manually, choose the authoritative one,")
        lines.append("update the other side, and regenerate the baseline manifest.\n")
    if actions["factory_transitions"]:
        lines.append("For factory transitions: capture the customized file to the repo")
        lines.append("(`scp office2-claude:<path> scripts/openclaw/agents/<agent>/<file>`).")
        lines.append("Then regenerate the baseline manifest.\n")

    return "\n".join(lines)


def send_whatsapp(
    message: str,
    config: dict,
    dry_run: bool = False,
) -> bool:
    """Send a WhatsApp message via openclaw agent --deliver."""
    if dry_run:
        logger.info("DRY RUN: would send WhatsApp: %s", message[:100])
        return True

    recipient = config["notification"]["recipient"]
    agent = config["notification"].get("openclaw_agent", "main")

    try:
        result = subprocess.run(
            [
                "openclaw", "agent",
                "--agent", agent,
                "--message", message,
                "--deliver",
                "--channel", "whatsapp",
                "--to", recipient,
            ],
            capture_output=True, text=True, timeout=60,
        )
        if result.returncode != 0:
            logger.error("WhatsApp send failed: %s", result.stderr.strip())
            return False
        logger.info("WhatsApp alert sent")
        return True
    except (subprocess.TimeoutExpired, FileNotFoundError) as e:
        logger.error("WhatsApp send error: %s", e)
        return False


def create_drift_issue(
    actions: dict,
    config: dict,
    dry_run: bool = False,
) -> str | None:
    """Create a GitHub issue for unresolved drift. Returns issue URL or None."""
    if dry_run:
        logger.info("DRY RUN: would create drift-alert issue")
        return None

    repo = config["notification"]["issue_repo"]
    labels = ",".join(config["notification"]["issue_labels"])

    n_conflicts = len(actions.get("conflicts", []))
    n_transitions = len(actions.get("factory_transitions", []))
    title = f"Drift alert: {n_conflicts} conflict(s), {n_transitions} factory transition(s)"
    body = compose_issue_body(actions)

    try:
        result = subprocess.run(
            [
                "gh", "issue", "create",
                "--repo", repo,
                "--title", title,
                "--body", body,
                "--label", labels,
            ],
            capture_output=True, text=True, timeout=30,
        )
        if result.returncode == 0:
            url = result.stdout.strip()
            logger.info("Created drift-alert issue: %s", url)
            return url
        logger.error("Issue creation failed: %s", result.stderr.strip())
        return None
    except (subprocess.TimeoutExpired, FileNotFoundError) as e:
        logger.error("Issue creation error: %s", e)
        return None


def notify(actions: dict, config: dict, dry_run: bool = False) -> None:
    """Send notifications for conflicts and factory transitions."""
    needs_notification = actions.get("conflicts") or actions.get("factory_transitions") or actions.get("errors")
    if not needs_notification:
        return

    message = compose_alert_message(actions)

    # Create issue first (so we can include the URL in the WhatsApp message)
    if actions.get("conflicts") or actions.get("factory_transitions"):
        issue_url = create_drift_issue(actions, config, dry_run)
        if issue_url:
            message += f"\nIssue: {issue_url}"

    send_whatsapp(message, config, dry_run)
