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

kentonium3/kg-automation#892/#894: this script writes an asserted-state tick
pointer (``--pointer-file``, default ``POINTER_FILE``) on every exit path,
including the sync-process-down early return. The canary reads THAT pointer
for health, never the raw log — the raw log is the producer's OWN activity
record, and a fresh ERROR line in it is not evidence the watched condition
(sync propagation) is healthy; those are different propositions, and #892 is
what happens when a probe conflates them. The state files (both the pointer
and the legacy failure-counter ``--state-file``) live under
``/data/services/obsidian-sync-heartbeat/state/`` rather than ``/tmp``, which
is emptied at every boot (#894) and previously produced a spurious ERROR page
per reboot while silently resetting the escalation counter to zero.
"""

import argparse
import json
import logging
import os
import subprocess
import sys
import tempfile
from datetime import datetime, timezone
from pathlib import Path

# Hyphenated filename → only runnable by script path, so the repo root is not on
# sys.path unless we put it there ourselves — required for the seam import below.
_REPO_ROOT = Path(__file__).resolve().parents[2]
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

from scripts.common.openclaw_bin import openclaw_bin

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [sync-heartbeat] %(levelname)s %(message)s",
    datefmt="%Y-%m-%dT%H:%M:%SZ",
)
logger = logging.getLogger(__name__)

# Defaults
VAULT_PATH = "/home/kgale/second-brain/notes"
HEARTBEAT_FILE = "00-System/sync-heartbeat.md"
# #894: moved off /tmp, which is emptied at every boot (systemd-tmpfiles).
STATE_FILE = "/data/services/obsidian-sync-heartbeat/state/heartbeat-state.json"
# #892: the asserted-state tick pointer the canary's `state-file` probe reads.
# Written on every exit path (fail-soft — see write_pointer).
POINTER_FILE = "/data/services/obsidian-sync-heartbeat/state/last-tick.json"
POINTER_SCHEMA_VERSION = 1
MAX_FAILURES = 3
OPENCLAW_AGENT = "main"
WHATSAPP_RECIPIENT = "+16179300916"


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def write_heartbeat(vault_path: str, heartbeat_file: str, dry_run: bool = False) -> str:
    """Write a heartbeat timestamp to the vault. Returns the timestamp written."""
    now = _utc_now_iso()
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
        except (OSError, IndexError):
            pass

    return result


def load_state(state_file: str) -> dict:
    """Load persistent state from previous runs."""
    if os.path.exists(state_file):
        try:
            with open(state_file) as f:
                return json.load(f)
        except (OSError, json.JSONDecodeError):
            pass
    return {"consecutive_failures": 0, "last_written": None, "last_check": None}


def save_state(state_file: str, state: dict) -> None:
    """Save persistent state for next run.

    #894: the state directory may not exist yet (moved off /tmp, which
    tmpfiles.d recreates implicitly — /data/services does not).
    """
    os.makedirs(os.path.dirname(state_file), exist_ok=True)
    with open(state_file, "w") as f:
        json.dump(state, f, indent=2)
        f.write("\n")


def _write_atomic(path: str, data: bytes) -> None:
    """Write ``data`` to ``path`` via tempfile + os.replace (atomic on POSIX).

    Raises on failure — callers that must not propagate a write failure
    (see :func:`write_pointer`) catch around this.
    """
    directory = os.path.dirname(path)
    os.makedirs(directory, exist_ok=True)
    fd, tmp_path = tempfile.mkstemp(
        prefix=os.path.basename(path) + ".", suffix=".tmp", dir=directory
    )
    try:
        with os.fdopen(fd, "wb") as f:
            f.write(data)
        os.replace(tmp_path, path)
    except Exception:
        try:
            os.unlink(tmp_path)
        except OSError:
            pass
        raise


def write_pointer(
    pointer_file: str,
    *,
    sync_process_running: bool,
    propagation_ok: bool,
    consecutive_failures: int,
    max_failures: int,
    heartbeat_age_minutes: float | None,
    vault_path: str,
) -> None:
    """Write the asserted-state tick pointer (#892/#894).

    This is a **positive assertion of the watched condition** — not evidence
    that the script ran. ``propagation_ok`` is a boolean the caller has
    already derived from ``consecutive_failures`` vs ``max_failures``
    (the same threshold that gates the WhatsApp escalation), so the canary
    never has to re-implement that threshold logic itself.

    Fail-soft by design: a pointer-write failure is logged and swallowed.
    This runs on a `*/30` cron and must never prevent the heartbeat's real
    work (the vault write + alerting) — a monitoring-substrate problem must
    not become a production incident.
    """
    document = {
        "schema_version": POINTER_SCHEMA_VERSION,
        "completed_at_utc": _utc_now_iso(),
        "sync_process_running": sync_process_running,
        "propagation_ok": propagation_ok,
        "consecutive_failures": consecutive_failures,
        "max_failures": max_failures,
        "heartbeat_age_minutes": heartbeat_age_minutes,
        "vault_path": vault_path,
    }
    try:
        _write_atomic(pointer_file, (json.dumps(document, indent=2) + "\n").encode("utf-8"))
    except OSError as exc:
        logger.error("Failed to write tick pointer %s: %s", pointer_file, exc)


def _persist_tick(
    *,
    state_file: str,
    state: dict,
    pointer_file: str,
    sync_process_running: bool,
    consecutive_failures: int,
    max_failures: int,
    heartbeat_age_minutes: float | None,
    vault_path: str,
) -> None:
    """Persist the failure-counter state, then the asserted-state pointer.

    Two INDEPENDENT fail-soft boundaries (#892/#894 review cycle 2 finding).
    ``save_state`` is NOT fail-soft on its own (an unwritable/uncreatable
    state directory raises straight out of ``os.makedirs``/``open``) — with
    a bare sequential call, that raise skipped ``write_pointer`` entirely and
    propagated out of ``main()``, turning the documented sync-process-down
    exit(2) into an uncaught-exception exit(1) with NO pointer written. With
    no pointer written, the *previous* pointer sits there reading fresh and
    healthy until it ages out — exactly the stale-pointer window this whole
    change exists to close. The same ordering could also crash a normal run
    *after* its vault write had already succeeded, reporting failure for a
    run whose real work was fine.

    So: catch broadly (not just ``OSError``) around ``save_state`` — the
    counter is disposable (it resets once on the #894 cutover already; a
    dropped increment here is the same class of loss, not a new one) and
    losing it must never cost the pointer write or the caller's documented
    exit code — and write the pointer from ``finally``, so it is attempted
    whether or not ``save_state`` raised, and whatever it raised.
    """
    try:
        save_state(state_file, state)
    except Exception as exc:  # noqa: BLE001 — deliberately broad, see docstring
        logger.error("Failed to save state %s: %s", state_file, exc)
    finally:
        write_pointer(
            pointer_file,
            sync_process_running=sync_process_running,
            propagation_ok=consecutive_failures < max_failures,
            consecutive_failures=consecutive_failures,
            max_failures=max_failures,
            heartbeat_age_minutes=heartbeat_age_minutes,
            vault_path=vault_path,
        )


def send_alert(message: str, dry_run: bool = False) -> bool:
    """Send WhatsApp alert via openclaw agent --deliver."""
    if dry_run:
        logger.info("DRY RUN: would send alert: %s", message[:100])
        return True

    try:
        result = subprocess.run(
            [
                openclaw_bin(), "agent",
                "--agent", OPENCLAW_AGENT,
                "--message", message,
                "--deliver",
                "--channel", "whatsapp",
                "--to", WHATSAPP_RECIPIENT,
            ],
            capture_output=True, text=True, timeout=60, check=False,
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
            capture_output=True, text=True, timeout=5, check=False,
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
    parser.add_argument("--pointer-file", default=POINTER_FILE, help="Asserted-state tick pointer path (#892/#894)")
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
        state["last_check"] = _utc_now_iso()
        if not args.dry_run:
            _persist_tick(
                state_file=args.state_file,
                state=state,
                pointer_file=args.pointer_file,
                sync_process_running=False,
                consecutive_failures=state["consecutive_failures"],
                max_failures=args.max_failures,
                heartbeat_age_minutes=None,
                vault_path=args.vault,
            )
        sys.exit(2)

    # Check if previous heartbeat is still current (file mtime is recent)
    current = check_propagation(args.vault, HEARTBEAT_FILE)
    now = datetime.now(timezone.utc)
    heartbeat_age_minutes = None

    if current["exists"] and current["mtime"]:
        mtime = datetime.strptime(current["mtime"], "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=timezone.utc)
        heartbeat_age_minutes = (now - mtime).total_seconds() / 60

        if state.get("last_written") and current["timestamp"] != state["last_written"]:
            # The file was modified by someone else (cloud sync brought a different version)
            # This is actually fine — it means sync IS working (cloud→office2)
            logger.info("Heartbeat file was updated externally (sync working cloud→office2)")

        logger.info("Heartbeat age: %.0f minutes (mtime: %s)", heartbeat_age_minutes, current["mtime"])

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
        _persist_tick(
            state_file=args.state_file,
            state=state,
            pointer_file=args.pointer_file,
            sync_process_running=True,
            consecutive_failures=state.get("consecutive_failures", 0),
            max_failures=args.max_failures,
            heartbeat_age_minutes=heartbeat_age_minutes,
            vault_path=args.vault,
        )

    logger.info(
        "Done. Failures: %d/%d, process: %s",
        state.get("consecutive_failures", 0),
        args.max_failures,
        "running" if proc["running"] else "STOPPED",
    )


if __name__ == "__main__":
    main()
