---
id: escalation-ops
doc_type: runbook
title: Escalation Operations
status: approved
level: 2
owners: [kent]
last_validated: '2026-05-21'
updated_by: '#309'
version: '2.0.0'
---

# Escalation Operations

## Overview

The `felix-admin-escalation` agent detects overdue and at-risk tasks in
Vikunja and delivers level-appropriate WhatsApp alerts to Kent. It runs
daily at 8:00 AM ET via the OpenClaw cron `escalation-daily`, 55 minutes
after the morning habit check-in.

As of mission #309 (ADR-0002 Phase 6), escalation state is **canonical in
per-project JSONL files** under `/data/services/openclaw/state/escalation/`.
The agent reads state via `scripts/escalation/derive_state.py` and writes
events via `scripts/escalation/record_completion.py`. The legacy
`[Felix-Escalation]` Vikunja comments are still written during the
post-cutover 3-day soak for rollback safety, but they are **not** read.

**What it escalates**: tasks where `done=false`, `due_date < today` (or
due today with high+ priority), and `priority >= 2`. Habits project
(id=13) and Goals project (id=11) are excluded.

**What it does NOT escalate**: low-priority tasks, done tasks, habits,
goals, snoozed tasks (until snooze expires), or tasks Kent has
dismissed.

## Daily operation (steady state)

### Tick cadence

| Job | Schedule (UTC) | Local time (EDT) | Purpose |
|-----|----------------|------------------|---------|
| escalation-daily | `0 12 * * *` | 8:00 AM ET | Daily overdue task check |

The escalation runs 55 minutes after the morning habit check-in
(7:05 AM ET) so habit context is in Kent's awareness before task
escalations arrive.

### Where state lives

- **Canonical (read + write)**: `/data/services/openclaw/state/escalation/`
- **Per-project file**: `project-<project_id>-escalation-history.jsonl`
  (e.g., `project-4-escalation-history.jsonl` for the Everyday project)
- **UI mirror (write only, during soak)**: `[Felix-Escalation]` comments
  on each Vikunja task — convenient to view in the web UI but **NOT**
  read by the agent
- **Pre-cutover snapshot**: `/data/services/openclaw/state/escalation/pre-phase6-snapshot.json`

### Query current escalation state for a task

```bash
ssh office2-claude 'python3 -m scripts.escalation.derive_state --task-id <task-id> --project-id <project-id>'
```

Exit codes:

- `0` — state derived (JSON on stdout)
- `2` — JSONL read failure (missing directory or file)
- `3` — `EscalationStateError` (malformed/conflicting records — see hard-fail flow)
- `4` — zero records for `(task_id, project_id)` — task is new or unsubscribed

### Read recent JSONL records for a project

```bash
ssh office2-claude 'tail -20 /data/services/openclaw/state/escalation/project-4-escalation-history.jsonl'
```

Each line is a single JSON record with fields: `event_type` (one of
`level_sent | snoozed | dismissed | done | rescheduled`), `task_id`,
`project_id`, `task_title`, `date`, `recorded_at`, `source`, plus
per-state structured params (`level`, `snooze_days`, `snooze_until`,
`reschedule_to`, `reason`, `note`).

### View today's tick output

```bash
ssh office2-claude 'openclaw cron runs --id 5f734842-ca17-44f7-8040-f8e6a15355c4 | head -20'
```

(Get the cron UUID once via `openclaw cron list | grep escalation-daily`
and reuse — it is stable.)

### Manual trigger

```bash
ssh office2-claude 'openclaw cron run 5f734842-ca17-44f7-8040-f8e6a15355c4'
```

## Cutover procedure

The Phase 6 cutover from v1 (comment-as-state) to v2 (JSONL-as-state)
is documented in the mission quickstart:

- [`kitty-specs/migrate-escalation-to-jsonl-state-model-01KS5R4D/quickstart.md`](../../kitty-specs/migrate-escalation-to-jsonl-state-model-01KS5R4D/quickstart.md)

That document is the single source of truth for the cutover steps
(pre-flight, backfill, smoke-test, soak window). Do not duplicate
those steps here.

## Verification & monitoring

### Tick success rate (24 hour window)

```bash
ssh office2-claude 'openclaw cron runs --id 5f734842-ca17-44f7-8040-f8e6a15355c4 --since "1 day ago"'
```

A successful tick exits `0`. Anything else is a failure for NFR-002
accounting purposes.

For a wider window, parse the agent journal:

```bash
ssh office2-claude 'journalctl --user -u openclaw-gateway.service --since "7 days ago" | grep -E "escalation-daily|felix-admin-escalation"'
```

### JSONL growth check

```bash
ssh office2-claude 'wc -l /data/services/openclaw/state/escalation/project-*-escalation-history.jsonl'
```

NFR-003 budget: ≤10 MB per project after 1 year. At ~200 bytes/record,
that's ~50K records — far above expected traffic (≤50 escalation-subscribed
tasks × a few events each).

### Open hard-fail bugs

```bash
gh issue list --repo kentonium3/kg-automation --label P2-bug --search "Escalation hard-fail" --state open --json number,title,createdAt
```

Hard-fail bugs are filed by the agent when a task's JSONL state is
malformed or missing while Vikunja shows the task as escalation-subscribed.
The task is skipped that tick (no level sent, no synthetic correction).
Title-prefix dedup keyed on the Vikunja `id` ensures only one open bug
per task at a time. See [Maintenance § hard-fail triage](<#hard-fail-triage>)
for the repair workflow.

### Spurious re-alert check

This is the original 2026-05-16 incident class — Kent UI-marked a task
done and Felix re-alerted on the next tick. Verify by inspection:

1. Read the previous day's escalation WhatsApp summary.
2. For each alerted task, check Vikunja UI history (Activity tab) for a
   `done=true` mutation BEFORE the alert went out.
3. Any match = regression. Stop and rollback per the quickstart.

This is currently a manual audit — no automated alert exists. The
3-day soak gate (`escalation-soak-window.md`) operationalizes this.

### Reconcile dry-run (drift check, no writes)

```bash
ssh office2-claude 'python3 -m scripts.escalation.reconcile_completions --all --dry-run --quiet'
```

The summary JSON line reports `synthetic_done`, `synthetic_rescheduled`,
and `hard_fails`. Non-zero `synthetic_done` between ticks is expected
(Kent's UI mutations are the design driver); large counts (>5 per tick)
warrant investigation.

## Rollback procedure

The v1 (comment-as-state) code paths remain on disk during the soak.
Rollback is a single config flip. See the mission quickstart:

- [`kitty-specs/migrate-escalation-to-jsonl-state-model-01KS5R4D/quickstart.md` § Rollback procedure](../../kitty-specs/migrate-escalation-to-jsonl-state-model-01KS5R4D/quickstart.md#rollback-procedure)

Trigger conditions for rollback:

- Spurious re-alerts after Kent UI-resolves a task (SC-002 regression)
- Missing alerts on tasks that should escalate (SC-001 regression)
- Hard-fail epidemic (>5 hard-fail bugs filed in a single tick — points
  to a systemic schema bug, not isolated bad data)

Hard-fail counts on isolated tasks do NOT trigger rollback — they trigger
triage of the affected JSONL records.

## Maintenance

### Hard-fail triage

When a P2-bug with `Escalation hard-fail:` title appears:

1. Open the bug. Read the body — it includes the JSONL path, the
   detection snippet, and the current Vikunja state for the task.
2. SSH to office2 and inspect the affected JSONL file:

   ```bash
   ssh office2-claude 'grep "\"task_id\": <id>" /data/services/openclaw/state/escalation/project-<pid>-escalation-history.jsonl | tail -10'
   ```

3. Decide the repair:
   - **Malformed record**: edit the JSONL line in place to fix the
     schema violation, OR add a synthetic `operator_repair` record
     that supersedes it.
   - **Missing record** (phantom subscription): the task is in Vikunja
     but has no JSONL anchor. Either remove it from escalation
     subscription via UI (mark done / dismiss), or add an
     `operator_repair` record establishing the baseline state.

4. Add the synthetic record via `record_completion.py` with
   `--source operator_repair`:

   ```bash
   ssh office2-claude 'python3 -m scripts.escalation.record_completion \
     --task-id <id> --project-id <pid> --title "<title>" \
     --date $(date -I) --state <best-fit-state> --source operator_repair \
     --no-vikunja --note "manual triage <date> per bug #<num>"'
   ```

   The `--no-vikunja` flag skips the side-effect (no comment write —
   the JSONL record is the only artifact).

5. Close the GitHub bug. The next escalation tick reprocesses the task
   cleanly. If the issue re-fires, the dedup query returns empty
   (closed issues are excluded) and a fresh bug lands — meaning the
   repair was insufficient.

### Inspect a malformed record manually

```bash
ssh office2-claude 'jq -c . /data/services/openclaw/state/escalation/project-<pid>-escalation-history.jsonl 2>&1 | head -5'
```

`jq` exits non-zero on the first malformed line. The error message
points to the offending line. Pair with `wc -l` on the JSONL to
identify the line number, then `sed -n '<n>p' <file>` to read it raw.

### Repair a JSONL file by hand

A JSONL file is just append-only newline-delimited JSON. To repair:

1. Stop the escalation cron (so a tick doesn't race the repair):

   ```bash
   ssh office2-claude 'openclaw cron disable 5f734842-ca17-44f7-8040-f8e6a15355c4'
   ```

2. Edit the file:

   ```bash
   ssh office2-claude 'nano /data/services/openclaw/state/escalation/project-<pid>-escalation-history.jsonl'
   ```

3. Validate every line parses:

   ```bash
   ssh office2-claude 'jq -c . /data/services/openclaw/state/escalation/project-<pid>-escalation-history.jsonl > /dev/null && echo OK'
   ```

4. Re-enable the cron:

   ```bash
   ssh office2-claude 'openclaw cron enable 5f734842-ca17-44f7-8040-f8e6a15355c4'
   ```

Prefer adding an `operator_repair` record over hand-editing — the
append-only history stays cleaner and the repair is traceable.

### File rotation

Per NFR-003, per-project JSONL files are bounded and do **not** rotate.
At ~50 escalation-subscribed tasks × a few events each, the per-project
file size is ~50 KB and well under the 10 MB annual budget. If a
project's file ever crosses 1 MB, investigate before rotating —
something has gone wrong with the schema or retention assumptions.

### Adjust cron schedule

```bash
ssh office2-claude 'openclaw cron update 5f734842-ca17-44f7-8040-f8e6a15355c4 --cron "<new-expression>"'
```

### Temporarily pause escalation

```bash
ssh office2-claude 'openclaw cron disable 5f734842-ca17-44f7-8040-f8e6a15355c4'
```

Re-enable:

```bash
ssh office2-claude 'openclaw cron enable 5f734842-ca17-44f7-8040-f8e6a15355c4'
```

### Update agent workspace files

```bash
for f in SOUL.md USER.md IDENTITY.md TOOLS.md AGENTS.md; do
  ssh office2-claude "cat > /data/services/openclaw/escalation-agent/$f" \
    < scripts/openclaw/agents/felix-admin-escalation/$f
done
```

### Update escalation skill

```bash
ssh office2-claude "cat > /home/claude/.openclaw/skills/escalation/SKILL.md" \
  < scripts/openclaw/skills/escalation/SKILL.md
```

### Verify deployed agent + skill

```bash
ssh office2-claude 'openclaw agents list | grep felix-admin-escalation'
ssh office2-claude 'grep -c "JSONL\|derive_state" /data/services/openclaw/escalation-agent/AGENTS.md'
# Expect: non-zero (post-#309 references JSONL helpers)
ssh office2-claude 'grep -c "Felix-Escalation.*parse\|comment-parsing" /data/services/openclaw/escalation-agent/AGENTS.md'
# Expect: 0 (FR-007 — agent must not parse comments)
```

## Troubleshooting

| Symptom | Check | Fix |
|---------|-------|-----|
| No escalation alerts received | `ssh office2-claude 'openclaw cron runs --id 5f734842-ca17-44f7-8040-f8e6a15355c4'` | Verify cron exists, is enabled, has `--to` set |
| Wrong tasks escalated | Check priority and project filters in escalation skill | Update skill, redeploy to office2 |
| Duplicate alerts on same task same day | Check JSONL for same-day duplicates: `grep '"date": "$(date -I)"' /data/services/openclaw/state/escalation/project-<pid>-escalation-history.jsonl` | Likely dedup logic bug — investigate `record_completion --idempotent` path |
| Response not processed | Send response, check agent reply | Verify escalation skill deployed; restart gateway if needed |
| Snoozed task re-escalated early | `python3 -m scripts.escalation.derive_state --task-id <id> --project-id <pid>` and inspect `snooze_active_until` | If `snooze_active_until` is in the past, snooze expired correctly. If it disagrees with the most recent JSONL record, file hard-fail |
| Agent not responding | `ssh office2-claude 'openclaw agents list'` | Restart gateway: `ssh office2-claude 'systemctl --user restart openclaw-gateway'` |
| `derive_state` exit code 3 | Read the structured error JSON on stderr | Triage per [Hard-fail triage](<#hard-fail-triage>) |
| `derive_state` exit code 4 | Task has no JSONL records | Either (a) task is new (expected) or (b) phantom subscription — see hard-fail triage |

## Privacy boundary

**Absolute rule**: `04-Growth/_private/` is never read, processed, routed
to, referenced, or logged. Tasks from private context appear as task
names only in alerts and JSONL records. This is enforced in SOUL.md,
AGENTS.md, TOOLS.md, and in the `_sanitize_for_body` redaction layer in
`scripts/escalation/hard_fail.py` (every hard-fail bug body strips
`~/second-brain`, `/second-brain`, and `_private` substrings before
filing). No exceptions.

## Cross-references

- **Mission**: [#309](https://github.com/kentonium3/kg-automation/issues/309) — ADR-0002 Phase 6 (this migration)
- **Cutover playbook**: [`quickstart.md`](../../kitty-specs/migrate-escalation-to-jsonl-state-model-01KS5R4D/quickstart.md)
- **Soak monitoring template**: [`escalation-soak-window.md`](<./escalation-soak-window.md>)
- **Spec**: [`spec.md`](../../kitty-specs/migrate-escalation-to-jsonl-state-model-01KS5R4D/spec.md)
- **Agent surface**: [`scripts/openclaw/agents/felix-admin-escalation/AGENTS.md`](../../scripts/openclaw/agents/felix-admin-escalation/AGENTS.md)
- **Skill**: [`scripts/openclaw/skills/escalation/SKILL.md`](../../scripts/openclaw/skills/escalation/SKILL.md)
- **JSONL state library**: `scripts/common/state_log.py` (Phase 2, #305)
- **Pre-flight checklist**: [`docs/runbooks/governance/pre-flight-checklist.md`](<./governance/pre-flight-checklist.md>)
- **Habits ops (sibling Phase 5 precedent)**: [`docs/runbooks/habits-ops.md`](<./habits-ops.md>)
- **ADR**: `docs/design/architecture/adr/0002-felix-vikunja-task-model.md`
