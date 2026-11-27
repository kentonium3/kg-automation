---
work_package_id: WP02
title: Skill wording and skill coverage
dependencies:
- WP01
requirement_refs:
- FR-004
- FR-005
- SC-003
planning_base_branch: fix/1146-delivery-doctrine-followups
merge_target_branch: fix/1146-delivery-doctrine-followups
branch_strategy: Planning artifacts for this mission were generated on fix/1146-delivery-doctrine-followups. During /spec-kitty.implement this WP may branch from a dependency-specific base, but completed changes must merge back into fix/1146-delivery-doctrine-followups unless the human explicitly redirects the landing branch.
base_branch: kitty/mission-delivery-doctrine-followups-01M8FBH0
base_commit: 46602a1113dc914ed3f0bb13855dd496709aec42
created_at: '2026-11-27T22:02:24.207264+00:00'
subtasks:
- T007
- T008
- T009
- T010
phase: Phase 2 - Skill consistency
history:
- at: '2026-11-27T20:57:33Z'
  actor: system
  action: Prompt generated via /spec-kitty.tasks
agent_profile: python-pedro
authoritative_surface: scripts/openclaw/
create_intent:
- scripts/openclaw/agents/tests/test_announce_skill_coverage.py
execution_mode: code_change
model: claude-sonnet-5-5
owned_files:
- scripts/openclaw/skills/escalation/SKILL.md
- scripts/openclaw/agents/tests/test_announce_skill_coverage.py
role: implementer
tags: []
task_type: implement
tracker_refs: []
---

# Work Package Prompt: WP02 – Skill wording and skill coverage

## ⚡ Do This First: Load Agent Profile

Use the `/spk-charter-profile-load` skill to load the agent profile specified in the frontmatter (or any user-defined profile), and behave according to its guidance before parsing the rest of this prompt.

- **Profile**: `python-pedro`
- **Role**: `implementer`
- **Agent/tool**: `claude`

If no profile is specified, run `spec-kitty agent profile list` and select the best match for this work package's `task_type` and `authoritative_surface`.

---

## ⚠️ IMPORTANT: Review Feedback

**Read this first if you are implementing this task!**

- **Has review feedback?**: Check the `review_ref` field in the event log (via `spec-kitty agent tasks status`).
- **You must address all feedback** before your work is complete. Feedback items are your implementation TODO list.
- **Report progress**: As you address each feedback item, record what you changed with `spec-kitty agent tasks add-history <WPID> --note "..."` (stored in the status event log).

---

## Review Feedback

*[If this WP was returned from review, the reviewer feedback reference appears in the status event log.]*

---

## Markdown Formatting

Wrap HTML/XML tags in backticks: `` `<div>` ``, `` `<script>` ``
Use language identifiers in code blocks: ````python`,````bash`

---

## Objectives & Success Criteria

- The escalation skill's §7 "Daily Deduplication" describes the dedup the agent actually performs (FR-004).
- A new test runs the improved guard (from WP01) in skill mode over every skill each announce agent reads, and fails if any of them contains forbidden delivery wording. A same-fixture positive control proves the probe can see a violation (FR-005, SC-003).
- No skill gains new wording (decision 01M8FC8T0WYHWPQ9MW7XHJWFYA: FR-005 is verify-and-pin).

## Context & Constraints

- **Read**:
  - `spec.md` (FR-004, FR-005);
  - `plan.md` (IC-03, and Planning decisions: FR-005 is verify-and-pin);
  - `data-model.md` (the agent → skills mirror);
  - `research.md` (Q6).
- **Depends on WP01** (the improved guard). Branch from the lane the tool allocates; never hand-pick a base.
- **The real dedup** (research Q6): escalation decides with `scripts/escalation/derive_state.py` over the per-project JSONL history. The caller skips a task when its `last_event` is a `level_sent` at that level dated today (America/New_York). `record_completion --idempotent` additionally pre-checks duplicate (task, date, state) records. There is no comment-based dedup. Read the code and the escalation `AGENTS.md` to confirm before writing.
- **Escalation headroom**: this WP does not edit `AGENTS.md`. `SKILL.md` has no cap test, but keep the §7 text short.

## Branch Strategy

- **Strategy**: {{branch_strategy}}
- **Planning base branch**: {{planning_base_branch}}
- **Merge target branch**: {{merge_target_branch}}

> These fields are populated automatically by `spec-kitty agent mission finalize-tasks`.
> Do NOT change them manually unless you are certain the branch topology has changed.

## Subtasks & Detailed Guidance

### Subtask T007 – Escalation SKILL.md §7

- **Purpose**: remove stale wording that contradicts the code.
- **Steps**:
  1. Read `scripts/escalation/derive_state.py` and the escalation `AGENTS.md` dedup step, and identify the exact rule: the event name, the per-level check, the date basis and the timezone.
  2. Replace the body of `## 7. Daily Deduplication` in `scripts/openclaw/skills/escalation/SKILL.md` (about L278–286). It must say that dedup comes from the per-project history (`derive_state`), not from task comments. Keep the "max one alert per task per level per calendar day" rule, and name the timezone.
  3. Remove any remaining mention of `level-N | sent` comments as the dedup source anywhere in that skill. Grep for it.
- **Notes**: no behaviour change. Text must match code. Cite the function name, not line numbers.

### Subtask T008 – Announce agent → skills mirror

- **Purpose**: a committed, reviewable list of which skills each announce agent reads.
- **Steps**:
  1. In the new test module `scripts/openclaw/agents/tests/test_announce_skill_coverage.py`, define the mapping from `data-model.md`:
     - capture → `vikunja_api`, `github`
     - escalation → `escalation`, `vikunja_api`
     - habits → `vikunja_api`, plus task-intelligence (referenced from its prompt)
  2. Resolve each skill id to its repo source `SKILL.md` under `scripts/openclaw/skills/`, using the repo's directory names (`vikunja-api`, `task-intelligence`, `escalation`). If a skill has no repo source (for example `github`, if it is a bundled OpenClaw skill), record it in the mirror with an explicit reason and skip it.
  3. Add a test that the mirror's agent set equals `ANNOUNCE_AGENTS` from `delivery_doctrine.py`, so a new announce agent forces a mirror update.
- **Notes**: the live config is the authority. The canary re-checks this mirror against `agents.entries.<id>.skills` read-only.

### Subtask T009 – Skill-coverage test

- **Purpose**: FR-005 and SC-003.
- **Steps**:
  1. Parametrise over every (agent, skill) in the mirror that has a repo source. Assert that `delivery_violations(text, require_block=False) == []`.
  2. Positive control on the same fixture: take one real skill's text, append `Send Kent a WhatsApp if delivery fails.`, and assert that the guard flags it. This proves the probe sees violations in skill mode.
  3. Run against the WP01 guard and confirm green, and that the positive control is red without the appended line removed.
- **Files**: `scripts/openclaw/agents/tests/test_announce_skill_coverage.py` (new).

### Subtask T010 – Sync path and clean state

- **Purpose**: make sure the skill edit reaches office2 and stays clean.
- **Steps**:
  1. Confirm from the repo (`deploy_agent_skills` / agent-skill-sync, research Q8) that `scripts/openclaw/skills/escalation/SKILL.md` is synced on merge to `main`, with no manifest needed. Note the deployed path for the canary.
  2. Run the full `scripts/openclaw` test suite and confirm it is green.

## Test Strategy

```bash
.venv/bin/python -m pytest scripts/openclaw/agents/tests/test_announce_skill_coverage.py -q
.venv/bin/python -m pytest scripts/openclaw -q
```

## Risks & Mitigations

| Risk | Mitigation |
|---|---|
| The mirror drifts from live config | Agent-set equality test; canary re-check |
| The dedup text misstates the code | Derive it from `derive_state`; the reviewer checks it against the code |

## Review Guidance

- Compare the §7 text with `derive_state.py` and the escalation `AGENTS.md`.
- Confirm the positive control exists and is built from a real skill's text.
- Confirm that no skill other than escalation `SKILL.md` changed.

## Progress & Status

Progress, history, and status all live in the status event log
(`status.events.jsonl`) — never in this prompt file. Do **not** hand-edit a
history section here.

- **Record a progress note**: `spec-kitty agent tasks add-history <WPID> --note "<what you did>"`
- **Change WP status**: `spec-kitty agent tasks move-task <WPID> --to <status>`
- **View history and status**: `spec-kitty agent tasks status`
