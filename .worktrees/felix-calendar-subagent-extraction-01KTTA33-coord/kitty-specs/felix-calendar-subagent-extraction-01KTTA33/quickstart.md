# Quickstart — Felix Calendar Subagent Extraction

**Audience**: operator running the mission's deploy + verification cycle after implementation WPs are complete and merged on the coord branch.

## Pre-conditions

- Implementation WPs all done; coord branch `kitty/mission-felix-calendar-subagent-extraction-01KTTA33` has all changes committed locally (Mac repo).
- `git status` clean.
- `pytest scripts/openclaw/agents/tests/` green locally.
- Office2 reachable: `ssh office2-claude 'date'` returns a fresh timestamp.
- Restic backup log fresh (`/data/services/backup/logs/backup-YYYY-MM-DD.log` present and recent) — hygiene check; Tier 3 doesn't gate on it.

## Deploy

From repo root on Mac:

```bash
./scripts/deploy/deploy-felix-admin-calendar.sh
```

What the script does (full detail in plan.md § Deploy substrate):

1. Pre-flight: artifact presence, char-count assertions, SSH reachable.
2. Trigger `agent-prompt-sync.service` on office2 to sync prompt files immediately.
3. Backup + edit `~/.openclaw/openclaw.json` on office2 via jq.
4. Restart `openclaw-gateway.service`.
5. Watch journal for `truncating in injected context` warnings (NFR-002).
6. Print the smoke runbook link and the rebaseline command.

If any step fails, the script halts and prints rollback instructions.

## Smoke

Open `docs/runbooks/felix-calendar-subagent-extraction-01KTTA33-smoke.md`. Walk the DM checklist.

Coverage:

- SC-001: habit DM → reply
- SC-002: calendar DM → reply (single-shot AND clarification round-trip)
- SC-005: every other OpenClaw subagent DM → reply
- SC-006: scheduled outbound flows fire normally over 24h
- doc-auditor `last-tick.json` freshness check (separate substrate)

## Rebaseline

After smoke is satisfied (or in parallel; rebaseline doesn't require smoke complete):

```bash
ssh office2-claude 'rm /data/services/security-monitor/baselines/* && sg docker -c /data/services/security-monitor/scripts/audit.sh'
```

Verification:

```bash
ssh office2-claude 'ls /data/services/security-monitor/baselines/ | wc -l && tail -5 /data/services/security-monitor/logs/audit-$(date +%Y-%m-%d).log'
```

Expected: 14 baselines, audit log clean.

## Mark complete

When all SC-* satisfied and rebaseline done:

- Spec-kitty mission accept + merge
- Merge commit footer includes: `Rebaseline: completed at <ts>` (the audited-surface rebaseline obligation per #557)
- Close issue #579 with a comment referencing the merge commit

## If something goes wrong

- Deploy script halts mid-way: follow printed rollback (restore openclaw.json from `.bak-<ts>`, restart service, git revert if needed).
- Smoke fails for a non-calendar subagent: regression in main/AGENTS.md tightening. File bug, halt mission, consider rollback.
- Smoke fails for calendar (single-shot): check `felix-admin-calendar` workspace files synced, openclaw.json entry present, journal for calendar-agent bootstrap errors.
- Smoke fails for calendar clarification round-trip: state file path (`~/second-brain/agents/state/pending-calendar-clarifications.jsonl`) and handler logic; verify the self-dispatch contract.
- Scheduled outbound miss: not necessarily caused by this mission; check service-inventory schedule entries.
