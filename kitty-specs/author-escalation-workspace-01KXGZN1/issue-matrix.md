# Issue matrix — author-escalation-workspace-01KXGZN1

Per FR-037 of the spec-kitty-mission-review skill Gate-4. One row per issue referenced in spec.md.

| Issue | Title | Verdict | Evidence ref |
|-------|-------|---------|--------------|
| #585 | Feature: Intentionally author felix-admin-escalation workspace context | fixed | WP01 commit 975d916f — SOUL/USER/TOOLS/AGENTS re-homed to #587 owners; escalation-scoped validator ok; 469 tests green |
| #724 | Clean stale Goals(11) references in felix-admin-escalation prompt + setup_vikunja.py | fixed | WP01 commit 975d916f — full Goals(11) elimination across TOOLS.md, setup_vikunja.py, SKILL.md, escalation-ops.md, test (expanded from #724's literal scope per post-plan Codex HIGH-2) |
| #732 | Docs debt: canonicalize the _private path representation across agent prompts | deferred-with-followup | Follow-up: #732 — fleet-wide path inconsistency deferred out of #585 (Kent's scope call); escalation path left byte-unchanged |
| #167 | Epic: Intentionally author every OpenClaw agent workspace | deferred-with-followup | Follow-up: #586 — parent epic; escalation is the 3rd child; next child is tasker #586 |
| #587 | Feature: OpenClaw workspace authoring standard | verified-already-fixed | Standard shipped ad7ee47d (on main); this mission is written against it and reuses validate_workspace.py |
| #584 | Feature: author felix-admin-capture workspace (pilot) | verified-already-fixed | Merged 0e9c8254; the pure-refactor precedent this mission mirrors |
| #583 | Feature: author main workspace | verified-already-fixed | Merged 9829acef; sibling authoring child, done+closed |
| #717 | Vikunja task migration (deleted Goals project 11) | verified-already-fixed | Merged 6616935f; deleting Goals(11) is what created the stale references #724/this mission clean |
| #636 | agent-prompt-sync vs felix-deployer deploy boundary | verified-already-fixed | Boundary established/documented; this mission deploys prompts via agent-prompt-sync (no manifest) per that boundary |
| #621 | Rebaseline gap — agent prompt files not hashed by audit.sh | deferred-with-followup | Follow-up: #621 — open gap; referenced to justify "Rebaseline: not required"; no baseline hashed by this mission |

Valid `Verdict` values: `fixed`, `verified-already-fixed`, `deferred-with-followup`, `in-mission` (being fixed by a later WP in this mission; must reach a terminal verdict before mission `done`).
