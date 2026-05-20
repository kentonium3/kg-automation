---
work_package_id: WP09
title: Cutover execution and post-rework measurement
dependencies:
- WP06
- WP07
- WP08
requirement_refs:
- FR-010
planning_base_branch: main
merge_target_branch: main
branch_strategy: Planning artifacts were generated on main; completed changes must merge back into main.
subtasks:
- T040
- T041
- T042
- T043
- T044
- T045
phase: Phase 5 — Cutover
assignee: ''
agent: ''
history:
- timestamp: '2026-05-20T16:25:00Z'
  agent: system
  action: Prompt generated via /spec-kitty.tasks
authoritative_surface: docs/design/architecture/baselines/
execution_mode: code_change
owned_files:
- docs/design/architecture/baselines/felix-doc-auditor-post-rework.json
- docs/design/architecture/baselines/cutover-log.md
tags: []
---

# Work Package Prompt: WP09 — Cutover execution and post-rework measurement

## Objective

Execute the cutover: drain the audit queue → confirm merge to main → deploy on office2 → verify the first tick under the new driver → run post-rework measurement → verify ≥80% token reduction (NFR-001).

This is operationally consequential. The deploy is fail-forward per spec C-007. No automatic rollback — if any step fails, surface the error and fix forward.

## Context

- This WP RUNS the deploy script from WP08, against the deploy code from WP06.
- Pre-flight gate: spec C-004 requires queue-drained state at deploy time to minimize in-flight pending-approval orphaning.
- Post-rework measurement reuses `scripts/doc_audit/baselines/measure-tokens.py` from WP07 (now adapted for the new driver's tick-signal artifact format).
- The NFR-001 acceptance gate is ≥80% reduction. If the measurement comes in lower, the rework is INCOMPLETE — keep on the branch, investigate, and patch forward.

## Branch Strategy

- **Planning base branch**: `main`
- **Final merge target**: `main`
- **Execution worktree**: allocated per lane; run `spec-kitty agent action implement WP09 --agent <name>`.

## Subtasks

### T040 — Pre-cutover queue drain confirmation

**Purpose**: Verify the audit queue is in a deploy-safe state per spec C-004.

**Steps**:

1. Check open `Doc audit:` issues with `status:in-progress`:
   ```bash
   gh issue list --repo kentonium3/kg-automation \
     --label "Doc audit:,status:in-progress" --state open \
     --json number,title
   ```
   Expected: empty list. If non-empty:
   - Investigate via the auditor's log / journal — was this orphaned by a prior tick?
   - If orphan, manually clear the `status:in-progress` label and let the next pre-cutover tick re-pick up
   - Wait for the queue to clear

2. Check open `audit-pending-approval` issues:
   ```bash
   gh issue list --repo kentonium3/kg-automation \
     --label "audit-pending-approval" --state open \
     --json number,title,labels
   ```
   Expected: either empty OR all entries have one of the three decision labels (`audit-approve`, `audit-reject`, `audit-skip`).
   - If pending-approvals exist without decision labels: ask Kent to triage before deploy
   - If pending-approvals exist WITH decision labels: it's safe; the new driver will pick them up post-deploy

3. Document the pre-cutover state:
   - Open audits count
   - Open pending-approvals count
   - Active drift events processed in last 24h (`tail` the drift-events.jsonl)
   - Last successful tick timestamp from current `last-tick.json` (if exists) OR from the activity log

**Files**:
- New: `docs/design/architecture/baselines/cutover-log.md` (starts here with pre-cutover snapshot)

**Validation**:
- [ ] No open audits with `status:in-progress` (or known-orphan + cleared)
- [ ] No pending-approvals without decision labels (or known-OK + Kent signoff)
- [ ] Pre-cutover state captured in `cutover-log.md`

---

### T041 — Execute cutover

**Purpose**: Run the deploy script in apply mode, with explicit Tier-2 protocol acknowledgment.

**Steps**:

1. Confirm Tier 2 pre-flight:
   - Restic backup ran within last 24 hours: `ssh office2-claude 'tail -20 /data/services/backup/logs/backup-*.log'` — look for recent SUCCESS
   - openclaw-gateway service is healthy: `ssh office2-claude 'systemctl --user is-active openclaw-gateway.service'`
   - gh auth as kg-felix-bot: `ssh office2-claude 'gh auth status'`

2. Confirm the merge: this mission's branch must be merged to main first. The git log should show all WP01-WP08 commits on main.
   ```bash
   git log origin/main --oneline | head -20
   ```

3. Execute the deploy in apply mode:
   ```bash
   ssh office2-claude 'bash /home/claude/kg-automation/scripts/office2/deploy/felix-doc-auditor-driver.sh --apply --backup-confirmed'
   ```

4. Capture deploy output in `cutover-log.md`:
   - Timestamp deploy started
   - Each step's [APPLY] line (steps 1-8)
   - Timestamp deploy ended
   - Final exit code

**Files**:
- Modified: `docs/design/architecture/baselines/cutover-log.md` (deploy output appended)

**Validation**:
- [ ] Deploy script exits 0
- [ ] All 8 steps printed as completed
- [ ] Workspace files at `/data/services/openclaw/felix-doc-auditor/` no longer exist
- [ ] systemd unit installed at `~/.config/systemd/user/felix-doc-auditor.service` matches the new ExecStart
- [ ] openclaw agent deregistered (`openclaw agent list` no longer shows felix-doc-auditor)
- [ ] cutover-log.md updated with deploy timestamps

---

### T042 — Verify first tick under new driver

**Purpose**: Force a verification tick immediately after deploy to catch any deploy errors before the next cron fire.

**Steps**:

1. Trigger the verification tick:
   ```bash
   ssh office2-claude 'systemctl --user start --wait felix-doc-auditor.service'
   ```
   `--wait` blocks until the oneshot exits.

2. Inspect the tick signal:
   ```bash
   ssh office2-claude 'cat /data/services/openclaw/felix-doc-auditor-driver/last-tick.json | jq'
   ```
   Required: `status: "success"`, `exit_code: 0`, `timestamp_utc` within last minute, errors `[]`.

3. Inspect the systemd journal:
   ```bash
   ssh office2-claude 'journalctl --user -u felix-doc-auditor --since "2 minutes ago" --no-pager'
   ```
   Expected: SUMMARY: line at end, no exception traces.

4. Inspect the activity log:
   ```bash
   ssh office2-claude 'tail -20 /home/kgale/second-brain/agents/logs/doc-auditor-$(date -u +%Y-%m-%d).md'
   ```
   Expected: a new entry with the verification tick's timestamp.

5. If any check fails: STOP. Do not proceed to T043-T045. Investigate; patch forward via a follow-up commit OR revert via manual restore (per C-007, document but don't auto-revert).

**Files**:
- Modified: `docs/design/architecture/baselines/cutover-log.md` (verification tick result appended)

**Validation**:
- [ ] Tick signal: status=success, exit_code=0
- [ ] Journal SUMMARY line present
- [ ] Activity log entry written
- [ ] No exceptions in journal

---

### T043 — Run post-rework measurement

**Purpose**: Capture token usage from the new driver across representative outcomes for NFR-001 comparison.

**Steps**:

1. Wait for natural tick variation: let the hourly timer fire 3+ times across enough hours to capture (ideally) an empty tick, a debt-only tick, and a Tier-A tick.

2. Use the helper script (`scripts/doc_audit/baselines/measure-tokens.py` from WP07, now adapted) to extract per-tick token data from the new driver's tick-signal artifacts (or the journal SUMMARY lines, whichever the script consumes):
   ```bash
   ssh office2-claude 'python3 /home/claude/kg-automation/scripts/doc_audit/baselines/measure-tokens.py \
     --source post-rework \
     --since 2026-MM-DDTHH:MM:SSZ \
     --output /tmp/post-rework-measurements.json'
   scp office2-claude:/tmp/post-rework-measurements.json /Users/kentgale/repos/kg-automation/tmp/
   ```

3. If natural variation doesn't yield all 3 outcomes within a reasonable window (~24h), document the gap and proceed with what was measured.

**Files**: intermediate data in `/tmp/` — committed in T044

**Validation**:
- [ ] ≥3 ticks measured
- [ ] At minimum 1 outcome captured (empty is most common)
- [ ] Token counts in plausible range (input ≪ pre-rework baseline; output similar)

---

### T044 — Write `baselines/felix-doc-auditor-post-rework.json`

**Purpose**: Commit the post-rework baseline data alongside the pre-rework one, formatted identically for comparison.

**Steps**:

1. Create `docs/design/architecture/baselines/felix-doc-auditor-post-rework.json`:

   ```json
   {
     "schema_version": "1.0",
     "name": "felix-doc-auditor-post-rework",
     "captured_at": "2026-MM-DDTHH:MM:SSZ",
     "captured_by": "#343-WP09",
     "captured_via": "scripts/doc_audit/baselines/measure-tokens.py against new driver tick signals",
     "subject": {
       "service": "felix-doc-auditor-driver",
       "host": "office2",
       "model": "anthropic/claude-haiku-4-5",
       "invocation": "/usr/bin/python3 /home/claude/kg-automation/scripts/doc_audit/run.py",
       "git_sha": "<sha at time of measurement>"
     },
     "measurements": [
       {
         "outcome": "empty",
         "samples": [...],
         "average_input_tokens": ...,
         "average_cache_hit_input_tokens": ...,
         "average_output_tokens": ...,
         "average_duration_seconds": ...
       },
       ... etc per outcome ...
     ],
     "comparison_with_pre_rework": {
       "per_outcome": [
         {
           "outcome": "empty",
           "pre_input_tokens": <from pre-rework>,
           "post_input_tokens": <from post-rework>,
           "reduction_pct": <computed>
         },
         ...
       ],
       "weighted_average_reduction_pct": <computed by representative-mix weighting>
     },
     "methodology": "<reference to pre-rework methodology + any deltas>",
     "open_caveats": []
   }
   ```

2. Compute the per-outcome reduction percentage:
   ```
   reduction_pct = ((pre_input_tokens - (post_input_tokens - post_cache_hit_tokens * 0.9)) / pre_input_tokens) * 100
   ```
   (Cache hits are billed at ~10% of standard rate; the effective input cost is `input - cache_hit*0.9`.)

3. Document the weighted-average methodology if outcomes are weighted differently (e.g., empty ticks happen 90% of the time, others 10%).

**Files**:
- New: `docs/design/architecture/baselines/felix-doc-auditor-post-rework.json` (~80 lines)

**Validation**:
- [ ] Baseline JSON parses; all fields present
- [ ] Comparison section computed correctly
- [ ] Methodology cites the pre-rework methodology + notes new fields from the driver's tick signal

---

### T045 — Verify ≥80% reduction; record per-outcome breakdown

**Purpose**: NFR-001 acceptance gate. The whole rework is graded against this number.

**Steps**:

1. Examine `felix-doc-auditor-post-rework.json` `comparison_with_pre_rework`:
   - **PASS**: weighted_average_reduction_pct ≥ 80%
   - **FAIL**: weighted_average_reduction_pct < 80%

2. **On PASS**:
   - Update `cutover-log.md` with the result: "NFR-001 acceptance gate PASSED at X% reduction"
   - Tag the commit (optional)
   - Proceed to WP10 (architecture doc updates)

3. **On FAIL**:
   - Update `cutover-log.md` with the result: "NFR-001 acceptance gate FAILED at X% reduction"
   - Investigate. Likely root causes:
     - Prompt caching not working (cache_hit_input_tokens = 0)
     - Per-judgment input is larger than expected (prompts too verbose)
     - Output tokens larger than expected (LLM responses too verbose)
   - File a follow-up issue OR plan a patch-forward fix within this mission
   - Do NOT close the mission until NFR-001 passes

4. Update `cutover-log.md` with the per-outcome breakdown table:

   | Outcome | Pre input | Post input (effective) | Reduction |
   |---|---|---|---|
   | empty | N | N' | X% |
   | debt-only | M | M' | Y% |
   | tier-A apply | K | K' | Z% |

**Files**:
- Modified: `docs/design/architecture/baselines/cutover-log.md` (acceptance gate result appended)
- Possibly modified: `docs/design/architecture/baselines/felix-doc-auditor-post-rework.json` (if patch-forward iteration occurs)

**Validation**:
- [ ] Acceptance gate result recorded in cutover-log.md
- [ ] If PASS: NFR-001 satisfied
- [ ] If FAIL: investigation + patch-forward path documented; mission stays open

---

## Definition of Done

- [ ] Queue drained pre-cutover (or known state documented)
- [ ] Deploy executed successfully on office2 (all 8 steps + exit 0)
- [ ] First tick under new driver: success (signal + journal + activity log all clean)
- [ ] Post-rework measurement captured for ≥3 ticks across ≥1 outcome
- [ ] post-rework.json committed alongside pre-rework.json
- [ ] NFR-001 acceptance gate: PASS (or patch-forward path active if FAIL)
- [ ] cutover-log.md captures the full operational record

## Risks

| Risk | Mitigation |
|---|---|
| Deploy fails mid-way; partial state | Each step idempotent; reviewer re-runs from the failed step after fixing |
| Verification tick reveals integration bug not caught by tests | Patch forward; mission stays open until first tick is clean |
| Measurement window is too short, undersampling outcomes | Document the gap; defer broader measurement to a follow-on mission if needed (but record what's available) |
| ≥80% reduction not met → mission incomplete | Investigate; patch forward; do not declare mission done until met |

## Reviewer Guidance

- Confirm queue-drained pre-flight passed BEFORE deploy
- Confirm first-tick verification: status=success, no exceptions
- Confirm post-rework JSON computes the reduction correctly
- Confirm cutover-log.md is a complete operational record (sufficient for a future operator to replicate / understand)

## Implementation Command

```bash
spec-kitty agent action implement WP09 --agent <name>
```

## Cross-references

- **Research**: D10 (cutover sequence), D13 (cost baseline methodology)
- **Contracts**: `contracts/driver-invocation.contract.md`, `contracts/tick-signal.contract.md`
- **Spec**: NFR-001 (≥80% reduction), NFR-002 (95% successful ticks — start of soak), C-004 (queue-drained), C-007 (fail-forward), FR-010 (retire old agent)
- **Pre-rework baseline**: `docs/design/architecture/baselines/felix-doc-auditor-pre-rework.json`
- **Deploy script**: `scripts/office2/deploy/felix-doc-auditor-driver.sh`
