---
work_package_id: WP04
title: Apply engine
dependencies:
- WP01
- WP02
- WP03
requirement_refs:
- FR-007
- FR-009
- FR-010
- FR-012
- FR-013
- FR-014
- FR-017
tracker_refs:
- '750'
planning_base_branch: feat/task-intake-validation-loop
merge_target_branch: feat/task-intake-validation-loop
branch_strategy: Planning artifacts for this mission were generated on feat/task-intake-validation-loop. During /spec-kitty.implement this WP may branch from a dependency-specific base, but completed changes must merge back into feat/task-intake-validation-loop unless the human explicitly redirects the landing branch.
subtasks:
- T014
- T015
- T016
- T017
- T018
- T019
phase: Phase 3 - Apply
agent: "claude:sonnet:python-pedro:implementer"
shell_pid: "64436"
shell_pid_created_at: "1784328975.410204"
history:
- at: '2026-07-17T21:55:00Z'
  actor: system
  action: Prompt generated via /spec-kitty.tasks
agent_profile: python-pedro
authoritative_surface: scripts/intake/apply_reply.py
create_intent:
- scripts/intake/apply_reply.py
- tests/intake/test_apply_reply.py
execution_mode: code_change
model: claude-sonnet-5
owned_files:
- scripts/intake/apply_reply.py
- tests/intake/test_apply_reply.py
role: implementer
tags: []
---

# Work Package Prompt: WP04 — Apply engine

## ⚡ Do This First: Load Agent Profile

Use `/ad-hoc-profile-load` to load the profile and behave per its guidance first.

- **Profile**: `python-pedro` · **Role**: `implementer` · **Agent/tool**: `claude`

---

## Branch Strategy

Planning branch / merge target: `feat/task-intake-validation-loop`. Worktree per `lanes.json`. Consumes WP02's correlation record + WP03's `shorthand` module — import them, do not reimplement.

## Objective

Build `scripts/intake/apply_reply.py`: correlate Kent's reply to the right digest, apply
project + labels + applicable Tier-2 through the **kent token** with read-modify-write and
**family-replace**, and return a precise per-line status set. This WP closes **#750**
(kent-token writes only). **No LLM in the helper.**

Read first: `contracts/helpers.contract.md` (`apply_reply` — flags, invariants), `data-model.md`
(Apply result, Tier-2 matrix, family-replace rule, correlation), spec FR-007/009/010/012/013/
014/017 + SC-002/004/005/006/007/008/010/012 + NFR-003/005,
`scripts/vikunja/migrate_tasks.py` (`DEFAULT_KENT_TOKEN_FILE = /data/services/openclaw/secrets/
vikunja-api-kent`, RMW + readback diff, `list_labels`, refuse-felix-bot-token guard),
`scripts/habits/parse_morning_reply.py::correlate_reply_to_checkin` (content-based correlation),
`scripts/habits/record_completion.py` (`_reschedule_due_date_et` — ET end-of-day writer; there
is NO `scripts/common/et_datetime.py`, reuse this approach inline).

## Subtasks

### T014 — Correlation selection (FR-016)
Given a reply, select the correlated digest by the reply's **line-number set + task-title/
content evidence** within `--window-hours` (default 48), mirroring `correlate_reply_to_checkin`
semantics. Map each `<n>` → `task_id`. A number with no unambiguous task across live digests →
that line becomes `echoed_back`.

### T015 — kent-token apply + family-replace (FR-007/013, closes #750)
Write via the **kent token** only (`DEFAULT_KENT_TOKEN_FILE`; refuse the felix-bot path — reuse
migrate_tasks' guard). Read-modify-write with readback diff (Vikunja POST is partial-replace).
**Family-replace:** applying a new `q:` removes any existing `q:`-family label; a new `f:`
removes any existing `f:`-family label; all non-family labels preserved. `q:eliminate` → mark
the task **done** rather than requiring a project (FR-008). Sparse: apply only supplied fields.

### T016 — Tier-2 matrix + f:4 disposition (FR-010/017/009)
Implement the compatibility matrix (data-model): `due:` ET-EOD on `q:do`/`q:schedule`;
ignore-with-note on `q:eliminate`/`f:4`; `habit`→`t:habit` (note if already recurring);
malformed `loe:`/`due:` → `echoed_back`. When quadrant is `q:do`/`q:schedule` and no `due:` was
supplied → emit a **non-blocking** due follow-up. `f:4` → attach `f:4-overload`, record
**decomposition-pending**, one confirmation, not scheduled (SC-004).

### T017 — Per-line statuses + aggregates (FR-012/014)
Each line yields an independent status in `{applied, echoed_back, overload_flagged, noop,
not_found, already_done, moved_conflict, access_denied}`. `noop` only when live
project/labels/due already match, or the task is done/deleted (Codex #8). Emit `aggregates`
counts and append an `intake-apply-<ET-date>.jsonl` ledger.

### T018 — CLI
`apply_reply.py` flags: `--reply -` (stdin) / `--reply-file`, `--state-dir`, `--window-hours`,
`--unresolved <json>` (constrained; pass to WP03's `resolve_with_fallback`), `--dry-run`,
`--json`. Bound every Vikunja call with an explicit timeout (NFR-005).

### T019 — Unit tests (NFR-003)
`tests/intake/test_apply_reply.py` (mock Vikunja): family-replace preserves non-family labels
and never leaves two `q:`/`f:` (NFR-003 zero-clobber); each Tier-2 matrix cell; each per-line
status incl. `moved_conflict`/`not_found`/`access_denied`; idempotent re-apply = `noop`; f:4
terminal; `q:eliminate`→done; correlation across two same-day digests (SC-011); kent-token-only
writes.

## Definition of Done
- `apply_reply` applies a sparse shorthand reply correctly via the kent token, family-coherent, non-clobbering.
- All per-line statuses + Tier-2 matrix + f:4 disposition implemented; #750 path (felix-bot attach) impossible.
- `pytest tests/intake/test_apply_reply.py -q` green; timeouts on all external calls.

## Risks / reviewer guidance
- **Reviewer:** confirm kent-token-only (no felix-bot attach — #750/SC-008); family-replace never leaves two quadrants (Codex #2); noop only on true match (Codex #8); correlation is evidence-based (Codex #1); Tier-2 matrix matches data-model (Codex #5/#6); ET-EOD due dates (no `T00:00:00Z`, #733).

## Implementation command
`spec-kitty agent action implement WP04 --agent claude`

## Activity Log

- 2026-07-17T22:56:55Z – claude:sonnet:python-pedro:implementer – shell_pid=64436 – Assigned agent via action command
