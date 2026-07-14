---
work_package_id: WP01
title: Probe classification collapse + schema + probe tests
dependencies: []
requirement_refs:
- FR-001
- FR-002
- FR-003
- FR-005
- FR-008
- FR-009
- NFR-001
- NFR-002
- NFR-003
- NFR-004
tracker_refs: []
planning_base_branch: feat/731-gog-cred-post-publish-cleanup
merge_target_branch: feat/731-gog-cred-post-publish-cleanup
branch_strategy: Planning artifacts for this mission were generated on feat/731-gog-cred-post-publish-cleanup. During /spec-kitty.implement this WP may branch from a dependency-specific base, but completed changes must merge back into feat/731-gog-cred-post-publish-cleanup unless the human explicitly redirects the landing branch.
subtasks:
- T001
- T002
- T003
- T004
agent: "claude"
shell_pid: "76216"
shell_pid_created_at: "1784045406.077521"
history:
- '2026-07-14: authored from spec + plan (post-plan Codex folded)'
agent_profile: python-pedro
authoritative_surface: scripts/security/credential_health_check/
create_intent: []
execution_mode: code_change
owned_files:
- scripts/security/credential_health_check/liveness.py
- scripts/security/credential_health_check/manifest.py
- docs/design/architecture/data/credential-manifest.json
- tests/security/test_liveness.py
role: implementer
tags: []
---

## ⚡ Do This First: Load Agent Profile

Before reading anything else, load your assigned profile:
`/ad-hoc-profile-load python-pedro` (role: implementer). Adopt its identity,
boundaries, and initialization declaration, then proceed.

## Objective

The Google OAuth app is now **published**, so refresh tokens no longer expire on the
External+Testing 7-day cycle. Collapse the liveness probe's three-way classification
`{dead-routine-7day, dead-unexpected, probe-error}` into `{dead, probe-error}`, delete
the now-dead `#616` cycle-baseline machinery, remove the `reauth_marker_glob` schema
field and its config, and rewrite the probe tests. Every `invalid_grant` becomes a
single genuinely-unexpected `dead`.

Context: [spec.md](../spec.md), [plan.md](../plan.md) (IC-01, IC-02), [research.md](../research.md)
(R-03, R-04, R-05, R-06), [data-model.md](../data-model.md),
[contracts/liveness-classification.md](../contracts/liveness-classification.md).

## Subtasks

### T001 — Collapse classification + delete baseline machinery (`liveness.py`)

File: `scripts/security/credential_health_check/liveness.py`

1. Change the classification type:
   `LivenessClassification = Literal["dead", "probe-error"]` (remove
   `dead-routine-7day`, `dead-unexpected`).
2. In the `invalid_grant` branch of `probe_oauth_liveness`, DELETE the baseline
   computation entirely (the `_resolve_cycle_baseline(cfg)` call, the
   `expected_expiration`/`delta`/`baseline_label` logic, and the
   `if delta <= timedelta(hours=CYCLE_WINDOW_HOURS)` split). Replace with a single
   result:
   - `classification = "dead"`
   - `reason` = a concise message that the token failed the liveness probe
     (`invalid_grant`) and to run the recovery command. **Must not** mention "7-day",
     "Testing", "cycle boundary", or a baseline source label. Example:
     `"Refresh token is no longer valid (gog reported invalid_grant). Run the recovery command to re-mint."`
   - `recovery_command = cfg.recovery_command`
   - keep the existing `credential_dead` INFO log line, but drop the now-removed
     `classification`-split wording (log `classification=dead`).
3. DELETE the function `_resolve_cycle_baseline(...)` entirely.
4. DELETE the module constants `CYCLE_WINDOW_HOURS` and `EXPECTED_TTL_DAYS`.
5. Remove now-unused imports: `glob as _glob`, `timedelta`, and `Path` **iff** they
   become unused after the deletions (check — `Path`/`timedelta` may no longer be
   referenced). Keep `datetime`/`timezone` (still used for `now`).
6. Leave the alive path (`return None`), the timeout / FileNotFoundError /
   non-`invalid_grant` probe-error paths, and the `enabled is False` ValueError guard
   **unchanged**.

Note: the `dead` path no longer reads `keyring_file` at all — do not stat it.

### T002 — Remove `reauth_marker_glob` from the schema (`manifest.py`)

File: `scripts/security/credential_health_check/manifest.py`

1. In `LivenessProbeConfig`: delete the `reauth_marker_glob: Optional[str] = None`
   field and rewrite the docstring to drop the entire `reauth_marker_glob` / 7-day /
   keyring-fallback explanation (keep the first paragraph describing the required
   fields when `enabled`).
2. In `_validate_and_construct`: remove `"reauth_marker_glob"` from the `allowed_keys`
   set, and remove `reauth_marker_glob=liveness_probe_raw.get("reauth_marker_glob")`
   from the `LivenessProbeConfig(...)` constructor call.
3. Leave the `enabled ⇒ gog_account/keyring_file/recovery_command` required-field
   validation unchanged (`keyring_file` stays — it is not part of the removed
   machinery, see research R-04).

### T003 — Remove the config key + 7-day/Testing narrative (`credential-manifest.json`)

File: `docs/design/architecture/data/credential-manifest.json`

**This MUST land with T002 (atomicity — `manifest.py` rejects unknown liveness_probe
keys).**

1. In the `gog-credentials-keyring` credential's `liveness_probe` block, delete the
   `"reauth_marker_glob": "..."` key.
2. In that credential's narrative fields (e.g. `expiry_notes`/`notes`/any
   `liveness_probe` description) drop language asserting a 7-day Testing-app expiry
   cycle or the routine/unexpected classification; describe the probe as detecting an
   invalid/revoked token (single `dead`). Search the file for `7-day`, `Testing-app`,
   `routine-7day`, `reauth_marker_glob` and fix only the credential-liveness ones.
3. Keep JSON valid (trailing commas, etc.).

### T004 — Rewrite the probe tests (`test_liveness.py`)

File: `tests/security/test_liveness.py`

1. DELETE these tests (they exercise the removed split/machinery):
   `test_dead_routine_7day`, `test_dead_unexpected_too_early`,
   `test_dead_unexpected_too_late`, `test_routine_boundary_just_inside`,
   `test_routine_boundary_just_outside`, and the whole
   "reauth_marker_glob tests (#616)" block:
   `make_credential_with_reauth_marker`, `_set_mtime`,
   `test_reauth_marker_drives_routine_classification`,
   `test_reauth_marker_drives_unexpected_classification`,
   `test_reauth_marker_picks_max_mtime_across_multiple_files`,
   `test_reauth_marker_no_match_falls_back_to_keyring`,
   `test_keyring_fallback_message_labels_source`.
2. REPLACE the deleted timing tests with a single behavior test:
   `test_invalid_grant_is_dead` — `invalid_grant` in stderr → `classification == "dead"`
   and `recovery_command == cred.liveness_probe.recovery_command`, and assert the reason
   contains NO `"7-day"` / `"Testing"` / `"reauth"` / `"keyring+"` substring.
3. UPDATE `test_keyring_missing_is_probe_error` → rename/rework to
   `test_invalid_grant_keyring_missing_is_dead`: with the keyring file removed and
   `invalid_grant`, the result is now `classification == "dead"` (keyring is no longer
   consulted). Assert `recovery_command` is set.
4. UPDATE `test_recovery_command_in_dead_result` to drive a plain `invalid_grant`
   (no mtime setup) and assert `classification == "dead"` + recovery command present.
5. KEEP unchanged: `test_alive_returns_none`, `test_probe_timeout`,
   `test_probe_missing_binary`, `test_probe_other_failure`,
   `test_recovery_command_none_in_probe_error`,
   `test_raises_if_liveness_probe_disabled`, `test_probed_at_is_utc`.
6. Remove now-unused imports/helpers (`_set_keyring_mtime`, `timedelta`, `os` if
   unused). Keep `--cov-branch` green; add `# pragma: no branch` only on a defensive
   branch that is provably unreachable after the change (justify in a comment).

## Branch Strategy

Planning/base branch and final merge target are both
`feat/731-gog-cred-post-publish-cleanup`. Execution worktrees are allocated per lane
from `lanes.json` at implement time.

## Definition of Done

- [ ] T001–T004 complete; `liveness.py` and `manifest.py` free of `reauth_marker_glob`,
      `CYCLE_WINDOW_HOURS`, `EXPECTED_TTL_DAYS`, `_resolve_cycle_baseline`, and any
      `routine-7day`/`Testing-app` string.
- [ ] `credential-manifest.json` has no `reauth_marker_glob` and no 7-day/Testing
      framing for the gog credential; file is valid JSON.
- [ ] `python3 -m pytest tests/security/test_liveness.py -v` passes.
- [ ] `grep -rnE "reauth_marker_glob|CYCLE_WINDOW_HOURS|EXPECTED_TTL_DAYS|_resolve_cycle_baseline|routine-7day|Testing-app" scripts/security/credential_health_check/liveness.py scripts/security/credential_health_check/manifest.py` returns nothing.
- [ ] Branch coverage maintained.

## Risks / Reviewer guidance

- **Atomicity**: verify T002 (allowed_keys) and T003 (JSON key) are in the same commit;
  otherwise the routine raises `ManifestQualityError` on the gog credential every tick.
- Confirm the alive and all three probe-error paths are byte-for-byte behavior-preserved.
- Confirm `keyring_file` remains in the schema and required-when-enabled (NOT removed).
- Confirm no leftover import warnings (unused `timedelta`/`Path`/`glob`).

## Activity Log

- 2026-07-14T16:10:20Z – claude – shell_pid=76216 – Assigned agent via action command
