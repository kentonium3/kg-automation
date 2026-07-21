---
title: Inbox Processing Operations Runbook
doc_type: runbook
audience: agents
status: draft
---

# Inbox processing operations

## Overview

The felix-admin-capture agent processes Kent's Obsidian inbox autonomously.
It runs on office2 via OpenClaw, 3 times daily on a cron schedule. It reads
unprocessed notes from `01-Inbox/`, classifies content, routes it to the
correct vault locations, creates Vikunja tasks for action items, and writes
a processing log.

As of mission `capture-atomic-finalize-01KXRM7J` (#746), each note is committed
through a single **note-level finalize transaction**: the agent classifies the
note's blocks, assembles a routing plan, and invokes one `route_and_finalize`
command. That helper routes every block, verifies every artifact, writes a
per-block routing-log entry, and marks the note `processed` **once, only after
all blocks are logged** — atomic, fail-loud, and retry-safe. This closes the
silent-loss class where a note could be marked done while a later route quietly
dropped. See [§ Note-level finalize](#note-level-finalize-746) below.

## Agent management

- **Agent name**: `felix-admin-capture`
- **Workspace on office2**: `/data/services/openclaw/inbox-agent/`
- **Source in repo**: `scripts/openclaw/agents/felix-admin-capture/`
- **Model**: `anthropic/claude-sonnet-4-6`

### Workspace files

| File | Purpose |
|------|---------|
| SOUL.md | Kent-voice authoring identity |
| USER.md | Kent's context |
| IDENTITY.md | Agent identity metadata |
| TOOLS.md | Vault paths, Vikunja API reference |
| AGENTS.md | Standing orders: full processing workflow |

### Update workspace files

```bash
for f in SOUL.md USER.md IDENTITY.md TOOLS.md AGENTS.md; do
  ssh office2-claude "cat > /data/services/openclaw/inbox-agent/$f" \
    < scripts/openclaw/agents/felix-admin-capture/$f
done
```

### Verify agent

```bash
ssh office2-claude "openclaw agents list"
```

Expected: `felix-admin-capture` with workspace `/data/services/openclaw/inbox-agent`.

### Deploy: source → office2

Capture changes reach office2 through two independent, existing mechanisms — no
per-change deploy manifest is required (see below):

| Surface | Source in repo | How it lands on office2 |
|---|---|---|
| Helper scripts | `scripts/inbox/*.py`, `scripts/inbox/prescan.py` | office2 checkout **self-pull** — felix-deployer auto-pulls `origin/main` every ~5 min into `/home/claude/kg-automation/`; the helpers are imported from that checkout at their `-m` module paths. |
| Agent prompts | `scripts/openclaw/agents/felix-admin-capture/AGENTS.md`, `TOOLS.md` | **agent-prompt-sync** (`scripts/openclaw/deploy/deploy_agent_prompts.py`, 5-min timer, #567) copies them to the workspace dir. Note the slug ≠ dir: `felix-admin-capture` → `/data/services/openclaw/inbox-agent/` (see `[[reference_office2_agent_deploy_paths]]`). |

**No deploy manifest for mission #746.** A `deploys/queued/<name>.yaml` manifest is
only needed when an office2-side apply step is required **beyond** the self-pull +
agent-prompt-sync (e.g. a systemd unit install, a state-file migration, a config
write). This mission is pure Python helpers + agent-prompt edits — both surfaces
deploy through the two standing mechanisms above with zero apply step — so **no
manifest was created**. Do not add an empty/no-op manifest.

**Rebaseline: not required** (#621). Evidence in
`docs/design/architecture/data/audited-surfaces.json`:
- `scripts/openclaw/agents/*/AGENTS.md` (and `TOOLS.md` is not even listed) falls
  under the `openclaw-agent-prompts` surface, which carries
  `rebaseline_required: false` and `affected_baselines: []` — `audit.sh` hashes
  only `openclaw.json`, never deployed AGENTS.md, so no baseline moves and none can
  be reset.
- `scripts/inbox/` matches **no** audited-surface pattern at all, so helper edits
  are not an audited surface.

Merge commit should record `Rebaseline: not required — AGENTS.md not a hashed
audited surface (#621); scripts/inbox not in audited-surfaces.json`.

## Schedule

Three cron jobs run the agent in isolated sessions:

| Job | Schedule (UTC) | Local time (EDT) |
|-----|---------------|-----------------|
| inbox-morning | `0 11 * * *` | 7:00 AM ET |
| inbox-midday | `0 16 * * *` | 12:00 PM ET |
| inbox-evening | `0 22 * * *` | 6:00 PM ET |

All jobs have a 5-minute (300s) timeout and use `--no-deliver` (no WhatsApp
notification on completion).

### View jobs

```bash
ssh office2-claude "openclaw cron list"
```

### Manual trigger

```bash
ssh office2-claude "openclaw cron run <job-uuid>"
```

Get the UUID from `openclaw cron list`. Cron run by name is not currently
supported.

### Direct agent invocation

```bash
ssh office2-claude "openclaw agent --agent felix-admin-capture \
  --message 'Process the inbox now.' --json --timeout 300"
```

## Processing log

- **Location**: `/home/kgale/second-brain/agents/logs/inbox-processing-YYYY-MM-DD.md`
- **Multiple runs per day**: Appended with time-stamped section headers

### Check recent logs

```bash
ssh office2-claude "ls -lt /home/kgale/second-brain/agents/logs/ | head"
```

### What to look for

- **Files processed**: Count and descriptions
- **Tasks created**: Vikunja tasks with project, label, and source
- **Goals routed**: Felix declarations added to Goals-MOC.md
- **Items flagged**: Errors, needs-review items, potential-goals

## Note-level finalize (#746)

Mission `capture-atomic-finalize-01KXRM7J` (#746) replaced the old per-route,
mark-then-log sequence with one atomic **note-level finalize transaction**. This
is the load-bearing routing path now — understand it before touching capture.

### The flow

1. **Classify blocks.** The agent splits the note into content blocks and
   classifies each one (deterministic heuristics from `classify_content.py` plus
   LLM judgment for ambiguous blocks) into a route `kind`.
2. **Assemble a RoutingPlan.** The agent builds one JSON plan for the whole note:
   `{"blocks": [{"block_index", "kind", "content", "payload"|"task_id"|"issue_number"}, ...]}`.
   A note with no routable content becomes an `empty` plan.
3. **One finalize call.** The agent invokes the transaction exactly once per note
   (mandatory `-m` form):

   ```bash
   cd /home/claude/kg-automation && python3 -m scripts.inbox.route_and_finalize \
     --source-path <abs-path-of-source-note> \
     --plan-file <abs-path-of-routing-plan.json>
   ```

   `--dry-run` validates the plan and reports `would_finalize` with **no** side
   effect (credential-free wiring check).

### The atomic guarantee (route → verify → log → mark, once)

For each block in `block_index` order the helper: routes it, verifies the
artifact — delegated `vikunja_task` ids are additionally checked to belong to
this note (source provenance via the `Source:` footer); delegated `github_issue`
numbers are verified to exist (`gh issue view`), with a null/missing number a
finalize failure — then writes that block's routing-log entry **before** the note
is marked. Only after **every** block is routed and logged
does the helper mark the note `processed` — **once**, by invoking
`mark_processed` as a subprocess (the outside-inbox-root validation and symlink
`.resolve()` guard live in `mark_processed.main()`; finalize never calls it
in-process).

- **Log-before-mark + per-block keys** make it retry-safe: routing-log entries
  are keyed on `filename + block_index + block_hash`. On a re-run an
  already-logged block is skipped with no repeated side effect, so a partial
  failure that left the note unprocessed re-routes only the missing blocks on the
  next tick.
- **Any block failure aborts before the mark.** The note is left `unprocessed`,
  the helper exits non-zero, and the succeeded blocks are already logged (never
  recreated next tick). No note is ever marked processed with an unrouted block.
- The exit code derives from the **note-level outcome**, never from an always-0
  route step.

### Route kinds

`calendar`, `someday`, `vikunja_task`, `journal`, `github_issue`, and the
no-route disposition `empty`. Calendar folds in the #737 create/verify path
verbatim (source-path idempotency key → a re-create returns the same event, never
a duplicate). `empty` **refuses a non-empty body** (only whitespace after
stripping Templater cursor tags counts as empty) so it can never bury real
content — the silent-loss escape hatch this mission closes.

### Terminals

- **`needs-review`** — a terminal inbox state (frontmatter `status: needs-review`).
  The note is excluded from `unprocessed_paths` (prescan will not re-offer it) and
  is **not** flagged by the health rail below. Human triage only.
- **`empty`** — a verified-empty note gets a `kind=empty` routing-log entry and is
  marked processed once, so it leaves a recorded disposition (never a silent skip).
- **`needs_clarification`** — currently calendar-only. The block is left unrouted,
  the note stays `unprocessed` (exit 0), and capture enters the calendar
  clarification flow (pending-calendar-clarifications state, **8h** sweep-finalize —
  see [§ Calendar clarification sweep-finalize (8h + all-day fallback)](#calendar-clarification-sweep-finalize-8h--all-day-fallback-780)).

### Standalone helpers removed from the agent flow

The agent **no longer** calls `mark_processed` or `append_routing_entry` as
separate steps — `route_and_finalize` owns both, in the correct order, internally.
`append_routing_entry.py` is retained only as a CLI for any non-capture caller;
it is off the capture agent's standing-orders path.

### Health rail: `processed-without-routing-log`

Because a note is marked `processed` only after every block is logged, a
`processed` note with **no** routing-log entry is the silent-loss signature.
`prescan.scan_processed_without_routing_log()` (#746) scans both `01-Inbox/` and
`02-Inbox-Processed/`, cross-references the routing-log reader, and flags any such
note (read-only — it never remediates). The warning text is load-bearing:

> `status:processed but no routing-log entry (silent-loss signature #746)`

**IDLE-gate surfacing:** the capture agent's Step 1 IDLE gate treats a non-empty
health rail as work — the agent does **not** reply `[felix-admin-capture]: IDLE`
when the rail has findings; it surfaces them so the anomaly is not buried by a
quiet tick. If the routing log is unreadable the rail is disabled for that run and
a warning is emitted rather than a false all-clear.

## Calendar clarification sweep-finalize (8h + all-day fallback, #780)

When a captured note resolves to an appointment with a **date but no time**
("Meet Rob Thursday"), capture asks Kent for the start time (Step 3c) and records
a **pending clarification** carrying the resolved `start_date` and the
`missing_fields` signal. The **ask always fires first** — the all-day event is a
timeout-only fallback, never a substitute for asking (spec C-005).

Each tick, capture's **Step 1a** runs the deterministic sweep-finalize command
(replaces the old bare `handle_clarification_state sweep`):

```bash
cd /home/claude/kg-automation && python3 -m scripts.inbox.clarification_sweep_finalize
```

- **8h window (C-006).** The whole clarification lifecycle ages out at **8h**
  (reduced from 24h — the single `SWEEP_MAX_AGE` in `handle_clarification_state.py`).
  A record is aged out once `now − created_at ≥ 8h`; non-aged-out records are
  untouched.
- **All-day fallback (eligible).** An aged-out record is **eligible** iff its
  `partial_payload` has a `title`, a well-formed `start_date` (`YYYY-MM-DD`), and a
  `missing_fields` list that contains `start_time` and is a subset of the timing
  fields `{start_time, end_or_duration}`. For an eligible record the sweep builds a
  single-block all-day `calendar` plan and creates the event through the #746
  `route_and_finalize` transaction (atomic + idempotent), marks the note processed,
  removes the record, and writes a distinct **`calendar_all_day_fallback`**
  routing-log marker (so the operator can count fallback creates separately from
  normal creates and sweep-deletes — spec SC-004).
- **Delete-and-release (ineligible).** An aged-out record that is **not** eligible
  (missing title, a non-timing gap, or a legacy record with no `missing_fields` /
  `start_date`) gets today's delete-and-release: the record is dropped so the note
  re-scans / re-asks — consistent with the prior timeout semantics (C-007).
- **Fail-closed + reconcile.** If the create/mark does not complete, the record is
  **retained** and the note left unprocessed for a later retry — never a partial or
  duplicate. On a retry where a prior run already created + logged the event but the
  note-mark or record-removal did not finish, the transaction's per-block
  idempotency recognizes the reconcile and removes the stale record **without
  re-creating** the event (the `calendar_all_day_fallback` marker still emits exactly
  once).
- **Output.** One-line JSON counts summary
  (`{"aged_out","finalized","reconciled","released","retained"}`); exit 0 even when
  records are retained (that is the expected fail-closed outcome). The agent
  continues regardless of the counts and never creates the event itself.

**Canonical flow doc:** the full ask → 8h age-out → all-day-fallback process flow
(with the reconciliation/idempotency ladder) lives at
[`../design/process-flows/calendar-clarification.md`](../design/process-flows/calendar-clarification.md).
This runbook is the operational pointer; that doc is the source of truth for the flow.

## WhatsApp trigger

Send "process my inbox" (or natural variations) via WhatsApp. The main agent
delegates to felix-admin-capture and responds with a processing summary.

**Known limitation**: The nested agent call requires sufficient timeout. If
the main agent times out before felix-admin-capture finishes, the processing
still completes but the summary is not relayed back.

## Cowork fallback

When the office2 agent is down or misconfigured, processing can be done
manually using the original Cowork skills on Mac.

### Fallback procedure

1. Open a Claude session on Mac
2. Invoke the inbox-processor skill manually:
   ```
   Use the inbox-processor skill to process my inbox
   ```
3. The skill reads from `~/second-brain/notes/01-Inbox/`
4. Results are written directly to the vault (syncs to office2 via Obsidian Sync)

### Skill locations (Mac)

- `~/second-brain/.claude/skills/inbox-processor/SKILL.md`
- `~/second-brain/.claude/skills/kent-voice/SKILL.md`
- `~/second-brain/.claude/skills/vault-writer/SKILL.md`

**Warning**: Do not run both the office2 agent and Cowork fallback
simultaneously on the same inbox files. This will cause duplicate processing.

## Troubleshooting

| Symptom | Check | Fix |
|---------|-------|-----|
| No processing logs | `ssh office2-claude "openclaw cron list"` | Verify cron jobs exist and are enabled |
| Vault not accessible | `ssh office2-claude "ls /home/kgale/second-brain/notes/01-Inbox/"` | Check Obsidian Sync: `ssh office2-kgale "systemctl status obsidian-sync"` |
| Vikunja tasks not created | Check processing log error section | Verify vikunja_api skill and API token |
| Agent not responding | `ssh office2-claude "openclaw agents list"` | Restart gateway: `ssh office2-claude "systemctl --user restart openclaw-gateway"` |
| Session lock error | Check for stale `.lock` files | `ssh office2-claude "rm -f ~/.openclaw/agents/felix-admin-capture/sessions/*.lock"` |
| Timeout on large inbox | Processing log shows partial results | Increase `--timeout-seconds` on cron jobs or process manually |
| Note mistakenly skipped (#185 dedup) | `ssh office2-claude "cat /data/services/openclaw/state/inbox-routing.jsonl \| jq -c 'select(.filename==\"<filename>\")'"` | Edit the routing log to remove the offending entry (or move the note to a new filename). Next tick will re-route normally. |
| `processed-without-routing-log` flagged (#746 silent-loss signature) | Prescan health rail lists the note; `ssh office2-claude "cat /data/services/openclaw/state/inbox-routing.jsonl \| jq -c 'select(.filename==\"<filename>\")'"` returns nothing | A `processed` note with no routing-log entry means it was marked done without a recorded route. Reset it: clear the note's `status: processed` frontmatter so the next tick re-routes it through `route_and_finalize` (which will log-before-mark). Investigate why it was marked without a log entry before clearing. |
| "Inbox quality" issue filed | See §"When you see an 'Inbox quality' issue" below | Fix frontmatter in each affected note per the issue body |

## When you see an "Inbox quality" issue (#185)

The `felix-admin-capture` agent files a batched GitHub issue with title
prefix `Inbox quality:` when one or more inbox notes have unparseable
frontmatter. The agent halts routing for those notes (rather than misfiling
them as generic content issues) and surfaces the problem through the
issue + an Obsidian callout marker on each affected note.

To resolve:

1. **Open the GitHub issue.** Each row in the body's table identifies an
   affected note by filename and the specific malformation reason.
2. **Open each affected note in Obsidian.** The agent has injected a
   `> [!error] felix-capture:` callout at the top of the note's body
   showing the same error and the issue number.
3. **Fix the malformation.** Common cases:
   - **Leading whitespace before `---`** — delete blank lines / spaces /
     BOM before the opening `---` fence.
   - **UTF-8 BOM** — re-save the file in UTF-8 without BOM. (Obsidian
     uses no-BOM UTF-8 by default; this usually comes from
     paste-from-Word or a misconfigured editor.)
   - **Missing closing `---`** — add the closing fence.
   - **Invalid YAML** — fix the syntax (mismatched quotes, unescaped
     colons in values, tab indentation).
4. **Save.** The next cron tick will:
   - Re-classify the note as well-formed
   - Auto-strip the callout marker as part of routing
   - Route the note normally and append to the routing log
5. **Close the GitHub issue manually** once all listed notes are fixed
   (or moved out of `01-Inbox/`).

   **Important — how dedup interacts with new failures**: while an
   "Inbox quality:" issue is OPEN, subsequent ticks that encounter new
   parse failures do NOT file a new issue and do NOT update the open
   issue's body. Newly-failing notes still get a callout marker
   injected pointing at the existing open issue, so they ARE
   discoverable by opening the inbox in Obsidian — but they will not
   appear in the issue's table.

   This means: keep the issue closed promptly. A new "Inbox quality:"
   issue is only filed by the next tick AFTER the previous one is
   closed. If you suspect new parse failures while an issue is open,
   check the inbox directly for notes with the felix-capture callout
   marker rather than relying on the issue body to enumerate them.

### Routing log

The agent uses an append-only JSONL file at
`/data/services/openclaw/state/inbox-routing.jsonl` (on office2, owned by
the `claude` user; relocated from `~/second-brain/agents/state/` by #656) as
the load-bearing dedup substrate. The classifier reads this file on every cron
tick and filters already-routed filenames out of the agent's input.

As of #746 each **block** a finalize routes appends its own row, keyed on
`filename + block_index + block_hash` (with `kind` ∈
`calendar｜someday｜vikunja_task｜journal｜github_issue｜empty`), in addition to
the legacy `{filename, issue_number, vikunja_task_id, routed_at, note_excerpt}`
fields. Legacy rows that predate the block fields still satisfy the note-level
`reader.has(filename)` dedup check, so the reader stays backward-compatible. The
per-block key is what makes the finalize transaction retry-safe (an already-logged
block is skipped on re-run).

If a note is mistakenly skipped, inspect this file:

```bash
ssh office2-claude "cat ~/second-brain/agents/state/inbox-routing.jsonl | jq -c"
```

To force re-routing of one filename, edit out the offending entry (or
just delete the whole file to reset state — the routing log is recreated
on the next route). The file is backed up by the nightly Restic job; it
is NOT git-tracked.

## Privacy boundary

**Physical exclusion (#848)**: Kent's private growth content (formerly
`04-Growth/_private/`) is not present on office2 — it lives in a separate
laptop/phone-only Obsidian vault office2 never joins, and the old folder was
deleted and verified absent from office2. The inbox flow therefore never
encounters it. `mark_processed` still refuses any path outside the resolved
inbox root (a folder-independent guard), so nothing is stamped outside the inbox.

> The boundary is now the content's physical absence rather than an in-repo
> "never touch `_private`" rule the agent must carry.

## Inbox-Processed destination

After mission 026 (#152), processed items are eligible to be moved into
`01-Inbox`'s sibling folder `02-Inbox-Processed/`. The actual move logic
ships in the inbox pre-scan helper (mission #149); this runbook is the
current consumer reference until that mission lands.
