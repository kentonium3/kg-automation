---
work_package_id: WP01
title: Cutover AGENTS.md to v2 workflow + update runbook
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
planning_base_branch: main
merge_target_branch: main
branch_strategy: Planning artifacts for this feature were generated on main. During /spec-kitty.implement this WP may branch from a dependency-specific base, but completed changes must merge back into main unless the human explicitly redirects the landing branch.
base_branch: kitty/mission-habits-cutover-to-jsonl-v2-flow-01KS1FKE
base_commit: 79da069acb7077f24355a17a150a562c11c0e0ee
created_at: '2026-05-20T01:41:08.250536+00:00'
subtasks:
- T001
- T002
- T003
- T004
- T005
- T006
shell_pid: '15280'
history:
- date: '2026-05-20T01:35:51Z'
  event: created
  note: Phase 5 cutover — single WP for the AGENTS.md edit + runbook documentation update.
authoritative_surface: scripts/openclaw/agents/felix-admin-habits/
execution_mode: code_change
mission_id: 01KS1FKE0QHYEHZW684YEJNEPW
mission_slug: habits-cutover-to-jsonl-v2-flow-01KS1FKE
owned_files:
- scripts/openclaw/agents/felix-admin-habits/AGENTS.md
- docs/runbooks/habits-ops.md
priority: P1
tags: []
---

# WP01 — Cutover AGENTS.md to v2 workflow + update runbook

## Objective

Switch the deployed habits agent's standing orders (`scripts/openclaw/agents/felix-admin-habits/AGENTS.md`) from the v1 comment-parsing flow to the v2 JSONL-based flow. Update the operator runbook (`docs/runbooks/habits-ops.md`) to document the cutover. **Zero Python code changes** per spec constraint C-005.

After this WP merges and the operator runs the documented deploy command, the next morning cron tick will use the v2 helpers and write to the JSONL state log. Tuesday morning check-ins will no longer surface a workout (the original #306 bug).

---

## Context (read these before editing)

The implementer **MUST** read the following spec/plan artifacts before editing:

1. **Required content per section**: [`contracts/agents-md-sections.md`](../contracts/agents-md-sections.md) — exhaustive BEFORE/AFTER specification for each modified AGENTS.md section. This is the authoritative source for what the new file must contain.
2. **AGENTS.md section map**: [`data-model.md`](../data-model.md) Entity 1 — shows which sections change, which stay byte-identical, and the line-number anchors in the pre-mission file.
3. **Tactical content decisions**: [`research.md`](../research.md) — D1 (drop Step 3), D2 (Weekly report → JSONL), D3 (keep Comment format spec), D4 (grep testing), D5 (reuse existing deploy), D6 (light Action Logging update).
4. **Operator walkthrough**: [`quickstart.md`](../quickstart.md) — Steps 1-6 the operator will run post-merge. Confirms the deploy command shape and the smoke test sequence.
5. **Mission spec**: [`spec.md`](../spec.md) — FR/NFR/C requirements, success criteria, scenarios.

**Pre-mission baseline**:

- File: `scripts/openclaw/agents/felix-admin-habits/AGENTS.md`
- Size: 16,367 bytes
- sha256: `471545db698f9a50cee83eb72261a3fbbdccf55e2da7bf94a2dff733448a2de6`
- Deployed to: `/data/services/openclaw/habits-agent/AGENTS.md` on office2 (byte-identical pre-mission)

**Helpers referenced by the new AGENTS.md** (all already on main and deployed to office2; do NOT modify):

- `scripts/habits/reconcile_completions.py` — Step 0
- `scripts/habits/query_active_habits_v2.py` — Step 1
- `scripts/habits/exclude_completed_v2.py` — Step 2
- `scripts/habits/record_completion.py` — Completion marking

---

## Subtasks

### Subtask T001 — Restructure the Morning check-in section

**Purpose**: Replace the v1 step-list (Steps 1-6 with set_due_dates and v1 helpers) with the v2 step-list (Step 0 reconcile, v2 helpers, no Step 3, gap-preserved numbering).

**Steps**:

1. Open `scripts/openclaw/agents/felix-admin-habits/AGENTS.md`. Locate the `## Morning check-in` section (around line 68 in the pre-mission file).
2. Preserve the opening paragraph (the high-level intro to the section).
3. Replace the step-list body with the content specified in [`contracts/agents-md-sections.md`](../contracts/agents-md-sections.md) § "Section: `## Morning check-in`" § "AFTER — Required content". This includes:
   - A short framing paragraph that names Steps 0-4 as deterministic helpers and Steps 5-6 as LLM-mediated.
   - **Step 0 (NEW)**: `python3 -m scripts.habits.reconcile_completions` with helper behavior description (drift detection, vikunja-ui backfill) and exit code semantics.
   - **Step 1 (unchanged)**: keep the existing `compute_today.py` content verbatim (the contract preserves it).
   - **Step 2 (CHANGED)**: rename invocation to `python3 -m scripts.habits.query_active_habits_v2`. Update the description to reference the Vikunja-native filter (`due_date <= now/d AND done = false`) and project-scoping.
   - **Step 4 (CHANGED)**: rename invocation to `python3 -m scripts.habits.exclude_completed_v2`. Update the description to reference the JSONL state log directly (no LLM-mediated comment parsing). Mention the three sources excluded (whatsapp, vikunja-ui, manual).
   - **Step 4.5 (unchanged)**: helper failure handling — preserve verbatim.
   - **Step 5 (unchanged)**: format the check-in message — preserve verbatim.
   - **Step 6 (unchanged)**: output check-in text only — preserve verbatim.
4. Add a short NOTE explaining the gap at Step 3 (the previous Step 3 was set_due_dates.py; removed because Vikunja's native `repeat_after` from Phase 3 #306 now handles due_date roll automatically). Numbering stays 0/1/2/4/4.5/5/6 to preserve external references.

**Files modified**:

- `scripts/openclaw/agents/felix-admin-habits/AGENTS.md` (Morning check-in section only)

**Validation**:

- [ ] `grep -F "reconcile_completions" scripts/openclaw/agents/felix-admin-habits/AGENTS.md` returns ≥1 line.
- [ ] `grep -F "query_active_habits_v2" scripts/openclaw/agents/felix-admin-habits/AGENTS.md` returns ≥1 line.
- [ ] `grep -F "exclude_completed_v2" scripts/openclaw/agents/felix-admin-habits/AGENTS.md` returns ≥1 line.
- [ ] The Morning check-in section does NOT reference `query_active_habits.py` (the v1 name without `_v2`) or `exclude_completed.py` AS WORKFLOW INSTRUCTIONS.
- [ ] The Morning check-in section does NOT reference `set_due_dates.py` (per D1).

---

### Subtask T002 — Restructure the Completion marking section

**Purpose**: Replace the v1 inline-write instructions (agent calls POST /tasks/<id> done=true AND PUT /tasks/<id>/comments directly) with a single `record_completion.py` helper invocation. Add a small "State mapping table" subsection mapping Kent's natural language to the three valid states (`complete`, `incomplete`, `skipped`).

**Steps**:

1. Locate the `## Completion marking` section (around line 187).
2. Preserve subsections 1, 2, and 4 (Recognize natural language signals / Handle ambiguity / Confirm to Kent).
3. Replace subsection 3 ("Record completion in Vikunja") with the content specified in [`contracts/agents-md-sections.md`](../contracts/agents-md-sections.md) § "Section: `## Completion marking`" § "AFTER — Required content":
   - Document the `record_completion.py` invocation with all required flags (`--task-id`, `--title`, `--date`, `--state`, `--source`).
   - List the three-write atomic operation that the helper performs internally (POST done=true + PUT comment + JSONL append).
   - Document the helper's exit codes (0 success/idempotent, 1 Vikunja failure, 2 state_log failure, 3 validation error).
   - Explicitly forbid the agent from making inline POST/PUT calls for habit completion.
4. Add the "State mapping table" subsection mapping Kent's natural language to `complete` / `incomplete` / `skipped`. Include the ambiguity escape hatch (ask Kent to clarify per subsection 2).

**Files modified**:

- `scripts/openclaw/agents/felix-admin-habits/AGENTS.md` (Completion marking section only)

**Validation**:

- [ ] `grep -F "record_completion" scripts/openclaw/agents/felix-admin-habits/AGENTS.md` returns ≥1 line.
- [ ] The Completion marking section does NOT instruct the agent to POST `/api/v1/tasks/<id>` or PUT `/api/v1/tasks/<id>/comments` inline. (Manual inspection: read the section and confirm.)
- [ ] The State mapping table is present with all three valid states (`complete`, `incomplete`, `skipped`).

---

### Subtask T003 — Switch Weekly pattern report data source to JSONL

**Purpose**: Update the Weekly pattern report section's Step 2 from "query Vikunja comments and parse `[Felix]` entries" to "query the JSONL state_log via `state_log.read("habits", date_from=..., date_to=..., state="complete")`".

**Steps**:

1. Locate the `## Weekly pattern report` section (around line 285).
2. Preserve Steps 1, 3, 4 (date range determination, rate calculation, formatting). Only Step 2's data-source instructions change.
3. Replace Step 2 with the content specified in [`contracts/agents-md-sections.md`](../contracts/agents-md-sections.md) § "Section: `## Weekly pattern report`" § "AFTER — Required content". Include both Path A (Python module import) and Path B (CLI) options so the report's implementation style is preserved.
4. Document the returned record schema (task_id, title, date, state, source, note, timestamp) and the expected performance improvement (single JSONL read replaces N per-task HTTP fetches).
5. Adjust downstream Steps 3 and 4 ONLY if they reference comment-parsing field names; replace with the JSONL schema field names (`date`, `state`). If they reference logical concepts only, no change needed.

**Files modified**:

- `scripts/openclaw/agents/felix-admin-habits/AGENTS.md` (Weekly pattern report section only)

**Validation**:

- [ ] `grep -F "habits-history.jsonl" scripts/openclaw/agents/felix-admin-habits/AGENTS.md` returns ≥1 line (will be hit by either this subtask or T004).
- [ ] The Weekly pattern report Step 2 references `state_log` (either as Python module import or CLI invocation).
- [ ] Step 2 no longer instructs the agent to fetch comments per habit task for the weekly report flow.

---

### Subtask T004 — Light annotations on three sections (Comment format spec + Track record query + Action Logging)

**Purpose**: Add small pointer notes that clarify the new canonical data source without rewriting these sections. Three small edits in one subtask because each is a 2-5 line change.

**Steps**:

1. **Comment format specification section (~line 256)**: Add the short pointer note at the top of the section per [`contracts/agents-md-sections.md`](../contracts/agents-md-sections.md) § "Section: `## Comment format specification`" § "AFTER — Required content". The note clarifies that JSONL is canonical and the comment format is the Vikunja UI mirror written by `record_completion.py`. Keep the format spec body (regex, structure) — the spec is still the contract for the comment shape.
2. **Track record query section (~line 336)**: Replace explicit comment-parsing instructions with the `state_log.read("habits", task_id=<id>, ...)` pattern per [`contracts/agents-md-sections.md`](../contracts/agents-md-sections.md) § "Section: `## Track record query`" § "AFTER — Required content".
3. **Action Logging section (~line 411)**: Lightly annotate per [`contracts/agents-md-sections.md`](../contracts/agents-md-sections.md) § "Section: `## Action Logging`" § "AFTER — Required content". Specify that completion-action entries MUST include the (task_id, date, state) tuple that identifies the corresponding JSONL record. Include the illustrative example entry. Keep the rest of the section (action types, context fields, F014 semantics) byte-identical.

**Files modified**:

- `scripts/openclaw/agents/felix-admin-habits/AGENTS.md` (Comment format spec, Track record query, Action Logging sections only)

**Validation**:

- [ ] Comment format spec section contains the JSONL-canonical pointer note.
- [ ] Track record query section references `state_log.read`.
- [ ] Action Logging section mentions the (task_id, date, state) tuple cross-reference.

---

### Subtask T005 — Update docs/runbooks/habits-ops.md

**Purpose**: Document the cutover in the operator runbook so future-Kent (and any other operator) understands the workflow shape change. The deploy command itself is unchanged (per FR-007 and D5); only the surrounding documentation is updated.

**Steps**:

1. Open `docs/runbooks/habits-ops.md`.
2. Add a new "Phase 5 cutover (2026-05-20)" section near the top of the runbook (after the introduction, before the routine ops sections). Include:
   - **Date** the cutover landed (use 2026-05-20 as a placeholder; the operator can adjust at deploy time if needed).
   - **Issue reference**: GitHub #308.
   - **Workflow shape change summary**: bullet-list the v1→v2 transition (Step 0 reconcile NEW; Step 1/2 v2 helpers; Step 3 removed; Completion marking via record_completion; Weekly pattern report via JSONL).
   - **Pointer** to the [`quickstart.md`](../quickstart.md) operator walkthrough for the deploy procedure.
3. Verify the existing "Update workspace files" section (the deploy command) is untouched and continues to be the authoritative deploy procedure.
4. If the runbook has a "Workflow overview" or "Morning check-in" reference section, lightly update it to reflect the new step-list (or add a one-line note pointing to AGENTS.md as source of truth).

**Files modified**:

- `docs/runbooks/habits-ops.md`

**Validation**:

- [ ] The runbook has a Phase 5 cutover section with date, issue reference, and workflow-shape summary.
- [ ] The deploy command in the "Update workspace files" section is unchanged.
- [ ] `grep -F "Phase 5" docs/runbooks/habits-ops.md` returns ≥1 line.

---

### Subtask T006 — Validation: grep contract + size budget + commit

**Purpose**: Run the validation grep contract from research D4, confirm the size budget (NFR-002: < ~24,500 bytes), and commit the WP.

**Steps**:

1. Run the required-present grep assertions:
   ```bash
   grep -F "reconcile_completions" scripts/openclaw/agents/felix-admin-habits/AGENTS.md
   grep -F "query_active_habits_v2" scripts/openclaw/agents/felix-admin-habits/AGENTS.md
   grep -F "exclude_completed_v2" scripts/openclaw/agents/felix-admin-habits/AGENTS.md
   grep -F "record_completion" scripts/openclaw/agents/felix-admin-habits/AGENTS.md
   grep -F "habits-history.jsonl" scripts/openclaw/agents/felix-admin-habits/AGENTS.md
   ```
   All five must return ≥1 line.
2. Confirm `set_due_dates.py` is NOT in any active workflow section. If it appears only as a historical-context mention with explicit framing, that is acceptable. If it appears as a workflow instruction (the agent is told to invoke it), that is a FAILURE.
3. Check the size budget:
   ```bash
   wc -c scripts/openclaw/agents/felix-admin-habits/AGENTS.md
   ```
   Must be < 24,500 bytes per NFR-002. Pre-mission size was 16,367 bytes; expected post-mission size is ~17,500-19,500 bytes.
4. Visual review: read the modified sections and confirm that the sections marked "No change" in [`data-model.md`](../data-model.md) Entity 1 remain byte-identical to the pre-mission file. The unchanged sections are: Governance, Authority, Message identity, Output discipline, Scope, Habit management, Error handling, Privacy.
5. Stage and commit:
   ```bash
   git add scripts/openclaw/agents/felix-admin-habits/AGENTS.md docs/runbooks/habits-ops.md
   git commit -m "feat(WP01): Phase 5 — cutover AGENTS.md to v2 JSONL workflow + update runbook"
   ```
6. Mark subtasks done:
   ```bash
   spec-kitty agent tasks mark-status T001 T002 T003 T004 T005 T006 --status done
   ```
7. Move WP01 to for_review:
   ```bash
   spec-kitty agent tasks move-task WP01 --to for_review --note "Phase 5 cutover ready: AGENTS.md edited per contract; runbook updated; grep contract satisfied; size budget OK"
   ```

**Files modified**:

- None (validation + commit subtask)

**Validation**:

- [ ] All five required-present grep assertions return ≥1 line.
- [ ] `set_due_dates.py` does NOT appear as a workflow instruction.
- [ ] `wc -c scripts/openclaw/agents/felix-admin-habits/AGENTS.md` < 24,500.
- [ ] Sections marked "No change" in data-model.md Entity 1 are byte-identical to pre-mission. (Spot-check a few — Governance, Authority, Message identity, Privacy.)
- [ ] Commit landed; WP01 moved to for_review.

---

## Branch Strategy

- **Planning branch**: main (where this WP was authored)
- **Final merge target**: main
- **Execution worktree**: allocated by `finalize_tasks` per `lanes.json`. The implementing agent enters the worktree printed by `spec-kitty agent action implement WP01 --agent <name>`. The worktree's branch is the execution lane branch; merge target on completion is main.

---

## Definition of Done

- All 6 subtasks completed and committed.
- All five required-present grep assertions return ≥1 line.
- No v1 helper names appear AS WORKFLOW INSTRUCTIONS in the active workflow sections.
- `set_due_dates.py` does not appear as a workflow instruction.
- AGENTS.md size is < 24,500 bytes.
- `docs/runbooks/habits-ops.md` has the Phase 5 cutover section.
- WP01 moved to for_review with a clear note describing the changes.

---

## Risks

- **Risk**: Over-rewriting a section that should remain byte-identical (e.g., touching the Privacy section).
  **Mitigation**: [`data-model.md`](../data-model.md) Entity 1 enumerates the sections that change vs stay; validate via spot-checking unchanged sections.

- **Risk**: Implementer interprets D1 (drop Step 3) literally and renumbers the entire flow, breaking external doc references.
  **Mitigation**: The contract explicitly says "Keep the gap-numbered (0, 1, 2, 4, 4.5, 5, 6)". Step number gap is intentional.

- **Risk**: Grep assertions pass but the prose is semantically broken (e.g., implementer writes "DO NOT use reconcile_completions" — grep would still match).
  **Mitigation**: Manual visual review of the modified sections is part of T006. Reviewer should also catch this.

- **Risk**: Runbook update introduces a divergent deploy command (e.g., implementer rewrites the cat|ssh loop).
  **Mitigation**: FR-007 and D5 explicitly forbid this — the existing deploy command is the authoritative procedure.

---

## Reviewer Guidance

A reviewer should verify:

1. **All grep assertions pass** (run the five `grep -F` commands from T006).
2. **Semantic accuracy of new sections** — read Morning check-in, Completion marking, and Weekly pattern report end-to-end. Confirm the instructions make sense for an LLM consuming them at cron time. Pay attention to:
   - Step numbering preserves the gap at 3.
   - record_completion.py invocation has all the required flags.
   - Weekly report Step 2 documents both Path A and Path B (LLM picks).
   - State mapping table is present and complete.
3. **Untouched sections are byte-identical** to the pre-mission file. Spot-check at least: Governance, Authority, Message identity, Privacy.
4. **Runbook update** has the Phase 5 cutover documentation without modifying the existing deploy command.
5. **Size budget**: `wc -c scripts/openclaw/agents/felix-admin-habits/AGENTS.md` < 24,500.
6. **No scope creep**: WP01 must not include any of the out-of-scope items from [`spec.md`](../spec.md) § "Out of scope" (no v1 script deletions, no `_v2.py` renames, no data-flows.json updates).
7. **No code changes** (C-005): `git diff` should show changes ONLY to `scripts/openclaw/agents/felix-admin-habits/AGENTS.md` and `docs/runbooks/habits-ops.md`. Any Python file changes are a rejection-grade scope violation.
