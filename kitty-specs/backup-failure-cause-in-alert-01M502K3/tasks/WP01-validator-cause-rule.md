---
work_package_id: WP01
title: Validator learns the cause member (rule 9)
dependencies: []
requirement_refs:
- FR-004
- NFR-002
- C-003
- C-004
planning_base_branch: fix/backup-failure-cause-in-alert
merge_target_branch: fix/backup-failure-cause-in-alert
branch_strategy: Planning artifacts for this mission were generated on fix/backup-failure-cause-in-alert. During /spec-kitty.implement this WP may branch from a dependency-specific base, but completed changes must merge back into fix/backup-failure-cause-in-alert unless the human explicitly redirects the landing branch.
base_branch: kitty/mission-backup-failure-cause-in-alert-01M502K3
base_commit: 87258a114840c7aac4ac45239ab5757821fda342
created_at: '2026-10-15T15:36:57.951958+00:00'
subtasks:
- T001
- T002
history:
- at: '2026-10-15T16:00:00Z'
  actor: tasks
  action: Prompt generated via /spec-kitty.tasks (post-plan Codex review APPROVE)
agent_profile: python-pedro
authoritative_surface: tooling/scripts/
execution_mode: code_change
lane: planned
model: claude-opus-5-5
owned_files:
- tooling/scripts/validate_architecture_data.py
- tests/architecture/test_key_ledger_rules.py
role: implementer
tags: []
task_type: implement
tracker_refs: []
---

# Work Package Prompt: WP01 – Validator learns the cause member (rule 9)

## ⚡ Do This First: Load Agent Profile

Use the `/spk-charter-profile-load` skill to load the agent profile specified in the frontmatter, and behave according to its guidance before parsing the rest of this prompt.

- **Profile**: `python-pedro`
- **Role**: `implementer`
- **Agent/tool**: `claude`

---

## ⚠️ IMPORTANT: Review Feedback

Check `review_ref` via `spec-kitty agent tasks status`; address every item; record progress with `spec-kitty agent tasks add-history <WP> --note "..."`.

---

## Branch Strategy

- **Planning base branch**: `fix/backup-failure-cause-in-alert` · **Merge target branch**: `fix/backup-failure-cause-in-alert`. Worktrees come from `lanes.json`.

## Context

- **The authoritative shape**: `contracts/key-ledger-cause-member.md` (rule 9) and `data-model.md` § "Key ledger — new optional member `cause`".
- **The existing contract**: `kitty-specs/pointer-key-ledger-01M189P6/contracts/key-ledger.md`, structural rules 1–8.
- **The validator**: `tooling/scripts/validate_architecture_data.py`.
  - `KEY_LEDGER_MEMBERS` is near line 180.
  - `check_key_ledger` starts near line 354. Rule 1's unknown-member loop is near lines 381–385.

This WP lands **before** any inventory declares `cause`, so the inventory change in WP02 validates when it arrives.

## Objective

`cause` becomes a recognised **optional** `key_ledger` member, and a malformed `cause` cannot merge.

## Subtasks

### T001 – Accept and check `cause`

1. Add `"cause"` to `KEY_LEDGER_MEMBERS`. Update the authority comment there to cite `kitty-specs/backup-failure-cause-in-alert-01M502K3/contracts/key-ledger-cause-member.md` alongside the original contract.
2. In `check_key_ledger`, when `"cause" in ledger`, emit `Finding`s with a new rule id, `key-ledger-cause`, for each of these:
   - `cause` is not an object, or its members are not exactly `{"key", "codes"}`. Name the extra or missing members.
   - `key` is not a non-empty string.
   - `key` is not a member of `diagnostic_only` (including when `diagnostic_only` is absent or not a dict).
   - `key` is a member of `adjudicated`. Report this explicitly even though rule 3 already forbids a key being in both. The message must say a cause key may never decide health.
   - `codes` is not a non-empty object.
   - A code name does not match `^[a-z][a-z0-9_]{0,63}$`.
   - A code text is not a string, is empty or whitespace-only, is longer than 120 characters, or contains a control character (U+0000–U+001F or U+007F).
3. Absence of `cause` is always legal and yields nothing.
4. Follow the existing gating pattern exactly: the check is gated on `health_check`, never on `"key_ledger" in entry`. See the docstring for why.
5. Update the `check_key_ledger` docstring from "rules 1-8" to "rules 1-9".

### T002 – Tests (`tests/architecture/test_key_ledger_rules.py`)

Follow the file's existing fixture style; it trims a representative ledger.

- **Positive control**: a valid `cause` yields zero findings. Use the exact four codes and texts from `data-model.md`.
- **One test per failure bullet above**, each asserting the rule id `key-ledger-cause` and a message fragment.
- **Ratchet**: an unknown member such as `causes` still fails `key-ledger-unknown-member`.
- **Ratchet**: a ledger without `cause` stays clean.
- **Boundaries**: exactly 120 characters is accepted and 121 is rejected; a `\n` in the text is rejected.

## Definition of Done

- `.venv/bin/python3 -m pytest tests/architecture -q` passes.
- `.venv/bin/python3 tooling/scripts/validate_architecture_data.py` reports 0 findings on the current inventory, which has no `cause` yet.
- No other file is touched.

## Risks

- Do not loosen rule 1 for anything except `cause`.
- Keep the 120-character limit and the code-name regex as named module constants. WP04 imports nothing from the validator, but the constants must match `data-model.md`.

## Reviewer guidance

- Check that every bullet in T001 has a failing-fixture test.
- Check that the positive control uses the real `data-model.md` codes.
