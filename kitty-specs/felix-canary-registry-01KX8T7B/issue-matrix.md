# Issue matrix — felix-canary-registry-01KX8T7B

Per FR-037 of the spec-kitty-mission-review skill Gate-4. One row per issue referenced in spec.md.

| Issue | Title | Verdict | Evidence ref |
|-------|-------|---------|--------------|
| #516 | Epic: Foundation 1 — Felix-wide health & observability (canary registry + single alert stream) | in-mission | This mission delivers F1's canary-registry core across WP01–WP07 (spec.md Summary; IC-01..07). Reaches terminal at mission done. |
| #701 | Infra: unified alert bus — single ntfy thread + structured message schema + shared emit library | verified-already-fixed | Alert bus shipped; the canary emits only via the existing `scripts/common/alert_bus` shared lib (C-002; WP04 emit; data-model Alert §). No new delivery path. |
| #269 | Felix outage watchdog: out-of-band Sev-0 alert when Felix/OpenClaw is silently broken | deferred-with-followup | Dead-timer / whole-host-silence out of scope (research R8; SC-006). This mission covers crash via `OnFailure=` (WP06) and self-registers the runner in the inventory (WP05, FR-010) so #269 can later detect a dead timer. |
| #511 | P3-debt: Restic backup discoverability — add health-pointer + register in service-inventory.json | verified-already-fixed | `last-backup.json` pointer + inventory registration already shipped (research R11 / Codex F10). WP05 normalizes it onto the uniform freshness path (`max_age_seconds`), not the #511 fix itself. |
| #706 | Feature: alert-bus durable local ledger — record every felix-alert on office2 for query + fault-awareness | verified-already-fixed | Ledger shipped; every canary emit is recorded by the existing #706 alert-bus ledger even on delivery failure (INV-C; NFR-005; WP04 emit path). |

Valid `Verdict` values: `fixed`, `verified-already-fixed`, `deferred-with-followup`, `in-mission` (being fixed by a later WP in this mission; must reach a terminal verdict before mission `done`).
