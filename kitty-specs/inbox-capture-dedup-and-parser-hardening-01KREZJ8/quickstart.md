# Quickstart — Inbox Capture Dedup and Parser Hardening

**Mission**: `inbox-capture-dedup-and-parser-hardening-01KREZJ8`
**Audience**: Kent (operator), and future Felix agents that may need to redeploy.

## Initial deploy

The fix lives in two places:

1. **`scripts/inbox/`** Python helpers — pulled to office2 via `git pull`.
2. **`scripts/openclaw/agents/felix-admin-capture/AGENTS.md`** workspace file — deployed via `bash scripts/office2/deploy/felix-admin-capture.sh` (which rsyncs the workspace to `/data/services/openclaw/inbox-agent/`).

### Steps

```bash
ssh office2-claude
cd /home/claude/kg-automation
git pull origin main

# Redeploy the agent workspace + skill (existing deploy script).
bash scripts/office2/deploy/felix-admin-capture.sh
```

The Python helpers are picked up automatically (`prescan.py` and the new helpers in `scripts/inbox/` live in the repo and are invoked via absolute paths from AGENTS.md — no separate deploy step needed for the Python files).

### Verify

```bash
# 1. Routing log helper sanity (should print empty set on first run).
ssh office2-claude 'python3 -c "
import sys
sys.path.insert(0, \"/home/claude/kg-automation/scripts/inbox\")
from routing_log import RoutingLogReader
print(RoutingLogReader().routed_filenames())
"'

# 2. Extended prescan classifier sanity (against a synthetic fixture).
ssh office2-claude 'python3 /home/claude/kg-automation/scripts/inbox/prescan.py --dry-run' || \
  echo "(dry-run flag may not be supported in v1; just running normally is also fine)"

# 3. Agent workspace deployed.
ssh office2-claude 'grep -q "routing log" /data/services/openclaw/inbox-agent/AGENTS.md && echo "[OK] AGENTS.md updated"'
```

## First-run safety (R)

Per the spec's first-run safety path: the routing log starts empty. On the next OpenClaw cron tick after deploy:

- The 4 already-`status: processed` notes are skipped (existing prescan behavior).
- The 1 currently-unprocessed note (fresh from today) is routed normally — creates one GitHub issue + one Vikunja task. Routing log gets its first entry.

No retroactive backfill is performed. If the unprocessed note turns out to have been a bug-residual after all, a single duplicate appears in the GitHub queue and you close it manually.

## SC-002 canary (controlled-failure acceptance)

Validates that a malformed-frontmatter note correctly halts + surfaces + auto-cleans up.

### A. Inject a malformed note

In Obsidian on Mac, create a new note in `01-Inbox/` and edit it so the very first byte is a newline:

```
<empty line>
---
title: Canary test note
status: unprocessed
created: 2026-05-12
---

Body content for canary testing.
```

Save. Wait for Obsidian Sync to propagate to office2 (typically a few seconds).

### B. Force a cron tick (or wait for the next 6:00 / 12:00 / 18:00 / 22:00 ET scheduled run)

```bash
ssh office2-claude 'openclaw delegate felix-admin-capture "Process the inbox per AGENTS.md"'
```

### C. Verify

```bash
# 1. The note is NOT in unprocessed_paths (because parse failed).
ssh office2-claude 'python3 /home/claude/kg-automation/scripts/inbox/prescan.py' \
  | python3 -c "import sys,json; d=json.load(sys.stdin); print('parse_failures:', d.get('parse_failures'))"
# Expect the canary note in parse_failures with reason "leading whitespace before opening ---".

# 2. An "Inbox quality" issue was filed.
gh issue list --repo kentonium3/kg-automation --search 'in:title "Inbox quality"' --state open

# 3. The canary note has a callout marker injected.
ssh office2-claude 'head -3 "/home/kgale/second-brain/notes/01-Inbox/<canary-filename>.md"'
# Expect: > [!error] felix-capture: could not parse frontmatter on YYYY-MM-DD. See issue #<N> ...

# 4. NO routing log entry exists for the canary (because the note was not routed).
ssh office2-claude 'grep "<canary-filename>" ~/second-brain/agents/state/inbox-routing.jsonl' || echo "[OK] not in routing log"

# 5. NO GitHub issue or Vikunja task was created for the canary's CONTENT.
gh issue list --repo kentonium3/kg-automation --search '<canary-content-keyword>'
```

### D. Auto-cleanup

In Obsidian, fix the canary note by removing the leading newline. Save. Next cron tick:

```bash
# Marker auto-stripped, note routed.
ssh office2-claude 'head -3 "/home/kgale/second-brain/notes/01-Inbox/<canary-filename>.md"'
# Expect: marker is GONE; first line is now the `---`.

ssh office2-claude 'grep "<canary-filename>" ~/second-brain/agents/state/inbox-routing.jsonl'
# Expect: one new line with the canary's issue_number and task_id.
```

### E. Close the "Inbox quality" issue manually

After the canary verifies, close the `Inbox quality:` issue on GitHub. The agent doesn't auto-close it — Kent does that as part of acknowledging.

## Day-2 ops

- **Tail logs**: `ssh office2-claude 'tail -50 /home/kgale/second-brain/agents/logs/inbox-processing-$(date -u +%Y-%m-%d).md'`
- **Inspect routing log**: `ssh office2-claude 'cat ~/second-brain/agents/state/inbox-routing.jsonl | jq -r "[.filename, .issue_number, .routed_at] | @tsv" | column -t'`
- **Force a tick**: `ssh office2-claude 'openclaw delegate felix-admin-capture "Process the inbox per AGENTS.md"'`

## Rollback

If something is wrong post-deploy:

1. Stop the inbox-processing cron schedule: edit `/home/claude/.openclaw/openclaw.json` to comment out the `felix-admin-capture` cron entries (`inbox-7am`, etc.). Or use `openclaw cron disable` if available.
2. Revert the in-repo changes: `git -C /home/claude/kg-automation revert <merge-commit>`.
3. Redeploy the previous AGENTS.md: `bash scripts/office2/deploy/felix-admin-capture.sh`.

Routing log file (`~/second-brain/agents/state/inbox-routing.jsonl`) is harmless to leave in place during rollback — pre-mission code paths don't read it. Either remove it or leave it; rolling back to a clean state is `rm <path>`.
