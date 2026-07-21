---
work_package_id: WP05
title: Governance/instruction/constitution docs — remove absolute rule, keep repo boundary
dependencies: []
requirement_refs:
- FR-004
tracker_refs: []
planning_base_branch: feat/retire-private-folder-guards
merge_target_branch: feat/retire-private-folder-guards
branch_strategy: Planning artifacts for this mission were generated on feat/retire-private-folder-guards. During /spec-kitty.implement this WP may branch from a dependency-specific base, but completed changes must merge back into feat/retire-private-folder-guards unless the human explicitly redirects the landing branch.
subtasks:
- T017
- T018
- T019
agent: "claude:sonnet:reviewer-renata:reviewer"
history: []
agent_profile: curator-carla
authoritative_surface: ai-agents/
create_intent: []
execution_mode: code_change
owned_files:
- CLAUDE.md
- CODEX.md
- ai-agents/claude-instructions.md
- ai-agents/claude-code-instructions.md
- ai-agents/gemini-instructions.md
- docs/constitution/FELIX-CONSTITUTION.md
role: implementer
tags: []
shell_pid: "38015"
shell_pid_created_at: "1784651857.325672"
---

## ⚡ Do This First: Load Agent Profile

Load your profile via `/ad-hoc-profile-load curator-carla` before anything else.

## Objective

Remove the `_private` "absolute rule" from the governance/instruction docs while KEEPING the general
second-brain-repo boundary. Authoritative detail: `data-model.md` IC-04 rows; FR-004; charter anchor
"Two Constitutions — Don't Conflate". **Surgical, per-file edits — do not delete the repo boundary.**

## Subtasks

- **T017** — `CLAUDE.md` "Second Brain Boundary" §: remove ONLY the "**Absolute rule**:
  `~/second-brain/notes/04-Growth/_private/` is never read/written/referenced/logged" line. **KEEP**
  "The second brain lives at `~/second-brain/` (separate repo …). This repo contains the system that
  acts on the second brain. Do not conflate them. Do not write to second-brain paths …". Optionally
  add a one-line physical-exclusion note (the private content now lives in a separate vault office2
  never syncs). Do the same for `CODEX.md`.
- **T018** — `ai-agents/{claude,claude-code,gemini}-instructions.md`: remove the folder absolute-rule
  statement; keep any general "separate repo / don't write to the vault" guidance.
- **T019** — `docs/constitution/FELIX-CONSTITUTION.md`: reframe the directive/principle text that
  states the folder absolute rule to the physical-exclusion model; keep the general privacy/boundary
  principle intact. Do not renumber or restructure directives beyond the minimal edit.

## Definition of Done

- None of these files state the `_private` folder absolute rule as a current agent constraint.
- The general "second brain is a separate repo; do not write to it" guidance remains in CLAUDE.md and
  the constitution.
- `grep -n "_private" CLAUDE.md CODEX.md ai-agents/*.md docs/constitution/FELIX-CONSTITUTION.md`
  returns only intentional physical-exclusion narrative (if any), no absolute-rule enforcement.

## Risks & reviewer guidance

- Over-removal that deletes the still-valid repo boundary is the main risk (charter: Two
  Constitutions — Don't Conflate). Reviewer: confirm the repo boundary survives in CLAUDE.md + the
  constitution, and only the folder rule is gone.

## Activity Log

- 2026-07-21T16:26:29Z – claude:sonnet:implementer:implementer – shell_pid=22263 – Assigned agent via action command
- 2026-07-21T16:33:30Z – claude:sonnet:implementer:implementer – shell_pid=22263 – WP05 implemented in lane (commit 880c7308); absolute rule removed, repo boundary preserved, _private scrubbed. Transition from primary per #710.
- 2026-07-21T16:38:09Z – claude:sonnet:reviewer-renata:reviewer – shell_pid=38015 – Started review via action command
- 2026-07-21T16:39:03Z – user – shell_pid=38015 – Review passed: _private absolute rule removed from CLAUDE.md/CODEX.md/ai-agents/constitution; general repo boundary preserved (verified); physical-exclusion note added. FR-004 met.
