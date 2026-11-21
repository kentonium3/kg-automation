---
work_package_id: WP09
title: Agent guidance teaches the rule model
dependencies:
- WP04
- WP08
requirement_refs:
- FR-019
planning_base_branch: fix/felix-rrule-adaptation
merge_target_branch: fix/felix-rrule-adaptation
branch_strategy: Planning artifacts for this mission were generated on fix/felix-rrule-adaptation. During /spec-kitty.implement this WP may branch from a dependency-specific base, but completed changes must merge back into fix/felix-rrule-adaptation unless the human explicitly redirects the landing branch.
base_branch: kitty/mission-felix-rrule-adaptation-01M7TKNX
base_commit: 4eb04d4f4e709f12d9dcfe4a2d31bb6a3e15e63e
created_at: '2026-11-20T18:43:31.038516+00:00'
subtasks:
- T041
- T042
- T043
- T044
- T045
phase: Phase 3 - Guidance
history:
- at: '2026-11-19T22:30:00Z'
  actor: system
  action: Prompt generated via /spec-kitty.tasks
agent_profile: python-pedro
authoritative_surface: scripts/openclaw/skills/
create_intent:
- scripts/vikunja/preview_rule.py
- tests/vikunja/test_preview_rule.py
execution_mode: code_change
model: claude-opus-5-5
owned_files:
- scripts/vikunja/preview_rule.py
- tests/vikunja/test_preview_rule.py
- scripts/openclaw/skills/task-intelligence/SKILL.md
- scripts/openclaw/skills/vikunja-api/SKILL.md
- scripts/openclaw/agents/felix-admin-tasker/AGENTS.md
- scripts/openclaw/agents/felix-admin-habits/AGENTS.md
role: implementer
tags: []
task_type: implement
tracker_refs: []
---

# Work Package Prompt: WP09 – Agent guidance teaches the rule model

## ⚡ Do This First: Load Agent Profile

Use the `/spk-charter-profile-load` skill to load the agent profile specified in the frontmatter, and behave according to its guidance before parsing the rest of this prompt.

- **Profile**: `python-pedro`
- **Role**: `implementer`
- **Agent/tool**: `claude`

---

## ⚠️ IMPORTANT: Review Feedback

Check `spec-kitty agent tasks status` for a `review_ref`, and address every item before going back to review.

---

## Objectives & Success Criteria

Fix audit rows 25–28 (#1111) and adopt O5, partially (FR-019):

1. **`scripts/vikunja/preview_rule.py`** is a read-only helper. Given rule text and an anchor, it checks the rule with Vikunja's preview and prints the next 3 dates in ET, or a clear error (2002 invalid rule, 2003 bad timezone, 401 missing `tasks.occurrences_preview`). It is invoked as `python3 -m scripts.vikunja.preview_rule --rrule "..." (--due <iso> | --initial-due-time HH:MM) [--from-completion] [--count 3]`, and its last line is a JSON summary.
2. **task-intelligence SKILL** (L259-299; 10 old-shape hits):
   - Replace the seconds/`repeat_mode` table with an RRULE table: daily, weekdays, fortnightly, monthly by date, "every N days after I finish" (`FREQ=DAILY;INTERVAL=N` plus from-completion), "6 times" (COUNT), and "until March" (UNTIL).
   - Remove the "critical caveat" that now itself strips rules.
   - Proposals must run `preview_rule` and show Kent the next 3 dates before creating.
   - Creates go through `create_task --rrule`.
   - Remove the stale 2.4.0 `/tasks/all` caveat (L188).
3. **vikunja-api SKILL** (L238-264, L311, L465):
   - State that v1 POST replaces the whole task.
   - Name `repeat`, `repeats_from_current_date` and `reminders`.
   - All task updates go through Felix helpers, which use v2 PATCH.
   - Remove "send only the fields you want", the bare `{"done": true}` curl and the `/tasks/all` caveats.
4. **tasker AGENTS.md** (L171, 173, 194): defer to the new task-intelligence rule table and the preview step. **habits AGENTS.md** (L159, 177): reword "done=true POST" to "the helper records a completion (v2 partial update, rule kept)".
5. **The doc-guard test from WP04** passes across all of these docs. Do not loosen it; extend its fixtures if needed.

## Context & Constraints

- Spec: FR-019, NFR-001. Plan IC-07. research.md R-004 (the preview token permission) and R-011 (the stale caveats).
- Docs must only name helpers that exist. WP04 (escalation helper), WP08 (`create_task --rrule`) and this WP (`preview_rule`) provide them.
- **Agent-doc conventions.** Read `docs/runbooks/openclaw-agent-setup.md` before editing AGENTS.md or SKILL.md: Output-Discipline sections, size caps (memory: AGENTS.md 12k cap), and structure. Keep each change surgical, and keep each file under its cap; measure `wc -c` before and after and record both.
- Agent docs reach office2 through agent-prompt-sync and agent-skill-sync, with no manifest and no rebaseline (#621).
- `preview_rule` depends on the token permission. If Kent's token re-issue hasn't happened, it prints the 401 message and exits 2. The skill text must tell the agent to say exactly that to Kent and not guess dates.

## Branch Strategy

- **Strategy**: {{branch_strategy}}
- **Planning base branch**: {{planning_base_branch}}
- **Merge target branch**: {{merge_target_branch}}

```bash
spec-kitty agent action implement WP09 --agent claude --mission felix-rrule-adaptation-01M7TKNX
```

## Subtasks & Detailed Guidance

### Subtask T041 – `preview_rule` helper

- Follow `docs/design/helper-script-conventions.md`: CLI contract, last-line JSON, exit codes (0 ok, 2 bad input or permission, 3 Vikunja error).
- Validate the rule locally (`rrule_text_to_parts`), then call `client.preview_occurrences(...)` with `timezone="America/New_York"`.
- Render each occurrence in ET with a weekday name, e.g. `Mon 2026-11-23 07:30 ET`.
- Include `reason` when present; for example, COUNT exhausted after 2 shows "series ends after 2 occurrences".
- No writes. A test asserts only POST to `/tasks/occurrences/preview`, which is read-only server-side.

### Subtask T042 – task-intelligence SKILL

- Rewrite the recurrence section. The new table, with one example each:

| Human | `--rrule` | flags |
|---|---|---|
| every day | `FREQ=DAILY` | |
| weekdays | `FREQ=WEEKLY;BYDAY=MO,TU,WE,TH,FR` | |
| every 2 weeks | `FREQ=WEEKLY;INTERVAL=2` | |
| monthly on the 15th | `FREQ=MONTHLY;BYMONTHDAY=15` | |
| every 10 days after I finish | `FREQ=DAILY;INTERVAL=10` | `--from-completion` |
| 6 times weekly | `FREQ=WEEKLY;COUNT=6` | |
| weekly until 2027-03-01 | `FREQ=WEEKLY;UNTIL=20270301T000000Z` | |

- Procedure: draft the rule, run `preview_rule`, show Kent the 3 dates, and on confirmation run `create_task --rrule`. Completing a recurring task advances it; it does not close it. The last occurrence of a COUNT or UNTIL series stays Done.
- Remove every `repeat_after`/`repeat_mode` mention (NFR-001 ratchet, WP08).

### Subtask T043 – vikunja-api SKILL

- Replace L238-264 with a short "Updating tasks" section:
  - never write tasks with curl;
  - use the Felix helpers (`create_task`, the escalation and habits record helpers, intake apply);
  - why: v1 POST replaces the whole task, so omitted fields are cleared, including the rule and reminders.
- Keep the read examples. Remove the 2.4.0 `/tasks/all` caveats at L311 and L465 if they no longer hold. Verify against `research.md`, or leave them and note it.

### Subtask T044 – tasker and habits AGENTS.md

- tasker L171/173/194: point to the task-intelligence recurrence section and the preview step. Remove "repeat interval conversion".
- habits L159/177: reword to describe the helper's completion (v2 partial update, rule kept, "series ended" reported when a COUNT or UNTIL series finishes).

### Subtask T045 – Tests

- `tests/vikunja/test_preview_rule.py`:
  - happy path, rendering 3 ET dates;
  - an invalid rule rejected locally;
  - a server 2002;
  - a 401 giving exit 2 with a message naming `tasks.occurrences_preview`;
  - the only call made is the preview POST.
- Run WP04's `tests/architectural/test_agent_docs_no_direct_task_writes.py` and WP08's `tests/architectural/test_no_retired_repeat_fields.py`; both must pass.

```bash
python3 -m pytest -q tests/vikunja/test_preview_rule.py tests/architectural
```

```bash
make test
```

## Risks & Mitigations

- **Exceeding the AGENTS.md size cap.** Measure, and trim prose rather than rules.
- **Docs promising preview before the token re-issue.** The skill text covers the 401 path explicitly.

## Review Guidance

- Read each doc as the agent would. Is there any path to a direct task write, or to a dead field?
- Is the preview step mandatory before a recurring create?
- Are the file sizes within their caps?

## Progress & Status

Use `spec-kitty agent tasks add-history WP09 --note "..."` and `spec-kitty agent tasks mark-status T0xx --status done`.
