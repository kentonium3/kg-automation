# Quickstart: Inbox Pre-Scan Helper

**Mission**: 027-inbox-pre-scan-helper
**Target audience**: implementer picking up any work package in this mission

## What you're building

A Python script that `felix-admin-capture` runs as its first action on every cron run. The script lists unprocessed inbox files and archives stale (>7 day) processed files. When the inbox is empty of unprocessed content, the agent replies IDLE and the run costs ≤500 tokens instead of full-scan tokens × 28 files.

## Local dev loop

```bash
# From repo root, work inside your assigned worktree (spec-kitty creates it per lane)
cd /Users/kentgale/repos/kg-automation

# Set up test fixtures and run unit tests
pytest tests/scripts/inbox/ -v

# Run the helper against a local test vault (NOT office2)
# Create a fake paths.json and fake inbox in a tmp dir, then:
python3 scripts/inbox/prescan.py
```

## Deploy to office2 (WP05 scope only)

```bash
# From repo root on Mac
./scripts/deploy/deploy-149.sh --dry-run
# review the planned changes, then:
./scripts/deploy/deploy-149.sh --apply
```

The wrapper prints each step and halts on the first failure. On halt, follow the manual rollback instructions it prints.

## Verification commands (post-deploy, WP05 scope)

```bash
# 1. Verify helper exists and is runnable on office2
ssh office2-claude 'python3 /home/claude/kg-automation/scripts/inbox/prescan.py --self-check'
# Expected: exit 0, JSON with self_check: ok

# 2. Verify all 4 inbox crons show the new payload
ssh office2-claude 'openclaw cron list --json' | python3 -c "
import json, sys
jobs = json.load(sys.stdin)['jobs']
for j in jobs:
    if j['name'].startswith('inbox-'):
        print(j['name'], '→', j['payload']['message'][:80])
"

# 3. Trigger a smoke run against the current inbox
ssh office2-claude 'openclaw cron run 7fa9b299-f8fc-44c2-b37d-de4163c80cdf'
# (inbox-noon UUID; or any of the 4)

# 4. Inspect the most recent helper log
ssh office2-claude 'ls -t /home/claude/second-brain/agents/logs/inbox-prescan-*.md | head -1 | xargs cat'

# 5. Inspect the openclaw run history for the smoke run
ssh office2-claude 'openclaw cron runs 7fa9b299-f8fc-44c2-b37d-de4163c80cdf 2>&1 | head -20'
```

## Reference paths (absolute)

| What | Where |
|---|---|
| Helper source (repo) | `/Users/kentgale/repos/kg-automation/scripts/inbox/prescan.py` |
| Helper tests (repo) | `/Users/kentgale/repos/kg-automation/tests/scripts/inbox/` |
| Deploy wrapper (repo) | `/Users/kentgale/repos/kg-automation/scripts/deploy/deploy-149.sh` |
| Agent workspace (repo) | `/Users/kentgale/repos/kg-automation/ai-agents/felix-admin-capture/` |
| Architecture data (repo) | `/Users/kentgale/repos/kg-automation/docs/design/architecture/data/service-inventory.json` |
| Helper deployed (office2) | `/home/claude/kg-automation/scripts/inbox/prescan.py` |
| Agent workspace (office2) | `/home/claude/.openclaw/agents/felix-admin-capture/` |
| Helper daily log (office2) | `/home/claude/second-brain/agents/logs/inbox-prescan-YYYY-MM-DD.md` |
| Agent processing log (office2) | `/home/claude/second-brain/agents/logs/inbox-processing-YYYY-MM-DD.md` |
| Vault registry (repo) | `/Users/kentgale/repos/kg-automation/scripts/vault/paths.json` |
| Vault registry (office2) | `/home/claude/kg-automation/scripts/vault/paths.json` |

## Key contracts to preserve

1. **FR-003 safety default**: unknown/missing `status` → treat as unprocessed. Never archive a file whose status is unclear.
2. **C-001 privacy boundary**: never touch any path under `~/second-brain/notes/04-Growth/_private/`. The registry doesn't resolve it; helper defense-in-depth also skips any `_private/` subdirectory encountered during iteration.
3. **C-002 no content modification**: helper moves whole files; it never rewrites frontmatter.
4. **FR-014 deploy order**: helper first, then workspace, then cron edit. Any mid-deploy cron fire must run cleanly under the legacy Step 1 (i.e., the old message must still be valid until cron edit completes).

## Common failure modes to avoid

- **Do NOT use the system crontab** for anything in this mission. `openclaw cron edit` is the only correct mechanism for changing inbox cron payloads. See closed #162 for the failure mode.
- **Do NOT hardcode vault paths.** Every path must come from `paths.json` via the registry.
- **Do NOT swallow errors silently.** Helper errors go to stderr + non-zero exit; warnings go to stderr + the `warnings` list in the JSON; agent reports helper errors as turn output.
- **Do NOT assume the agent's SOUL.md / AGENTS.md / USER.md structure.** Read the files first before editing; confirm which file owns "Step 1" before patching.

## Definition of Done (mission-level)

All 10 success criteria in `spec.md` must be verifiable:
- Empty run stays ≤500 tokens (SC-001)
- Non-empty run routes correctly (SC-002)
- 8-day-old processed file archives on first helper run (SC-003)
- 6-day-old processed file stays (SC-004)
- 30-day-old unprocessed file stays (SC-005)
- Missing `{{VAULT_INBOX_PROCESSED}}` → helper fails loud, agent reports error (SC-006)
- Agent workspace Step 1 reflects the new contract (SC-007)
- Deploy wrapper executes in the correct order (SC-008)
- `data/service-inventory.json` + markdown view updated (SC-009)
- Issue #149 closable (SC-010)

When all 10 are verified on office2 against live state, the mission can move to `/spec-kitty.review` → `/spec-kitty.merge` → close #149.
