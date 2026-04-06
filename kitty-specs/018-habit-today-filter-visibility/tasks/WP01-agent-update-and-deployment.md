---
work_package_id: WP01
title: Agent Update and Deployment
dependencies: []
requirement_refs:
- FR-001
- FR-002
- FR-003
- FR-004
- FR-005
- FR-006
- FR-007
planning_base_branch: main
merge_target_branch: main
branch_strategy: Planning artifacts for this feature were generated on main. During /spec-kitty.implement this WP may branch from a dependency-specific base, but completed changes must merge back into main unless the human explicitly redirects the landing branch.
base_branch: main
base_commit: 157e6bf55db76c16ca8c50016fad3b8f2fc6e2a6
created_at: '2026-04-06T18:42:42.938147+00:00'
subtasks: [T001, T002, T003, T004, T005]
shell_pid: "6204"
agent: "claude"
history:
- date: '2026-04-06'
  action: created
  by: spec-kitty.tasks
authoritative_surface: scripts/openclaw/agents/felix-admin-habits/
execution_mode: code_change
owned_files:
- scripts/openclaw/agents/felix-admin-habits/AGENTS.md
- docs/runbooks/habits-ops.md
---

# WP01: Agent Update and Deployment

## Objective

Add a due_date step to the felix-admin-habits morning check-in workflow so
that scheduled habits appear in the Vikunja Today filter. Update the habits
operations runbook. Deploy the updated AGENTS.md to office2. Verify the
change works end-to-end.

## Context

**Why this change is needed**: F009 deployed habits as static Vikunja tasks
with no `due_date`. The Vikunja Today filter queries
`dueDate >= now/d && dueDate < now/d+1d` — tasks without a due_date are
invisible to it. F017 research confirmed the fix: set `due_date = today`
on each scheduled habit during the morning check-in.

**What the agent currently does** (morning check-in workflow):
1. Step 1: Determine today's day and date
2. Step 2: Query active habits from Vikunja project 13
3. Step 3: Exclude already-completed habits (check comments for today)
4. Step 4: Format the check-in message
5. (Deliver via WhatsApp)

**What changes**: A new step is inserted between Step 2 (query habits) and
Step 3 (exclude completed). After determining which habits are scheduled
for today, the agent sets `due_date = today` on each one before proceeding.

**Key reference**: Read `kitty-specs/017-vikunja-habit-tracking-architecture/findings.md`
for the full architecture recommendation, API confirmation, and comparison
of approaches that led to this decision.

**Constraints**:
- The comment-based completion model is unchanged
- Error handling must be non-blocking — failed due_date updates must not
  prevent WhatsApp delivery
- Access office2 via `ssh office2-claude` only

## Branch Strategy

- Planning/base branch: `main`
- Merge target: `main`
- Implementation command: `spec-kitty implement WP01`

---

## Subtask T001: Read Current AGENTS.md and Identify Insertion Point

**Purpose**: Understand the existing morning check-in workflow structure
so the new step is inserted in the correct position.

**Steps**:
1. Read `scripts/openclaw/agents/felix-admin-habits/AGENTS.md` (repo copy)
2. Locate the "Morning check-in" section
3. Identify the current step numbering:
   - Step 1: Determine today's day
   - Step 2: Query active habits
   - Step 3: Exclude already-completed habits
   - Step 4: Format the check-in message
4. Confirm the insertion point: the new due_date step goes AFTER Step 2
   (query habits — we need the filtered list) and BEFORE Step 3 (exclude
   completed — the due_date must be set even on habits that might already
   be complete, since Today filter visibility is independent of completion)

**Wait** — actually, re-read the AGENTS.md Step 2 carefully. The agent
first queries tasks, then filters by today's schedule. The due_date step
should happen AFTER schedule filtering but BEFORE completion exclusion.
This ensures only today's scheduled habits get due_date = today.

**Output**: Understanding of where the new step goes. No file changes yet.

---

## Subtask T002: Add due_date Step to AGENTS.md (Repo Copy)

**Purpose**: Insert the new step into the morning check-in workflow.

**File**: `scripts/openclaw/agents/felix-admin-habits/AGENTS.md`

**What to add** — a new step (renumber subsequent steps accordingly):

The new step should be titled something like:
"Step 3: Set due_date for Today filter visibility"

Content of the new step:

```
For each habit that passed the schedule filter in Step 2, set its
due_date to today so it appears in the Vikunja Today filter:

  PUT /api/v1/tasks/{habit_id}
  Body: {"due_date": "<YYYY-MM-DD>T00:00:00Z"}

Where <YYYY-MM-DD> is today's date from Step 1.

Rules:
- Skip any habit with "(PAUSED)" in the description or done = true
- If the API call fails for one habit, log the error and continue
  with the remaining habits — do NOT stop the check-in workflow
- This step is a visibility aid only — the due_date field is NOT
  used for completion tracking (comments are the authority)
```

**Renumbering**: The old Step 3 (exclude completed) becomes Step 4.
The old Step 4 (format message) becomes Step 5. Update all references
to step numbers in the AGENTS.md file.

**Validation**:
- [ ] New step is positioned after schedule filtering, before completion exclusion
- [ ] Step numbering is consistent throughout the document
- [ ] Error handling is explicitly non-blocking
- [ ] The step clearly states due_date is for visibility only
- [ ] No other sections of AGENTS.md are changed (completion recording,
      weekly reporting, habit management all stay the same)

---

## Subtask T003: Update habits-ops.md Runbook

**Purpose**: Document the due_date behavior and add troubleshooting.

**File**: `docs/runbooks/habits-ops.md`

**Changes needed**:

1. **In the "Overview" section** (or after it): Add a brief note explaining
   that the agent sets `due_date = today` on scheduled habits each morning
   so they appear in the Vikunja Today filter.

2. **In the "Troubleshooting" table**: Add a new row:

   | Symptom | Check | Fix |
   |---------|-------|-----|
   | Habits not in Today filter | Verify morning cron ran: `ssh office2-claude "openclaw cron runs --id <uuid>"` | If cron succeeded but habits missing, check task due_dates via API. If cron failed, investigate cron error. |

3. **In the "Vikunja habits project" section**: Add a note that habit tasks
   have their `due_date` updated daily by the agent — this is a visibility
   mechanism, not a completion indicator. The comment model remains the
   authoritative source of completion state.

**Validation**:
- [ ] Runbook explains the due_date mechanism
- [ ] Troubleshooting table includes Today filter entry
- [ ] due_date is clearly described as visibility-only (not completion state)
- [ ] File passes doc validation (frontmatter intact)

---

## Subtask T004: Deploy Updated AGENTS.md to office2

**Purpose**: Sync the deployed agent instructions with the repo copy.

**Steps**:
1. Use the existing deployment pattern from habits-ops.md:
   ```bash
   ssh office2-claude "cat > /data/services/openclaw/habits-agent/AGENTS.md" \
     < scripts/openclaw/agents/felix-admin-habits/AGENTS.md
   ```

2. Verify the deployed file matches:
   ```bash
   ssh office2-claude "head -30 /data/services/openclaw/habits-agent/AGENTS.md"
   ```
   Confirm the new due_date step is present.

**Validation**:
- [ ] Deployed AGENTS.md on office2 contains the new due_date step
- [ ] File content matches the repo copy

---

## Subtask T005: Verify — Trigger Check-in and Confirm Today Filter

**Purpose**: End-to-end verification that the change works.

**Steps**:
1. Get the habits-morning-checkin cron UUID:
   ```bash
   ssh office2-claude "openclaw cron list"
   ```

2. Trigger the cron manually:
   ```bash
   ssh office2-claude "openclaw cron run <uuid>"
   ```

3. Wait for the run to complete (check status):
   ```bash
   ssh office2-claude "openclaw cron runs --id <uuid>"
   ```
   Confirm status is `ok` and delivery succeeded.

4. Check that habit tasks now have today's due_date:
   ```bash
   ssh office2-claude 'curl -s -H "Authorization: Bearer $(cat /data/services/openclaw/secrets/vikunja-api)" \
     "https://office2.tail0f5f56.ts.net/api/v1/tasks/15" | python3 -c "import sys,json; d=json.load(sys.stdin); print(d[\"title\"], d[\"due_date\"])"'
   ```
   Expected: due_date should be today's date (e.g., `2026-04-06T00:00:00Z`),
   not the null sentinel (`0001-01-01T00:00:00Z`).

5. Spot-check 1-2 more tasks to confirm the pattern.

6. Report findings: which tasks got due_date updated, whether WhatsApp
   was delivered, any errors.

**Validation**:
- [ ] Cron run completed successfully (status `ok`)
- [ ] WhatsApp check-in was delivered
- [ ] At least 5 habit tasks have today's due_date set
- [ ] Tasks not scheduled today (if any — depends on day of week) do NOT
      have today's due_date

**Edge case**: If today is a day where all 7 habits are scheduled (e.g.,
a weekday), all 7 should have today's due_date. If it's Sunday, only 5
should (strength training and wake-at-5 are not scheduled).

---

## Definition of Done

- [ ] AGENTS.md (repo copy) contains the new due_date step in the correct position
- [ ] Step numbering is consistent throughout AGENTS.md
- [ ] habits-ops.md documents the due_date mechanism and troubleshooting
- [ ] Deployed AGENTS.md on office2 matches repo copy
- [ ] Morning check-in triggered successfully after deployment
- [ ] Habit tasks have today's due_date set (verified via API)
- [ ] WhatsApp check-in was delivered
- [ ] No unrelated changes to AGENTS.md or habits-ops.md
- [ ] All documentation passes CI validation

## Risks

| Risk | Mitigation |
|------|------------|
| Agent misinterprets new step | Step uses clear, specific language with explicit API call format |
| API call fails during verification | F017 confirmed the call works; if it fails, check Vikunja status |
| Cron timeout exceeded | 7 API calls add < 5 seconds; well within 120s timeout |
| Deployment drift after future AGENTS.md edits | habits-ops.md documents the deployment command |

## Reviewer Guidance

1. Read the AGENTS.md diff — confirm the new step is between schedule
   filtering and completion exclusion
2. Verify step numbering is consistent (no duplicate or missing numbers)
3. Confirm the step explicitly states error handling is non-blocking
4. Check habits-ops.md changes are limited to due_date documentation
5. Verify the deployment was confirmed (T004 output)
6. Check verification results (T005 output) — at least 5 tasks should
   have today's due_date

---

**END OF WORK PACKAGE**

## Activity Log

- 2026-04-06T18:47:46Z – unknown – shell_pid=5091 – Moved to for_review
- 2026-04-06T18:47:52Z – claude – shell_pid=6204 – Started review via workflow command
- 2026-04-06T18:48:11Z – claude – shell_pid=6204 – Review passed: AGENTS.md Step 3 correctly positioned. Step numbering consistent. Error handling non-blocking. habits-ops.md updated with due_date docs and troubleshooting. Deployed to office2 and verified — all 7 tasks have today's due_date. WhatsApp delivery confirmed.
