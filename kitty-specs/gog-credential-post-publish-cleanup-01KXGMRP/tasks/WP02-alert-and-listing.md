---
work_package_id: WP02
title: Alert construction + operator listing + their tests
dependencies:
- WP01
requirement_refs:
- FR-004
- FR-009
- FR-010
- NFR-002
- NFR-004
tracker_refs: []
planning_base_branch: feat/731-gog-cred-post-publish-cleanup
merge_target_branch: feat/731-gog-cred-post-publish-cleanup
branch_strategy: Planning artifacts for this mission were generated on feat/731-gog-cred-post-publish-cleanup. During /spec-kitty.implement this WP may branch from a dependency-specific base, but completed changes must merge back into feat/731-gog-cred-post-publish-cleanup unless the human explicitly redirects the landing branch.
subtasks:
- T005
- T006
- T007
- T008
agent: "claude"
shell_pid: "79576"
shell_pid_created_at: "1784046004.931338"
history:
- '2026-07-14: authored from spec + plan (post-plan Codex folded)'
agent_profile: python-pedro
authoritative_surface: scripts/security/credential_health_check/
create_intent: []
execution_mode: code_change
owned_files:
- scripts/security/credential_health_check/orchestrator.py
- scripts/security/credential_health_check/listing.py
- tests/security/test_orchestrator.py
- tests/security/test_listing.py
role: implementer
tags: []
---

## ⚡ Do This First: Load Agent Profile

Before reading anything else, load your assigned profile:
`/ad-hoc-profile-load python-pedro` (role: implementer). Adopt its identity,
boundaries, and initialization declaration, then proceed.

## Objective

Update the alert writer and the operator `--list` view to the collapsed single `dead`
classification produced by WP01. The alert's "investigate" guidance becomes
unconditional and the issue title prefix becomes `credential-liveness-dead`; the
`--list --liveness` view drops the fabricated `expected_next_expiration` column.

**Depends on WP01** — the `LivenessClassification` is now `{dead, probe-error}`.

Context: [plan.md](../plan.md) (IC-03, IC-07), [research.md](../research.md) (R-03, R-08),
[data-model.md](../data-model.md),
[contracts/liveness-classification.md](../contracts/liveness-classification.md).

## Subtasks

### T005 — Single-classification alert construction (`orchestrator.py`)

File: `scripts/security/credential_health_check/orchestrator.py`

1. `_build_liveness_issue_body`: make the "investigate at
   https://myaccount.google.com/permissions before re-auth" block **unconditional**
   (delete the `if r.classification == "dead-unexpected":` guard — every dead token is
   now genuinely unexpected). Keep the classification line, reason, recovery command,
   and close-out note.
2. `_process_liveness_alert`:
   - The `title_prefix` currently derives from
     `liveness_result.classification.removeprefix('dead-')`. With the single value
     `dead`, `"dead".removeprefix("dead-")` returns `"dead"` → title
     `credential-liveness-dead: <name>`. Either keep the `removeprefix` (still correct)
     or simplify to a literal `f"credential-liveness-dead: {cred.name}"`. Update the
     stale comment that enumerates "routine-7day"/"unexpected".
   - Leave the `probe-error` early-return, dedup, dry-run, labels
     (`P1-bug`, `area/infrastructure`), and logging intact.
3. Do not change cadence/staleness/manifest-quality processors.

### T006 — Remove the fabricated expiration from the `--list` view (`listing.py`)  [P]

File: `scripts/security/credential_health_check/listing.py`

1. Remove `expected_next_expiration` from the `LivenessListing` dataclass.
2. In `build_liveness_listings`: delete the `expiration = mtime + timedelta(days=7)`
   and `expected_next_expiration = expiration.date().isoformat()` lines, and the
   `expected_next_expiration="—"` assignments in both the no-`liveness_probe` branch
   and the exception branch. Keep `keyring_mtime_age` (factual).
3. In `render_liveness_table`: remove `"expected_next_expiration"` from `headers` and
   the corresponding cell from `_row`.
4. Drop the `timedelta` import if it becomes unused.

### T007 — Update orchestrator tests (`test_orchestrator.py`)

File: `tests/security/test_orchestrator.py`

1. Update any test that constructs a `LivenessResult`/stub with
   `classification="dead-routine-7day"` or `"dead-unexpected"` to use `"dead"`.
2. Update expected issue title assertions from
   `credential-liveness-routine-7day` / `credential-liveness-unexpected` to
   `credential-liveness-dead`.
3. If a test asserted the investigate block only for `dead-unexpected`, update it to
   expect the block for `dead` (now unconditional).
4. Keep probe-error / alive / dedup / dry-run cases behaviorally intact.

### T008 — Update listing tests (`test_listing.py`)  [P]

File: `tests/security/test_listing.py`

1. Remove assertions on `expected_next_expiration` (field and rendered column),
   including the cases near the previously-flagged lines (~269, ~329).
2. Keep assertions on `keyring_mtime_age`, `enabled`, `gog_account`,
   `recovery_command`, and the non-oauth2 skip behavior.
3. If a fixture set an mtime purely to drive the 7-day expiration, simplify it.

## Branch Strategy

Planning/base branch and final merge target are both
`feat/731-gog-cred-post-publish-cleanup`. This WP depends on WP01; branch from the
WP01 result per the implement flow. Execution worktrees are per-lane from `lanes.json`.

## Definition of Done

- [ ] T005–T008 complete.
- [ ] `orchestrator.py` files a `credential-liveness-dead: <name>` alert with an
      unconditional investigate block; no reference to the old classes remains.
- [ ] `listing.py` has no `expected_next_expiration`; `--list --liveness` renders the
      remaining columns.
- [ ] `python3 -m pytest tests/security/test_orchestrator.py tests/security/test_listing.py -v` passes.
- [ ] `grep -rnE "dead-routine-7day|dead-unexpected|routine-7day|expected_next_expiration" scripts/security/credential_health_check/orchestrator.py scripts/security/credential_health_check/listing.py` returns nothing.
- [ ] Branch coverage maintained.

## Risks / Reviewer guidance

- The `removeprefix('dead-')` on the single `dead` value is subtle — verify the
  emitted title is exactly `credential-liveness-dead: <name>` (a literal is clearer).
- Confirm `keyring_mtime_age` is retained in `listing.py` (only the projection is removed).
- Dedup vs pre-existing old-titled open issues (#629) is handled out-of-band at deploy
  (IC-08) — not this WP's concern, but do not add transitional dedup code here.

## Activity Log

- 2026-07-14T16:20:17Z – claude – shell_pid=79576 – Assigned agent via action command
