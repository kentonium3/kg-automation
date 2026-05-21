# Quickstart: Migrate escalation to JSONL state model

**Mission**: `migrate-escalation-to-jsonl-state-model-01KS5R4D`
**Audience**: Kent + future operators running the Phase 6 cutover and 3-day soak.

End-to-end procedure for backfill, cutover, soak verification, and rollback. Read top-to-bottom before executing.

---

## Pre-cutover preparation

Run from Mac (the repo is the source of truth; office2 receives a `git pull` for the new helpers).

### 1. Confirm risk-tier pre-flight (Tier 2)

Per `docs/runbooks/governance/pre-flight-checklist.md`:

- [ ] Restic backup within last 24 hours. If not, trigger one before any deploy.
- [ ] OpenClaw `felix-admin-escalation` agent identity verified as `felix-bot` (Vikunja) per `docs/design/architecture/identity-model.md`.
- [ ] No active escalation tick is in flight (check timer status: `systemctl --user --machine=office2-claude@ status escalation.timer`).

### 2. Verify scripts are present on office2

After PR merge to main, on office2:

```bash
ssh office2-claude
cd /home/claude/repos/kg-automation
git pull origin main
ls scripts/escalation/
# Expect: __init__.py, record_completion.py, reconcile_completions.py,
#         backfill_jsonl_from_comments.py, derive_state.py, schema.py
```

### 3. Confirm state directory + permissions

```bash
ssh office2-claude
sudo mkdir -p /data/services/openclaw/state/escalation
sudo chown claude:claude /data/services/openclaw/state/escalation
ls -la /data/services/openclaw/state/escalation/
# Should be empty, owned by claude:claude, mode 0755
```

(Per CLAUDE.md: the claude user does NOT have sudo. If the above sudo step is needed, stop and present the command for Kent to run via `ssh office2-kgale`.)

---

## Step 1 — Dry-run backfill (verify mapping correctness)

On office2 as `claude`:

```bash
cd /home/claude/repos/kg-automation
python3 -m scripts.escalation.backfill_jsonl_from_comments --all --dry-run
```

Expected output:

- Summary JSON at end with non-zero `comments_parsed` and matching `comments_replayed`.
- Zero or very few `comments_malformed`. Inspect each one — they will not be replayed in the real run.
- `snapshot_path` and `jsonl_path` shown (these are the destinations the real run will write to).

**Stop conditions**:
- High malformed-comment count (>5% of total). Triage before real run.
- Any task with zero parseable comments AND `done=false` AND in scope per the existing SKILL.md criteria — investigate why.

---

## Step 2 — Real backfill

```bash
python3 -m scripts.escalation.backfill_jsonl_from_comments --all
```

Expected:

- `snapshot_path` is created (~5-50 KB file).
- One `<project-slug>-escalation-history.jsonl` per escalation-active project.
- Same parsed/replayed counts as dry-run.

**Verify**:

```bash
ls -la /data/services/openclaw/state/escalation/
wc -l /data/services/openclaw/state/escalation/*.jsonl
head -2 /data/services/openclaw/state/escalation/everyday-escalation-history.jsonl
# Inspect a few records — confirm flat-enum state field, structured params
```

---

## Step 3 — Smoke-test derive_state on a known task

Pick a task that has at least one `level_sent` JSONL record:

```bash
python3 -m scripts.escalation.derive_state --task-id <id> --project-id <pid>
```

Expected: clean JSON output with sensible `current_state`, `next_eligible_level`, no exceptions.

Repeat for a snoozed task (verify `snooze_active_until` is in the future and `current_state` is `snoozed`).

---

## Step 4 — Update the OpenClaw agent (SKILL.md + AGENTS.md)

The new SKILL.md and AGENTS.md files were merged to main as part of this mission. Sync them to office2:

```bash
ssh office2-claude

# SKILL.md
cp /home/claude/repos/kg-automation/scripts/openclaw/skills/escalation/SKILL.md \
   /home/claude/.openclaw/skills/escalation/SKILL.md

# AGENTS.md
sudo cp /home/claude/repos/kg-automation/scripts/openclaw/agents/felix-admin-escalation/AGENTS.md \
   /data/services/openclaw/escalation-agent/AGENTS.md
```

(The sudo step on AGENTS.md needs Kent. The repo files are the source of truth; the office2 paths receive the synced copies.)

Verify:

```bash
grep -n "JSONL\|state_log\|derive_state" /data/services/openclaw/escalation-agent/AGENTS.md
# Should find references to the new helpers and JSONL state
grep -n "Felix-Escalation.*parse\|comment-parsing" /data/services/openclaw/escalation-agent/AGENTS.md
# Should return NOTHING (FR-007: stop in-prompt comment parsing)
```

---

## Step 5 — Trigger a manual escalation tick (verification before resumption)

Stop the timer first to avoid race:

```bash
systemctl --user --machine=office2-claude@ stop escalation.timer
```

Manually invoke the agent (via OpenClaw CLI or the cron's normal invocation path — see existing `docs/runbooks/escalation-ops.md` for the exact incantation).

Expected behavior:
- Agent reads JSONL via `derive_state`, NOT by parsing comments.
- Any qualifying tasks → Level N WhatsApp + record_completion call.
- record_completion writes both v1 `[Felix-Escalation]` comment AND JSONL record.

Spot-check:

```bash
tail -3 /data/services/openclaw/state/escalation/everyday-escalation-history.jsonl
# New record(s) should appear if any task was escalated this tick
```

---

## Step 6 — Resume the timer + begin 3-day soak

```bash
systemctl --user --machine=office2-claude@ start escalation.timer
systemctl --user --machine=office2-claude@ list-timers | grep escalation
```

Mark soak start date in `kitty-specs/migrate-escalation-to-jsonl-state-model-01KS5R4D/SOAK.md` (new file, freeform notes).

### Soak monitoring (each day)

```bash
# Tick success rate
journalctl --user --machine=office2-claude@ -u escalation.service --since "1 day ago" | grep -E "Started|Failed"

# JSONL growth
wc -l /data/services/openclaw/state/escalation/*.jsonl

# Open hard-fail bugs
gh issue list --repo kentonium3/kg-automation --label P2-bug --search "Escalation hard-fail" --state open

# Spurious re-alert check (the original 2026-05-16 incident class)
# Inspect WhatsApp history. Any Level N alert for a task Kent UI-resolved BEFORE the alert = regression. Stop and triage.
```

**Soak success gate** (per NFR-002, SC-006):
- ≥95% of escalation ticks complete with exit 0 over 3 days.
- Zero spurious re-alerts (test scenario: SC-002).
- Hard-fail count tracked but does NOT block the gate.

---

## Step 7 — Soak complete: declare Phase 6 done

After 3 days of successful soak:

1. Close issue #309 with a comment summarizing soak metrics.
2. File the follow-on issue: "Retire `felix-admin-escalation` OpenClaw agent + integrate priority/life-goals/time-context evolution" (the epic per scope decision 2026-05-21).
3. Stop the v1 comment write (remove the `[Felix-Escalation]` PUT in `record_completion.py` — this is the soak-end follow-on).

---

## Rollback procedure

If a regression appears during soak (spurious re-alerts, missing alerts, hard-fail epidemic):

### Step R1 — Stop the timer

```bash
systemctl --user --machine=office2-claude@ stop escalation.timer
```

### Step R2 — Restore v1 AGENTS.md

The pre-mission AGENTS.md is preserved via the spec-kitty merge commit history. Recover:

```bash
ssh office2-kgale

# Identify the parent of the mission's squash merge:
cd /home/claude/repos/kg-automation
git log --oneline --all | grep -m1 "mission-migrate-escalation"
# Note the commit hash. Its parent is pre-merge state.

# Restore AGENTS.md from pre-merge:
git show <parent-commit>:scripts/openclaw/agents/felix-admin-escalation/AGENTS.md > /tmp/AGENTS-v1.md
sudo cp /tmp/AGENTS-v1.md /data/services/openclaw/escalation-agent/AGENTS.md

# Restore SKILL.md the same way:
git show <parent-commit>:scripts/openclaw/skills/escalation/SKILL.md > /home/claude/.openclaw/skills/escalation/SKILL.md
```

### Step R3 — Verify rollback

```bash
grep -c "Felix-Escalation" /data/services/openclaw/escalation-agent/AGENTS.md
# Should be > 0 (v1 references comment vocabulary)
```

### Step R4 — Resume timer

```bash
systemctl --user --machine=office2-claude@ start escalation.timer
```

The JSONL files remain on disk (no destructive cleanup). They are inert under v1; the v1 path reads `[Felix-Escalation]` comments and writes nothing to JSONL. If the issue is later resolved, re-cutover by re-applying Step 4.

### Step R5 — File a follow-on bug

```bash
gh issue create --repo kentonium3/kg-automation \
  --title "Phase 6 rollback: <one-line cause>" \
  --label P1-bug,area/escalation \
  --body "<rollback reason + which step in soak triggered + JSONL state at rollback>"
```

This becomes the input to triage the regression before re-attempting cutover.

---

## Cross-references

- Pre-flight checklist: `docs/runbooks/governance/pre-flight-checklist.md`
- Post-change verification: `docs/runbooks/governance/post-change-verification.md`
- Existing escalation ops: `docs/runbooks/escalation-ops.md` (this mission may revise it)
- Phase 5 cutover precedent: `kitty-specs/habits-cutover-to-jsonl-v2-flow-01KS1FKE/quickstart.md`
- Spec: success criteria SC-001..SC-007; NFR-002 (95% gate)
