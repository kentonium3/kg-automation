# Issue matrix — author-tasker-workspace-01KXXEVB

Per FR-037 of the spec-kitty-mission-review skill Gate-4. One row per issue referenced in spec.md.

| Issue | Title | Verdict | Evidence ref |
|-------|-------|---------|--------------|
| #586 | Feature: Intentionally author felix-admin-tasker workspace context | fixed | WP01 commit 76a8f9d3 — SOUL/USER/TOOLS re-homed to #587 owners; tasker-scoped validator ok:true; behavior-preserving (AGENTS + IDENTITY byte-unchanged); reviewer-renata APPROVE |
| #167 | Epic: Intentionally author every OpenClaw agent workspace | deferred-with-followup | Follow-up: #635 — parent epic; tasker is the 5th child; the remaining child is calendar #635 (RRULE gate) |
| #587 | Feature: OpenClaw workspace authoring standard | verified-already-fixed | Standard shipped ad7ee47d (on main); this mission is written against it and reuses validate_workspace.py |
| #582 | Feature: author felix-admin-habits workspace | verified-already-fixed | Merged ab0c99fc (main); sibling authoring child and the closest move-table precedent this mission mirrors |
| #584 | Feature: author felix-admin-capture workspace (pilot) | verified-already-fixed | Merged 0e9c8254; the pure-refactor precedent this mission mirrors |
| #636 | agent-prompt-sync vs felix-deployer deploy boundary | verified-already-fixed | Boundary established/documented; this mission deploys prompts via agent-prompt-sync (no manifest) per that boundary |
| #621 | Rebaseline gap — agent prompt files not hashed by audit.sh | deferred-with-followup | Follow-up: #621 — open gap; referenced to justify "Rebaseline: not required"; no baseline hashed by this mission |
| #583 | Feature: author main workspace | verified-already-fixed | Merged (main); sibling authoring child, done+closed |
| #2533 | Coordination-split stranded-husk fault (upstream spec-kitty) | deferred-with-followup | Follow-up: #2533 — upstream; avoided here via single-branch topology (C-008), so the fault is not triggered by this mission |
| #656 | Agent action logs under per-agent subdir (/home/kgale/second-brain/agents/logs) | verified-already-fixed | DEFAULT_AGENT_LOGS_DIR shipped in config.py; the FR-008 action-log correction rests on the `<log_dir>/<agent>/YYYY-MM-DD.jsonl` shape log_action.py produces |
| #808 | audited-surfaces.json openclaw-agent-prompts patterns omit TOOLS.md | deferred-with-followup | Follow-up: #808 — filed this mission (post-plan Codex finding); pre-existing data drift, out of NFR-002 scope; posture unaffected (rebaseline_required:false regardless) |

Valid `Verdict` values: `fixed`, `verified-already-fixed`, `deferred-with-followup`, `in-mission` (being fixed by a later WP in this mission; must reach a terminal verdict before mission `done`).
