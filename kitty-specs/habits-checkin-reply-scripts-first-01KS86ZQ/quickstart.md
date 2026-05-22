# Quickstart: Habits check-in + reply scripts-first port

**Mission**: `habits-checkin-reply-scripts-first-01KS86ZQ`
**Audience**: Kent + future operators running the cutover for #371.

End-to-end procedure for cutover, manual verification, and rollback. Cron is currently DISABLED on office2; the cutover ends with re-enabling it.

---

## Pre-cutover preparation

### 1. Tier 2 pre-flight

- [ ] Restic backup within last 24 hours. If not, trigger one before any deploy.
- [ ] Confirm habits-morning-checkin cron is DISABLED:
  ```bash
  ssh office2-claude 'openclaw cron list 2>&1 | grep habits-morning-checkin'
  # Expect: NO output (cron removed from list while disabled)
  # OR explicit "disabled" status in the row
  ```
- [ ] Confirm no escalation-related changes will conflict (this mission touches only `scripts/habits/`, `scripts/openclaw/agents/felix-admin-habits/AGENTS.md`, `docs/runbooks/habits-ops.md`, and `docs/design/architecture/data/*.json`).

### 2. Verify mission code on office2 post-merge

After mission #371's merge commit lands on origin/main, on office2:

```bash
ssh office2-claude
cd /home/claude/kg-automation
git pull origin main
ls scripts/habits/morning_checkin_list.py scripts/habits/parse_morning_reply.py scripts/habits/judgment/disambiguate_reply.py
# Expect: all three present
```

### 3. Confirm state directory + permissions

```bash
ssh office2-claude
mkdir -p /data/services/openclaw/state/habits
ls -ld /data/services/openclaw/state/habits
# Expect: drwxr-sr-x claude:secondbrain (or felix-group writable)
```

If sudo is required to create the dir: stop and present the command to Kent for manual execution via `ssh office2-kgale` per CLAUDE.md.

---

## Step 1 — Dry-run smoke-test the morning-list helper

```bash
ssh office2-claude 'cd /home/claude/kg-automation && python3 -m scripts.habits.morning_checkin_list --dry-run'
```

Expected:
- Stdout: a properly-formatted WhatsApp check-in message with N numbered habits.
- Exit code 0.
- NO file written to `/data/services/openclaw/state/habits/`.

**Stop conditions**:
- Exit non-zero → triage; do NOT proceed to cutover.
- Habits list is unexpectedly empty AND today's date isn't a weekend / holiday → triage (Vikunja query may be misfiltering).

---

## Step 2 — Real morning-list emission (writes artifact)

```bash
ssh office2-claude 'cd /home/claude/kg-automation && python3 -m scripts.habits.morning_checkin_list'
```

Expected:
- Stdout: same formatted message.
- File created at `/data/services/openclaw/state/habits/morning-checkin-<today-local-date>.json`.
- Schema matches `data-model.md` Entity 1.

**Verify the artifact**:

```bash
ssh office2-claude 'cat /data/services/openclaw/state/habits/morning-checkin-$(TZ=America/New_York date +%Y-%m-%d).json | python3 -m json.tool'
```

---

## Step 3 — Smoke-test the parser with a synthetic reply

Use the day's emitted morning list:

```bash
ssh office2-claude 'cd /home/claude/kg-automation && python3 -m scripts.habits.parse_morning_reply --reply "1 done"'
```

Expected:
- Stdout: JSON with `tuples: [{task_id: <id-of-position-1>, state: "complete", matched_via: "position", position: 1}]`.
- `judgment_required: []`, `errors: []`.
- Exit code 0.

Try an ambiguous reply too:

```bash
ssh office2-claude 'cd /home/claude/kg-automation && python3 -m scripts.habits.parse_morning_reply --reply "PT done"'
```

Expected (assuming today's list has 2+ habits matching "PT"):
- `tuples: []`
- `judgment_required: [{token: "PT", candidate_task_ids: [...], candidate_titles: [...], inferred_state: "complete"}]`
- Exit code 0.

---

## Step 4 — Smoke-test the disambiguator

Pipe the previous step's `judgment_required` item into the disambiguator:

```bash
ssh office2-claude 'cat <<EOF | python3 -m scripts.habits.judgment.disambiguate_reply
{
  "schema_version": 1,
  "reply_text": "PT done",
  "ambiguity": {
    "token": "PT",
    "candidate_task_ids": [19, 16, 17],
    "candidate_titles": ["Morning shoulder PT", "Evening shoulder PT", "Morning hip PT"],
    "inferred_state": "complete"
  }
}
EOF
'
```

Expected: JSON output with `result: "chosen"` and a `chosen_task_id` from the candidate set, OR `result: "clarify"` with a `suggested_question`. Either is acceptable.

---

## Step 5 — Deploy the new AGENTS.md

The new AGENTS.md was merged to main as part of this mission. Sync to the deployed workspace:

```bash
ssh office2-claude
diff /home/claude/kg-automation/scripts/openclaw/agents/felix-admin-habits/AGENTS.md \
     /data/services/openclaw/habits-agent/AGENTS.md
# Expect: large diff — the old version is being replaced
```

Take a snapshot of the current deployed version BEFORE overwriting (rollback safety):

```bash
ssh office2-claude 'cp /data/services/openclaw/habits-agent/AGENTS.md /tmp/habits-agents-pre-371.md.bak'
```

Then deploy:

```bash
ssh office2-claude 'cp /home/claude/kg-automation/scripts/openclaw/agents/felix-admin-habits/AGENTS.md /data/services/openclaw/habits-agent/AGENTS.md'
```

**Verify char count**:

```bash
ssh office2-claude 'wc -c /data/services/openclaw/habits-agent/AGENTS.md'
# Expect: ≤14000 (target per FR-011)
```

If wc -c exceeds 14,000: STOP. Restore from `/tmp/habits-agents-pre-371.md.bak`. File a follow-on issue noting the cut didn't meet target.

---

## Step 6 — Manual cron tick (single one-off)

```bash
ssh office2-claude 'openclaw cron run 3082343c-bc7f-47ee-916b-ee070b1e50dc'
```

Watch journalctl:

```bash
ssh office2-claude 'journalctl --user -u openclaw-gateway.service --since "1 minute ago" -f | grep -E "habits|truncat|error"'
```

**Verify**:
- NO `truncating in injected context` warning for habits-agent's AGENTS.md (per NFR-004).
- The helper invocation appears in the log (`python3 -m scripts.habits.morning_checkin_list ...`).
- The morning-list artifact file exists for today's date.
- The agent's final reply is the helper's stdout verbatim (the formatted WhatsApp message).

If you got a truncation warning: STOP. Restore AGENTS.md from `/tmp/habits-agents-pre-371.md.bak`. Investigate.

If the helper isn't invoked: STOP. The agent prompt cut may have removed essential orchestration instructions. Restore and investigate.

---

## Step 7 — Simulated reply (controlled test)

Send a reply via WhatsApp (or OpenClaw's reply path) using known reply text — e.g., `"1 done"`.

Verify:

```bash
# Inspect the habits JSONL log for today
ssh office2-claude 'tail -5 /data/services/openclaw/state/habits-history.jsonl'
# Expect: one new entry with task_id matching position 1 from today's morning list, state=complete

# Inspect the agent's reply (via journalctl or WhatsApp history)
# Expect: short confirmation message; no errors
```

If the recorded task_id doesn't match position 1's task_id in the morning artifact: STOP. The integration is broken. Rollback.

---

## Step 8 — Re-enable the cron

```bash
ssh office2-claude 'openclaw cron enable 3082343c-bc7f-47ee-916b-ee070b1e50dc'
ssh office2-claude 'openclaw cron list | grep habits-morning-checkin'
# Expect: the cron appears with normal scheduling
```

Mark cutover complete:

```bash
gh issue comment 371 --repo kentonium3/kg-automation --body "Cutover complete <commit-hash>. Re-enabled cron $(date -u +%Y-%m-%dT%H:%M:%SZ). Next firing: tomorrow 7:05 AM ET. Manual tick verification passed; helper invocation visible in journal; no truncation warning; recorded task_id matched position 1 of the artifact."
```

---

## Step 9 — Tomorrow morning's first real tick

7:05 AM ET 2026-05-23 (or the next morning after cutover):

1. Kent observes the WhatsApp check-in message.
2. Kent sends a reply (real or test).
3. After ~30 minutes, verify the recorded JSONL matches Kent's intent:
   ```bash
   ssh office2-claude 'tail -10 /data/services/openclaw/state/habits-history.jsonl | python3 -m json.tool'
   ```
4. Cross-check against the morning artifact:
   ```bash
   ssh office2-claude 'cat /data/services/openclaw/state/habits/morning-checkin-$(TZ=America/New_York date +%Y-%m-%d).json | python3 -m json.tool'
   ```
5. Each recorded `task_id` in the JSONL should match the `vikunja_task_id` at the corresponding `position` in the artifact for the habits Kent referenced.

If verified clean: declare #371 fix successful. Close the issue with the cutover commit hash.

---

## Rollback procedure

If any cutover step fails:

### Step R1 — Disable cron

```bash
ssh office2-claude 'openclaw cron disable 3082343c-bc7f-47ee-916b-ee070b1e50dc'
```

### Step R2 — Restore previous AGENTS.md

```bash
ssh office2-claude 'cp /tmp/habits-agents-pre-371.md.bak /data/services/openclaw/habits-agent/AGENTS.md'
```

### Step R3 — Optionally revert the merge

If the helper scripts themselves are buggy (not just the AGENTS.md cut), revert the merge on Mac and re-push:

```bash
# On Mac, from main
git revert <merge-commit-hash> --no-edit
git push origin main

# Then on office2
ssh office2-claude 'cd /home/claude/kg-automation && git pull origin main'
```

The rollback leaves Kent's habit logging in the same broken state as before #371 — i.e., the original bug returns. Kent logs habits manually until the next fix attempt.

### Step R4 — File follow-on

```bash
gh issue create --repo kentonium3/kg-automation \
  --title "Bug: habits #371 cutover failed at step <N>" \
  --label P1-bug,area/task-intel,spec: brief \
  --body "Rollback details + next steps"
```

---

## Cross-references

- Spec FR-001 through FR-011 + SC-001 through SC-008
- Research D11 (cutover sequence — this doc is the verbatim execution of it)
- Phase 5 cutover precedent: `kitty-specs/habits-cutover-to-jsonl-v2-flow-01KS1FKE/quickstart.md`
- Mission #309 cutover precedent: `kitty-specs/migrate-escalation-to-jsonl-state-model-01KS5R4D/quickstart.md`
- Soak template: not used for this mission (smaller scope; one-tick verification is sufficient)
