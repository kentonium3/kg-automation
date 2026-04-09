---
work_package_id: WP03
title: Validate Habits and Escalation on Haiku
dependencies: [WP01]
requirement_refs:
- FR-002
- FR-003
planning_base_branch: main
merge_target_branch: main
branch_strategy: Planning artifacts for this feature were generated on main. During /spec-kitty.implement this WP may branch from a dependency-specific base, but completed changes must merge back into main unless the human explicitly redirects the landing branch.
subtasks: [T006, T007, T008, T009, T010, T011, T012]
history:
- date: '2026-04-09T17:18:21Z'
  action: created
  by: spec-kitty.tasks
authoritative_surface: kitty-specs/021-openclaw-agent-model-tiering/artifacts/
execution_mode: planning_artifact
owned_files:
- kitty-specs/021-openclaw-agent-model-tiering/artifacts/validation-habits-escalation.md
---

# WP03: Validate Habits and Escalation Agents on Haiku

## Objective

Test whether `felix-admin-habits` (daily check-in + weekly review) and `felix-admin-escalation` (overdue task detection) produce acceptable results on Haiku. The habits weekly review does trend reasoning and the escalation agent has the highest consequence if wrong — these are the most critical validation decisions.

## Context

- **Habits agent** (`felix-admin-habits`):
  - Workspace: `/data/services/openclaw/habits-agent/`
  - Agent dir: `/home/claude/.openclaw/agents/felix-admin-habits/agent/`
  - Tasks: Morning check-in (routine), weekly review with trend analysis (complex)
  - Single agent handles both — can't assign different models per task type
  - Decision: Validate both on Haiku; if weekly review fails, entire agent stays on Sonnet until #141 splits it

- **Escalation agent** (`felix-admin-escalation`):
  - Workspace: `/data/services/openclaw/escalation-agent/`
  - Agent dir: `/home/claude/.openclaw/agents/felix-admin-escalation/agent/`
  - Tasks: Detect overdue tasks, evaluate priority/due dates, deliver level-appropriate alerts
  - Highest risk if wrong — missed escalation has real consequences
  - If any doubt, stays on Sonnet

- Access via `ssh office2-claude`

## Branch Strategy

- Planning base: `main`
- Merge target: `main`
- Implementation command: `spec-kitty implement WP03 --base WP01`
- **Parallel with WP02** — both depend on WP01 but are independent of each other

---

## Subtask T006: Collect Habits Daily Check-in Samples

**Purpose**: Gather representative daily check-in interactions to use as validation inputs.

**Steps**:
1. SSH to office2
2. Check habits agent session logs: `/home/claude/.openclaw/agents/felix-admin-habits/sessions/sessions.json`
3. Find 3+ recent daily check-in sessions showing:
   - The morning check-in message sent to Kent
   - Kent's responses (habit completions)
   - Agent's processing of those responses
4. Document each sample: agent output, interaction quality, correctness

**Validation**:
- [ ] 3+ daily check-in sessions collected with Sonnet baseline outputs

---

## Subtask T007: Run Habits Daily Check-in on Haiku

**Purpose**: Test whether Haiku produces acceptable daily check-in interactions.

**Steps**:
1. Temporarily change `felix-admin-habits` model to `anthropic/claude-haiku-4-5` in `openclaw.json`
2. Trigger a check-in run (or simulate by providing the same prompt/context)
3. Compare Haiku output to Sonnet baseline:
   - Is the check-in message clear and well-formatted?
   - Does it list the correct habits?
   - Does completion recording work correctly?
4. Record pass/fail with specific observations
5. Revert model to Sonnet after testing

**Quality criteria**:
- Habit list accuracy: Must list correct habits
- Message formatting: Must be clear and readable (doesn't need to be identical to Sonnet)
- Completion processing: Must correctly record marked habits

**Validation**:
- [ ] Daily check-in comparison complete
- [ ] Pass/fail recorded with observations

---

## Subtask T008: Collect Habits Weekly Review Samples

**Purpose**: Gather representative weekly review outputs to test the most complex aspect of this agent.

**Steps**:
1. Check session logs for recent weekly review runs
2. Find 2-3 weekly review outputs showing:
   - Trend analysis (which habits improving/declining)
   - Pattern detection (day-of-week patterns, streaks)
   - Recommendations (suggestions for improvement)
3. Document Sonnet's output quality — this is the benchmark

**Important**: The weekly review is the key quality decision. If Haiku can't match Sonnet's reasoning quality here, the entire habits agent stays on Sonnet until #141 splits daily from weekly.

**Validation**:
- [ ] 2+ weekly review outputs collected with Sonnet baseline

---

## Subtask T009: Run Habits Weekly Review on Haiku

**Purpose**: Test whether Haiku can produce adequate trend analysis and recommendations.

**Steps**:
1. With habits agent still on Haiku (or temporarily switched), trigger a weekly review
2. Compare Haiku's output to Sonnet baseline:
   - **Trend accuracy**: Does it identify the same improving/declining habits?
   - **Pattern detection**: Does it spot the same day-of-week or streak patterns?
   - **Recommendation quality**: Are recommendations actionable and relevant?
   - **Reasoning depth**: Does it explain WHY trends are happening, or just list facts?
3. Record pass/fail — be strict here:
   - PASS: Haiku identifies the same trends and produces actionable recommendations
   - MARGINAL: Haiku identifies trends but recommendations are shallow
   - FAIL: Haiku misses trends, gives generic advice, or produces factual errors

**Decision logic**:
- If PASS: Habits agent can move to Haiku
- If MARGINAL or FAIL: Habits agent stays on Sonnet; document findings for #141

**Validation**:
- [ ] Weekly review comparison complete
- [ ] Trend accuracy assessed
- [ ] Recommendation quality assessed
- [ ] Clear pass/marginal/fail verdict recorded

---

## Subtask T010: Collect Escalation Agent Inputs

**Purpose**: Gather representative task snapshots including known escalation triggers.

**Steps**:
1. Check escalation agent session logs: `/home/claude/.openclaw/agents/felix-admin-escalation/sessions/sessions.json`
2. Find 3+ recent sessions showing:
   - Task data the agent evaluated (overdue tasks, at-risk tasks)
   - Escalation decisions made (which tasks flagged, which ignored)
   - Alert messages generated
3. **Critical**: Include at least one session with a known escalation trigger:
   - A task that was genuinely overdue and should have been flagged
   - Verify Sonnet correctly identified it
4. Also include sessions where no escalation was needed (to test for false positives)

**Validation**:
- [ ] 3+ escalation sessions collected
- [ ] At least 1 session with known escalation trigger and confirmed correct Sonnet decision
- [ ] At least 1 session with no escalations (baseline for false positive testing)

---

## Subtask T011: Run Escalation Agent on Haiku

**Purpose**: Test whether Haiku correctly identifies overdue tasks and escalation triggers without missing any.

**Steps**:
1. Temporarily change `felix-admin-escalation` model to Haiku
2. Trigger an escalation detection run against the same or equivalent task state
3. Compare Haiku decisions to Sonnet baseline:
   - **True positives**: Does Haiku flag the same overdue/at-risk tasks?
   - **False negatives** (CRITICAL): Does Haiku miss any tasks that Sonnet caught?
   - **False positives**: Does Haiku flag tasks that Sonnet correctly ignored?
   - **Alert quality**: Are alert messages clear and contain the right task details?
4. Record pass/fail — zero tolerance for missed escalations:
   - PASS: Same tasks flagged, no missed escalations, acceptable alert quality
   - FAIL: Any missed escalation, or significantly degraded alert quality
5. Revert model to Sonnet after testing

**Decision logic**:
- If PASS: Escalation agent can move to Haiku
- If FAIL: Escalation agent stays on Sonnet (pinned)
- If uncertain: Default to Sonnet — the cost of a missed escalation exceeds the savings

**Validation**:
- [ ] Escalation comparison complete
- [ ] Zero false negatives (no missed escalations)
- [ ] False positive rate acceptable
- [ ] Clear pass/fail verdict

---

## Subtask T012: Document Validation Results

**Purpose**: Create a comprehensive validation report that drives the deployment decisions in WP04.

**Steps**:
1. Compile results from T005 (inbox), T007/T009 (habits daily/weekly), T011 (escalation)
2. Create a validation report in the mission directory with:

   | Agent | Task | Haiku Verdict | Key Observations | Recommendation |
   |---|---|---|---|---|
   | felix-admin-capture | Inbox scan | PASS/FAIL | [specifics] | Move to Haiku / Stay on Sonnet |
   | felix-admin-habits | Daily check-in | PASS/FAIL | [specifics] | [recommendation] |
   | felix-admin-habits | Weekly review | PASS/MARGINAL/FAIL | [specifics] | [recommendation] |
   | felix-admin-escalation | Escalation detection | PASS/FAIL | [specifics] | [recommendation] |

3. For habits: If daily passes but weekly fails, recommend keeping on Sonnet with note that #141 will split
4. Include token usage observations from Haiku runs (for cost projection in WP05)
5. Final model assignment table:

   | Agent | Final Model | Policy |
   |---|---|---|
   | main | Sonnet (pinned) | pinned |
   | felix-admin-capture | [based on validation] | [pinned/optimizable] |
   | felix-admin-habits | [based on validation] | [pinned/optimizable] |
   | felix-admin-escalation | [based on validation] | [pinned/optimizable] |
   | felix-admin-tasker | Sonnet (pinned) | pinned |

**Validation**:
- [ ] All 4 agent validations documented
- [ ] Final model assignment table complete
- [ ] Token usage from Haiku runs recorded for cost projection
- [ ] All models reverted to Sonnet (production is unchanged until WP04)

---

## Definition of Done

- [ ] Habits daily check-in validated on Haiku (pass/fail)
- [ ] Habits weekly review validated on Haiku (pass/marginal/fail)
- [ ] Escalation detection validated on Haiku (pass/fail)
- [ ] Comprehensive validation report created
- [ ] Final model assignment recommendations documented
- [ ] All agent models reverted to Sonnet after testing
- [ ] Token usage data captured for cost projection

## Risks

- **Habits weekly review fails on Haiku**: Expected possible outcome — document and keep habits on Sonnet. #141 tracks the split.
- **Escalation agent misses a trigger**: Any miss = fail. Default to Sonnet.
- **Insufficient session history**: If agents haven't run recently (credits exhausted), may need to trigger runs or use older logs
- **Side effects from test runs**: Escalation alerts may fire via WhatsApp during testing — warn Kent before triggering

## Reviewer Guidance

- The weekly review is the swing decision — scrutinize trend reasoning quality carefully
- For escalation: zero tolerance for missed triggers — one miss = stay on Sonnet
- Verify all models were reverted after testing
- Check that token usage was recorded (needed for WP05 cost calculation)
