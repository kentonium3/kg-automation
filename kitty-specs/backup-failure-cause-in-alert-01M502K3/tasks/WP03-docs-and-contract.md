---
work_package_id: WP03
title: Operator docs and contract amendment
dependencies:
- WP02
requirement_refs:
- FR-009
- C-002
planning_base_branch: fix/backup-failure-cause-in-alert
merge_target_branch: fix/backup-failure-cause-in-alert
branch_strategy: Planning artifacts for this mission were generated on fix/backup-failure-cause-in-alert. During /spec-kitty.implement this WP may branch from a dependency-specific base, but completed changes must merge back into fix/backup-failure-cause-in-alert unless the human explicitly redirects the landing branch.
subtasks:
- T007
- T008
- T009
history:
- at: '2026-10-15T16:00:00Z'
  actor: tasks
  action: Prompt generated via /spec-kitty.tasks (post-plan Codex review APPROVE)
agent_profile: python-pedro
authoritative_surface: docs/
execution_mode: planning_artifact
model: claude-opus-5-5
owned_files:
- docs/runbooks/restic-backup-ops.md
- docs/design/architecture/service-inventory.md
- docs/design/architecture/observability-and-alerting.md
- kitty-specs/pointer-key-ledger-01M189P6/contracts/key-ledger.md
role: implementer
tags: []
task_type: implement
tracker_refs: []
---

# Work Package Prompt: WP03 – Operator docs and contract amendment

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

- **What this documents**: WP02 made `restic-backup.sh` write `failure_reason`, and declared it in the inventory with a `cause` member: four codes plus texts. See `data-model.md`.
- **The canary side lands in WP04.** WP04 also adds a test asserting every declared code appears in the runbook, so the runbook **must** name all four codes literally.

## Subtasks

### T007 – Runbook (`docs/runbooks/restic-backup-ops.md`)

1. Add a section, **"Failure cause in alerts (`failure_reason`, #1067)"**, near the pointer-field table. It contains:
   - A table: code | what happened | what to do. Use the four codes exactly.
     - `backup_mount_missing`: reseat or remount the drive per the existing drive-recovery steps; link to them.
     - `repo_inaccessible`: check the password file, check repo locks (`restic unlock` per existing guidance), and run `restic check`.
     - `backup_failed`: read `backup-<date>.log`.
     - `unclassified`: read the log; the script exited by an unexpected path.
   - One sentence saying the cause decorates the canary and health-check alert text and never changes health or alert frequency.
   - One sentence saying the cause appears only after the new `backup.sh` is hand-installed.
2. Add `failure_reason` to the pointer-field table, if one lists the keys, consistent with how the other diagnostic keys are described.
3. In § "Operator handoff", add a short dated note: the #1067 version of the script is outstanding until installed. After installing, confirm `backup-script-drift` reports `converged` and that the next pointer has `"failure_reason": null`.
4. Find the existing line that says the script "does not alert directly from `backup.sh` yet; that is tracked as" #1067 (around line 312) and correct it. #1067 was resolved by naming the cause in the canary alert; a direct alert from root was rejected (#899). Keep the rest of the paragraph.

### T008 – Architecture prose [P]

- In `docs/design/architecture/service-inventory.md` and `observability-and-alerting.md`, wherever `key_ledger` members are enumerated, add `cause` (optional; rule 9). Wherever restic pointer keys are counted, update the count.
- Do not touch the JSON; WP02 owns it.
- If neither file enumerates members or counts, make no change and record "no change needed" in the WP history.

### T009 – Contract amendment [P] (`kitty-specs/pointer-key-ledger-01M189P6/contracts/key-ledger.md`)

- **Add only; rewrite nothing.** Append a section headed `## Amendment 2026-10-15 — optional \`cause\` member (rule 9)`.
- It states that rule 1's allowed set now also includes the optional `cause`, and it restates rule 9 by reference to `kitty-specs/backup-failure-cause-in-alert-01M502K3/contracts/key-ledger-cause-member.md` with a one-paragraph summary.
- Directly under rule 1 in the original text, add a single line: `> Amended 2026-10-15: see "Amendment … rule 9" below.` This is the only in-place insertion.
- Rationale, for the WP history: this file is the authority the validator, ledger and tests cite, so leaving rule 1 silently stale would mislead. The edit is add-only and dated.

## Definition of Done

- `.venv/bin/python3 tooling/scripts/validate_docs.py` is OK, or the repo's doc validator under its actual path; the pre-commit hook runs it.
- `.venv/bin/python3 tooling/scripts/check_doc_links.py` is clean, if it is present.
- All four codes appear literally in the runbook.

## Reviewer guidance

- Confirm the contract edit is add-only: `git diff` shows only additions in `key-ledger.md`.
- Confirm the stale "#1067 tracks a direct alert" sentence is corrected.
