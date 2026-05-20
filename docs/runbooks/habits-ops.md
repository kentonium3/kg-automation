---
title: Habit Check-in Operations Runbook
doc_type: runbook
audience: agents
status: draft
---

# Habit check-in operations

## Overview

The felix-admin-habits agent manages Kent's daily habit check-ins and
accountability tracking. It runs on office2 via OpenClaw, delivering a
morning check-in via WhatsApp and recording completion state in the
JSONL state log (canonical) plus Vikunja (UI mirror, written by
`record_completion.py`). A weekly pattern report runs Sunday evenings.
Vikunja's native `repeat_after` (set in Phase 3 #306) handles
`due_date` rolling automatically when a habit task is marked
`done=true`.

## Phase 5 cutover (2026-05-20)

**Date**: 2026-05-20 (UTC). Operator deploys via the [Update workspace
files](#update-workspace-files) command after the cutover commit lands
on `main`.

**Issue reference**: [GitHub #308](https://github.com/kentonium3/kg-automation/issues/308)
— Phase 5 of ADR-0002 (state-log migration).

**Workflow shape change** — `scripts/openclaw/agents/felix-admin-habits/AGENTS.md`
moves from the v1 comment-parsing flow to the v2 JSONL-based flow:

- **Step 0 (NEW)** — `reconcile_completions.py` runs before any habit
  enumeration. Backfills any Vikunja-UI completions into the JSONL log
  with `source="vikunja-ui"`.
- **Step 1 (CHANGED)** — `query_active_habits_v2.py` replaces the v1
  helper. Uses Vikunja's native filter
  (`due_date <= now/d AND done = false`), project-scoped to Habits.
- **Step 2 (CHANGED)** — `exclude_completed_v2.py` replaces the v1
  helper. Reads the JSONL state log directly; no LLM-mediated comment
  parsing.
- **Step 3 (REMOVED)** — the previous `set_due_dates.py` invocation
  is dropped; Vikunja's native `repeat_after` now handles due_date
  rolling. Step numbering keeps a gap at 3 (0/1/2/4/4.5/5/6) to
  preserve external doc references.
- **Completion marking (CHANGED)** — `record_completion.py` performs
  the atomic three-write (Vikunja `done=true` + `[Felix]` comment +
  JSONL append). The agent no longer makes inline POST/PUT calls for
  habit completion.
- **Weekly pattern report (CHANGED)** — Step 2 reads from the JSONL
  state log (`state_log.read("habits", date_from=..., date_to=...,
  state="complete")`) instead of fetching per-task Vikunja comments.

**v1 files preserved**: per spec constraints C-001/C-002, the v1
helpers (`query_active_habits.py`, `exclude_completed.py`,
`set_due_dates.py`) remain on disk and on office2 untouched during the
2-3 day soak. A follow-up post-soak mission will remove them and
rename the `_v2.py` files to canonical names.

**Operator deploy walkthrough**: see the mission
[quickstart.md](../../kitty-specs/habits-cutover-to-jsonl-v2-flow-01KS1FKE/quickstart.md)
for the full Steps 1-6 procedure (pull → deploy → sha256 verify →
wait for next cron → smoke-test → verify the Tuesday structural fix).
The deploy itself uses the existing [Update workspace files](#update-workspace-files)
command unchanged.

**Soak posture**: 2-3 day fail-forward observation window (per spec
C-007). Non-catastrophic anomalies become forward-fix follow-up
commits, NOT triggers to revert. Only catastrophic failures (cron
silent for 24+ hours, agent crashes on every invocation, JSONL data
corruption) trigger the rollback procedure documented in the
quickstart.

## Agent management

- **Agent name**: `felix-admin-habits`
- **Workspace on office2**: `/data/services/openclaw/habits-agent/`
- **Source in repo**: `scripts/openclaw/agents/felix-admin-habits/`
- **Model**: `anthropic/claude-sonnet-4-6`

### Workspace files

| File | Purpose |
|------|---------|
| SOUL.md | Kent-voice authoring identity |
| USER.md | Kent's context |
| IDENTITY.md | Agent identity metadata |
| TOOLS.md | Vikunja API reference, habit task IDs |
| AGENTS.md | Standing orders: check-in, completion, reporting, management |

### Update workspace files

```bash
for f in SOUL.md USER.md IDENTITY.md TOOLS.md AGENTS.md; do
  ssh office2-claude "cat > /data/services/openclaw/habits-agent/$f" \
    < scripts/openclaw/agents/felix-admin-habits/$f
done
```

### Verify agent

```bash
ssh office2-claude "openclaw agents list"
```

Expected: `felix-admin-habits` with workspace `/data/services/openclaw/habits-agent`.

## Schedule

Two cron jobs run the agent in isolated sessions, delivering output to
Kent's WhatsApp:

| Job | Schedule (UTC) | Local time (EDT) | Purpose |
|-----|---------------|-----------------|---------|
| habits-morning-checkin | `5 11 * * *` | 7:05 AM ET | Daily check-in |
| habits-weekly-report | `0 22 * * 0` | Sunday 6:00 PM ET | Weekly pattern report |

Both jobs use `--to +16179300916` for WhatsApp delivery and 120s timeout.
They do NOT use `--no-deliver`.

### View jobs

```bash
ssh office2-claude "openclaw cron list"
```

### Manual trigger

```bash
ssh office2-claude "openclaw cron run <job-uuid>"
```

Get the UUID from `openclaw cron list`.

### View run history

```bash
ssh office2-claude "openclaw cron runs --id <job-uuid>"
```

### Direct agent invocation

```bash
ssh office2-claude "openclaw agent --agent felix-admin-habits \
  --message 'Generate today'\''s habit check-in.' --json --timeout 120"
```

## Vikunja habits project

- **Project name**: Habits (id=13)
- **Web UI**: `https://office2.tail0f5f56.ts.net/projects/13`

### View habits

All habits are tasks in the Habits project. Each has a title, frequency
in the description field, and a personal identity label. As of the
Phase 5 cutover (2026-05-20, #308), Vikunja's native `repeat_after`
handles `due_date` roll automatically when a habit task is marked
`done=true` — the agent no longer manually sets `due_date` during the
morning check-in. The JSONL state log
(`/data/services/openclaw/state/habits-history.jsonl`) is the
authoritative source of completion state; the `[Felix]` comment on
each task is the Vikunja UI mirror written by `record_completion.py`.

### Current habits

| # | Task ID | Title | Frequency |
|---|---------|-------|-----------|
| 1 | 14 | Wake at 5:00 AM | Mon-Sat |
| 2 | 15 | Meditate 45 min | Daily |
| 3 | 16 | Morning shoulder PT | Daily |
| 4 | 17 | Functional strength training 45 min | Mon/Wed/Fri |
| 5 | 18 | 10K steps (monthly average) | Daily |
| 6 | 19 | Read 30 min minimum | Daily (evening) |
| 7 | 20 | Evening shoulder PT | Daily |

### Check completion history

Canonical completion records live in the JSONL state log
(`/data/services/openclaw/state/habits-history.jsonl`). Inspect via:

```bash
ssh office2-claude 'tail -20 /data/services/openclaw/state/habits-history.jsonl'
```

Or via the state_log CLI for filtered reads:

```bash
ssh office2-claude 'python3 -m scripts.common.state_log read \
    --domain habits \
    --date-from 2026-05-01 \
    --date-to 2026-05-31 \
    --state complete'
```

Each habit task also has `[Felix]` comments as a UI-visible mirror,
written by `record_completion.py`. These are convenient to view in the
Vikunja web UI but are NOT the canonical source. The comment-API path
remains for historical inspection only:

```bash
# Via Vikunja API (UI mirror — JSONL is canonical)
curl -s -H "Authorization: Bearer $(cat /data/services/openclaw/secrets/vikunja-api)" \
  "https://office2.tail0f5f56.ts.net/api/v1/tasks/15/comments" | python3 -m json.tool
```

Comment format: `[Felix] YYYY-MM-DD | {complete|incomplete|skipped} | optional note`

### Add/remove habits directly in Vikunja

Habits can be managed via the Vikunja web UI or API. To add a habit,
create a task in the Habits project with the frequency in the description
field and the personal label.

To pause a habit, add `(PAUSED)` to the description. To archive, mark
the task as done (history is preserved).

## WhatsApp interaction

### Check-in delivery

The morning cron delivers a numbered list of today's habits. Reply with
completions using natural language:

- "1 and 2 done" — marks habits #1 and #2 as `complete`
- "meditation done" — fuzzy matches to Meditate 45 min
- "all done" — marks all remaining habits as `complete`
- "skipping training" — marks as `skipped`
- "didn't get to PT" — marks as `incomplete`

### On-demand queries

Send any of these via WhatsApp (routed through the main agent):

- "how am I doing on my habits?"
- "show my track record"
- "habit status"

### Habit management via WhatsApp

- "add daily journaling" — adds a new habit (with confirmation)
- "pause steps habit" — pauses without deleting history
- "resume evening PT" — resumes a paused habit
- "remove reading habit" — archives (marks done, preserves history)

## Troubleshooting

| Symptom | Check | Fix |
|---------|-------|-----|
| No check-in delivered | `ssh office2-claude "openclaw cron list"` | Verify cron exists, is enabled, and has `--to` set |
| Completion not recorded | Check JSONL state log: `ssh office2-claude 'tail -20 /data/services/openclaw/state/habits-history.jsonl'` | Verify `record_completion.py` exit code in session log; check vikunja_api skill: `ssh office2-claude "openclaw skills info vikunja_api"` |
| Agent not responding | `ssh office2-claude "openclaw agents list"` | Restart gateway: `ssh office2-claude "systemctl --user restart openclaw-gateway"` |
| Delivery error | `ssh office2-claude "openclaw cron runs --id <uuid>"` | Check `--to` flag is set on the cron job |
| Session cache stale | Agent uses old AGENTS.md | Restart gateway or wait for isolated session |
| Main agent not delegating | Send habit message, check response | Verify habits delegation in `/data/services/openclaw/data/AGENTS.md` |
| Habits not in Today filter | Verify morning cron ran: `ssh office2-claude "openclaw cron runs --id <uuid>"` | If cron succeeded, confirm Vikunja's native `repeat_after` is set on the habit task (Phase 3 #306). If cron failed, investigate cron error. |

## Privacy boundary

**Absolute rule**: `04-Growth/_private/` is never read, processed, routed to,
referenced, or logged. Habits originating from private context appear only as
habit names. This is enforced in SOUL.md, AGENTS.md, and TOOLS.md. There are
no exceptions. (Path renumbered from `02-Growth/_private/` in mission 026 / #152.)
