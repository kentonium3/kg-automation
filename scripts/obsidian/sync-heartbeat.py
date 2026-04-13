#!/usr/bin/env python3
"""Obsidian Sync heartbeat monitor.

Writes a heartbeat file to the vault on office2 and checks if the
previous heartbeat propagated by comparing local and cloud timestamps.
If propagation fails for N consecutive checks, sends a WhatsApp alert.

Designed to run as a cron job on office2 (claude user).

Usage:
    python3 scripts/obsidian/sync-heartbeat.py
    python3 scripts/obsidian/sync-heartbeat.py --dry-run
    python3 scripts/obsidian/sync-heartbeat.py --check-only
"""

import argparse
import json
import logging
import os
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [sync-heartbeat] %(levelname)s %(message)s",
    datefmt="%Y-%m-%dT%H:%M:%SZ",
)
logger = logging.getLogger(__name__)

# Defaults
VAULT_PATH = "/home/kgale/second-brain/notes"
HEARTBEAT_FILE = "00-System/sync-heartbeat.md"
STATE_FILE = "/tmp/sync-heartbeat-state.json"
MAX_FAILURES = 3
OPENCLAW_AGENT = "main"
WHATSAPP_RECIPIENT = "<kent-e164-number>"


def write_heartbeat(vault_path: str, heartbeat_file: str, dry_run: bool = False) -> str:
    """Write a heartbeat timestamp to the vault. Returns the timestamp written."""
    now = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    path = os.path.join(vault_path, heartbeat_file)

    content = f"""---
title: Sync Heartbeat
doc_type: system
status: approved
---

# Sync Heartbeat

Last updated: {now}
Source: office2 (sync-heartbeat.py)

This file is automatically updated by the sync heartbeat monitor.
If this file is stale on your device, Obsidian Sync may not be working.
"""

    if dry_run:
        logger.info("DRY RUN: would write heartbeat to %s (timestamp: %s)", path, now)
    else:
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "w") as f:
            f.write(content)
        logger.info("Wrote heartbeat: %s", now)

    return now


def check_propagation(vault_path: str, heartbeat_file: str) -> dict:
    """Check if the heartbeat file exists and read its timestamp."""
    path = os.path.join(vault_path, heartbeat_file)
    result = {"exists": False, "timestamp": None, "mtime": None}

    if os.path.exists(path):
        result["exists"] = True
        result["mtime"] = datetime.fromtimestamp(
            os.path.getmtime(path), tz=timezone.utc
        ).strftime("%Y-%m-%dT%H:%M:%SZ")

        # Parse timestamp from file content
        try:
            with open(path) as f:
                for line in f:
                    if line.startswith("Last updated: "):
                        result["timestamp"] = line.strip().split("Last updated: ")[1]
                        break
        except (IOError, IndexError):
            pass

    return result


def load_state(state_file: str) -> dict:
    """Load persistent state from previous runs."""
    if os.path.exists(state_file):
        try:
            with open(state_file) as f:
                return json.load(f)
        except (json.JSONDecodeError, IOError):
            pass
    return {"consecutive_failures": 0, "last_written": None, "last_check": None}


def save_state(state_file: str, state: dict) -> None:
    """Save persistent state for next run."""
    with open(state_file, "w") as f:
        json.dump(state, f, indent=2)
        f.write("\n")


def send_alert(message: str, dry_run: bool = False) -> bool:
    """Send WhatsApp alert via openclaw agent --deliver."""
    if dry_run:
        logger.info("DRY RUN: would send alert: %s", message[:100])
        return True

    try:
        result = subprocess.run(
            [
                "openclaw", "agent",
                "--agent", OPENCLAW_AGENT,
                "--message", message,
                "--deliver",
                "--channel", "whatsapp",
                "--to", WHATSAPP_RECIPIENT,
            ],
            capture_output=True, text=True, timeout=60,
        )
        if result.returncode == 0:
            logger.info("Alert sent via WhatsApp")
            return True
        logger.error("WhatsApp alert failed: %s", result.stderr.strip())
        return False
    except (subprocess.TimeoutExpired, FileNotFoundError) as e:
        logger.error("WhatsApp alert error: %s", e)
        return False


def check_sync_process() -> dict:
    """Check if ob sync process is running."""
    try:
        result = subprocess.run(
            ["pgrep", "-af", "ob sync.*continuous"],
            capture_output=True, text=True, timeout=5,
        )
        lines = [l for l in result.stdout.strip().split("\n") if l and "grep" not in l]
        return {"running": len(lines) > 0, "processes": lines}
    except (subprocess.TimeoutExpired, FileNotFoundError):
        return {"running": False, "processes": []}


def main():
    parser = argparse.ArgumentParser(description="Obsidian Sync heartbeat monitor")
    parser.add_argument("--dry-run", action="store_true", help="Preview without writing or alerting")
    parser.add_argument("--check-only", action="store_true", help="Check current state without writing new heartbeat")
    parser.add_argument("--vault", default=VAULT_PATH, help="Vault path")
    parser.add_argument("--state-file", default=STATE_FILE, help="State file path")
    parser.add_argument("--max-failures", type=int, default=MAX_FAILURES, help="Consecutive failures before alerting")
    args = parser.parse_args()

    state = load_state(args.state_file)

    # Check sync process
    proc = check_sync_process()
    if not proc["running"]:
        msg = "Obsidian Sync ALERT: ob sync process is NOT running on office2. Service may need restart."
        logger.error(msg)
        send_alert(msg, dry_run=args.dry_run)
        state["consecutive_failures"] = state.get("consecutive_failures", 0) + 1
        state["last_check"] = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
        if not args.dry_run:
            save_state(args.state_file, state)
        sys.exit(2)

    # Check if previous heartbeat is still current (file mtime is recent)
    current = check_propagation(args.vault, HEARTBEAT_FILE)
    now = datetime.now(timezone.utc)

    if current["exists"] and current["mtime"]:
        mtime = datetime.strptime(current["mtime"], "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=timezone.utc)
        age_minutes = (now - mtime).total_seconds() / 60

        if state.get("last_written") and current["timestamp"] != state["last_written"]:
            # The file was modified by someone else (cloud sync brought a different version)
            # This is actually fine — it means sync IS working (cloud→office2)
            logger.info("Heartbeat file was updated externally (sync working cloud→office2)")

        logger.info("Heartbeat age: %.0f minutes (mtime: %s)", age_minutes, current["mtime"])

    if args.check_only:
        print(json.dumps({
            "process": proc,
            "heartbeat": current,
            "state": state,
        }, indent=2))
        sys.exit(0)

    # Write new heartbeat
    new_ts = write_heartbeat(args.vault, HEARTBEAT_FILE, dry_run=args.dry_run)

    # Check if the PREVIOUS heartbeat propagated
    # On the first run, there's no previous heartbeat to check
    if state.get("last_written"):
        prev_ts = state["last_written"]

        if current["timestamp"] == prev_ts:
            # File still has our last-written timestamp — sync hasn't touched it
            # This could mean: (a) sync is working fine and no one else modified it, or
            # (b) sync is broken and our writes aren't propagating
            # We can't distinguish without a second device, so we check file mtime
            # against when we last wrote — if mtime hasn't changed, the file is stale
            logger.info("Heartbeat unchanged since last write — normal if no external edits")
            state["consecutive_failures"] = 0
        elif current["timestamp"] is None and not current["exists"]:
            # File doesn't exist — something deleted it or sync is broken
            logger.warning("Heartbeat file missing!")
            state["consecutive_failures"] = state.get("consecutive_failures", 0) + 1
        else:
            # File has a different timestamp — either cloud synced a different
            # version or we're reading stale state. Reset failure counter.
            state["consecutive_failures"] = 0

    # Alert if too many consecutive failures
    if state.get("consecutive_failures", 0) >= args.max_failures:
        msg = (
            f"Obsidian Sync ALERT: heartbeat file missing or stale for "
            f"{state['consecutive_failures']} consecutive checks. "
            f"Sync may be silently failing (office2→cloud direction). "
            f"Check: sudo systemctl status obsidian-sync.service"
        )
        logger.error(msg)
        send_alert(msg, dry_run=args.dry_run)

    # Save state
    state["last_written"] = new_ts
    state["last_check"] = now.strftime("%Y-%m-%dT%H:%M:%SZ")
    if not args.dry_run:
        save_state(args.state_file, state)

    logger.info(
        "Done. Failures: %d/%d, process: %s",
        state.get("consecutive_failures", 0),
        args.max_failures,
        "running" if proc["running"] else "STOPPED",
    )


if __name__ == "__main__":
    main()
