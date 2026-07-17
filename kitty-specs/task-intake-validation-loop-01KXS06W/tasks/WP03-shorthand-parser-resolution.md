---
work_package_id: WP03
title: Shorthand parser and token resolution
dependencies:
- WP01
requirement_refs:
- FR-005
- FR-006
tracker_refs: []
planning_base_branch: feat/task-intake-validation-loop
merge_target_branch: feat/task-intake-validation-loop
branch_strategy: Planning artifacts for this mission were generated on feat/task-intake-validation-loop. During /spec-kitty.implement this WP may branch from a dependency-specific base, but completed changes must merge back into feat/task-intake-validation-loop unless the human explicitly redirects the landing branch.
subtasks:
- T010
- T011
- T012
- T013
phase: Phase 2 - Engine
agent: "claude:opus:reviewer-renata:reviewer"
shell_pid: "62768"
shell_pid_created_at: "1784328720.142682"
history:
- at: '2026-07-17T21:55:00Z'
  actor: system
  action: Prompt generated via /spec-kitty.tasks
agent_profile: python-pedro
authoritative_surface: scripts/intake/shorthand.py
create_intent:
- scripts/intake/shorthand.py
- tests/intake/test_shorthand.py
execution_mode: code_change
model: claude-sonnet-5
owned_files:
- scripts/intake/shorthand.py
- tests/intake/test_shorthand.py
role: implementer
tags: []
---

# Work Package Prompt: WP03 — Shorthand parser and token resolution

## ⚡ Do This First: Load Agent Profile

Use `/ad-hoc-profile-load` to load the profile and behave per its guidance first.

- **Profile**: `python-pedro` · **Role**: `implementer` · **Agent/tool**: `claude`

---

## Branch Strategy

Planning branch / merge target: `feat/task-intake-validation-loop`. Worktree per `lanes.json`. **This WP is parallel with WP02** (both depend only on WP01) — own only `scripts/intake/shorthand.py` + its test; do not touch `scan_inbox.py`.

## Objective

Build the deterministic compact-shorthand parser + token resolver as a standalone module
(`scripts/intake/shorthand.py`) the apply engine (WP04) will consume. **No LLM in this
module** — it exposes a constrained hook for the agent's LLM-fallback, which it re-resolves
through the seam.

Read first: `contracts/helpers.contract.md` (`--unresolved` schema), `data-model.md`
(Compact-shorthand reply grammar + alias table), spec FR-005/006 + NFR-002,
`scripts/common/vikunja_refs.py` (`project_id`, `label_id(name,"kent")`), and
`docs/design/vikunja-configuration-design.md` (canonical taxonomy + short-names).

## Subtasks

### T010 — Sparse line grammar parser (FR-005)
Parse one line: `<n> [project-token] [f<1-4>] [quadrant-token] [due:<date>] [habit] [loe:<s|m|l>]`.
Every token after `<n>` is **optional** (sparse — a line supplies only the missing fields).
Return a structured `ParsedLine{n, project?, friction?, quadrant?, due?, habit?, loe?, raw,
unresolved_tokens[]}`. Lines are independent; a malformed token is captured, not fatal.

### T011 — Token resolution + alias table (FR-006, deterministic)
Resolve tokens to canonical names/ids via the seam, case-insensitive, using the documented
alias table: friction `f1/f2/f3/f4`; quadrant `do|sched|schedule|deleg|delegate|elim|eliminate`
→ `q:*`; project short-names (`personal`, `felix`, `clients`, `pointerhealth`, `spec-kitty`,
`intentional`, `habits`) → `project_id`. A token not in the alias table and not a
seam-declared name is left in `unresolved_tokens`. **Never** hardcode ids — go through
`vikunja_refs`.

### T012 — Constrained LLM-fallback re-resolution (FR-006, Directive-6)
Expose `resolve_with_fallback(parsed, unresolved_map)` where `unresolved_map` items are
strictly `{line, token, position, canonical_name}`. The module **re-resolves** each
`canonical_name` through `vikunja_refs` and **rejects** any raw id / free-form label/project
value. The LLM can only propose a canonical name; the module validates it. Anything still
unresolved stays echo-back-bound.

### T013 — Unit tests (NFR-002)
`tests/intake/test_shorthand.py`: 100% of documented projects + `f:`/`q:`/`t:`/`loe:` tokens
and their aliases resolve **without** any fallback; sparse lines (`1 personal`, `2 f2 schedule`,
`3 clients f3 do due:fri`); unknown token → `unresolved_tokens`; `--unresolved`-style fallback
accepts only canonical names and rejects a raw id / free-form value.

## Definition of Done
- Parser handles sparse lines; resolver covers the full documented taxonomy without LLM.
- Fallback interface is constrained to `{line,token,position,canonical_name}` + seam re-resolution.
- `pytest tests/intake/test_shorthand.py -q` green.

## Risks / reviewer guidance
- **Reviewer:** confirm sparse grammar (Codex #3), no hardcoded ids (all via seam), and the fallback cannot inject ids/free-form (Codex #7 Directive-6 leak). Verify NFR-002 100%-coverage test is real, not tautological.

## Implementation command
`spec-kitty agent action implement WP03 --agent claude`

## Activity Log

- 2026-07-17T22:41:12Z – claude:sonnet:python-pedro:implementer – shell_pid=59372 – Assigned agent via action command
- 2026-07-17T22:52:12Z – claude:sonnet:python-pedro:implementer – shell_pid=59372 – WP03 sparse shorthand parser + seam resolution + constrained fallback; 58 tests green
- 2026-07-17T22:52:21Z – claude:opus:reviewer-renata:reviewer – shell_pid=62768 – Started review via action command
