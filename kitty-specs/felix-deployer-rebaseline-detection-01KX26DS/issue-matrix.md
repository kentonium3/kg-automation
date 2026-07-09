# Issue matrix — felix-deployer-rebaseline-detection-01KX26DS

Per FR-037 of the spec-kitty-mission-review skill Gate-4. One row per issue referenced in spec.md.

| Issue | Title | Verdict | Evidence ref |
|-------|-------|---------|--------------|
| #685 | felix-deployer #618 auto-rebaseline does not fire for manifest deploys touching systemd units + openclaw cron config | fixed | This mission's target defect. Root cause (out-of-band pull → `pre==post` → observe skipped) fixed by WP01's watermark-based observe range (`rebaseline-observed-head.json`, `last_observed..post_pull_head`); the CLI-mutation gap (`openclaw-cron.txt` with no repo-file signal) closed by WP02's manifest `expected_baselines` + WP01's `fold_manifest_baselines`. Codex-found robustness gaps (diff-failure classification, same-tick clear grace rule, structured `_record_success`) folded in. Closes on mission merge. |
| #673 | Epic: Felix Bedrock Stabilization | deferred-with-followup | Parent epic; #685 is one child defect fixed here. The epic (F0–F3 reliability/observability program) continues via its other children. No action on #673 itself. |
| #557 | Rebaseline obligation for audited surfaces | deferred-with-followup | Standing policy this fix honors, not a bug closed here. The fix touches `scripts/deploy/**` whose `affected_baselines` is empty → rebaseline "not required" (recorded on merge). The obligation mechanism itself remains #557's domain. |
| #618 | Auto-rebaseline on deploy (deferred-confirm engine) | deferred-with-followup | The prior (merged) feature whose two defects this mission repairs; #685 is effectively #618's fast-follow. #618 itself needs no further action — referenced as the feature under repair. |
| #676 | Deterministic monitoring checks (deploy that surfaced #685) | deferred-with-followup | The merged deploy whose post-verification (2026-07-09) surfaced #685 (out-of-band pull + cron-removal). Referenced as the reproduction context; no action on #676 itself. |
| #621 | Rebaseline directives gap (audit.sh hashing / audited-surfaces mapping) | deferred-with-followup | Known separate gap (audit.sh hashes only `openclaw.json`; agent AGENTS.md unmonitored). Explicitly OUT OF SCOPE per spec; the manifest `expected_baselines` path (WP02) sidesteps it for CLI-mutation drift but does not close it. Tracked in #621. |

Valid `Verdict` values: `fixed`, `verified-already-fixed`, `deferred-with-followup`, `in-mission` (being fixed by a later WP in this mission; must reach a terminal verdict before mission `done`).
