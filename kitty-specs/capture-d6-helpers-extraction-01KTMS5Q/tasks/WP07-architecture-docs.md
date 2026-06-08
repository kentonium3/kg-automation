---
work_package_id: WP07
title: Architecture documentation sync
dependencies:
- WP01
- WP02
- WP03
- WP04
- WP05
- WP06
requirement_refs:
- FR-012
- FR-013
tracker_refs: []
planning_base_branch: main
merge_target_branch: main
branch_strategy: lane-from-coordination
subtasks:
- T013
- T014
agent: claude
history: []
agent_profile: curator-carla
authoritative_surface: docs/
execution_mode: code_change
mission_id: 01KTMS5QGXFJWQYVXB03SPYB48
mission_slug: capture-d6-helpers-extraction-01KTMS5Q
model: claude-sonnet-4-6
owned_files:
- docs/design/architecture/data/service-inventory.json
role: implementer
tags: []
---

## ⚡ Do This First: Load Agent Profile

```
/ad-hoc-profile-load curator-carla
```

Curator posture: accurate to current code, no aspirational claims, no speculative descriptions.

## Objective

Extend `services[openclaw-gateway].agents.felix-admin-capture.components` array in `docs/design/architecture/data/service-inventory.json` with 6 new component entries (one per helper shipped in WPs 1-6). Bump `last_updated` and extend `updated_by`. Follow the existing component-entry schema verbatim.

Per DIR-005, every mission spec must include a doc-sync requirement and it ships with the feature.

## Context

| Document | Why |
|---|---|
| [../spec.md](../spec.md) § Architecture Documentation Updates | The doc-sync requirement |
| `docs/design/architecture/data/service-inventory.json` § `services[openclaw-gateway].agents.felix-admin-capture.components` | Existing entries to mirror |

## Subtask Guidance

### T013 — Extend `service-inventory.json` with 6 new component entries

Locate `services[].name == "openclaw-gateway"` → `.agents.felix-admin-capture.components` array. Append 6 entries, one per helper:

```json
{
  "id": "<helper-id>",
  "type": "script",
  "language": "python",
  "source": "scripts/inbox/<helper>.py",
  "deploy_path": "/home/claude/kg-automation/scripts/inbox/<helper>.py",
  "purpose": "<one-line purpose>",
  "invoked_by": "felix-admin-capture (post #566 follow-on AGENTS.md rewrite)",
  "introduced_by": "#566",
  "updated_at": "2026-06-08"
}
```

Per-helper:

- **`mark-processed`**: `purpose: "Atomic frontmatter mutation — sets status:processed + processed_at while preserving file location, other frontmatter, and body verbatim. Idempotent."`
- **`route-journal-entry`**: `purpose: "Append routed content to 08-Journal/Journal YYYY-MM-DD HHmm.md (creates file with correct frontmatter if absent)."`
- **`route-someday`**: `purpose: "Create Vikunja task in Someday project (resolved by name via scripts.common.vikunja_client). Uses create endpoint per Vikunja partial-replace gotcha."`
- **`route-calendar-event`**: `purpose: "Validate calendar payload via scripts.calendar_routing.validate_calendar_event; emit normalized payload JSON on stdout for the agent to delegate to Felix main for gog calendar create."`
- **`handle-clarification-state`**: `purpose: "Manages pending-calendar-clarifications.json — add / sweep (24h aging) / match subcommands. Safe on missing state file."`
- **`classify-content`**: `purpose: "Per-block deterministic content classification with LLM-judgment flagging for ambiguous tokens. Mirrors the doc-audit judgment/ pattern. Heuristics documented inline."`

### T014 — Bump top-level `last_updated` + extend `updated_by`

At the top of `service-inventory.json`:

- Update `last_updated: "2026-06-08"` (or current date)
- Extend `updated_by` string to include `"capture-d6-helpers-extraction-01KTMS5Q (#566) + "` at the start

## Definition of Done

- [ ] `service-inventory.json` has 6 new component entries under felix-admin-capture
- [ ] Each new entry follows the existing-entry schema (verified by comparing with `inbox-prescan-helper` entry)
- [ ] `python3 -c "import json; json.load(open('docs/design/architecture/data/service-inventory.json'))"` exits 0
- [ ] Top-level `last_updated` bumped
- [ ] Top-level `updated_by` extended with this mission
- [ ] Lane committed; WP moved to `for_review`

## Risks

- Schema is rich; malformed addition fails downstream consumers. Mitigation: copy `inbox-prescan-helper`'s shape verbatim; only modify per-helper fields.
- Existing entries may have additional fields (e.g., `state_files`) — only include them where applicable to the new helper.
