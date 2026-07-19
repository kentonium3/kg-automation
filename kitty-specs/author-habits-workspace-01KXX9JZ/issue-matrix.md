# Issue matrix — author-habits-workspace-01KXX9JZ

Per FR-037 of the spec-kitty-mission-review skill Gate-4. One row per issue referenced in spec.md.

| Issue | Title | Verdict | Evidence ref |
|-------|-------|---------|--------------|
| #582 | Feature: Intentionally author felix-admin-habits workspace context | fixed | WP01 commit 1d3dfc78 — SOUL/USER/TOOLS re-homed to #587 owners; habits-scoped validator ok:true; behavior-preserving (AGENTS byte-unchanged); reviewer-renata APPROVE |
| #167 | Epic: Intentionally author every OpenClaw agent workspace | deferred-with-followup | Follow-up: #586 — parent epic; habits is the 4th child; next child is tasker #586 |
| #587 | Feature: OpenClaw workspace authoring standard | verified-already-fixed | Standard shipped ad7ee47d (on main); this mission is written against it and reuses validate_workspace.py |
| #723 | Move weekly habit report to a deterministic systemd timer | verified-already-fixed | felix-habits-weekly timer shipped; this mission's weekly-out-of-scope (FR-003) and the FR-012 service-inventory.md doc-sync both rest on it |
| #796 | Weekly-report owner: dedicated LLM agent considered + declined | verified-already-fixed | Decided/closed 2026-07-19 (timer is permanent owner); reflected in SOUL removal + AGENTS single authoritative statement |
| #409 | Standing-orders conflict: felix-admin-habits SOUL vs AGENTS on weekly reports | verified-already-fixed | Closed 2026-07-19; this mission confirms incorporation (FR-011) — one authoritative weekly-out-of-scope statement in AGENTS, none in SOUL |
| #585 | Feature: author felix-admin-escalation workspace | verified-already-fixed | Merged (main); sibling authoring child + the move-table precedent this mission mirrors |
| #584 | Feature: author felix-admin-capture workspace (pilot) | verified-already-fixed | Merged 0e9c8254; the pure-refactor precedent this mission mirrors |
| #636 | agent-prompt-sync vs felix-deployer deploy boundary | verified-already-fixed | Boundary established/documented; this mission deploys prompts via agent-prompt-sync (no manifest) per that boundary |
| #621 | Rebaseline gap — agent prompt files not hashed by audit.sh | deferred-with-followup | Follow-up: #621 — open gap; referenced to justify "Rebaseline: not required"; no baseline hashed by this mission |
| #583 | Feature: author main workspace | verified-already-fixed | Merged (main); sibling authoring child, done+closed |
| #2533 | Coordination-split stranded-husk fault (upstream spec-kitty) | deferred-with-followup | Follow-up: #2533 — upstream; avoided here via single-branch topology (C-008), so the fault is not triggered by this mission |

Valid `Verdict` values: `fixed`, `verified-already-fixed`, `deferred-with-followup`, `in-mission` (being fixed by a later WP in this mission; must reach a terminal verdict before mission `done`).
