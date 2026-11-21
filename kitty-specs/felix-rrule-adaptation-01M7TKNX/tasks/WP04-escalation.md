---
work_package_id: WP04
title: Escalation — the agent never writes Vikunja
dependencies:
- WP01
- WP02
- WP06
requirement_refs:
- FR-006
- FR-014
- FR-015
- FR-020
- NFR-002
- SC-005
planning_base_branch: fix/felix-rrule-adaptation
merge_target_branch: fix/felix-rrule-adaptation
branch_strategy: Planning artifacts for this mission were generated on fix/felix-rrule-adaptation. During /spec-kitty.implement this WP may branch from a dependency-specific base, but completed changes must merge back into fix/felix-rrule-adaptation unless the human explicitly redirects the landing branch.
base_branch: kitty/mission-felix-rrule-adaptation-01M7TKNX
base_commit: c29399bd63a8540ad26663226f39b05a2b5eb349
created_at: '2026-11-19T23:19:24.180720+00:00'
subtasks:
- T017
- T018
- T019
- T020
- T021
phase: Phase 1 - Destructive write paths
history:
- at: '2026-11-19T22:30:00Z'
  actor: system
  action: Prompt generated via /spec-kitty.tasks
agent_profile: python-pedro
authoritative_surface: scripts/escalation/
create_intent:
- tests/escalation/test_escalation_rule_roundtrip.py
- tests/architectural/test_agent_docs_no_direct_task_writes.py
execution_mode: code_change
model: claude-opus-5-5
owned_files:
- scripts/escalation/record_completion.py
- scripts/escalation/reconcile_completions.py
- scripts/openclaw/agents/felix-admin-escalation/AGENTS.md
- scripts/openclaw/agents/felix-admin-escalation/TOOLS.md
- scripts/openclaw/skills/escalation/SKILL.md
- tests/escalation/test_record_completion.py
- tests/escalation/test_reconcile_completions.py
- tests/escalation/test_escalation_rule_roundtrip.py
- tests/architectural/test_agent_docs_no_direct_task_writes.py
role: implementer
tags: []
task_type: implement
tracker_refs: []
---

# Work Package Prompt: WP04 – Escalation — the agent never writes Vikunja

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

Fix audit rows 5 and 6, plus the combined effect described in research.md R-005. Today the agent's `N done` path runs a bare `POST /api/v1/tasks/{id}` with `{"done": true}`, which strips the rule. It then runs the helper, whose v1 `PATCH` returns **405**, so the helper exits 1 **before** the JSONL append. The destructive write succeeds and the bookkeeping fails.

After this WP:
1. `scripts/escalation/record_completion.py` writes through WP02's `patch_task` on v2: `{"done": true}` for done, `{"due_date": eod}` for reschedule. That fixes the 405. For done it records the WP01 `completion_outcome`, and for reschedule it asserts the rule is unchanged.
2. The agent docs (`AGENTS.md` L202-212, `TOOLS.md` L26-33) and the escalation skill (`SKILL.md` L218, L222) **never** instruct a direct Vikunja task write. `N done` means: call the helper, then confirm.
3. Reconcile (`reconcile_completions.py`) labels "rule present, due date advanced, not done" as a **completion**, not a reschedule (FR-015). A series that has finished reads as `done` (FR-014).
4. A guard test fails on any agent or skill doc that tells an agent to POST, PUT or PATCH a Vikunja task directly.

## Context & Constraints

- Spec: FR-006, FR-014, FR-015, FR-020, NFR-002. Plan IC-03. research.md R-005. data-model.md Completion outcome. post-plan-review.md finding 7: the deploy-skew risk is handled by the quickstart rollout window, not by code.
- **Dependency on WP06.** Reconcile reads the sync cache (`view.fields`, around L972), which only carries `repeat` once WP06 adds it to `TRACKED_TASK_FIELDS`. Use `has_rule(view.fields)`. If the field is absent (an old cache), fall back to today's behaviour, never to a guess.
- The helper's public CLI (`--task-id --project-id --title --date --state --source`) and its JSONL contract stay unchanged. The `--no-vikunja`/`skip_vikunja` path used by reconcile (L918, 1020, 1085) stays.
- `_patch_task` keeps the module's error contract: it raises this module's own `VikunjaError` with `HTTP <status>`. Existing tests rely on those substrings (`tests/escalation/test_record_completion.py:161-195, 329`). Update the substrings that said `PATCH <base>/api/v1/...` to the v2 URL.
- Agent docs reach office2 through agent-prompt-sync every 5 minutes. They are not hashed, so no rebaseline is needed (#621).

## Branch Strategy

- **Strategy**: {{branch_strategy}}
- **Planning base branch**: {{planning_base_branch}}
- **Merge target branch**: {{merge_target_branch}}

```bash
spec-kitty agent action implement WP04 --agent claude --mission felix-rrule-adaptation-01M7TKNX
```

## Subtasks & Detailed Guidance

### Subtask T017 – Helper writes on v2 with outcome

- **Steps**:
  1. Rewrite `_patch_task` (L192-228) to:
     - build `VikunjaClient(base_url=..., token=..., timeout=HTTP_TIMEOUT_SECONDS)`;
     - call `client.patch_task(task_id, body)`;
     - translate client exceptions as today, with the URL now from `client.v2_base_url`;
     - return the response task, or `None` on 304.
  2. In the Vikunja step (L415-433):
     - **done**:
       - `before = client.get_task_v2(id)` and `exhaustion = exhaustion_expected(before, preview=client.preview_occurrences)`;
       - PATCH; re-read if the response was 304;
       - `outcome = completion_outcome(...)`.
       - Append `task_PATCH_done` plus `outcome:<x>` to `actions`.
       - On `unexpected`, **still write the JSONL done record**, because Kent did say done. Add `"note": "vikunja outcome unexpected: <before/after summary>"` and return a non-zero CLI status **after** the JSONL write. The record must not be lost, and the agent must report the anomaly. Document that ordering in the docstring.
     - **rescheduled**:
       - PATCH the due date, then read back.
       - If `not same_rule(before, after)`, raise `VikunjaError("rule changed by reschedule ...")` **before** the JSONL write. The task's state is then wrong, so no record should claim success.
  3. A task with no rule (one-off) keeps working: done gives done=true, and the outcome function returns `unexpected` only when exhaustion was unknown **and** the task had a rule. Check the WP01 semantics. For a no-rule task, `exhaustion_expected` returns `"no"` and `completion_outcome` would return `unexpected` for done=true. So **special-case a one-off task** here: if `not has_rule(before)`, a result of done=true is simply `done_one_off`. Record that, and add a test.
- **Files**: `scripts/escalation/record_completion.py`

### Subtask T018 – Reconcile labels

- **Steps**:
  1. In `_reconcile_one_task`, step 3b (rescheduled-drift, around L1046+): when the cached task has a rule (`has_rule(view.fields)`), the due date is later than the JSONL's last-known due date, and the task is **not** done, emit a synthetic **`done`** record. Use `source="reconcile"` and `note="Synthesized by reconcile: recurring task advanced (completed in UI); due_date <old>→<new>"`. Do not emit `rescheduled`.
  2. Without a rule, keep today's `rescheduled` path unchanged.
  3. Done-drift (3a): unchanged. A finished series is done=true and is already handled.
  4. Missing `repeat` key in an old cache: keep today's behaviour, and add a test for it.
- **Edge**: Kent manually moving a recurring task's due date forward without completing it will be labelled done. Document this in the docstring as a known ambiguity; the rule plus an advanced due date is the best signal available. It is low-stakes, because the record is synthetic and the history keeps both dates.

### Subtask T019 – Agent docs and skill

- **Steps**:
  1. `AGENTS.md` around L200-215:
     - Remove step 1 (the bare POST) from the `N done` procedure.
     - The helper call becomes the only step that changes Vikunja.
     - Add a bold rule: "Never POST, PUT or PATCH a Vikunja task directly. The helper does the write."
     - Keep "Marked #N done." as the reply. When the helper exits non-zero, the agent reports the anomaly verbatim (Truthful reporting, L96).
  2. `TOOLS.md` L26-33: remove the direct `POST /api/v1/tasks/{id}` done example. Keep the read examples, and replace the stale `/tasks/all` caveat at L14 if present (research.md R-011).
  3. `skills/escalation/SKILL.md` L218 and L222: same change. "N and M done" means one helper call per task.
- Keep each file's structure, headings and Output-Discipline sections. Make minimal, surgical edits.

### Subtask T020 – Doc guard test

- New `tests/architectural/test_agent_docs_no_direct_task_writes.py`:
  - Scan `scripts/openclaw/agents/**/*.md` and `scripts/openclaw/skills/**/SKILL.md`.
  - Fail on any line that combines a write verb (`POST`, `PUT`, `PATCH`, `curl -X (POST|PUT|PATCH)`) with a task path (`/tasks/{`, `/tasks/<`, `/tasks/:id`, `/api/v1/tasks/`, `/api/v2/tasks/`) **and is not** inside a block explicitly marked as a negative example (e.g. a line containing `Never` / `Do not`).
  - Use a **per-file allowlist** for known non-agent docs, if any, each with a reason string.
- **Make it fail first.** Run it on the current AGENTS.md and record the red result. WP09 extends coverage of the skills it rewrites. The test must already pass on them after WP09's rewrites; WP09 must not loosen it.

### Subtask T021 – Tests

- `tests/escalation/test_escalation_rule_roundtrip.py`, using the WP01 factory and `mock_vikunja_urlopen`:
  - done on recurring: the PATCH body is exactly `{"done": true}` against `/api/v2/tasks/{id}`; the outcome is advanced and the JSONL is written.
  - done COUNT=1: series_ended.
  - done with unexpected: JSONL written, the note recorded, non-zero exit.
  - done on a one-off: `done_one_off`.
  - reschedule: the PATCH body is exactly `{"due_date": ...}`.
  - **Positive control**: the fake server returns `strip_rule` after the reschedule, so the helper raises and the JSONL is not written.
  - 405 no longer possible: assert no v1 PATCH is ever issued.
- Convert `tests/escalation/test_record_completion.py` (PATCH assertions at L161-195) to the v2 URL.
- Add reconcile cases to `tests/escalation/test_reconcile_completions.py`: recurring advanced gives synthetic done; non-recurring gives rescheduled; an old cache without `repeat` gives today's behaviour.
- Red-then-green: run the round-trip file on a `cc4f2154` scratch checkout and record the failures with `add-history`.

```bash
python3 -m pytest -q tests/escalation tests/architectural
```

```bash
make test
```

## Risks & Mitigations

- **Deploy skew** between docs and helper. Not solvable in code; it's handled by the quickstart rollout window. Mention it in the WP history so the reviewer checks that quickstart covers it.
- **Over-matching guard test.** Keep its patterns tight and test the guard itself: one positive and one negative synthetic doc string.

## Review Guidance

- Is the agent left with no path to a direct write? Read the three docs end to end.
- Is the ordering right: JSONL before the non-zero exit for unexpected done; no JSONL for a rule-changing reschedule?
- Does reconcile have a test for the old-cache fallback?

## Progress & Status

Use `spec-kitty agent tasks add-history WP04 --note "..."` and `spec-kitty agent tasks mark-status T0xx --status done`.
