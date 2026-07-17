---
work_package_id: WP01
title: Routing-log block-keyed schema
dependencies: []
requirement_refs:
- FR-009
- FR-010
tracker_refs: []
planning_base_branch: fix/capture-atomic-finalize
merge_target_branch: fix/capture-atomic-finalize
branch_strategy: Planning artifacts for this mission were generated on fix/capture-atomic-finalize. During /spec-kitty.implement this WP may branch from a dependency-specific base, but completed changes must merge back into fix/capture-atomic-finalize unless the human explicitly redirects the landing branch.
subtasks:
- T001
- T002
- T003
- T004
- T005
phase: Phase 1 - Foundation
agent: "claude:sonnet:python-pedro:implementer"
shell_pid: "82399"
shell_pid_created_at: "1784313800.985211"
history:
- at: '2026-07-17T18:30:00Z'
  actor: system
  action: Prompt generated via /spec-kitty.tasks
agent_profile: python-pedro
authoritative_surface: scripts/inbox/routing_log
create_intent: []
execution_mode: code_change
model: claude-sonnet-5
owned_files:
- scripts/inbox/routing_log.py
- scripts/inbox/append_routing_entry.py
- tests/inbox/test_routing_log.py
- tests/inbox/test_append_routing_entry.py
role: implementer
tags: []
---

# Work Package Prompt: WP01 – Routing-log block-keyed schema

## ⚡ Do This First: Load Agent Profile

Use the `/ad-hoc-profile-load` skill to load the agent profile specified in the frontmatter, and behave according to its guidance before parsing the rest of this prompt.

- **Profile**: `python-pedro`
- **Role**: `implementer`
- **Agent/tool**: `claude`

---

## Branch Strategy

Planning branch: `fix/capture-atomic-finalize`. Merge target: `fix/capture-atomic-finalize`. Your execution worktree is allocated per the computed lane in `lanes.json`.

## Objective

Evolve the inbox routing log (`scripts/inbox/routing_log.py`) from a filename-keyed
dedup substrate into a **per-block** substrate, so a multi-block note can record one
entry per routed block without one block masking another. This is the foundation the
note-level finalize (WP02) and health rail (WP03) build on.

Read first: `../research.md` (D10), `../data-model.md` (RoutingEntry), and the current
`scripts/inbox/routing_log.py` + `scripts/inbox/append_routing_entry.py`.

## Context

Today `RoutingEntry` = `filename, issue_number, vikunja_task_id, routed_at, note_excerpt,
kind (issue_task|calendar), destination`, and `RoutingLogReader.has(filename)` dedups on
filename only. Multi-block notes and the new kinds need a block-level key.

## Subtasks

### T001 — Extend `RoutingEntry` with block fields
- Add `block_index: Optional[int] = None` and `block_hash: Optional[str] = None` to the
  frozen dataclass (defaults keep old call sites + old on-disk rows valid).
- `to_dict()` includes them; JSONL round-trips.

### T002 — Grow the `kind` vocabulary + destination
- Accept `someday`, `journal`, `vikunja_task`, `github_issue`, `empty` in addition to the
  existing `issue_task`, `calendar`. Keep it permissive (a `str`), but document the set.
- Ensure `destination` is populated per kind by the writer (task id / issue# / file path /
  event id / "" for empty).

### T003 — Block-key helpers
- Add a stable `block_hash(block_text: str) -> str` helper (e.g. sha256 hexdigest of the
  normalized block text) — deterministic across ticks for unchanged content.
- Add `RoutingLogReader.has_block(filename, block_index, block_hash) -> bool`: true when an
  entry matches all three. **Legacy fallback**: if the log has a matching-`filename` entry
  that carries no `block_index` (a pre-WP01 row), treat the filename as satisfied (preserves
  #737 calendar dedup). Keep the existing `has(filename)` for the health rail's note-level check.
- Cache semantics unchanged (read-once per reader instance).

### T004 — Update `append_routing_entry` CLI
- Grow `--kind` choices to the full set; add `--block-index` and `--block-hash` optional args
  and a generic `--destination`. Keep the existing positional/`--event-id` behavior working
  (back-compat). This CLI stays as a low-level surface; WP02's finalize writes entries via the
  library directly, and WP04 removes the agent's standalone use of it.

### T005 — Tests
- Round-trip: entry with block fields serializes + reads back.
- `has_block` true/false; **legacy row** (no block_index) satisfies filename fallback.
- Malformed-line skip + missing-filename skip still work (unchanged).
- All new `kind` values accepted; `destination` populated.

## Definition of Done
- All subtasks complete; `pytest tests/inbox/test_routing_log.py tests/inbox/test_append_routing_entry.py` green.
- Backward compatibility proven by a legacy-row test.
- No behavior change for existing `has(filename)` callers.
- Stdlib only; no new dependencies.

## Risks / reviewer guidance
- Block-hash stability: normalize before hashing (strip trailing whitespace) so an unchanged
  note re-hashes identically across ticks.
- Do not break the `RoutingLogReader` filename cache used elsewhere.
- Reviewer: confirm legacy on-disk rows (no block fields) still dedup and never raise.

## Activity Log

- 2026-07-17T18:43:34Z – claude:sonnet:python-pedro:implementer – shell_pid=82399 – Assigned agent via action command
