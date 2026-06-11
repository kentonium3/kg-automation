# Issue matrix — felix-calendar-subagent-extraction-01KTTA33

Per FR-037 of the spec-kitty-mission-review skill Gate-4. One row per issue referenced in spec.md.

| Issue | Title | Verdict | Evidence ref |
|-------|-------|---------|--------------|
| #579 | Felix main agent stops relaying subagent replies to WhatsApp — main/AGENTS.md truncated (25.9K vs 12K cap) drops delegation instructions | in-mission | This mission. Resolved by WP02 (extract felix-admin-calendar subagent) + WP03 (tighten main/AGENTS.md < 12K). Verification path: SC-001 through SC-004 in spec.md, verified post-deploy via deploy script's journal-watch (NFR-002) + operator smoke runbook (WP07). |
| #492 | Mission docs miss INDEX/Developer Portal updates when new doc surfaces added | verified-already-fixed | Resolved by the mission that shipped `docs/design/architecture/data/signal-to-doc-map.json` (the canonical source of truth for doc surfaces per change class). This mission HONORS the precedent: plan.md § Documentation Sync enumerates explicit doc targets pulled from signal-to-doc-map.json for `mission-agent-prompt-changed`, `mission-service-added-or-modified`, and `mission-runbook-added` change classes (5+4+2 targets respectively). WP05/06/07 are the implementation surface. No re-fix needed here; the spec.md reference is a "consult the canonical map" pointer, not a sub-issue. |

Valid `Verdict` values: `fixed`, `verified-already-fixed`, `deferred-with-followup`, `in-mission` (being fixed by a later WP in this mission; must reach a terminal verdict before mission `done`).

## Notes

- `#579` was NOT auto-detected by `scaffold_issue_matrix`'s regex (`(?:^|\s|\(|\[)#(\d{2,6})`) because spec.md references it as `kentonium3/kg-automation#579` — a digit precedes the `#`, failing the boundary check. Added manually.
- `#579` carries `in-mission` verdict during per-WP approvals; **must transition to `fixed` (or another terminal verdict) before mission `done`** per the gate-4 contract.
