---
id: habits-ops
doc_type: runbook
title: Habit Check-in Operations
status: approved
level: 2
owners: [kent]
audience: agents_and_humans
last_validated: '2026-06-02'
updated_by: '#408'
version: '2.1.0'
---

# Habit Check-in Operations

## Overview

The `felix-admin-habits` agent manages Kent's daily habit check-in and
accountability tracking. It runs on office2 via OpenClaw, delivering a
morning check-in via WhatsApp at 7:05 AM ET, parsing Kent's reply, and
recording completions to the canonical JSONL state log. A weekly
pattern report runs Sunday evenings.

As of mission [#371](https://github.com/kentonium3/kg-automation/issues/371)
(habits scripts-first port — sibling of [#309](https://github.com/kentonium3/kg-automation/issues/309)
ADR-0002 Phase 6 for escalation), the morning + reply flow is
**scripts-first**: the agent is a thin orchestrator that invokes
deterministic helper scripts and routes their output. The bug fixed by
#371: the morning cron tick and the reply tick were two separate
openclaw sessions; the reply session had no access to the morning
session's numbered list and regenerated it independently — orderings
diverged, and Kent's reply got applied to the wrong habits. The fix:

- `scripts/habits/morning_checkin_list.py` writes the canonical
  ordered list to `/data/services/openclaw/state/habits/morning-checkin-<YYYY-MM-DD>.json`
  AND emits the formatted WhatsApp message — both share the same
  ordering byte-for-byte (FR-001, FR-002).
- `scripts/habits/parse_morning_reply.py` loads the persisted morning
  list and maps Kent's reply against it deterministically (FR-003,
  FR-008) — NEVER re-querying Vikunja.
- `scripts/habits/judgment/disambiguate_reply.py` is invoked ONLY when
  the parser cannot deterministically resolve a reply token (FR-006),
  mirroring the #343 doc-audit narrow LLM judgment pattern.

Canonical completion state lives in the JSONL state log at
`/data/services/openclaw/state/habits-history.jsonl` (Phase 3 #306,
cutover #308). The `[Felix]` comments on each Vikunja habit task are a
UI mirror only, written by `scripts/habits/record_completion.py`.

**What it tracks**: 7 habit tasks in the Vikunja Habits project
(id=13). The agent surfaces today's active habits (those with
`due_date <= today AND done=false`), excludes ones already recorded
today, and records Kent's reply as `complete`/`incomplete`/`skipped`
per habit.

**What it does NOT do**: silently guess on ambiguous reply tokens
(asks ONE clarifying question per cluster instead — FR-006), re-query
Vikunja for the habit list during reply handling (the morning artifact
is authoritative — FR-008), or fall back to live Vikunja state when
the morning artifact is missing (files a P2-bug instead — FR-009).

## Daily operation (steady state)

### Tick cadence

| Job | UUID | Schedule (UTC) | Local time (EDT) | Purpose |
|-----|------|----------------|------------------|---------|
| habits-morning-checkin | `3082343c-bc7f-47ee-916b-ee070b1e50dc` | `5 11 * * *` | 7:05 AM ET | Daily check-in delivery |
| habits-weekly-report | (separate UUID) | `0 22 * * 0` | Sunday 6:00 PM ET | Weekly pattern report |

Both jobs use `--to +16179300916` for WhatsApp delivery and a 240s
timeout (morning) / 120s timeout (weekly).

### Where state lives

- **Canonical completion log** (read + write): `/data/services/openclaw/state/habits-history.jsonl`
  — Append-only JSONL per Phase 3 #306. Schema: `domain=habits`, state
  in `{complete, incomplete, skipped}`. Written by
  `record_completion.py`; read by `exclude_completed_v2.py` during the
  morning tick to drop already-addressed habits.
- **Per-date morning-list artifact** (read + write, post-#371):
  `/data/services/openclaw/state/habits/morning-checkin-<YYYY-MM-DD>.json`
  — One file per Kent-day. Schema per the mission data-model Entity 1:
  `{schema_version, date, generated_at, habits:[{position, vikunja_task_id, title}]}`.
  Written by `morning_checkin_list.py` at the morning tick; read by
  `parse_morning_reply.py` at reply time. ~1 KB per file at N=8-12
  habits (NFR-005); no rotation.
- **UI mirror** (write only): `[Felix]` comments on each Vikunja habit
  task. Convenient to view in the web UI but **NOT** read by any
  helper or by the agent post-#308.

### Query today's morning-list artifact

```bash
ssh office2-claude 'cat /data/services/openclaw/state/habits/morning-checkin-$(TZ=America/New_York date +%Y-%m-%d).json | python3 -m json.tool'
```

Each habit record is `{position, vikunja_task_id, title}`. Positions
are 1-indexed and match the numbers Kent sees in the WhatsApp message.

### Read recent JSONL completion records

```bash
ssh office2-claude 'tail -20 /data/services/openclaw/state/habits-history.jsonl | python3 -m json.tool'
```

Or via the state_log CLI for filtered reads:

```bash
ssh office2-claude 'python3 -m scripts.common.state_log read --domain habits --date-from 2026-05-01 --date-to 2026-05-31 --state complete'
```

### View today's morning tick output

```bash
ssh office2-claude 'openclaw cron runs --id 3082343c-bc7f-47ee-916b-ee070b1e50dc --since "1 day ago"'
```

### Manual trigger (morning tick)

```bash
ssh office2-claude 'openclaw cron run 3082343c-bc7f-47ee-916b-ee070b1e50dc'
```

### Direct helper invocation (debugging)

Morning-list helper (dry-run; emits message but writes NO artifact):

```bash
ssh office2-claude 'cd /home/claude/kg-automation && python3 -m scripts.habits.morning_checkin_list --dry-run'
```

Reply parser (against today's artifact):

```bash
ssh office2-claude 'cd /home/claude/kg-automation && python3 -m scripts.habits.parse_morning_reply --reply "1 done"'
```

Disambiguator (input via stdin JSON):

```bash
ssh office2-claude 'cd /home/claude/kg-automation && cat <<EOF | python3 -m scripts.habits.judgment.disambiguate_reply
{"schema_version": 1, "reply_text": "PT done", "ambiguity": {"token": "PT", "candidate_task_ids": [19, 16, 17], "candidate_titles": ["Morning shoulder PT", "Evening shoulder PT", "Morning hip PT"], "inferred_state": "complete"}}
EOF'
```

Full CLI surface (flags, exit codes, stdout/stderr shape) is documented
in the mission contracts:
[`kitty-specs/habits-checkin-reply-scripts-first-01KS86ZQ/contracts/cli.md`](../../kitty-specs/habits-checkin-reply-scripts-first-01KS86ZQ/contracts/cli.md).

## Cutover procedure

The #371 cutover from v1 (session-scoped numbered lists + AGENTS.md
fuzzy-matching prose) to v2 (per-date artifact + deterministic parser
+ narrow LLM judgment) is documented in the mission quickstart:

- [`kitty-specs/habits-checkin-reply-scripts-first-01KS86ZQ/quickstart.md`](../../kitty-specs/habits-checkin-reply-scripts-first-01KS86ZQ/quickstart.md)

That document is the single source of truth for the cutover steps
(pre-flight, smoke-test, AGENTS.md deploy, manual tick verification,
controlled reply test, cron re-enable). Do not duplicate those steps
here.

## Verification & monitoring

### Cron success check (24 hour window)

```bash
ssh office2-claude 'openclaw cron runs --id 3082343c-bc7f-47ee-916b-ee070b1e50dc --since "1 day ago"'
```

A successful tick exits `0`. Anything else is a failure to investigate.

### Truncation-warning check (NFR-004)

Per FR-011 / NFR-004, the deployed `AGENTS.md` must be ≤14,000 source
characters so openclaw does not silently truncate the agent's
standing orders. Verify by inspecting the journal after a tick:

```bash
ssh office2-claude 'journalctl --user -u openclaw-gateway.service --since "1 day ago" | grep -i "truncat"'
```

Expected: empty output. Any `truncating in injected context` line for
the habits-agent path is a regression — restore the pre-#371 AGENTS.md
from `/tmp/habits-agents-pre-371.md.bak` (created during the cutover)
and investigate.

Per-file char check on the deployed file:

```bash
ssh office2-claude 'wc -c /data/services/openclaw/habits-agent/AGENTS.md'
```

Expected: ≤14,000.

### JSONL growth check

```bash
ssh office2-claude 'wc -l /data/services/openclaw/state/habits-history.jsonl'
```

At ~7 habits × 1 completion record per day, expected growth is ~7
lines/day. Unusual jumps (>20 lines/day) warrant investigation —
either a reconcile sweep brought in backfilled records or the agent
double-recorded.

### Morning-list artifact presence

After 7:05 AM ET, verify today's artifact exists:

```bash
ssh office2-claude 'ls -l /data/services/openclaw/state/habits/morning-checkin-$(TZ=America/New_York date +%Y-%m-%d).json'
```

Expected: file exists, ~1 KB. Schema validates against data-model
Entity 1 — check via `python3 -m json.tool`.

If today's artifact is missing AND the cron is enabled: triage the
morning tick (cron failure, helper failure, or Vikunja unreachable).
See the troubleshooting table below.

### Reply-tick correctness spot-check

After Kent sends a reply, verify that the recorded JSONL `task_id` for
each habit matches the morning artifact's `vikunja_task_id` at the
corresponding `position`:

```bash
# Morning artifact
ssh office2-claude 'cat /data/services/openclaw/state/habits/morning-checkin-$(TZ=America/New_York date +%Y-%m-%d).json | python3 -m json.tool'

# Today's JSONL completions
ssh office2-claude 'grep "\"date\": \"$(TZ=America/New_York date +%Y-%m-%d)\"" /data/services/openclaw/state/habits-history.jsonl | python3 -m json.tool'
```

For habits Kent referenced by position (e.g., `"1 done"`), the
recorded `task_id` should match `habits[position-1].vikunja_task_id`
in the artifact. Mismatches mean the reply parser routed against the
wrong list — file a P1-bug.

## Rollback procedure

The #371 fix is a single AGENTS.md swap + three new helper scripts.
Rollback is documented in the mission quickstart:

- [`kitty-specs/habits-checkin-reply-scripts-first-01KS86ZQ/quickstart.md` § Rollback procedure](../../kitty-specs/habits-checkin-reply-scripts-first-01KS86ZQ/quickstart.md#rollback-procedure)

Trigger conditions for rollback:

- AGENTS.md cut introduces a truncation warning that wasn't present
  before (NFR-004 regression).
- Reply parser maps `(position N)` to a task_id that does not match
  the morning artifact's `habits[N-1].vikunja_task_id` (FR-008
  regression) — this means the parser is broken.
- Helper scripts buggy enough to corrupt the JSONL state log (file a
  P1-bug and rollback immediately).

Non-catastrophic anomalies (LLM disambiguator over-asks for
clarification, parser doesn't handle a novel reply shape) are
forward-fix candidates, NOT triggers to revert.

## Maintenance

### Manually correct a botched record

Per spec Out-of-Scope §2, this mission does NOT auto-repair existing
miscoded habit records. Kent edits the JSONL by hand when needed.

To repair a single record:

1. Stop the morning cron (safety — keep ticks from racing the repair):

   ```bash
   ssh office2-claude 'openclaw cron disable 3082343c-bc7f-47ee-916b-ee070b1e50dc'
   ```

2. Identify the bad line in `habits-history.jsonl`:

   ```bash
   ssh office2-claude 'grep "\"task_id\": <id>" /data/services/openclaw/state/habits-history.jsonl | tail -5'
   ```

3. Edit in place:

   ```bash
   ssh office2-claude 'nano /data/services/openclaw/state/habits-history.jsonl'
   ```

4. Validate every line parses:

   ```bash
   ssh office2-claude 'jq -c . /data/services/openclaw/state/habits-history.jsonl > /dev/null && echo OK'
   ```

5. Re-enable the cron:

   ```bash
   ssh office2-claude 'openclaw cron enable 3082343c-bc7f-47ee-916b-ee070b1e50dc'
   ```

Prefer appending an `operator_repair`-sourced record over hand-editing
when the goal is to log the correct state going forward — the
append-only history stays cleaner.

### Inspect a malformed morning-list artifact

If `cat morning-checkin-<date>.json | python3 -m json.tool` errors,
the artifact is corrupted. Delete it (the agent will file a P2-bug on
the next reply tick per FR-009), or regenerate by running the helper
manually with `--date <date>`. Note that re-running the helper queries
the CURRENT Vikunja state, not the state at the original tick time —
positions may shift. Prefer hand-recovery only if Kent has not yet
replied for that day.

### Cleanup of old morning-list artifacts

No automatic rotation (NFR-005). At ~365 files/year × ~1 KB each =
~365 KB/year, manual cleanup is not required for years. If desired:

```bash
ssh office2-claude 'find /data/services/openclaw/state/habits/ -name "morning-checkin-*.json" -mtime +30 -ls'
```

(Note the `-ls` flag — review the list before passing to `-delete`.)

### Update agent workspace files

```bash
for f in SOUL.md USER.md IDENTITY.md TOOLS.md AGENTS.md; do
  ssh office2-claude "cat > /data/services/openclaw/habits-agent/$f" < scripts/openclaw/agents/felix-admin-habits/$f
done
```

After updating `AGENTS.md`, immediately verify the char count:

```bash
ssh office2-claude 'wc -c /data/services/openclaw/habits-agent/AGENTS.md'
```

Expected: ≤14,000 (FR-011).

### Verify deployed agent

```bash
ssh office2-claude 'openclaw agents list | grep felix-admin-habits'
ssh office2-claude 'grep -c "morning_checkin_list\|parse_morning_reply\|disambiguate_reply" /data/services/openclaw/habits-agent/AGENTS.md'
```

Expected: non-zero on the grep (post-#371 references the new helpers).

### Adjust cron schedule

```bash
ssh office2-claude 'openclaw cron update 3082343c-bc7f-47ee-916b-ee070b1e50dc --cron "<new-expression>"'
```

### Temporarily pause habits

```bash
ssh office2-claude 'openclaw cron disable 3082343c-bc7f-47ee-916b-ee070b1e50dc'
```

Re-enable:

```bash
ssh office2-claude 'openclaw cron enable 3082343c-bc7f-47ee-916b-ee070b1e50dc'
```

## Vikunja habits project

- **Project name**: Habits (id=13)
- **Web UI**: `https://office2.tail0f5f56.ts.net/projects/13`

### Current habits

Per the 2026-05-22 inventory (post-#371 cutover):

| Position | Task ID | Title |
|---|---|---|
| 1 | 14 | Wake at 5:00 AM |
| 2 | 18 | Meditate |
| 3 | 19 | Morning shoulder PT |
| 4 | 20 | Get steps in today |
| 5 | 65 | Read 30 min minimum |
| 6 | 16 | Evening shoulder PT |
| 7 | 17 | Morning hip PT |
| 8 | 15 | Strength training — Friday |

Note: positions are computed dynamically by `morning_checkin_list.py`
at each tick — the table above reflects the current Habits project
inventory, but the authoritative day-by-day ordering is whatever the
helper wrote to `morning-checkin-<date>.json` for that date.

### Add/remove habits directly in Vikunja

Habits are managed via the Vikunja web UI or API. To add a habit,
create a task in the Habits project (id=13) with the personal
identity label. Set `repeat_after` so Vikunja rolls `due_date`
automatically when the task is marked done (Phase 3 #306 / cutover
#308).

To pause a habit, add `(PAUSED)` to the description. To archive, mark
the task done (history is preserved).

## Troubleshooting

| Symptom | Check | Fix |
|---------|-------|-----|
| No check-in delivered | `ssh office2-claude 'openclaw cron runs --id 3082343c-bc7f-47ee-916b-ee070b1e50dc'` | Verify cron exists, is enabled, has `--to` set |
| Morning artifact missing for today | `ssh office2-claude 'ls /data/services/openclaw/state/habits/'` | If cron ran but artifact is absent, run the helper manually with `--dry-run` to surface the error; check Vikunja reachability and the JSONL state log permissions |
| Reply applied to wrong habit | Compare `morning-checkin-<date>.json` positions vs. JSONL `task_id` recorded for the date | Parser routed against the wrong list (FR-008 regression) — file a P1-bug; rollback if confirmed |
| Completion not recorded | `tail -20 /data/services/openclaw/state/habits-history.jsonl` | Verify `record_completion.py` exit code in session log; check vikunja_api token: `ssh office2-claude 'openclaw skills info vikunja_api'` |
| Truncation warning on tick | `journalctl --user -u openclaw-gateway.service --since "1 hour ago" | grep truncat` | Restore AGENTS.md from `/tmp/habits-agents-pre-371.md.bak`; file a P1-bug to cut further |
| Parser exit code 4 (no artifact) | `ls /data/services/openclaw/state/habits/morning-checkin-<date>.json` | Expected behavior — agent files a P2-bug via `felix-file-issue.py` per FR-009; do NOT fall back to live Vikunja state |
| Parser exit code 5 (corrupted artifact) | `python3 -m json.tool /data/services/openclaw/state/habits/morning-checkin-<date>.json` | Investigate write path; delete the artifact and regenerate manually if Kent hasn't replied yet |
| Disambiguator over-asks for clarification | Inspect the disambiguator prompt at `scripts/habits/judgment/` | Forward-fix the prompt; not a rollback trigger |
| Agent not responding | `ssh office2-claude 'openclaw agents list'` | Restart gateway: `ssh office2-claude 'systemctl --user restart openclaw-gateway'` |
| Session cache stale | Agent uses old AGENTS.md | Restart gateway or wait for isolated session |

## 48hr response window (mission #408)

As of mission [#408](https://github.com/kentonium3/kg-automation/issues/408)
all habits — daily AND day-specific — stay **open in
`habits-history.jsonl` for 48 hours after their check-in delivery**.
Kent can reply to yesterday's WhatsApp check-in message on Wednesday
morning and the parser correctly attributes the reply to yesterday's
habits. The reply parser scans recent `morning-checkin-<date>.json`
artifacts within the 48hr window and chooses the best candidate via:

1. **Explicit date hint** in the reply (`"yesterday"`, `"Tue"`,
   `"2026-05-31"`).
2. **Most-recent-unresolved**: the most recent check-in whose habits
   the reply tokens map to (and that aren't already resolved).
3. **Default to today's check-in** — preserves existing behavior for
   prompt replies.

If 48 hours pass without a reply, the **felix-habit-sweeper** appends
an `auto_skipped` event to `habits-history.jsonl` and (for
day-specific habits) advances the Vikunja `due_date` to the next
designated weekday. The miss is recorded in history; the accountability
trail is preserved.

WhatsApp quote-reply metadata (priority 1 in the
[reply-correlation contract](<../../kitty-specs/habit-day-specific-scheduling-01KT48Y6/contracts/reply-correlation.contract.md>))
is NOT currently plumbed to the parser — the channel layer does not
forward it. If a future mission adds it, the hook point is
`parse_morning_reply.correlate_reply_to_checkin`'s reserved
`quote_reply_id` kwarg.

## Sweeper operations (felix-habit-sweeper, mission #408)

### Architecture at a glance

| Item | Value |
|---|---|
| Host | office2 (Ubuntu 24.04 LTS) |
| Timer cadence | `OnCalendar=*-*-* 07:30 America/New_York`, `Persistent=true` |
| ExecStart | `/usr/bin/python3 /home/claude/kg-automation/scripts/habits/sweeper.py` |
| State dir | `/data/services/openclaw/state/habits/` |
| Tick artifact | `sweeper-tick-<date>.json` (overwrite per ET date) |
| Ledger | `sweeper-ledger.jsonl` (append-only) |
| History writes | `auto_skipped` events appended to `habits-history.jsonl` |
| Vikunja writes | `POST /tasks/<id>` for day-specific habits only |
| Health signal | latest tick artifact's `exit_status` field |
| LLM calls | zero (deterministic per Directive 6) |
| Runs as | `claude` user |

### 30-second health check

```bash
ssh office2-claude 'jq -r "[.exit_status,.started_at_utc,.errors|length] | @tsv" /data/services/openclaw/state/habits/sweeper-tick-$(date -u +%Y-%m-%d).json'
```

A healthy tick prints `success   2026-MM-DDTHH:MM:SSZ   0`.

### Pre-cutover checklist

1. Code merged to `main` (`git pull` on office2 brings in `scripts/habits/sweeper.py` + the systemd units).
2. Restic backup for `/data/services/openclaw/state/` is current within the last 24h (Tier 2 — the sweeper appends to the existing JSONL history).
3. Vikunja API token exists and is readable by the `claude` user: `ssh office2-claude 'ls -l /data/services/openclaw/secrets/vikunja-api'` (expect `-rw------- claude claude`).
4. Schedule YAML has the day-specific entries: `ssh office2-claude 'grep designated_weekdays /home/claude/kg-automation/scripts/habits/migrations/phase3-schedule.yaml'` returns at least one match (the Mon/Wed/Fri strength-training entries).
5. System python has PyYAML available: `ssh office2-claude 'python3 -c "import yaml; print(yaml.__version__)"'` returns a version (NOT `ModuleNotFoundError`). If missing, install via `apt-get install python3-yaml` — present Kent the sudo command per CLAUDE.md Tier 0 protocol.

### Cutover procedure

Run each command one at a time, verifying each before proceeding.

Pull code on office2:

```bash
ssh office2-claude 'cd /home/claude/kg-automation && git pull --ff-only'
```

Verify schedule.yaml has the day-specific entries:

```bash
ssh office2-claude 'grep -c designated_weekdays /home/claude/kg-automation/scripts/habits/migrations/phase3-schedule.yaml'
```

Run a `--dry-run` sweep to preview without mutating state:

```bash
ssh office2-claude '/usr/bin/python3 /home/claude/kg-automation/scripts/habits/sweeper.py --dry-run'
```

Install the systemd units (idempotent — overwrite-symlink):

```bash
ssh office2-claude 'install -m 0644 /home/claude/kg-automation/scripts/office2/felix-habit-sweeper.service /home/claude/.config/systemd/user/felix-habit-sweeper.service'
```

```bash
ssh office2-claude 'install -m 0644 /home/claude/kg-automation/scripts/office2/felix-habit-sweeper.timer /home/claude/.config/systemd/user/felix-habit-sweeper.timer'
```

Reload systemd user units:

```bash
ssh office2-claude 'systemctl --user daemon-reload'
```

Verify both units parse:

```bash
ssh office2-claude 'systemd-analyze --user verify felix-habit-sweeper.service felix-habit-sweeper.timer'
```

Enable + start the timer:

```bash
ssh office2-claude 'systemctl --user enable --now felix-habit-sweeper.timer'
```

Force a `--dry-run` sweep to populate the first tick artifact (without mutating state):

```bash
ssh office2-claude '/usr/bin/python3 /home/claude/kg-automation/scripts/habits/sweeper.py --dry-run'
```

Inspect the tick artifact:

```bash
ssh office2-claude 'cat /data/services/openclaw/state/habits/sweeper-tick-$(TZ=America/New_York date +%Y-%m-%d).json'
```

### Post-cutover verification

1. Timer is active: `ssh office2-claude 'systemctl --user is-active felix-habit-sweeper.timer'` returns `active`.
2. Tick artifact is fresh: `ssh office2-claude 'ls -lt /data/services/openclaw/state/habits/sweeper-tick-*.json | head -1'` shows today's date.
3. No errors: `ssh office2-claude 'jq ".errors | length" /data/services/openclaw/state/habits/sweeper-tick-$(date +%Y-%m-%d).json'` returns `0`.

### Sweeper troubleshooting

| Symptom | Check | Fix |
|---------|-------|-----|
| Sweeper exited non-zero | `journalctl --user -u felix-habit-sweeper.service -n 50` | Read the `SUMMARY:` line + tick artifact's `errors[]`. Per-habit Vikunja PUT failures yield `exit_status: partial` (exit 1); schedule load failures yield `failure` (exit 2). |
| Unresolved habit not auto-skipped | `jq '.habits_evaluated[] | select(.task_id==N)' /data/services/openclaw/state/habits/sweeper-tick-*.json` | Confirm the relevant `morning-checkin-<date>.json` is actually >48hr old. The sweeper deliberately defers anything inside the 48hr window. |
| Kent's late reply didn't correlate | Read `parse_morning_reply` stderr + the produced JSON's `correlated_checkin_date_et` field | The 48hr correlation only fires when state_dir contains recent artifacts. If Kent replied >48hr after the relevant check-in, the sweeper has already marked the habits `auto_skipped` — the parser will not retroactively mark them done. |
| Vikunja PUT failed | tick `errors[*].error_type=="vikunja_put"` entries | Per-habit failures don't abort the tick; rerun the sweeper after Vikunja recovers. The idempotency check ensures already-skipped habits aren't double-emitted. |
| Tick artifact missing today's run | `systemctl --user list-timers felix-habit-sweeper.timer` | Verify next-fire timestamp is in the next 24hr. `Persistent=true` guarantees a missed tick fires on next start. |
| `auto_skipped` event in history but habit still appearing in next check-in | Verify the day-specific habit's Vikunja `due_date` was actually advanced (`jq '.habits_auto_skipped' /data/.../sweeper-tick-*.json` should show the advanced timestamp) | Vikunja PUT may have failed silently — rerun with `--dry-run` first to confirm the computed new_due_date, then rerun without `--dry-run`. |

### Sweeper rollback (mission #408)

Reverses each cutover step, in reverse order.

Stop + disable the timer:

```bash
ssh office2-claude 'systemctl --user disable --now felix-habit-sweeper.timer'
```

Optionally remove the systemd unit symlinks:

```bash
ssh office2-claude 'rm /home/claude/.config/systemd/user/felix-habit-sweeper.service /home/claude/.config/systemd/user/felix-habit-sweeper.timer'
```

Reload systemd:

```bash
ssh office2-claude 'systemctl --user daemon-reload'
```

State files (`sweeper-tick-*.json`, `sweeper-ledger.jsonl`,
`auto_skipped` events in `habits-history.jsonl`) are left in place —
they document what the sweeper did and don't affect the morning
check-in pipeline. The morning check-in resumes pre-#408 behavior
immediately on the next tick.

To revert the `exclude_completed_v2` extension (only if a regression
forces it), `git revert` the WP02 commit on the lane and redeploy.

## Reconciliation command (mission #408)

When Kent changes a habit's `designated_weekdays` (e.g., moves the Wed
strength training to Tue), run the reconciliation flag on
`set_due_dates.py` to advance the Vikunja `due_date` to the next
occurrence of the NEW designated weekday.

Edit the YAML (locally or on office2):

```bash
vim scripts/habits/migrations/phase3-schedule.yaml
```

Preview the changes against live Vikunja state (no PUTs issued):

```bash
ssh office2-claude 'cd /home/claude/kg-automation && /usr/bin/python3 -m scripts.habits.set_due_dates --reconcile-schedule --dry-run'
```

Apply (issues Vikunja POSTs to advance any due_dates that drifted):

```bash
ssh office2-claude 'cd /home/claude/kg-automation && /usr/bin/python3 -m scripts.habits.set_due_dates --reconcile-schedule'
```

The command writes an E5 reconciliation record at
`/data/services/openclaw/state/habits/reconcile-<datetime>.json`
documenting which task_ids changed and the old/new due_dates.

## Privacy boundary

**Absolute rule**: `04-Growth/_private/` is never read, processed,
routed to, referenced, or logged. Habits originating from private
context appear only as habit names. This is enforced in SOUL.md,
AGENTS.md, and TOOLS.md. There are no exceptions.

## Cross-references

- **Mission**: [#371](https://github.com/kentonium3/kg-automation/issues/371) — habits scripts-first port (this fix)
- **Cutover playbook**: [`quickstart.md`](../../kitty-specs/habits-checkin-reply-scripts-first-01KS86ZQ/quickstart.md)
- **Mission spec**: [`spec.md`](../../kitty-specs/habits-checkin-reply-scripts-first-01KS86ZQ/spec.md)
- **CLI contracts**: [`contracts/cli.md`](../../kitty-specs/habits-checkin-reply-scripts-first-01KS86ZQ/contracts/cli.md)
- **Data model**: [`data-model.md`](../../kitty-specs/habits-checkin-reply-scripts-first-01KS86ZQ/data-model.md)
- **Pattern source (architecture)**: [#309](https://github.com/kentonium3/kg-automation/issues/309) — escalation port to scripts-first (same shape); [`docs/runbooks/escalation-ops.md`](<./escalation-ops.md>)
- **Pattern source (narrow LLM judgment)**: [#343](https://github.com/kentonium3/kg-automation/issues/343) — felix-doc-auditor rework
- **Foundation**: [#306](https://github.com/kentonium3/kg-automation/issues/306) (habits Phase 3 — JSONL state model) and [#308](https://github.com/kentonium3/kg-automation/issues/308) (habits Phase 5 — cutover)
- **Agent surface**: [`scripts/openclaw/agents/felix-admin-habits/AGENTS.md`](../../scripts/openclaw/agents/felix-admin-habits/AGENTS.md)
- **JSONL state library**: `scripts/common/state_log.py` (Phase 2, #305)
- **ADR**: `docs/design/architecture/adr/0002-felix-vikunja-task-model.md`
- **Memory**: `reference_openclaw_gotchas.md` — AGENTS.md effective char budget
