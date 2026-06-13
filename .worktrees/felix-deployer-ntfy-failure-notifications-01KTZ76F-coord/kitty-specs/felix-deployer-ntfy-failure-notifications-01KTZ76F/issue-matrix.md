# Issue matrix — felix-deployer-ntfy-failure-notifications-01KTZ76F

Per FR-037 of the spec-kitty-mission-review skill Gate-4. One row per issue referenced in spec.md.

| Issue | Title | Verdict | Evidence ref |
|-------|-------|---------|--------------|
| #595 | felix-deployer applier dispatches to nonexistent openclaw cron flags — failure notifications silently fail | in-mission | Mission source issue. WP01 swaps the notify substrate end-to-end from openclaw cron to ntfy.sh: `scripts/deploy/felix-deployer/notify.py` rewritten (commit `8ecc65bb`); `_tick.py` call-site updated; comprehensive new tests in `tests/deploy/test_notify.py` cover the 7-code closed `error_code` enum, the redact-then-truncate boundary invariant, and NFR-003 import-time-no-side-effects; `tests/deploy/test_deployer.py` renamed `dispatch_failure_dm`→`dispatch_failure_notification` and `PHASE_TO_DM_PHASE`→`PHASE_TO_NOTIFY_PHASE`. Verdict transitions to `fixed` once all three WPs land and the merge commit closes the issue (per spec C-004 the code-only acceptance applies; operator-driven post-merge `--rollback`+`--apply` redeploy and the deliberate-failure smoke are tracked outside this mission). |
| #557 | Rebaseline obligation for audited surfaces | verified-already-fixed | #557 established the rebaseline framework (`docs/runbooks/security-baseline-ops.md`, `docs/design/architecture/data/audited-surfaces.json`, CI soft-reminder, merge-commit trailer requirement). This mission COMPLIES with the standing obligation: spec FR-015 captures the rebaseline-trailer requirement; WP01 modifies `scripts/deploy/felix-deployer/notify.py` + `_tick.py` (both in `audited-surfaces.json`). The framework itself is not modified by this mission; it is honored at merge time by recording `Rebaseline: completed at <ISO8601-UTC>` in the merge commit and by the operator running the canonical reset command on office2. No follow-up required from this mission. |

Valid `Verdict` values: `fixed`, `verified-already-fixed`, `deferred-with-followup`, `in-mission` (being fixed by a later WP in this mission; must reach a terminal verdict before mission `done`).

## Notes

- `#595` verdict remains `in-mission` through the WP-by-WP approval flow and will transition to `fixed` at mission-review time once WP02 (bootstrap-script step-5 removal + systemd `EnvironmentFile=` + env.sample) and WP03 (architecture data updates) also land and the mission merges to main. WP01 alone delivers the substantive code change but does not deliver the operationally-redeployable system; WP02 is required for the post-merge bootstrap to succeed.
- The merge-commit trailer MUST record `Rebaseline: completed at <ISO8601-UTC>` once the operator runs the canonical command on office2 (per `audited-surfaces.json`'s coverage of the touched paths). This is the standing #557 obligation, not a new task.
