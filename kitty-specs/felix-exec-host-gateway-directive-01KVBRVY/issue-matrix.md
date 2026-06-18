# Issue matrix — felix-exec-host-gateway-directive-01KVBRVY

Per FR-037 of the spec-kitty-mission-review skill Gate-4. One row per issue referenced in spec.md.

| Issue | Title | Verdict | Evidence ref |
|-------|-------|---------|--------------|
| #603 | Bug: inbox-5pm tool-invocation failure — `exec host=node requires a paired node` false-positive cron alert | fixed | WP01 (commit 671fde82) ships the identical `host=gateway`-only hard rule in all four Felix sub-agent AGENTS.md (FR-001..003/005, NFR-001 verified in-repo). The code fix is delivered and merged; the GitHub issue's operational close-condition is the post-deploy 7-day zero-`host=node` window (NFR-002 / SC-003) — verification of the shipped fix, not remaining mission work. |
| #557 | Rebaseline obligation for audited-surface changes | verified-already-fixed | The rebaseline mechanism #557 calls for is already implemented and automated via #618 (merged). This mission is an audited-surface change (AGENTS.md) that triggers the existing #618 felix-deployer observe→reconcile path on merge to main; no new fix to #557 is made here (C-001, SC-004). |

Valid `Verdict` values: `fixed`, `verified-already-fixed`, `deferred-with-followup`, `in-mission` (being fixed by a later WP in this mission; must reach a terminal verdict before mission `done`).
