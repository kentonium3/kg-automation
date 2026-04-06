---
work_package_id: WP04
title: Runbook and Verification
dependencies: [WP03]
requirement_refs:
- FR-014
planning_base_branch: main
merge_target_branch: main
branch_strategy: Planning artifacts for this feature were generated on main. During /spec-kitty.implement this WP may branch from a dependency-specific base, but completed changes must merge back into main unless the human explicitly redirects the landing branch.
subtasks: [T015, T016, T017, T018, T019]
history:
- date: '2026-04-06'
  action: created
  by: spec-kitty.tasks
authoritative_surface: docs/runbooks/
execution_mode: code_change
owned_files:
- docs/runbooks/escalation-ops.md
---

# WP04: Runbook and Verification

## Objective

Create the operations runbook for the escalation engine and verify the
full system end-to-end: alert delivery, response handling, silent run,
and comment format.

## Context

**Runbook pattern**: Follow `docs/runbooks/habits-ops.md` for structure
and format conventions. The escalation runbook covers the same categories:
agent management, schedule, Vikunja interaction, WhatsApp interaction,
and troubleshooting.

**Verification approach**: Trigger the cron manually, inspect outputs,
check Vikunja comments. All verification is done via
`ssh office2-claude` and Vikunja API queries.

**Prerequisite**: WP03 must be complete — agent deployed, cron created,
architecture docs updated.

## Branch Strategy

- Planning/base branch: `main`
- Merge target: `main`
- Implementation command: `spec-kitty implement WP04 --base WP03`

---

## Subtask T015: Create escalation-ops.md Runbook

**Purpose**: Operations documentation for the escalation engine.

**File**: `docs/runbooks/escalation-ops.md`

**Required frontmatter**:
```yaml
---
title: Escalation Engine Operations Runbook
doc_type: runbook
audience: agents_and_humans
status: draft
---
```

**Required sections** (follow habits-ops.md structure):

1. **Overview**: What the escalation engine does, when it runs, what it
   escalates, what it excludes.

2. **Agent management**: Agent name, workspace path, model, workspace
   file listing with purposes.

3. **Update workspace files**: Command to sync repo → office2 (same
   pattern as habits-ops.md deployment command).

4. **Schedule**: Table with cron job name, schedule (UTC and ET), purpose.
   Include the manual trigger command.

5. **Escalation model**: Summary of Level 1 vs Level 2 triggers, priority
   filter, project exclusions. Reference the skill for full details.

6. **Vikunja escalation state**: Explain the `[Felix-Escalation]` comment
   format. Show how to query escalation history for a task:
   ```bash
   ssh office2-claude 'curl -s -H "Authorization: Bearer $(cat /data/services/openclaw/secrets/vikunja-api)" \
     "https://office2.tail0f5f56.ts.net/api/v1/tasks/<ID>/comments" | python3 -m json.tool'
   ```

7. **WhatsApp interaction**: How alerts are delivered, how to respond
   (done, snooze, dismiss, reschedule, acknowledge).

8. **Configuration**: How to adjust priority threshold, project
   exclusions, or cron schedule. How to temporarily pause escalation
   (e.g., during travel): disable the cron job via
   `openclaw cron disable <uuid>`.

9. **Troubleshooting table**:

   | Symptom | Check | Fix |
   |---------|-------|-----|
   | No escalation alerts received | Check cron: `openclaw cron runs --id <uuid>` | Verify cron exists, is enabled, and has `--to` set |
   | Wrong tasks escalated | Check priority filter and project exclusions in skill | Update skill and redeploy |
   | Duplicate alerts on same task | Check `[Felix-Escalation]` comments for same-day duplicates | Likely a bug — check deduplication logic in skill |
   | Response not processed | Send message, check agent response | Verify escalation skill is deployed; restart gateway if needed |
   | Snoozed task re-escalated early | Check snooze comment date and duration calculation | Verify snooze expiry math in skill |

10. **Privacy boundary**: Same absolute rule as all agents.

---

## Subtask T016: Verify — Trigger Cron and Confirm Alert Delivery

**Purpose**: End-to-end test of the escalation detection and alerting pipeline.

**Steps**:
1. Get the escalation cron UUID:
   ```bash
   ssh office2-claude "openclaw cron list"
   ```

2. Trigger the cron manually:
   ```bash
   ssh office2-claude "openclaw cron run <uuid>"
   ```

3. Wait for completion, then check the run result:
   ```bash
   ssh office2-claude "openclaw cron runs --id <uuid> --limit 1"
   ```

4. Report:
   - Status (ok/error)
   - Whether a WhatsApp message was delivered
   - Summary of the message content (which tasks were listed, at what level)
   - If no tasks qualified, confirm silent run

**Note**: The result depends on whether Kent actually has overdue medium+
priority tasks. If none exist, a silent run is the correct outcome —
document that as a pass for the "silent run" scenario.

---

## Subtask T017: Verify — Test Response Handling

**Purpose**: Confirm the agent processes Kent's responses correctly.

**Steps**:
1. If an escalation message was delivered in T016, ask Kent to reply
   with a test response (e.g., "1 snooze 2d" or "1 done")
2. Check the agent's confirmation message
3. Verify the Vikunja comment was written:
   ```bash
   ssh office2-claude 'curl -s -H "Authorization: Bearer $(cat /data/services/openclaw/secrets/vikunja-api)" \
     "https://office2.tail0f5f56.ts.net/api/v1/tasks/<ID>/comments" | python3 -m json.tool'
   ```
4. If "done" was used, verify the task's `done` field is `true`

**If no escalation was delivered** (silent run): Skip this verification
and note it was not testable in this run. The response handling can be
verified on the next natural escalation.

---

## Subtask T018: Verify — Confirm Silent Run

**Purpose**: Verify the agent runs silently when no tasks qualify.

**Steps**:
1. If the T016 run was a silent run (no qualifying tasks), this is
   already verified — document the pass
2. If T016 did deliver an alert, this can be verified on a future run
   when all overdue tasks have been addressed
3. Check the cron run output — it should show status `ok` with no
   delivery (or delivery of the escalation message, not a "nothing
   to report" message)

---

## Subtask T019: Verify — Check Escalation Comments

**Purpose**: Confirm `[Felix-Escalation]` comments are written correctly.

**Steps**:
1. If an escalation was sent in T016, query the comments on one of the
   escalated tasks
2. Verify the comment matches the format:
   `[Felix-Escalation] YYYY-MM-DD | level-N | sent`
3. Verify the date is today's date
4. Verify the level matches what was shown in the WhatsApp message

**If no escalation was sent**: Skip and note not testable in this run.

---

## Definition of Done

- [ ] `docs/runbooks/escalation-ops.md` exists with all required sections
- [ ] Runbook passes doc validation (frontmatter compliant)
- [ ] Cron triggered successfully (status `ok`)
- [ ] If tasks qualified: WhatsApp alert delivered, comments written
- [ ] If no tasks qualified: silent run confirmed
- [ ] Response handling verified (if testable in this run)
- [ ] All verification results documented in the WP output

## Risks

| Risk | Mitigation |
|------|------------|
| No overdue tasks exist for testing | Silent run is valid; document as pass for that scenario |
| Response handling untestable if no alert sent | Note as deferred verification; test on next natural run |

## Reviewer Guidance

1. Check runbook covers all 10 required sections
2. Verify troubleshooting table has entries for the 5 specified symptoms
3. Confirm the "temporarily pause" mechanism is documented (cron disable)
4. Review verification results — were all testable scenarios covered?
5. If any verification was deferred, is the reason documented?

---

**END OF WORK PACKAGE**
