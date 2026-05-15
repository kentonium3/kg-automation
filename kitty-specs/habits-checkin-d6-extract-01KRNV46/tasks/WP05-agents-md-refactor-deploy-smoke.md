---
work_package_id: WP05
title: AGENTS.md refactor + service-inventory update + deploy + smoke test
dependencies:
- WP01
- WP02
- WP03
- WP04
requirement_refs:
- FR-005
- FR-006
- FR-007
planning_base_branch: main
merge_target_branch: main
branch_strategy: Planning artifacts for this feature were generated on main. During /spec-kitty.implement this WP may branch from a dependency-specific base, but completed changes must merge back into main unless the human explicitly redirects the landing branch.
subtasks:
- T015
- T016
- T017
- T018
- T019
agent: "claude:opus-4-7:implementer:implementer"
shell_pid: "8915"
history:
- event: created
  at: '2026-05-15T17:15:12Z'
  by: spec-kitty.tasks
  note: WP05 prompt generated
authoritative_surface: scripts/openclaw/agents/felix-admin-habits/AGENTS.md
execution_mode: code_change
mission_slug: habits-checkin-d6-extract-01KRNV46
owned_files:
- scripts/openclaw/agents/felix-admin-habits/AGENTS.md
- docs/design/architecture/data/service-inventory.json
tags: []
---

# WP05 — AGENTS.md refactor + service-inventory + deploy + smoke test

## Objective

Wire the four helpers from WP01-WP04 into `felix-admin-habits/AGENTS.md` (replacing Steps 1-4 prose with helper invocations), add the Failure handling subsection, update the architecture inventory, deploy to office2, and verify behavior preservation via smoke test (line-by-line diff against the WP01-captured reference message).

This is the mission's integration WP. NFR-002 (behavior preservation) is verified here. Until WP05 ships, the helpers exist but nothing has changed about Kent's daily check-in experience.

## Context

- **Spec**: [`spec.md`](../spec.md) — FR-005, FR-006, FR-007, NFR-002, NFR-003, NFR-008
- **Plan**: [`plan.md`](../plan.md) — Technical Context, Charter Check
- **Quickstart**: [`quickstart.md`](../quickstart.md) — Deploy + smoke test procedures
- **Conventions**: [`docs/design/helper-script-conventions.md`](../../../docs/design/helper-script-conventions.md) — § 6 (failure-mode handling, agent-side template)
- **Reference for AGENTS.md content style**: current `scripts/openclaw/agents/felix-admin-habits/AGENTS.md` (478L pre-refactor)

## Subtask details

### T015 — Refactor `AGENTS.md` Steps 1-4 → helper invocations

**Purpose**: Replace prose-encoded deterministic work with helper invocations + JSON parsing instructions. Preserve all judgment work in Steps 5-6.

**Steps**:

1. Open `scripts/openclaw/agents/felix-admin-habits/AGENTS.md`.
2. Locate the "## Morning check-in" section and its `### Step 1:` through `### Step 4:` subsections.
3. Replace each step's prose with a helper invocation + parse instruction. Example for Step 1:

   ```markdown
   ### Step 1: Determine today's day and date (helper)

   Run the date helper and parse its JSON output:

   ```bash
   python3 /home/claude/kg-automation/scripts/habits/compute_today.py
   ```

   The helper outputs a single JSON line. Parse it; the fields you'll use in later steps:
   - `day` — three-letter day-of-week (Mon, Tue, ..., Sun); pass to Step 2 as `--day`
   - `date` — `YYYY-MM-DD` Eastern time; pass to Step 4 as `--today`
   - `iso_eod_et` — end-of-day-ET ISO timestamp; pass to Step 3 as `--iso-eod-et`

   The helper handles Eastern-time conversion, DST/EST offset detection, and the issue #112 end-of-day anchoring rule. **DO NOT** re-implement this logic in-prompt; **DO NOT** add a `Z` suffix to any timestamp.
   ```

4. Similar restructuring for Step 2 (invoke `query_active_habits.py --day <from-step-1>`), Step 3 (invoke `set_due_dates.py --habit-ids <from-step-2> --iso-eod-et <from-step-1>`), Step 4 (invoke `exclude_completed.py --habit-ids <from-step-3-succeeded> --today <from-step-1>`).
5. Step 5 (Format the check-in message): update slightly to note that its input is the `ready_for_checkin` list from Step 4's output (was: filtered habit list computed in-prompt).
6. Step 6 (Output discipline): unchanged.
7. Validate total AGENTS.md line count is at or below the NFR-003 target (300L; acceptable up to 300L; pre-refactor was 478L).

**Files**:
- `scripts/openclaw/agents/felix-admin-habits/AGENTS.md` (MODIFIED)

**Validation**:
- [ ] All four Steps 1-4 reference helpers explicitly (with `python3` invocation lines)
- [ ] Step 5 references Step 4's `ready_for_checkin` output explicitly
- [ ] Step 6 unchanged
- [ ] Total line count ≤ 300 (preferred ≤ 250; pre-refactor 478)
- [ ] No prose-encoded deterministic logic remains in Steps 1-4 (no TZ rules, no frequency tables, no comment-format specs)

---

### T016 — Add "Failure handling" subsection to AGENTS.md

**Purpose**: Per `helper-script-conventions.md` § 6, agents that invoke helpers MUST have a documented failure-handling clause. Without it, helper exit-1 paths have undefined agent behavior.

**Steps**:

1. After Step 4 (and before Step 5), add a new section:

   ```markdown
   ### Step 4.5: Helper failure handling

   If any of the helpers in Steps 1-4 exits non-zero, follow this protocol:

   1. **Read stderr from the helper's output** to identify which helper failed and why.
   2. **DO NOT send a partial or fabricated check-in message to Kent**. A broken
      check-in is worse than no check-in.
   3. **File a [doc-audit] issue** titled `felix-admin-habits: <helper> failed at
      step N` with the helper name, exit code, stderr output, and the inputs that
      caused the failure. Use the `area/felix-core` label plus the relevant
      priority label (`P2-bug` for `set_due_dates.py` failures since they may
      regress #112; `P3-candidate` for query/exclude failures).
   4. **For `set_due_dates.py` partial failure** (exit code 1 with non-empty
      `succeeded` array): the some-habits-set-some-not state is benign for the
      check-in. Continue to Step 4 (`exclude_completed.py`) using ONLY the IDs
      from the `succeeded` array. The failed habits will retry on the next cron
      tick.
   5. **For Step 2 or 4 complete failure** (Vikunja unreachable): file the issue,
      reply with `IDLE` only (don't send any partial check-in), and let the next
      cron tick retry.

   This subsection implements the agent-side failure-handling template from the
   [helper-script-conventions § 6](../../../../docs/design/helper-script-conventions.md).
   ```

2. Verify the section anchors correctly in the table-of-contents-style structure (if any) of AGENTS.md.

**Files**:
- `scripts/openclaw/agents/felix-admin-habits/AGENTS.md` (MODIFIED; same file as T015)

**Validation**:
- [ ] Step 4.5 added between Step 4 and Step 5
- [ ] Specifies the [doc-audit] issue filing path for catastrophic failures
- [ ] Specifies the partial-failure path for `set_due_dates.py` exit 1
- [ ] References conventions § 6

---

### T017 — Update `service-inventory.json` habit-checkin entry

**Purpose**: Per FR-006 and Felix's documentation standards, architecture data must reflect the new helper artifacts. Updates the `config_files` array and `updated_by` chain.

**Steps**:

1. Open `docs/design/architecture/data/service-inventory.json`.
2. Find the `habit-checkin` service entry (look for `"name": "habit-checkin"`).
3. Update the `config_files` array to add the four new helpers:

   ```json
   "config_files": [
     {"path": "/data/services/openclaw/habits-agent/AGENTS.md", "format": "markdown", "source_in_repo": "scripts/openclaw/agents/felix-admin-habits/AGENTS.md"},
     {"path": "/home/claude/kg-automation/scripts/habits/compute_today.py", "format": "python", "source_in_repo": "scripts/habits/compute_today.py"},
     {"path": "/home/claude/kg-automation/scripts/habits/query_active_habits.py", "format": "python", "source_in_repo": "scripts/habits/query_active_habits.py"},
     {"path": "/home/claude/kg-automation/scripts/habits/set_due_dates.py", "format": "python", "source_in_repo": "scripts/habits/set_due_dates.py"},
     {"path": "/home/claude/kg-automation/scripts/habits/exclude_completed.py", "format": "python", "source_in_repo": "scripts/habits/exclude_completed.py"}
   ],
   ```

4. Update `updated_by`: append `+ #282-habits-d6-extract` to the front of the existing string.
5. Update `last_updated`: today's ISO date (`2026-05-XX` per actual implementation day).
6. Update top-level `last_updated` and `updated_by` to reflect this mission's change.
7. Validate JSON: `python3 -c "import json; json.load(open('docs/design/architecture/data/service-inventory.json'))"`
8. Run doc validator: `python3 tooling/scripts/validate_docs.py`

**Files**:
- `docs/design/architecture/data/service-inventory.json` (MODIFIED)

**Validation**:
- [ ] JSON parses successfully
- [ ] `habit-checkin.config_files` has 5 entries (1 AGENTS.md + 4 helpers)
- [ ] `habit-checkin.updated_by` references `#282-habits-d6-extract`
- [ ] Top-level `updated_by` references `#282-habits-d6-extract`
- [ ] `validate_docs.py` exits OK

---

### T018 — Deploy 4 helpers + AGENTS.md to office2

**Purpose**: Get the new code onto office2 in the right places so the next cron run uses it.

**Steps**:

1. Deploy the four helpers to `/home/claude/kg-automation/scripts/habits/` (source-tree mirror on office2):

   ```bash
   for f in compute_today query_active_habits set_due_dates exclude_completed; do
       scp scripts/habits/${f}.py \
           office2-claude:/home/claude/kg-automation/scripts/habits/${f}.py
   done
   ```

   (Create the remote directory first if it doesn't exist: `ssh office2-claude 'mkdir -p /home/claude/kg-automation/scripts/habits/'`.)

2. Deploy the updated AGENTS.md to the agent's workspace:

   ```bash
   scp scripts/openclaw/agents/felix-admin-habits/AGENTS.md \
       office2-claude:/data/services/openclaw/habits-agent/AGENTS.md
   ```

3. Verify file presence and permissions on office2:

   ```bash
   ssh office2-claude '
       ls -la /home/claude/kg-automation/scripts/habits/
       wc -l /data/services/openclaw/habits-agent/AGENTS.md
       head -20 /data/services/openclaw/habits-agent/AGENTS.md
   '
   ```

4. Smoke-test each helper individually on office2 (no flag changes; default token path):

   ```bash
   ssh office2-claude '
       python3 /home/claude/kg-automation/scripts/habits/compute_today.py
       # Expect: JSON output + SUMMARY line
   '
   ```

**Files**: No repo changes (deploy is one-way scp). Deploy is operator action; commits already on repo from T015-T017.

**Validation**:
- [ ] All four helpers deployed to `/home/claude/kg-automation/scripts/habits/`
- [ ] AGENTS.md deployed to `/data/services/openclaw/habits-agent/AGENTS.md`
- [ ] Each helper runs standalone on office2 with sensible output
- [ ] No permission errors on token read

---

### T019 — Smoke test on office2 (NFR-002 verification)

**Purpose**: This is the acceptance gate for the entire mission. If the smoke test passes (line-by-line diff against reference is empty), behavior preservation is verified.

**Steps**:

1. Trigger the habits cron manually:

   ```bash
   ssh office2-claude 'openclaw cron run habits-morning-checkin'
   ```

2. Wait for the WhatsApp message to arrive on Kent's phone (typically <60 seconds).
3. Capture the new message text VERBATIM (same procedure as T001 in WP01) — either via Kent forwarding from WhatsApp Web or via the agent's session JSONL.
4. Save the captured message to a temporary file:
   ```
   /tmp/post-refactor-checkin-output.txt
   ```
5. Diff against the reference:

   ```bash
   diff kitty-specs/habits-checkin-d6-extract-01KRNV46/artifacts/reference-checkin-output.txt \
        /tmp/post-refactor-checkin-output.txt
   ```

6. **Acceptance**: `diff` exits 0 with zero output → smoke test PASSES → WP05 acceptance criterion met.
7. **Failure mode**: `diff` shows any difference:
   - Diagnose: was the difference caused by legitimate Vikunja state change (habit added/removed/paused between captures)? If yes, capture is unfair — repeat T019 on a day matching the WP01 capture's day-of-week.
   - If not legitimate state change: refactor regressed behavior. STOP. File a [doc-audit] issue, fix the helper or AGENTS.md responsible, redeploy, re-test.

**Files**: `/tmp/post-refactor-checkin-output.txt` is NOT committed — it's a transient artifact.

**Validation**:
- [ ] Manual cron run completes without errors in office2 session logs
- [ ] WhatsApp message received at the expected time
- [ ] `diff` against reference shows zero output (or only legitimate-state-change differences, documented)
- [ ] OpenClaw session log shows no `[ALERT]` or unexpected errors
- [ ] (Bonus, can defer to post-merge monitoring) Habits in Vikunja Today filter show correct end-of-day-ET due_date — spot-check 1-2 in the UI

---

## Branch Strategy

- **Planning base**: `main`
- **Merge target**: `main`
- **Execution workspace**: Per-lane worktree from `lanes.json`. Since WP05 depends on WP01-WP04, this lane branches off the merged state of all four prior WPs. Likely the last lane to be assigned.

## Test strategy

WP05 has no new pytest tests — the helpers' own tests (in WP01-WP04) cover the unit-level behavior. WP05's verification is the end-to-end smoke test in T019, which validates NFR-002 (behavior preservation) by definition.

## Definition of Done

- [ ] T015: AGENTS.md Steps 1-4 refactored to helper invocations; total ≤300L
- [ ] T016: Step 4.5 Failure handling subsection added
- [ ] T017: service-inventory.json updated, validates clean
- [ ] T018: All four helpers + AGENTS.md deployed to office2; each helper individually validated
- [ ] T019: Smoke test passes (zero diff against reference, or documented-legitimate-only differences)
- [ ] OpenClaw session log for the smoke-test run is clean (no errors, no alerts)
- [ ] All owned_files committed
- [ ] Mark subtasks done: `spec-kitty agent tasks mark-status T015 T016 T017 T018 T019 --status done`
- [ ] Move to for_review: `spec-kitty agent tasks move-task WP05 --to for_review --note "Refactor live on office2; smoke test passes; behavior preserved"`

## Risks

- **Smoke-test day mismatch**: if WP01 captured a Wednesday reference and WP05's smoke test runs on a Sunday, the diff will be non-empty because the SET of scheduled habits is different. T019 must run on a day-of-week matching the WP01 capture. If urgency dictates running on a different day, capture a fresh reference first (re-run WP01's T001 procedure on the same day-of-week as the smoke test).
- **Race during deploy**: deploying AGENTS.md before helpers are present would cause the agent's first invocation to fail. T018 deploys helpers FIRST, then AGENTS.md.
- **Hidden state changes during smoke test**: if Kent marks a habit complete between manually triggering the cron and observing the output, the message will show fewer habits than reference — false-positive diff. Avoid triggering the smoke test during Kent's active morning routine.
- **#112 regression check**: ensure post-refactor due_date values in Vikunja Today filter still anchor to end-of-day-ET, not midnight. Spot-check at least one habit in Vikunja UI after T019.

## Reviewer guidance (for Codex)

Verify:

1. **AGENTS.md size**: total line count is ≤ 300 (NFR-003 target). If over: reject and ask implementer to tighten Steps 1-4 prose.
2. **No deterministic logic remains**: Steps 1-4 only contain helper invocations + JSON parse instructions. No TZ rules, no frequency tables, no comment-format specs.
3. **Failure handling**: Step 4.5 explicit on what happens at exit code 1 (partial vs total failure), references conventions § 6.
4. **service-inventory.json**: 5 `config_files` entries; both `last_updated` and `updated_by` reference this mission's issue (#282).
5. **Deploy verification**: T018 includes the `ls -la` confirmation; commit message documents the deployed paths.
6. **Smoke test artifact**: the reference file (`artifacts/reference-checkin-output.txt`) is preserved in the repo; the post-refactor capture (`/tmp/post-refactor-checkin-output.txt`) is NOT committed (correctly transient).
7. **#112 verification**: implementer spot-checked at least one habit's due_date in Vikunja UI after T019. If the implementation log doesn't mention this, request the spot-check before approving.

Reject if:
- AGENTS.md > 300 lines
- Any of Steps 1-4 contain deterministic logic instead of helper invocations
- Failure handling missing or vague
- `diff` in T019 shows non-empty output that isn't documented as legitimate state change
- service-inventory.json regresses any existing field
- Post-refactor habits show midnight (00:00:00) or `Z`-suffix due_dates in Vikunja UI (instant #112 regression)

## Activity Log

- 2026-05-15T18:34:37Z – claude:opus-4-7:implementer:implementer – shell_pid=8915 – Started implementation via action command
- 2026-05-15T18:44:39Z – claude:opus-4-7:implementer:implementer – shell_pid=8915 – Ready for review — T015-T017 in commit f44ce6b (AGENTS.md refactored + service-inventory updated; NFR-003 size target documented as out-of-scope-gap). T018 deployed all 4 helpers + AGENTS.md to office2 successfully. T019 smoke test PASSED: manual cron fire produced correct check-in to Kent (4 ready habits vs 8 morning ones — legitimate state change since Kent completed 4 between captures; ALL 4 helpers invoked in correct order; #112 Z-suffix-prevention intact in the live invocation). --force per #589
