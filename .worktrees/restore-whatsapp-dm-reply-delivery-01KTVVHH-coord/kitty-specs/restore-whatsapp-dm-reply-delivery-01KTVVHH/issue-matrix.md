# Issue matrix — restore-whatsapp-dm-reply-delivery-01KTVVHH

Per FR-037 of the spec-kitty-mission-review skill Gate-4. One row per issue referenced in spec.md.

| Issue | Title | Verdict | Evidence ref |
|-------|-------|---------|--------------|
| #588 | WhatsApp DM reply delivery silently fails — main/subagent generate replies but channel never sends | in-mission | This mission's source issue. WP01 verdict `Fix shape: H6 — upgrade openclaw 2026.5.28 → 2026.6.5` (commit `d6b5d2da`, decision ledger `DM-01KTW1CJVX0YPJZR27XZFRG95M`). WP02 builds upgrade-path deploy script; WP05 executes upgrade + 5-DM operator smoke per `contracts/journal-event-assertions.md`. Issue will be closed via `gh issue close 588` at mission merge with reference to merge commit and smoke evidence (`docs/diagnostics/restore-whatsapp-dm-reply-delivery-01KTVVHH-smoke.md`). Transitions to terminal verdict `fixed` (or `deferred-with-followup` if H6 fails and escalation path is taken per FR-009) at mission merge — must reach terminal before mission `done`. |
| #579 | Felix main agent stops relaying subagent replies — main/AGENTS.md truncation | verified-already-fixed | Closed via squash merge 37b3bf56 (2026-06-11). This mission's spec FR-006 explicitly preserves the #579 fix (main/AGENTS.md stays under 12K cap; felix-admin-calendar stays cleanly registered). H3 hypothesis was a rollback probe to verify the post-#579 AGENTS.md isn't the cause of #588 — WP01 verdict ruled H3 out (skipped per orchestrator since H6 desk verdict was unambiguous). #579 fix remains in force; no further action required by this mission. |
| #557 | Rebaseline obligation for audited surfaces | verified-already-fixed | #557 established the rebaseline framework (`docs/runbooks/security-baseline-ops.md`, `docs/design/architecture/data/audited-surfaces.json`, CI soft-reminder, merge-commit trailer requirement). This mission COMPLIES with the standing obligation: C-003 in spec.md, WP05 T025 executes the rebaseline command, and the mission's merge commit will carry `Rebaseline: completed at <ISO8601-UTC>`. The framework itself is not modified by this mission; it is honored. No follow-up required. |

Valid `Verdict` values: `fixed`, `verified-already-fixed`, `deferred-with-followup`, `in-mission` (being fixed by a later WP in this mission; must reach a terminal verdict before mission `done`).

## Notes

- `#588` carries `in-mission` verdict during per-WP approvals (WP01 → WP02 → WP03/WP04 → WP05). Transitions to terminal verdict at mission merge:
  - `fixed` — if WP05 operator smoke passes (5-DM acceptance per SC-001..SC-007); will close #588 via `gh issue close 588 --comment "fixed by <merge SHA> per mission restore-whatsapp-dm-reply-delivery-01KTVVHH; H6 verdict (openclaw 2026.6.5 upgrade) validated by post-deploy smoke."`
  - `deferred-with-followup` — if WP02 takes the FR-009 escalation path (H6 didn't fix; vendored regression confirmed); #588 stays open with link to the new internal tracking issue WP02 filed.
- `#579` listed because spec.md FR-006 references it as a regression-prevention invariant (must not undo the truncation fix). Verdict `verified-already-fixed` is correct — the fix is in production and this mission preserves it.
- `#557` listed because spec.md C-003 references it as the audit-surface + rebaseline-trailer obligation. Verdict `verified-already-fixed` is correct — the framework exists and this mission complies via WP05.
