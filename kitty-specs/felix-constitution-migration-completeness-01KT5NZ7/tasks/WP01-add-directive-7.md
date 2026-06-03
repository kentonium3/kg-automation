---
work_package_id: WP01
title: Add Directive 7
dependencies: []
requirement_refs:
- FR-001
- FR-002
- FR-003
- FR-004
- FR-005
- FR-006
- NFR-001
- NFR-002
- NFR-003
- C-001
- C-002
- C-003
- C-004
planning_base_branch: main
merge_target_branch: main
branch_strategy: Planning artifacts for this feature were generated on main. During /spec-kitty.implement this WP may branch from a dependency-specific base, but completed changes must merge back into main unless the human explicitly redirects the landing branch.
base_branch: kitty/mission-felix-constitution-migration-completeness-01KT5NZ7
base_commit: 94535080b587efa6c1608f063ae4c44b1bbc4f16
created_at: '2026-06-03T02:51:54.104191+00:00'
subtasks:
- T001
- T002
- T003
shell_pid: "83790"
agent: "claude"
history:
- timestamp: '2026-06-03T03:00:00Z'
  actor: claude:opus-4-7:planner
  action: created
authoritative_surface: docs/constitution/
execution_mode: code_change
owned_files:
- docs/constitution/FELIX-CONSTITUTION.md
tags: []
---

# WP01 — Add Directive 7

**Mission**: `felix-constitution-migration-completeness-01KT5NZ7` — [spec.md](../spec.md), [plan.md](../plan.md)
**Source issue**: [#514](https://github.com/kentonium3/kg-automation/issues/514)

## Objective

Insert Directive 7 ("Migration completeness — no orphaned transitional artifacts") into `docs/constitution/FELIX-CONSTITUTION.md` between Directive 6 and the "Privacy and Communication Boundaries" section. The directive codifies the principle that a migration is not done until all transitional artifacts are removed; it permits deferring cleanup to a follow-on issue only with explicit conditions (owner + forcing function + original mission acknowledges the weak link).

## Branch Strategy

- Planning base branch: `main`
- Final merge target: `main`
- Execution worktree: allocated automatically by `spec-kitty next` per `lanes.json`.

---

## Subtask T001 — Insert Directive 7

**Purpose**: Add the new directive at the correct location with prose that matches the existing format of Directives 1 through 6.

**Steps**:

1. Open `docs/constitution/FELIX-CONSTITUTION.md`. Read Directives 1 through 6 to internalize the established style (level-2 heading; opening sentence stating the principle; explanatory bullet list or paragraphs; closing `Rationale:` paragraph grounded in concrete incidents).
2. Identify the insertion anchor: the line immediately after Directive 6's closing Rationale paragraph and immediately before the `## Privacy and Communication Boundaries` heading.
3. Insert this directive verbatim (with the format and content adapted from the #514 draft, refined to match the established voice):

   ```markdown
   ## Directive 7: Migration Completeness — No Orphaned Transitional Artifacts

   A migration is not done when the new substrate ships. It is done when (1) the new substrate is in production AND (2) all transitional artifacts have been removed.

   Transitional artifacts to enumerate during `/spec-kitty.specify` and `/spec-kitty.plan` for any migration include:

   - Parity writes (dual-write code paths kept alive for rollback safety)
   - V1 readers that consume the soon-to-be-deprecated substrate
   - Schema fields kept only for the old shape
   - Feature flags that gate the swap
   - Dead callers in scripts and agents
   - Docstrings and comments that describe the old shape or the soak phase
   - Runbook sections, agent prompts, and architecture data entries that frame the substrate as transitional

   The spec MUST decide, for each enumerated artifact, between two options: (a) sequence its removal as a late work package within the same mission, gated on the soak window or another explicit criterion; or (b) explicitly accept the artifact as permanent infrastructure and rename it from its transitional framing to its long-term role.

   Soak windows and parity periods are temporary safety mechanisms. They MUST have an explicit owner and a calendar-bound forcing function (e.g., a deadline that flips a label, a follow-on issue that auto-promotes to current cycle on the soak end date). A soak-checklist mechanism without a forcing function is itself a planning defect — half-finished migrations are the worst state.

   Deferring cleanup to a separate follow-on issue is permitted only when (a) the cleanup work has its own explicit owner and forcing function, AND (b) the original mission's spec acknowledges this as a known weak link in the plan. Without both conditions, the cleanup MUST land within the same mission.

   This directive is operator-memory-linked: see `feedback_migration_no_vestiges` for the operator-stated rationale and `reference_openclaw_upgrade_gotchas` for the OpenClaw incident catalog the directive draws on.

   Rationale: load-bearing failures in #309 → #376 (escalation JSONL parity dual-write that ran 12+ days past the planned soak end with no runtime consumer; cleared by mission #62 on 2026-06-02) and the OpenClaw v2026.3.24 → v2026.5.28 plugin migration (WhatsApp moved from built-in to external plugin, undocumented, 19-hour silent gap during which `habits-morning-checkin`, `inbox-7am`, `escalation-daily`, and other crons all failed with `Unsupported channel: whatsapp`) demonstrate that without an explicit forcing function, cleanup work drifts indefinitely and the system accumulates half-completed migrations as permanent debt.
   ```

4. Save the file.

**Files**:
- `docs/constitution/FELIX-CONSTITUTION.md` (edit; insert ~25–35 lines)

**Validation**:
- [ ] `grep -nE "^## Directive 7:" docs/constitution/FELIX-CONSTITUTION.md` returns exactly one match.
- [ ] The match's line number is greater than the Directive 6 heading and less than the "Privacy and Communication Boundaries" heading.
- [ ] No other section is altered. The diff is purely additive at the insertion anchor.

---

## Subtask T002 — Run SC verification greps

**Purpose**: Confirm the success criteria from spec are met via the quickstart commands.

**Steps**:

1. Run SC-001:
   ```bash
   grep -nE "^## Directive 7:" docs/constitution/FELIX-CONSTITUTION.md
   ```
   Expected: exactly one match.
2. Run SC-001 positioning:
   ```bash
   grep -nE "^## Directive [0-9]+:|^## Privacy and Communication Boundaries" docs/constitution/FELIX-CONSTITUTION.md
   ```
   Expected: Directives 1, 2, 3, 4, 5, 6, 7 then Privacy heading, in that order.
3. Run SC-003 (incident citations):
   ```bash
   grep -nE "#309|#376|v2026\.5\.28" docs/constitution/FELIX-CONSTITUTION.md
   ```
   Expected: at least three hits inside the new Directive 7 section.

**Validation**:
- [ ] All three greps return the expected results.
- [ ] No regression in the existing Directive 1–6 prose (no off-target edits).

---

## Subtask T003 — Repo-wide audit for directive-index references

**Purpose**: Confirm no other file in the repo enumerates directives by number such that adding Directive 7 would create a stale cross-reference.

**Steps**:

1. Run:
   ```bash
   grep -rnE "Directive [1-6]:" docs/ ai-agents/ scripts/ --exclude-dir=archive --exclude-dir=__pycache__ | grep -v FELIX-CONSTITUTION.md
   ```
2. If the result is empty (no other directive-index exists outside the constitution itself), the audit passes — no other file needs updating.
3. If the result has matches, inspect each. If the match is a passing reference (e.g., "Directive 6 says...") rather than a numbered list, no update is needed. If the match is a directive-index that explicitly enumerates 1 through 6 as a closed list, append Directive 7 to it. Document the audit result in the commit message.

**Files** (read-only audit unless a stale index is found):
- All repo files matching the grep pattern.

**Validation**:
- [ ] Audit completed.
- [ ] Any stale directive-index found is updated (or the audit confirms none exist).

---

## Definition of Done

- [ ] T001, T002, T003 marked done.
- [ ] Directive 7 exists at the correct location in `FELIX-CONSTITUTION.md`.
- [ ] Quickstart greps return expected results.
- [ ] Repo-wide audit confirms no stale directive-index references.
- [ ] No other edits to other files (constitution-only mission).

## Reviewer guidance

A reviewer should verify, in order:

1. **The diff to `FELIX-CONSTITUTION.md` is purely additive** at the location between Directive 6 and the Privacy section. Any reordering, prose change, or edit outside the insertion point is a red flag.
2. **The new Directive 7's prose matches the established format**: level-2 heading; principle statement; enumeration of artifact categories; explicit two-option decision rule; conditions on deferral; closing Rationale paragraph with concrete incidents.
3. **The Rationale cites #309/#376 and the OpenClaw v2026.5.28 incident** explicitly, not just abstractly.
4. **The directive cross-references `feedback_migration_no_vestiges` and `reference_openclaw_upgrade_gotchas`** so the link from constitution → operator memory is traceable.
5. **No other file in the repo is altered** by this mission (the WP's owned_files declaration restricts the diff to `docs/constitution/FELIX-CONSTITUTION.md`).

## Risks

- **Drift from the established voice**: the constitution's tone is operator-facing and direct. The inserted prose should match that tone.
- **Hidden directive cross-references**: T003 catches the obvious case. A future audit might surface obscure ones.

## Activity Log

- 2026-06-03T02:51:56Z – claude – shell_pid=83790 – Assigned agent via action command
