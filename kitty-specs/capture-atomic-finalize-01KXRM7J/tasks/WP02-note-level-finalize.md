---
work_package_id: WP02
title: Note-level finalize transaction + per-kind adapters
dependencies:
- WP01
requirement_refs:
- FR-001
- FR-002
- FR-003
- FR-004
- FR-006
- FR-007
- FR-010
- FR-011
- FR-012
- FR-015
- NFR-002
- NFR-003
- NFR-004
- NFR-005
tracker_refs: []
planning_base_branch: fix/capture-atomic-finalize
merge_target_branch: fix/capture-atomic-finalize
branch_strategy: Planning artifacts for this mission were generated on fix/capture-atomic-finalize. During /spec-kitty.implement this WP may branch from a dependency-specific base, but completed changes must merge back into fix/capture-atomic-finalize unless the human explicitly redirects the landing branch.
subtasks:
- T006
- T007
- T008
- T009
- T010
- T011
- T012
- T013
phase: Phase 2 - Core
agent: claude
history:
- at: '2026-07-17T18:30:00Z'
  actor: system
  action: Prompt generated via /spec-kitty.tasks
agent_profile: python-pedro
authoritative_surface: scripts/inbox/route_and_finalize
create_intent:
- scripts/inbox/route_and_finalize.py
- tests/inbox/test_route_and_finalize.py
execution_mode: code_change
model: claude-sonnet-5
owned_files:
- scripts/inbox/route_and_finalize.py
- scripts/inbox/route_someday.py
- scripts/inbox/route_journal_entry.py
- scripts/inbox/route_calendar_event.py
- scripts/openclaw/agents/main/felix-file-issue.py
- tests/inbox/test_route_and_finalize.py
role: implementer
tags: []
---

# Work Package Prompt: WP02 – Note-level finalize transaction + per-kind adapters

## ⚡ Do This First: Load Agent Profile

Use the `/ad-hoc-profile-load` skill to load the agent profile specified in the frontmatter, and behave according to its guidance before parsing the rest of this prompt.

- **Profile**: `python-pedro`
- **Role**: `implementer`
- **Agent/tool**: `claude`

---

## Branch Strategy

Planning branch: `fix/capture-atomic-finalize`. Merge target: `fix/capture-atomic-finalize`. Execution worktree per `lanes.json`.

## Objective

Build the **note-level finalize transaction** — the single deterministic operation the
capture agent runs per note. It consumes an agent-assembled routing plan, routes every
block, verifies every artifact, writes a per-block routing-log entry, and marks the note
processed **once** — fail-loud and retry-safe. This is the core fix for #746's silent loss.

**Read first and treat as authoritative**: `../contracts/route-and-finalize-cli.md`,
`../research.md` (D8, D9, D10, D11, D12), `../data-model.md`. Model the implementation on
the proven precedent `scripts/inbox/route_calendar_event.py::_run_finalize` (the shape you
are generalizing).

## Context / load-bearing invariants (do not violate)

- `mark_processed` MUST be invoked as a **subprocess** (`sys.executable -m
  scripts.inbox.mark_processed --path <p>`), never an in-process call — its `_private`
  refusal (exit 3), inbox-root validation, and symlink `.resolve()` guard live in `main()`.
- Exit code derives from the **note-level outcome**, never from an always-0 route step.
- `classify_content.split_blocks` yields multiple blocks per note; marking is note-level.
- Log-before-mark, note-level (D9): write every block's routing-log entry first; mark once
  after all are logged; a re-run reconciles from the log via WP01's `has_block`.

## Subtasks

### T006 — Finalize skeleton + CLI (`route_and_finalize.py`)
- CLI: `--source-path <note> --plan-file <plan.json> [--dry-run]` (mandatory `-m` form).
- Parse the `RoutingPlan` (`{note_filename, blocks:[{block_index, kind, payload|task_id}]}`).
- Orchestrate per-block, then a single note-level `mark_processed` subprocess.
- Emit ONE note-level result JSON (see contract: `finalized`/`needs_clarification`/`error`/
  `dry_run` with per-block sub-results). Exit non-zero on any block error.
- `--dry-run`: validate the plan + report `would_finalize` without side effects (credential-free).

### T007 — Finalize state machine
- Per block: `route → verify → write block routing-log entry (block-keyed, via WP01)`.
- After ALL blocks logged: `mark_processed` once.
- Re-run reconciliation: a block whose `has_block` key is already present is `skipped`
  (no side effect). Any block failure aborts before the mark → note stays unprocessed;
  already-logged blocks are not repeated next tick.

### T008 — someday + vikunja_task adapters
- `someday`: route via `route_someday.route_someday(...)`; verify the returned `task_id`
  resolves (fetch via `VikunjaClient`); block-key idempotency (skip create if logged).
- `vikunja_task`: two provenances — in-process (as someday) OR tasker-delegated (`--task-id`
  in the plan). For delegated, **do not create**: verify the id exists AND belongs to this
  note via source provenance (the `Source: <note-filename>` footer route_someday writes, or
  the task description); a mismatch/absent-provenance id is a finalize failure (FR-006).

### T009 — journal adapter
- Route via `route_journal_entry`. Add a per-block **sentinel** (e.g. an HTML comment
  `<!-- src: <filename>#<block_index> -->`) to the appended section; **verify-before-append**
  so a reprocess never duplicates a section (FR-010). Verify the target file/section exists.

### T010 — github_issue adapter
- Invoke `felix-file-issue.py` (main-agent helper). Treat a **null/missing issue number as a
  finalize failure** (FR-012); verify the issue exists (e.g. `gh issue view <n>`), then log
  (issue# destination) + contribute to the mark. Document the agent-hop in code comments.

### T011 — calendar fold adapter (preserve #737)
- Reuse `route_calendar_event`'s create/verify (`_run_create` + event_id check). Preserve the
  `needs_clarification` (incomplete payload) and `error` paths verbatim (NFR-003).
- **Remove the `finalized` + `routing_logged:false` leniency** (FR-015): under the note-level
  state machine a routing-log write failure leaves the note unprocessed (not finalized). Keep
  calendar's source-path idempotency key.

### T012 — empty disposition
- `--kind empty` (or an empty plan `blocks` list): first **validate the note body is genuinely
  empty / templater-only** (mirror `prescan.classify_file`'s empty detection). Refuse a
  non-empty body loudly (finalize failure). On pass: write a `kind=empty` routing-log entry +
  mark. This closes the silent-loss escape hatch (FR-007).

### T013 — Tests
- Per kind: success; route-failure (note unprocessed); verify-failure (note unprocessed);
  **route-success-then-mark/log-failure → re-run → NO double-create** (the retry-safety proof, NFR-004).
- **Multi-block note**: one block fails → whole note unprocessed; on a clean re-run the
  succeeded block is `skipped` and the note marks once (SC-002/SC-003).
- Delegated vikunja_task with a non-belonging id → failure (SC-004).
- github null issue# → failure. empty non-empty-body → failure.
- Calendar regression: create / needs_clarification / error behavior unchanged; the removed
  leniency test updated to the new semantics (SC-006).
- Mock all external calls (Vikunja/GitHub/calendar helper); no live services.

## Definition of Done
- `pytest tests/inbox/test_route_and_finalize.py` green + existing calendar tests green
  (adjusted only for the FR-015 leniency removal).
- Full suite `python3 -m pytest tests/inbox -q` green.
- No note can be marked processed except through a successful all-blocks finalize.
- Stdlib only (calendar helper subprocess uses its venv python, as today).

## Risks / reviewer guidance
- Keep adapters cohesive; if the module grows unwieldy, factor per-kind route+verify into
  small functions but keep ownership within this WP's `owned_files`.
- Reviewer: verify (a) the note is marked exactly once and only after all blocks log;
  (b) every kind has a retry-no-double-create test; (c) the calendar leniency removal is the
  ONLY calendar behavior change; (d) mark_processed stays a subprocess; (e) exit code reflects
  the note-level outcome.
