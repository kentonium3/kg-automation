# Issue matrix — felix-calendar-subagent-extraction-01KTTA33

Per FR-037 of the spec-kitty-mission-review skill Gate-4. One row per issue referenced in spec.md.

| Issue | Title | Verdict | Evidence ref |
|-------|-------|---------|--------------|
| #579 | Felix main agent stops relaying subagent replies to WhatsApp — main/AGENTS.md truncated (25.9K vs 12K cap) drops delegation instructions | fixed | Merged at commit 37b3bf56 (squash merge of 7-WP mission to main, 2026-06-11). WP02 created felix-admin-calendar subagent (AGENTS.md 11,893 chars under cap). WP03 tightened main/AGENTS.md to 11,934 chars (NFR-001 PASS via pytest test_main_agents_md_under_12k). Issue closed via gh issue close 579 with full merge summary. Post-deploy verification (deploy script journal-watch NFR-002 + operator smoke runbook SC-001 through SC-008) is the operator's remaining surface; deploy script and smoke runbook both shipped in this merge. |
| #492 | Mission docs miss INDEX/Developer Portal updates when new doc surfaces added | verified-already-fixed | Resolved by the mission that shipped `docs/design/architecture/data/signal-to-doc-map.json` (the canonical source of truth for doc surfaces per change class). This mission HONORS the precedent: plan.md § Documentation Sync enumerates explicit doc targets pulled from signal-to-doc-map.json for `mission-agent-prompt-changed`, `mission-service-added-or-modified`, and `mission-runbook-added` change classes (5+4+2 targets respectively). WP05/06/07 are the implementation surface. No re-fix needed here; the spec.md reference is a "consult the canonical map" pointer, not a sub-issue. |

Valid `Verdict` values: `fixed`, `verified-already-fixed`, `deferred-with-followup`, `in-mission` (being fixed by a later WP in this mission; must reach a terminal verdict before mission `done`).

## Notes

- `#579` was NOT auto-detected by `scaffold_issue_matrix`'s regex (`(?:^|\s|\(|\[)#(\d{2,6})`) because spec.md references it as `kentonium3/kg-automation#579` — a digit precedes the `#`, failing the boundary check. Added manually.
- `#579` carries `in-mission` verdict during per-WP approvals; transitioned to `fixed` at mission merge (2026-06-11, commit 37b3bf56) per the gate-4 contract.
