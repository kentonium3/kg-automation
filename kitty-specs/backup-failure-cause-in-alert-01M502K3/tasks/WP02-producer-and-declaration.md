---
work_package_id: WP02
title: Backup script records the cause; inventory declares it
dependencies:
- WP01
requirement_refs:
- FR-001
- FR-002
- FR-003
- FR-004
- NFR-003
- C-001
- C-002
- C-004
- C-005
planning_base_branch: fix/backup-failure-cause-in-alert
merge_target_branch: fix/backup-failure-cause-in-alert
branch_strategy: Planning artifacts for this mission were generated on fix/backup-failure-cause-in-alert. During /spec-kitty.implement this WP may branch from a dependency-specific base, but completed changes must merge back into fix/backup-failure-cause-in-alert unless the human explicitly redirects the landing branch.
base_branch: kitty/mission-backup-failure-cause-in-alert-01M502K3
base_commit: 87258a114840c7aac4ac45239ab5757821fda342
created_at: '2026-10-15T15:42:57.816502+00:00'
subtasks:
- T003
- T004
- T005
- T006
history:
- at: '2026-10-15T16:00:00Z'
  actor: tasks
  action: Prompt generated via /spec-kitty.tasks (post-plan Codex review APPROVE)
agent_profile: python-pedro
authoritative_surface: scripts/office2/
execution_mode: code_change
lane: planned
model: claude-opus-5-5
owned_files:
- scripts/office2/restic-backup.sh
- tests/office2/restic_backup/test_pointer_emission.py
- tests/office2/restic_backup/test_ledger_reconciliation.py
- docs/design/architecture/data/service-inventory.json
role: implementer
tags: []
task_type: implement
tracker_refs: []
---

# Work Package Prompt: WP02 – Backup script records the cause; inventory declares it

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

- **Inputs**: `data-model.md` (pointer key, invariants, the `cause` member JSON) and `research.md` R2 (no schema bump) and R5 (classification).
- **The script**:
  - `scripts/office2/restic-backup.sh` runs as **root** via NOPASSWD sudo.
  - The sentinels are near lines 102–112. `write_state_pointer` is near line 115, and its heredoc is near lines 222–239. The trap is near line 258.
  - The fatal exits: not mounted (~302), repo inaccessible (~308), backup failed (~327).
- **Test harness**:
  - `tests/office2/restic_backup/test_pointer_emission.py` stubs `mountpoint` with `STUB_MOUNT_RC` and `restic` with `STUB_SNAPSHOTS_FAIL`, `STUB_BACKUP_RC`, `STUB_PRUNE_RC` and `STUB_CHECK_RC` on a PATH-prepended `bin/`.
  - It pins `FINAL_FOURTEEN_KEYS` (~line 48), asserted ~line 274.
  - `test_ledger_reconciliation.py` executes the script and fails if the emitted and declared key sets differ, in either direction.

**C-001 and C-002, non-negotiable:**
- The script must not invoke, source or import anything outside its current dependencies. The cause is data only.
- Do not add any install step. The live copy is hand-installed by Kent.

## Subtasks

### T003 – Producer (`restic-backup.sh`)

1. Next to the other sentinels, add `FAILURE_REASON=null`. Comment it in the file's style, citing this mission and #1067. Say that the value is a JSON literal from a fixed set, never derived from command output.
2. Set the reason immediately before each fatal `exit 1`, using the literal JSON string:
   - not mounted: `FAILURE_REASON='"backup_mount_missing"'`
   - repo inaccessible: `FAILURE_REASON='"repo_inaccessible"'`
   - backup failed: `FAILURE_REASON='"backup_failed"'`
3. In `write_state_pointer`, make the **very first statement** `local script_rc=$?`. Then, if `script_rc` is non-zero and `FAILURE_REASON` is still `null`, set it to `'"unclassified"'`. Exit 0 keeps `null`, which covers prune-only and integrity-only failures because the script still exits 0 for those.
   - Verify that `$?` in an EXIT trap holds the script's exit status. Check how the trap is installed: it is `trap write_state_pointer EXIT`, so the function is the trap body and `$?` is preserved on entry.
   - Add a test that would fail if anything ran before the capture.
4. Add `"failure_reason": $FAILURE_REASON` to the heredoc. Put it last, after `repo_fs_free_bytes`, with a correct comma.
5. Update the header comment block: a short paragraph on `failure_reason` with the four codes, in the style of the existing key paragraphs.
6. **Fail soft (NFR-003).** Nothing added may run under a condition that could abort the trap or change the exit status. No command substitution is needed at all; keep it pure assignments.

### T004 – Emission tests (`test_pointer_emission.py`)

- Rename `FINAL_FOURTEEN_KEYS` to a fifteen-key set that includes `failure_reason`, and update its comment.
- One test per fatal exit, asserting the exact code:
  - `STUB_MOUNT_RC=1` gives `backup_mount_missing`.
  - `STUB_SNAPSHOTS_FAIL=1` gives `repo_inaccessible`.
  - `STUB_BACKUP_RC=1` gives `backup_failed`.
- A happy path gives `null`. A prune failure (`STUB_PRUNE_RC=1`) gives `null` with exit 0.
- **`unclassified`**: drive a non-zero exit that is not one of the three. Prefer an existing stub lever. If none exists, add a minimal one to the harness: for example, a stub `restic` mode that kills the parent script, or a `forget` that triggers `exit 2` through a stubbed command the script calls. Document in the test why it represents an unclassified exit.
- **NFR-003**: for every fatal-path test, assert the script's exit status is unchanged (1) and that the pointer file exists and parses.
- Assert the emitted `failure_reason` is always a JSON string from the fixed set or `null`, never anything else.

### T005 – Inventory (`service-inventory.json`, `restic-backup` entry only)

- Under `health_check.key_ledger.diagnostic_only`, add `failure_reason` with a `reason` saying it is a diagnostic cause code, decorates alerts only, and never decides health (#1067).
- Add the `cause` member exactly as in `data-model.md`: key `failure_reason`, the four codes and their texts. Texts must be ≤ 120 characters.
- Update the `health_check.note` key count from fourteen to fifteen: eleven adjudicated is wrong, so state the real split, ten adjudicated and five diagnostic_only. Mention `failure_reason` and the `cause` member in one sentence.
- Prepend a concise `backup-failure-cause-in-alert-01M502K3 (#1067 — …)` entry to the top-level `updated_by`, following the existing pattern.
- Run `.venv/bin/python3 tooling/scripts/validate_architecture_data.py` and require 0 findings. This depends on WP01.

### T006 – Reconciliation

- `tests/office2/restic_backup/test_ledger_reconciliation.py` must pass with the new key. Update any "fourteen" prose in its docstring.
- Also run `tests/canary/test_inventory_health_checks.py`, which has restic prose and ledger asserts, and `tests/canary/test_tick_ledger_reconciliation.py`. Both must stay green.

## Definition of Done

- `.venv/bin/python3 -m pytest tests/office2/restic_backup tests/canary tests/architecture -q` passes.
- The validator reports 0 findings.
- `bash -n scripts/office2/restic-backup.sh` passes, and `shellcheck` raises no new warnings if it is installed.
- Commit message notes: "Rebaseline: not required — no audited surface touched."

## Risks

- **Heredoc JSON validity**: a missing comma breaks every pointer. The emission tests parse JSON on every path, so a missing comma fails them.
- Do not bump `schema_version` (research R2).

## Reviewer guidance

- Run the script tests yourself.
- Confirm the `$?` capture is the first statement.
- Confirm there is no new external command in the trap.
- Confirm the inventory texts match `data-model.md` exactly.
