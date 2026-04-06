---
work_package_id: WP01
title: Full Investigation and Findings
dependencies: []
requirement_refs:
- FR-001
- FR-002
- FR-003
- FR-004
- FR-005
planning_base_branch: main
merge_target_branch: main
branch_strategy: Planning artifacts for this feature were generated on main. During /spec-kitty.implement this WP may branch from a dependency-specific base, but completed changes must merge back into main unless the human explicitly redirects the landing branch.
base_branch: main
base_commit: 2a39adad78006cb5315584147485318ceed2c970
created_at: '2026-04-06T18:13:51.316232+00:00'
subtasks: [T001, T002, T003, T004, T005, T006]
shell_pid: "2294"
agent: "claude"
history:
- date: '2026-04-06'
  action: created
  by: spec-kitty.tasks
authoritative_surface: kitty-specs/017-vikunja-habit-tracking-architecture/
execution_mode: planning_artifact
owned_files:
- kitty-specs/017-vikunja-habit-tracking-architecture/findings.md
---

# WP01: Full Investigation and Findings

## Objective

Execute the complete F017 research investigation: verify Vikunja version,
audit the current F009 deployment, research Vikunja's recurring task
model, evaluate three candidate approaches against five criteria, confirm
API capabilities, and write a single architecture recommendation.

Produce `findings.md` in the feature directory as the sole deliverable.

## Context

**Why this research exists**: F009 (Daily Habit Check-in) deployed habit
tasks as static Vikunja tasks with comment-based completion tracking.
These tasks have no `due_date` set, so they never appear in the Vikunja
Today filter. Kent wants daily habits to appear in Today so he can check
them off directly in Vikunja. Before fixing F009, we need to determine
the correct data model.

**Pre-research findings already confirmed** (from diagnostic session
2026-04-06 — incorporate these, do not re-gather):
- Habit tasks 14, 17, 20: `due_date` is null sentinel
  (`0001-01-01T00:00:00Z`), `repeat_after: 0`, `repeat_mode: 0`
- Cron `habits-morning-checkin` runs daily at 11:05 UTC, status `ok`,
  WhatsApp delivery working
- Agent (AGENTS.md) is query-only: reads tasks, checks comments,
  delivers check-in. Never sets due_date or creates tasks.
- Completion comments use format:
  `[Felix] YYYY-MM-DD | {complete|rescheduled|will-not-do} | note`

**Read these files before starting**:
- `kitty-specs/017-vikunja-habit-tracking-architecture/spec.md` — full
  research questions, evaluation criteria, scope, success criteria
- `kitty-specs/017-vikunja-habit-tracking-architecture/plan.md` — methodology
- `kitty-specs/017-vikunja-habit-tracking-architecture/research.md` —
  source plan and pre-research data
- `docs/func-spec/F009_daily_habit_checkin.md` — the original spec with
  the deferred architecture decision
- `docs/runbooks/habits-ops.md` — current operational documentation

**Constraints (CRITICAL)**:
- **Read-only on office2**: No task creation, modification, deletion, or
  agent file changes. Query only.
- Access via `ssh office2-claude`
- Vikunja API token: `cat /data/services/openclaw/secrets/vikunja-api`
- Vikunja base URL: `https://office2.tail0f5f56.ts.net`

## Branch Strategy

- Planning/base branch: `main`
- Merge target: `main`
- Implementation command: `spec-kitty implement WP01`

---

## Subtask T001: Verify Vikunja Version on office2

**Purpose**: Gate all external source research against the actual
deployed version. Community posts and docs may reference different
versions with different behavior.

**Steps**:
1. Read `docs/design/architecture/data/service-inventory.json` locally
   to find the documented Vikunja version
2. Optionally confirm the running version via API:
   ```bash
   ssh office2-claude 'curl -s -H "Authorization: Bearer $(cat /data/services/openclaw/secrets/vikunja-api)" \
     "https://office2.tail0f5f56.ts.net/api/v1/info" | python3 -m json.tool'
   ```
3. Record the version. All subsequent external source findings must be
   validated against this version.

**Output**: Version number noted at the top of findings.md.

---

## Subtask T002: Complete RQ-2 — Current F009 Deployment State

**Purpose**: Document what F009 actually deployed vs. what the spec
intended. Build on pre-research findings; fill remaining gaps.

**Steps**:
1. Incorporate pre-research findings (tasks 14, 17, 20 already inspected)
2. Query remaining habit tasks (15, 16, 18, 19) to confirm all match
   the same pattern (no due_date, no recurrence):
   ```bash
   ssh office2-claude 'for id in 15 16 18 19; do
     echo "=== Task $id ==="
     curl -s -H "Authorization: Bearer $(cat /data/services/openclaw/secrets/vikunja-api)" \
       "https://office2.tail0f5f56.ts.net/api/v1/tasks/$id" | python3 -c "
   import sys,json; d=json.load(sys.stdin); print(f\"title: {d[\"title\"]}\ndue_date: {d[\"due_date\"]}\nrepeat_after: {d[\"repeat_after\"]}\nrepeat_mode: {d[\"repeat_mode\"]}\ndone: {d[\"done\"]}\")"
   done'
   ```
3. Query comments on 2-3 tasks to verify completion records exist:
   ```bash
   ssh office2-claude 'curl -s -H "Authorization: Bearer $(cat /data/services/openclaw/secrets/vikunja-api)" \
     "https://office2.tail0f5f56.ts.net/api/v1/tasks/15/comments" | python3 -m json.tool'
   ```
4. Read `docs/func-spec/F009_daily_habit_checkin.md` — find the deferred
   architecture decision ("Habits Are Not Tasks" section) and document
   what the spec intended vs. what was deployed
5. Identify gaps: what's working (cron, WhatsApp, comment recording),
   what's missing (Today filter visibility, due_date management)

**Output**: RQ-2 section of findings.md — factual current state report
with explicit gap analysis.

---

## Subtask T003: Research RQ-1 — Vikunja Recurring Task Behavior

**Purpose**: Determine exactly what happens when a Vikunja recurring
task is marked done — this is the key unknown for evaluating Option A.

**Steps**:
1. Read Vikunja API docs — task schema fields:
   - `repeat_after` (integer — seconds between repetitions)
   - `repeat_mode` (0=default, 1=from_current_date, 2=month)
   - Look for any other recurrence-related fields
   Fetch from: `https://try.vikunja.io/api/v1/docs` or
   `https://vikunja.io/docs/` (use WebFetch)
2. Read Vikunja help docs on dates and reminders:
   `https://vikunja.io/help/dates-and-reminders/`
   Look specifically for: what happens when a repeating task is marked
   done, whether a new instance is created or the same task resets,
   what happens to comments
3. Search Vikunja community forum for recurring task behavior threads
   (particularly: comment persistence, completion history, skip/will-not-do)
4. Document findings on these specific questions:
   - When a recurring task is marked done, does Vikunja create a new
     task or reset the existing one?
   - What happens to the due_date? (Advances by repeat_after?)
   - What happens to comments on the task?
   - Is completion history preserved anywhere (activity log, etc.)?
   - Can a "skipped" or "will not do" state be expressed natively?
   - What does the Today filter actually query? (due_date = today?)
5. **Version-gate**: Flag any findings that reference a different Vikunja
   version than what's running on office2 (from T001)

**Output**: RQ-1 section of findings.md — precise behavioral description
with source citations.

---

## Subtask T004: Evaluate RQ-3 — Candidate Approach Comparison

**Purpose**: Map three candidate approaches against five evaluation
criteria. Produce a comparison table with evidence-backed assessments.

**Depends on**: T002 (current state) and T003 (recurring task behavior)

**Candidate approaches**:
- **Option A**: Native Vikunja recurring tasks
- **Option B**: Agent-managed daily task creation (new child tasks with
  today's due_date each morning)
- **Option C**: Hybrid — Vikunja tasks for Today visibility + lightweight
  external log for completion history/state

**Evaluation criteria** (from spec):

| Criterion | Weight | Key question |
|-----------|--------|--------------|
| Today filter visibility | High | Do today's habits appear in Today? |
| Skipped state expressible | High | Can "will not do" be distinct from "complete"? |
| Completion history 90 days | High | Are records queryable across 90+ days? |
| 48-hour catch-up window | Medium | Can missed habits be marked retroactively? |
| Agent complexity | Medium | Implementable without new external data store? |

**Steps**:
1. For **Option A** (native recurring): Use RQ-1 findings to assess
   each criterion. Key concerns: does marking done preserve history?
   Can skip be expressed? Do comments survive the recurrence cycle?
2. For **Option B** (agent-managed daily creation): Assess feasibility
   — agent creates 7 tasks each morning with `due_date = today`. Tasks
   accumulate over time (history = old tasks). Consider: task volume
   over 90 days (630 tasks), project clutter, query performance.
3. For **Option C** (hybrid): Evaluate open-ended — what serves as the
   external log? Candidates include:
   - The existing comment model (already works for recording states)
   - JSONL file on office2
   - A second Vikunja project as a completion log
   - Any other lightweight option that fits
   Assess: does combining Vikunja due_date with an external log satisfy
   all five criteria?
4. Build comparison table: one row per criterion, one column per option,
   cell contains pass/fail/partial + evidence citation
5. Identify the recommended approach or best trade-off

**Output**: RQ-3 section of findings.md — comparison table + supported
recommendation.

---

## Subtask T005: Confirm RQ-4 — API Capabilities

**Purpose**: For the recommended approach from T004, confirm every API
call needed to implement it actually exists.

**Depends on**: T004 (recommendation)

**Steps**:
1. List all API operations the recommended approach requires:
   - Task creation or update (if approach creates/modifies tasks)
   - Setting due_date
   - Filtering tasks by due_date (for Today view behavior)
   - Comment creation and query
   - Task completion (marking done)
   - Any other operations
2. For each operation, confirm the endpoint exists in Vikunja's API:
   - HTTP method and path
   - Required fields
   - Expected behavior
3. Where possible, verify against the live instance using read-only
   queries (e.g., confirming filter parameters work)
4. Flag any capabilities that cannot be confirmed — these become risks
   for the F009 implementation spec

**Output**: RQ-4 section of findings.md — endpoint-level confirmation
table with any gaps noted.

---

## Subtask T006: Write Architecture Recommendation

**Purpose**: Synthesize all findings into a clear, actionable
recommendation that resolves the deferred F009 architecture decision.

**Depends on**: T005 (API confirmation)

**Steps**:
1. State the recommended approach (one of A/B/C)
2. Map rationale to each evaluation criterion by name:
   - "Today filter visibility: [approach] satisfies this because..."
   - Repeat for all five criteria
3. Document known risks and limitations
4. Provide specific guidance for the revised F009 implementation spec:
   - What the agent should create/modify and when
   - How completion states are recorded
   - How history is preserved and queried
   - What changes to AGENTS.md are needed
5. Confirm this recommendation fully resolves the deferred decision in
   the F009 spec's "Habits Are Not Tasks" section

**Output**: Architecture Recommendation section of findings.md —
actionable recommendation with rationale, risks, and implementation
guidance.

---

## Definition of Done

- [ ] `findings.md` exists at `kitty-specs/017-vikunja-habit-tracking-architecture/findings.md`
- [ ] RQ-1 through RQ-4 each answered with cited evidence
- [ ] At least 3 independent sources consulted and cited
- [ ] Findings verified against Vikunja version running on office2
- [ ] Comparison table maps three options against all five criteria
- [ ] Single recommended approach stated with criterion-by-criterion rationale
- [ ] API endpoints confirmed at field level for recommended approach
- [ ] Known risks and limitations documented
- [ ] No modifications made to live Vikunja instance or office2 agent files
- [ ] The F009 revised spec can be written from these findings alone

## Risks

| Risk | Mitigation |
|------|------------|
| Vikunja recurring behavior differs from docs | Verify via API inspection, not just docs |
| No option satisfies all five criteria | Spec allows "best available trade-off" |
| Community sources reference wrong version | T001 version gate; flag version mismatches |
| office2 unavailable during research | External source research can proceed first |

## Reviewer Guidance

When reviewing `findings.md`:
1. Check each RQ has cited evidence (not just assertions)
2. Verify the comparison table has an entry for every criterion/option cell
3. Confirm the recommendation rationale references criteria by name
4. Check API confirmation is at endpoint + field level (not just "it exists")
5. Verify no write operations were performed on office2
6. Ask: could the F009 implementation spec be written from this document
   alone? If not, what's missing?

---

**END OF WORK PACKAGE**

## Activity Log

- 2026-04-06T18:27:20Z – unknown – shell_pid=99350 – Moved to for_review
- 2026-04-06T18:27:26Z – claude – shell_pid=2294 – Started review via workflow command
