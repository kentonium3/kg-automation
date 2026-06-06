---
id: tasker-ops
doc_type: runbook
title: Tasker Operations (Enrichment JSONL Migration)
status: approved
level: 2
owners: [kent]
audience: agents_and_humans
last_validated: '2026-05-23'
updated_by: '#310'
version: '1.0.0'
---

# Tasker Operations

## Overview

The `felix-admin-tasker` agent transforms raw task descriptions (delivered via
delegation from `felix-admin-capture`, or directly via Kent's manual triggers)
into structured Vikunja tasks with project placement, identity label, due
date, priority, and goal relations. It also runs ad-hoc retroactive enrichment
(`retroactive_enrichment`) on flat tasks already in the Inbox project, and
ad-hoc single-task detection-and-offer (`detect_incomplete`) for tasks Kent
created directly.

**Tasker is delegation-driven, not cron-driven.** There is no OpenClaw cron
that fires the tasker on a schedule; every enrichment cycle is initiated by
either a delegation message from `felix-admin-capture` (the `enrich_task`
action) or an operator-initiated message (the `retroactive_enrichment` and
`detect_incomplete` actions). The previously-listed `task-detection` cron
(every 4 hours UTC) was unverified drift in the architecture inventory and
was removed by #310 spec-readiness verification.

As of mission #310 (ADR-0002 Phase 7 — the **final** phase of the JSONL-canonical
migration), enrichment state is **canonical in the JSONL ledger** at
`/data/services/openclaw/state/enrichment/enrichment-history.jsonl`. The agent
reads state via `scripts/enrichment/derive_state.py` and writes events via
`scripts/enrichment/record_completion.py`. The legacy
`[Felix] enrichment | <state> | <ISO timestamp>` Vikunja comments are still
written through during the post-cutover 3-day soak for rollback safety, but
they are **not** read.

**Enrichment states**: `proposed` → `confirmed` / `skipped` / `declined`. The
single-offer policy (per FR-001) makes `skipped` and `declined` terminal — a
task in either state is never re-proposed unless Kent explicitly asks.

## Cutover sequence

Run once per deploy after the #310 mission merges to main.

### Pre-flight (Tier 2 — required)

Tasker is a Tier 2 change (application/state — schema added, state log touched).
Per the [pre-flight checklist](<./governance/pre-flight-checklist.md>):

1. Confirm a Restic backup completed within the last 24 hours:

   ```bash
   ssh office2-claude 'ls -la /mnt/backups/restic-repo/snapshots/ | tail -5'
   ```

2. Confirm no in-flight enrichment activity in the last 15 minutes (so the
   cutover doesn't race a live `record_completion` call):

   ```bash
   ssh office2-claude 'grep -c "felix-admin-tasker" ~/second-brain/agents/logs/$(date -I).md 2>/dev/null || echo 0'
   ```

   Zero in a 15-minute window is typical (tasker is delegation-driven; ~10
   events/month natural traffic).

### Cutover (single command)

The operator runs the one-shot cutover from a local checkout on office2:

```bash
ssh office2-claude 'cd /home/claude/kg-automation && PYTHONPATH=scripts python3 scripts/openclaw/helpers/cutover_tasker.py'
```

This script (`scripts/openclaw/helpers/cutover_tasker.py`):

1. Deploys `scripts/openclaw/skills/task-intelligence/SKILL.md` →
   `/home/claude/.openclaw/skills/task-intelligence/SKILL.md`
   (closes the pre-existing skill deployment gap surfaced during #310
   spec-readiness — the deployed AGENTS.md referenced the skill but it was
   never deployed).
2. Deploys `scripts/openclaw/agents/felix-admin-tasker/AGENTS.md` →
   `/data/services/openclaw/tasker-agent/AGENTS.md` (the cut version, ≤14K
   chars per NFR-002).
3. Invokes `python3 -m scripts.enrichment.reconcile_completions` to backfill
   the JSONL ledger from historic `[Felix] enrichment` Vikunja comments since
   the 2026-04-11 window.
4. Writes the idempotency marker at `~/.config/openclaw/cutover-310.done`.

Exit codes:

- `0` — success (or idempotent no-op when the marker pre-exists)
- `1` — filesystem failure (deploy or marker write)
- `2` — reconcile subprocess failed
- `3` — invalid CLI arguments

The script is idempotent. Re-running on a fresh machine where the marker
exists is a no-op; pass `--force` if a partial deploy needs cleanup.

Preview with `--dry-run` before committing:

```bash
ssh office2-claude 'cd /home/claude/kg-automation && PYTHONPATH=scripts python3 scripts/openclaw/helpers/cutover_tasker.py --dry-run'
```

### Post-cutover verification

1. Confirm the marker landed:

   ```bash
   ssh office2-claude 'ls -la ~/.config/openclaw/cutover-310.done && cat ~/.config/openclaw/cutover-310.done'
   ```

2. Confirm the deployed AGENTS.md is the cut version (under 14K chars):

   ```bash
   ssh office2-claude 'wc -c /data/services/openclaw/tasker-agent/AGENTS.md'
   ```

3. Confirm the skill is deployed:

   ```bash
   ssh office2-claude 'ls -la /home/claude/.openclaw/skills/task-intelligence/SKILL.md && wc -c /home/claude/.openclaw/skills/task-intelligence/SKILL.md'
   ```

4. Confirm the JSONL ledger exists and contains backfilled rows (will be
   small — historic enrichment traffic is sparse, ~10/month):

   ```bash
   ssh office2-claude 'wc -l /data/services/openclaw/state/enrichment/enrichment-history.jsonl && head -3 /data/services/openclaw/state/enrichment/enrichment-history.jsonl'
   ```

5. Verify reconcile re-run is a no-op (idempotency check):

   ```bash
   ssh office2-claude 'cd /home/claude/kg-automation && PYTHONPATH=scripts python3 -m scripts.enrichment.reconcile_completions --dry-run'
   ```

   Expect zero new rows in the dry-run output.

## Soak verification (3 days)

The 3-day soak window harmonizes with #309 (escalation) and #371 (habits).
During the soak, both Vikunja comments AND JSONL rows are written for every
enrichment event (write-through pattern per C-002) so a defect surfaces with a
clean rollback path: revert the deployed AGENTS.md and the tasker resumes
writing only Vikunja comments.

### Synthetic enrichment runs (≥3 scenarios)

Natural enrichment traffic is sparse (~10 events/month), so passive
observation alone is insufficient. Run at least three controlled synthetic
scenarios during the soak — at least one for each non-`proposed` terminal
state. Each scenario should produce:

- One Vikunja comment with the new state
- One JSONL row appended to `enrichment-history.jsonl` with the matching
  `(task_id, state, timestamp)`
- One activity-log entry under `~/second-brain/agents/logs/<date>.md`

**Scenario 1 — confirmed path**: drop a deliberately under-specified note in
the Obsidian Inbox (`01-Inbox`). On the next `felix-admin-capture` cron,
expect a delegation to tasker → a `proposed` WhatsApp message → reply "yes" →
a Vikunja task created + `confirmed` JSONL row.

**Scenario 2 — skipped path**: drop a second Inbox note. Reply "skip" to the
proposal. Expect a `skipped` JSONL row + comment.

**Scenario 3 — declined path**: directly create a flat Vikunja task in the
Inbox project (no due date, no label). On the next operator-triggered
`detect_incomplete` run, expect a single-task proposal → reply "no" → a
`declined` JSONL row + comment.

**Optional Scenario 4 — proposed path (no resolution)**: drop a third Inbox
note. Do not reply for 24+ hours. Expect a `proposed` JSONL row + comment;
verify `derive_state.py --task-id <id>` reports `proposed`; verify the
single-offer policy permits one re-proposal once the 24-hour window elapses.

For each scenario, verify the three-write atomicity:

```bash
# After the agent has run, replace TASK_ID with the real Vikunja task id
ssh office2-claude 'grep "\"task_id\": <TASK_ID>" /data/services/openclaw/state/enrichment/enrichment-history.jsonl'
ssh office2-claude 'python3 -m scripts.enrichment.derive_state --task-id <TASK_ID>'
```

Then check the Vikunja UI for the corresponding `[Felix] enrichment` comment
and the agent log entry under `~/second-brain/agents/logs/`.

### Passive observation

Over the 3-day window, monitor for:

- Zero corruption events (no malformed JSONL lines; check with
  `jq -c . /data/services/openclaw/state/enrichment/enrichment-history.jsonl >/dev/null && echo OK`)
- Zero spurious re-proposals on `skipped` or `declined` tasks
- 1:1 correspondence between new `[Felix] enrichment` comments and JSONL rows
- Reconcile re-run remains a no-op (idempotency holds)

### Soak completion criteria (per spec SC-005)

- ≥3 synthetic runs covering all 4 states pass
- Passive observation shows zero corruption events
- Reconcile re-run is a no-op (idempotent)
- The existing escalation + habits + doc_audit regression suites continue to
  pass (full test suite green on main)

Once met, mission #310 closes and the C-002 soak technically ends. A v2
follow-on (analogous to #376 for #362) can remove the Vikunja-comment write
path; until then, write-through is preserved.

## Rollback procedure

The pre-#310 deployed AGENTS.md is preserved in git history (kitty merge
commit on main). If a defect surfaces during the soak:

1. Stop in-flight enrichment by withholding new delegations (no cron to
   disable — tasker is delegation-driven, so simply do not invoke it).
2. Revert the deployed AGENTS.md to the pre-#310 version. Find the commit:

   ```bash
   git log --oneline -- scripts/openclaw/agents/felix-admin-tasker/AGENTS.md | head -5
   ```

3. Copy the pre-#310 version to the deployed location:

   ```bash
   # On Mac, from the kg-automation checkout (replace <SHA> with the parent commit):
   git show <SHA>:scripts/openclaw/agents/felix-admin-tasker/AGENTS.md > /tmp/agents-pre-310.md
   scp /tmp/agents-pre-310.md office2-claude:/tmp/agents-pre-310.md
   ssh office2-claude 'cp /tmp/agents-pre-310.md /data/services/openclaw/tasker-agent/AGENTS.md && wc -c /data/services/openclaw/tasker-agent/AGENTS.md'
   ```

4. The agent resumes its pre-#310 behavior: direct Vikunja-comment writes via
   the old `Comment Write Procedure` section. The JSONL ledger remains on
   disk (no data loss); reads from it are abandoned, so the file ages-out
   harmlessly until v2.
5. Remove the cutover marker to allow a re-attempt later:

   ```bash
   ssh office2-claude 'rm ~/.config/openclaw/cutover-310.done'
   ```

The deployed SKILL.md is additive — leaving it in place is safe even after
rollback (the pre-#310 AGENTS.md also references it).

**Rollback trigger conditions** (from spec § Scenario F):

- A defect in `record_completion.py` causes Vikunja comments to land but
  JSONL writes silently corrupt
- Spurious re-proposals on `skipped` / `declined` tasks (the JSONL-canonical
  read returns the wrong state)
- Helper crash storm that blocks legitimate enrichment cycles

Isolated bugs that affect a single task do NOT trigger rollback — file a
P2-bug and triage via manual `operator_repair` JSONL records.

## Maintenance

### Query current enrichment state for a task

```bash
ssh office2-claude 'python3 -m scripts.enrichment.derive_state --task-id <task-id>'
```

Exit codes mirror the escalation pattern: `0` derived (JSON on stdout); `2`
JSONL read failure; `4` zero records for `task_id` (new task).

### Manual repair via operator_repair

When a JSONL record is missing or stale and Vikunja shows the correct state,
add a synthetic record:

```bash
ssh office2-claude 'python3 -m scripts.enrichment.record_completion \
  --task-id <id> --state <best-fit-state> --source operator_repair \
  --no-vikunja --note "manual triage <date>"'
```

The `--no-vikunja` flag suppresses the comment-write step (the JSONL row is
the only artifact). Use `--source operator_repair` so the record is
distinguishable from agent-originated writes in audits.

### Re-run reconcile during triage

If a backfill discrepancy surfaces (e.g., a historic comment that the initial
cutover backfill skipped due to a transient parse error), re-run reconcile:

```bash
ssh office2-claude 'cd /home/claude/kg-automation && PYTHONPATH=scripts python3 -m scripts.enrichment.reconcile_completions'
```

Idempotent — already-replayed comments are no-ops.

### Update agent workspace

To push a fresh AGENTS.md or SKILL.md without re-running the full cutover,
use the cutover script with `--force`:

```bash
ssh office2-claude 'cd /home/claude/kg-automation && git pull && PYTHONPATH=scripts python3 scripts/openclaw/helpers/cutover_tasker.py --force'
```

The `--force` flag overrides the existing marker; the marker is re-written
with a fresh `run_at_utc` timestamp.

## Troubleshooting

| Symptom | Check | Fix |
|---|---|---|
| `record_completion` exits 1 | Read stderr — Vikunja API unreachable or 401 | Verify token at `/data/services/openclaw/secrets/vikunja`; retry after Vikunja recovery |
| `record_completion` exits 0 with stderr warning | Read stderr — JSONL write failure (e.g., disk full) after Vikunja side-effect succeeded | Soft-fail per FR-013 — exit 0 means Vikunja is consistent; only the JSONL append failed. Agent continues; reconcile recovers the row later. |
| Duplicate state records for one task | `grep '"task_id": <id>' enrichment-history.jsonl` | Investigate dedup logic in `derive_state.py`; file P2-bug |
| Tasker re-proposes a `skipped` task | `derive_state.py --task-id <id>` and compare against the JSONL tail | Likely a JSONL parse bug; rollback per § Rollback procedure |
| Cutover script reports "already-done" but didn't run | `cat ~/.config/openclaw/cutover-310.done` | Pass `--force` to override the marker |
| AGENTS.md changes don't take effect | Tasker session is cached (systemPromptReport snapshots at session-init) | The tasker is delegation-driven and isolated — sessions are short-lived; no manual rotation needed |

## Privacy boundary

**Absolute rule**: `04-Growth/_private/` is never read, processed, routed
to, referenced, or logged. Tasks that originate from private context appear
as task titles only in proposals and JSONL records. This rule is enforced in
the tasker AGENTS.md (`Privacy — absolute rule` section) and in the inbox
processor that delegates to tasker. No exceptions.

(Path renumbered from `02-Growth/_private/` in mission 026 / #152. The
constitutional boundary itself is unchanged — only the parent folder ordinal
moved. See [Felix Constitution](<../constitution/FELIX-CONSTITUTION.md>) §
"Privacy Boundary".)

## Cross-references

- **Mission**: [#310](https://github.com/kentonium3/kg-automation/issues/310) — ADR-0002 Phase 7 (this migration; final phase)
- **Pattern source — escalation (Phase 6)**: [#309](https://github.com/kentonium3/kg-automation/issues/309); [`escalation-ops.md`](<./escalation-ops.md>)
- **AGENTS.md cut precedent — habits scripts-first port**: [#371](https://github.com/kentonium3/kg-automation/issues/371); [`habits-ops.md`](<./habits-ops.md>)
- **Spec**: [`spec.md`](../../kitty-specs/tasker-jsonl-migration-01KSB5XV/spec.md)
- **Plan + research**: [`plan.md`](../../kitty-specs/tasker-jsonl-migration-01KSB5XV/plan.md), [`research.md`](../../kitty-specs/tasker-jsonl-migration-01KSB5XV/research.md)
- **Contracts**: [`contracts/cli.md`](../../kitty-specs/tasker-jsonl-migration-01KSB5XV/contracts/cli.md)
- **Agent surface**: [`scripts/openclaw/agents/felix-admin-tasker/AGENTS.md`](../../scripts/openclaw/agents/felix-admin-tasker/AGENTS.md)
- **Skill**: [`scripts/openclaw/skills/task-intelligence/SKILL.md`](../../scripts/openclaw/skills/task-intelligence/SKILL.md)
- **Cutover script**: [`scripts/openclaw/helpers/cutover_tasker.py`](../../scripts/openclaw/helpers/cutover_tasker.py)
- **Enrichment module**: `scripts/enrichment/` (record_completion, reconcile_completions, derive_state, schema)
- **Pre-flight checklist**: [`governance/pre-flight-checklist.md`](<./governance/pre-flight-checklist.md>)
- **Task-intelligence skill ops**: [`task-intelligence-ops.md`](<./task-intelligence-ops.md>)
- **ADR**: [`docs/design/architecture/decisions/0002-state-log-migration.md`](../design/architecture/decisions/0002-state-log-migration.md)
