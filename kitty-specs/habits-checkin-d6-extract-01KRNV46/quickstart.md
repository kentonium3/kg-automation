# Quickstart — habits-checkin-d6-extract

How to develop, test, deploy, and verify the four new helpers locally and on office2.

---

## Local development

### Prerequisites

- Python 3.11+
- pytest installed (`pip install pytest` if not already)
- No third-party HTTP libraries needed (`urllib.request` is stdlib)
- For local Vikunja-touching runs against the real instance: SSH access to office2 to read `/data/services/openclaw/secrets/vikunja-api` (or set `--vikunja-token-path` to a local copy)

### Running an individual helper locally (against the real Vikunja API on office2)

```bash
# Step 1: compute today's context
python3 scripts/habits/compute_today.py
# {"day": "Wed", "date": "2026-05-15", "et_offset": "-04:00", "iso_eod_et": "2026-05-15T23:59:59-04:00"}
# SUMMARY: day=Wed date=2026-05-15 et_offset=-04:00

# Step 2: query habits scheduled for today
python3 scripts/habits/query_active_habits.py --day Wed \
    --vikunja-token-path ~/.config/felix/vikunja-test-token  # or your local copy

# Step 3 (DRY-RUN — don't actually mutate Vikunja during development):
python3 scripts/habits/set_due_dates.py --habit-ids 123,124 \
    --iso-eod-et 2026-05-15T23:59:59-04:00 --dry-run

# Step 4: exclude already-completed
python3 scripts/habits/exclude_completed.py --habit-ids 123,124 --today 2026-05-15
```

Always use `--dry-run` on `set_due_dates.py` during local development unless deliberately testing the production mutation path. Never POST/PUT to production Vikunja from a local development run without explicit intent.

### Running the test suite

```bash
# From repo root
pytest tests/habits/ -v

# Or just one module
pytest tests/habits/test_compute_today.py -v
```

Tests should pass with no Vikunja access required — all API interactions are mocked via `unittest.mock`.

---

## Deploy to office2

Manual `scp` per [conventions § 10](../../docs/design/helper-script-conventions.md) (no deploy automation in scope for this mission):

```bash
# 1. Deploy all four helpers
for f in compute_today query_active_habits set_due_dates exclude_completed; do
    scp scripts/habits/${f}.py office2-claude:/home/claude/kg-automation/scripts/habits/${f}.py
done

# 2. Deploy the updated AGENTS.md
scp scripts/openclaw/agents/felix-admin-habits/AGENTS.md \
    office2-claude:/data/services/openclaw/habits-agent/AGENTS.md

# 3. Verify deployment
ssh office2-claude 'ls -la /home/claude/kg-automation/scripts/habits/ && wc -l /data/services/openclaw/habits-agent/AGENTS.md'
```

Note: `/data/services/openclaw/habits-agent/` is the agent's workspace; `/home/claude/kg-automation/` is the source-tree mirror. The deployed AGENTS.md references helpers at the source-tree path.

---

## Smoke test (verifies NFR-002 behavior preservation)

### Step 1 — Capture pre-refactor reference message (FIRST task of WP01, BEFORE any code changes)

```bash
# On office2, trigger the current Sonnet-driven habits cron manually
ssh office2-claude 'openclaw cron run habits-morning-checkin'

# Wait for the WhatsApp to arrive on Kent's phone. Manually capture:
# 1. The message text (Kent: forward it via WhatsApp web or screenshot+OCR)
# 2. The agent's session log from /home/claude/.openclaw/agents/felix-admin-habits/sessions/

# Save the message text to kitty-specs/habits-checkin-d6-extract-01KRNV46/artifacts/reference-checkin-output.txt
# Commit the artifact to the mission's directory
```

### Step 2 — Implement the mission (helpers + tests + AGENTS.md refactor + inventory update)

Performed across multiple WPs per `/spec-kitty.tasks` decomposition. See spec.md FR-001 through FR-007 for the scope.

### Step 3 — Deploy refactored helpers + AGENTS.md to office2

(per "Deploy to office2" section above)

### Step 4 — Post-refactor smoke test

```bash
# Trigger the refactored habits cron manually on office2
ssh office2-claude 'openclaw cron run habits-morning-checkin'

# Wait for WhatsApp; capture the new message text the same way as Step 1
# Save to a separate file: post-refactor-checkin-output.txt (NOT committed; just for the diff)

# Diff against the reference
diff kitty-specs/habits-checkin-d6-extract-01KRNV46/artifacts/reference-checkin-output.txt \
     /tmp/post-refactor-checkin-output.txt
```

### Acceptance criterion (NFR-002)

`diff` exits 0 (zero lines of difference) → smoke test passes.

`diff` shows any difference → smoke test FAILS. Refactor regressed behavior. Either:
- Fix the helper/AGENTS.md and re-run
- If the difference is **acceptable** (e.g., Vikunja added a new habit between captures), explicitly document the cause and re-run the test once the state is stable

**Do NOT** merge until the diff is empty against a same-day-class reference. (If reference was a Wednesday, post-refactor run must also be a Wednesday for a fair diff.)

### Step 5 — First scheduled production run validation

After deploy, wait for the next scheduled daily run at 7:05 AM ET. Verify:

1. Kent received a WhatsApp check-in at the expected time
2. OpenClaw session log shows no errors
3. Habits in Vikunja's "Today" filter have correct end-of-day-ET `due_date` (spot-check 1-2)
4. No `[doc-audit]` issues filed by `felix-doc-auditor` overnight (drift signal)

If all four checks pass, the refactor is operationally validated. Sonnet → Haiku follow-up mission is unblocked.

---

## Rollback

If smoke test or production run reveals behavior regression:

```bash
# 1. Revert the commit(s) that landed the refactor
git revert <commit-sha>
git push origin main

# 2. Re-deploy the pre-refactor AGENTS.md to office2
scp scripts/openclaw/agents/felix-admin-habits/AGENTS.md \
    office2-claude:/data/services/openclaw/habits-agent/AGENTS.md

# 3. The new helpers in scripts/habits/ on office2 can stay
# (they're unused once AGENTS.md is reverted; no harm in leaving)

# 4. Verify rollback with another manual cron run
ssh office2-claude 'openclaw cron run habits-morning-checkin'
```

Rollback restores prior Sonnet-driven behavior. Diagnose the regression at the laptop; ship a fix as a follow-up commit.

---

## Cross-references

- [`plan.md`](./plan.md) — Implementation plan summary + Technical Context
- [`research.md`](./research.md) — Phase 0 research findings (auth source, HTTP library, test patterns)
- [`data-model.md`](./data-model.md) — Entities + frequency lexicon + output envelopes
- [`contracts/`](./contracts/) — Per-helper CLI + I/O contracts
- [`spec.md`](./spec.md) — FR/NFR/Constraints + acceptance criteria
- [`docs/design/helper-script-conventions.md`](../../docs/design/helper-script-conventions.md) — Operational conventions all helpers follow
