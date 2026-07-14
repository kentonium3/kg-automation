---
work_package_id: WP01
title: 'Author felix-admin-escalation workspace to #587 + full #724'
dependencies: []
requirement_refs:
- FR-001
- FR-002
- FR-003
- FR-004
- FR-005
- FR-006
- FR-007
- FR-008
- FR-009
- FR-010
- FR-011
- FR-012
tracker_refs: []
planning_base_branch: feat/author-escalation-workspace
merge_target_branch: feat/author-escalation-workspace
branch_strategy: Planning artifacts for this mission were generated on feat/author-escalation-workspace. During /spec-kitty.implement this WP may branch from a dependency-specific base, but completed changes must merge back into feat/author-escalation-workspace unless the human explicitly redirects the landing branch.
subtasks:
- T001
- T002
- T003
- T004
- T005
- T006
- T007
- T008
phase: Phase 1 - Author
assignee: ''
agent: "claude"
shell_pid: "78850"
shell_pid_created_at: "1784056983.424306"
history:
- at: '2026-07-14T19:19:26Z'
  actor: system
  action: Prompt generated via /spec-kitty.tasks
agent_profile: curator-carla
authoritative_surface: scripts/openclaw/agents/felix-admin-escalation/
create_intent: []
execution_mode: code_change
model: claude-sonnet-5
owned_files:
- scripts/openclaw/agents/felix-admin-escalation/SOUL.md
- scripts/openclaw/agents/felix-admin-escalation/USER.md
- scripts/openclaw/agents/felix-admin-escalation/TOOLS.md
- scripts/openclaw/agents/felix-admin-escalation/AGENTS.md
- scripts/openclaw/skills/escalation/SKILL.md
- docs/runbooks/escalation-ops.md
- scripts/vikunja/setup_vikunja.py
- tests/escalation/test_enumerate_candidates.py
role: implementer
tags: []
task_type: implement
---

# Work Package Prompt: WP01 – Author felix-admin-escalation workspace to #587 + full #724

## ⚡ Do This First: Load Agent Profile

Use the `/ad-hoc-profile-load` skill to load the agent profile specified in the frontmatter, and behave according to its guidance before parsing the rest of this prompt.

- **Profile**: `curator-carla`
- **Role**: `implementer`
- **Agent/tool**: `claude`

---

## Markdown Formatting

Wrap HTML/XML tags in backticks. Use language identifiers in code blocks.

---

## Objectives & Success Criteria

Re-home the `felix-admin-escalation` OpenClaw workspace content to its #587-canonical owner files, fully absorb the #724 Goals(11) cleanup, and fold the post-plan Codex coherence fixes — with **zero runtime-behavior change** and both #587 invariants preserved.

**Done when:**
- SOUL.md is voice/stance-only; USER.md is a filtered person-view (no date mechanics); TOOLS.md holds date-handling and has no Goals(11) or `Z` due-date examples.
- AGENTS.md has exactly the two narrow fixes (Z example + enforcement sentence) and nothing else changed.
- Every remaining Goals(11) reference is gone (SKILL.md, escalation-ops.md, setup_vikunja.py, the exclusion test).
- Escalation-scoped `validate_workspace.py` = `ok: true`; the conservation checklist all-passes; `pytest scripts/openclaw/agents/tests tests/openclaw tests/escalation` is green.

## Context & Constraints

Read these mission artifacts before editing — they are authoritative:
- `kitty-specs/author-escalation-workspace-01KXGZN1/data-model.md` — the **move-table** (every content block, its source, destination, and transform) + the invariants. Work it row by row.
- `kitty-specs/author-escalation-workspace-01KXGZN1/quickstart.md` §1 (exact edits), §2 (escalation-scoped validator), §3 (row-by-row conservation checklist).
- `kitty-specs/author-escalation-workspace-01KXGZN1/contracts/post-plan-review-resolutions.md` — why each folded fix exists (Codex HIGH-1/2/3/4, MED-5/6/7/8, LOW-9).
- `docs/design/openclaw-workspace-authoring-standard.md` — the #587 ownership model + the two invariants.
- The #584 capture precedent (`scripts/openclaw/agents/felix-admin-capture/`) — the same SOUL→voice-only, USER-date→TOOLS, privacy→stance pattern already applied there.

**Hard constraints:**
- **Scope (NFR-002):** touch ONLY the 8 `owned_files`. Do not edit IDENTITY.md, the `_private` path (deferred to #732), other agents, or the validator.
- **Invariant A (privacy):** the enforceable `04-Growth/_private/` rule must remain in BOTH AGENTS.md and TOOLS.md and be ABSENT from SOUL.md after your edits. Never delete it from AGENTS/TOOLS.
- **Invariant B (output discipline):** do not touch the Output Discipline block in AGENTS.md.
- **Zero behavior change:** candidate enumeration lives in the helper (`scripts/escalation/enumerate_candidates.py` + `scripts/common/vikunja_scope.py` = `[13]`), NOT the prompt — do not touch it. The only behavior-adjacent edit is the Z→ET-offset date-format fix (make it faithful).

## Branch Strategy

- **Strategy**: single_branch
- **Planning base branch**: feat/author-escalation-workspace
- **Merge target branch**: feat/author-escalation-workspace

> Populated by spec-kitty. Do not change manually.

## Subtasks & Detailed Guidance

### Subtask T001 – SOUL.md → voice/stance only

- **Purpose**: SOUL is the personality/voice layer per #587; strip operational role + enforceable policy.
- **Steps**:
  1. **Keep** the `## Voice — write as Kent` section (principles, escalation tone, words/phrases to avoid) — the keeper.
  2. On the "Structured and chunked" bullet, **trim** the trailing justification "Kent has ADD and processes best with clear, broken-out information." Keep the style rule itself ("Use headers and short sections. No walls of text.").
  3. **Remove** `## Purpose` (the "sole purpose is detecting overdue…" operational role — AGENTS `## Authority`/`## Scope` already owns it). **Preserve** the "insistence is a feature / hold Kent accountable" idea as a **one-line behavioral stance** in SOUL (it is genuinely voice/stance).
  4. **Reduce** `## Privacy boundary` to a single one-line behavioral stance (e.g. "I work only where I'm invited — I never touch Kent's private notes."). **Delete** from SOUL: the enforceable rule text, the filesystem path, and the mission-026 changelog parenthetical.
- **Files**: `scripts/openclaw/agents/felix-admin-escalation/SOUL.md`
- **Notes**: after this, SOUL must contain NO operational role, NO enforceable privacy rule/path, NO changelog. Cross-check against capture's SOUL.md for the target shape.

### Subtask T002 – USER.md → filtered person-view (remove Date handling)

- **Purpose**: USER is a filtered person-profile; TZ/API mechanics are operational and belong in TOOLS.
- **Steps**:
  1. **Keep** name / what-to-call / timezone / notes (including "ADD (managed)" as a neutral fact — matches #583 main) and the `## Context` block.
  2. **Remove** the entire `## Date handling` section (it moves verbatim-in-substance to TOOLS in T003).
- **Files**: `scripts/openclaw/agents/felix-admin-escalation/USER.md`

### Subtask T003 – TOOLS.md → receive Date handling; remove Goals(11); fix Z→ET-offset

- **Purpose**: TOOLS is the environment/setup home; also the #724 + HIGH-1 target.
- **Steps**:
  1. **Add** a `## Date handling` section carrying the content removed from USER: resolve all dates in America/New_York (not UTC); office2 runs UTC so use `TZ=America/New_York date`; include the ET offset (`-04:00` EDT / `-05:00` EST) when setting `due_date`; never use the `Z` (UTC) suffix for due dates.
  2. **#724**: change the overdue-query in-agent filter `project_id NOT IN (11, 13)` → `project_id NOT IN (13)`, and **delete** the `| 11 | Goals | … |` row from the Project exclusions table. Keep the Habits(13) row.
  3. **HIGH-1**: change the reschedule example `{"due_date": "2026-04-10T00:00:00Z"}` to the ET-offset form, e.g. `{"due_date": "2026-04-10T00:00:00-04:00"}` with a short note to use `-05:00` during EST — consistent with the no-Z rule you just added.
  4. **Leave** the `## Privacy` enforceable path line byte-unchanged (fleet canonicalization is deferred to #732).
- **Files**: `scripts/openclaw/agents/felix-admin-escalation/TOOLS.md`

### Subtask T004 – AGENTS.md → two narrow fixes only

- **Purpose**: keep AGENTS truthful + coherent after the SOUL reduction and the no-Z rule move. FR-008 permits ONLY these two edits.
- **Steps**:
  1. **HIGH-1**: in the Reschedule response-handling step, change `{"due_date": "<YYYY-MM-DD>T00:00:00Z"}` to the ET-offset form `{"due_date": "<YYYY-MM-DD>T00:00:00-04:00"}` (note `-05:00` for EST).
  2. **MED-5**: in the `## Privacy boundary` section, change the sentence "This is enforced in SOUL.md, AGENTS.md, and TOOLS.md." to "This is enforced in AGENTS.md and TOOLS.md; SOUL.md carries only a behavioral stance."
  3. Change **nothing else** in AGENTS.md — do NOT touch the Output Discipline block, Authority, Scope, tick workflow, or any other section.
- **Files**: `scripts/openclaw/agents/felix-admin-escalation/AGENTS.md`

### Subtask T005 – SKILL.md + escalation-ops.md → remove Goals(11) (FR-011)

- **Purpose**: full #724 absorption — the deterministic helper (`vikunja_scope.py` = `[13]`) is authoritative; these are stale docs.
- **Steps**:
  1. In `scripts/openclaw/skills/escalation/SKILL.md`: line ~50 `- \`project_id\` is NOT 11 (Goals) and NOT 13 (Habits)` → drop the Goals(11) clause, keep the Habits(13) exclusion (e.g. `- \`project_id\` is NOT 13 (Habits)`). Line ~60 `- Tasks in the Goals project (ID 11) — goals are anchors, not tasks` → remove that bullet. Do NOT alter the null-sentinel line (`0001-01-01T00:00:00Z` is a null marker, not a due-date write — leave it).
  2. In `docs/runbooks/escalation-ops.md` (~lines 29–34): remove "and Goals project (id=11)" from the excluded-projects sentence and drop "goals" from the "does NOT escalate" list, so only Habits(13) remains as the excluded project.
- **Files**: `scripts/openclaw/skills/escalation/SKILL.md`, `docs/runbooks/escalation-ops.md`

### Subtask T006 – setup_vikunja.py → remove dormant Goals filter block (FR-007)

- **Purpose**: dormant one-shot script still defines a "Goals" saved filter on the deleted project 11.
- **Steps**:
  1. Delete the saved-filter dict whose `"title": "Goals"` / `"filter": "project = 11 && done = false"` (around lines 68–74). Ensure the surrounding list stays valid Python (commas/brackets intact) and the other saved-filter definitions are unchanged.
- **Files**: `scripts/vikunja/setup_vikunja.py`

### Subtask T007 – test_enumerate_candidates.py → de-Goals(11) exclusion test (FR-011/LOW-9)

- **Purpose**: no active test should reference the deleted Goals project; keep the mechanism assertion.
- **Steps**:
  1. In `test_excluded_project_id_excluded` (~lines 169–172), the generic exclusion test uses `project_id=11` with excluded list `[11, 13]`. Switch to a non-Goals excluded id — e.g. keep the Habits case: `project_id=13` with `[13]`, OR use an arbitrary non-11 id (e.g. `99` / `[99]`) — whichever keeps the assertion `result == []` meaningful and does not collide with a neighboring test. Verify the adjacent `test_excluded_project_config_swap_changes_result` still passes.
- **Files**: `tests/escalation/test_enumerate_candidates.py`

### Subtask T008 – Validate + conservation checklist + suite green

- **Purpose**: prove invariants preserved, no content dropped, tests green.
- **Steps**:
  1. Run the escalation-SCOPED validator (quickstart §2) — do NOT rely on whole-fleet exit code (calendar/#635 fails Invariant B, out of scope). Expect `escalation ok: True`.
  2. Run the row-by-row conservation checklist (quickstart §3) — every line must print `OK:`.
  3. Run `python3 -m pytest scripts/openclaw/agents/tests tests/openclaw tests/escalation -q` — all green.
- **Files**: none (verification only).

## Test Strategy

- Reuse the existing suites: `scripts/openclaw/agents/tests` (validator/#587 tests incl. `test_agents_md_size.py` — note escalation is NOT capped, but do not regress `main`/`calendar`), `tests/openclaw`, `tests/escalation` (must stay green after T007's edit).
- No new tests are required (pure authoring + doc-hygiene). The escalation-scoped validator assertion + conservation checklist are the mission's acceptance gates.

## Risks & Mitigations

- **Invariant A regression** (SOUL reduction removes the enforceable rule from its home): mitigate by the conservation check `_private in AGENTS && TOOLS && NOT in SOUL`.
- **Z→offset over-reach**: keep the fix to the two reschedule examples; don't rewrite unrelated date text; the offset form must be faithful (`-04:00`/`-05:00`).
- **Test breakage from T007**: run `tests/escalation` after the edit; keep the mechanism assertion meaningful.
- **Scope creep**: 8 owned_files only; AGENTS limited to the two named edits.

## Review Guidance

- Confirm the move-table (`data-model.md`) is honored row by row and the conservation checklist all-passes.
- Confirm AGENTS.md diff is exactly two hunks (Z example + enforcement sentence) and the Output Discipline block is untouched.
- Confirm no active file references Goals/project 11 (`git grep -n "project.*11\|Goals" -- scripts/openclaw docs/runbooks scripts/vikunja tests/escalation` shows only intentional/archival hits).
- Confirm SOUL carries only voice + one-line stances; the enforceable privacy rule is gone from SOUL but present in AGENTS+TOOLS.

## Activity Log

- 2026-07-14T19:19:26Z – system – Prompt created.
- 2026-07-14T19:23:16Z – claude – shell_pid=78850 – Assigned agent via action command
- 2026-07-14T19:29:10Z – claude – shell_pid=78850 – WP01 implemented by curator-carla: validator ok, 469 tests green, conservation checklist all-pass (commit 975d916f)
