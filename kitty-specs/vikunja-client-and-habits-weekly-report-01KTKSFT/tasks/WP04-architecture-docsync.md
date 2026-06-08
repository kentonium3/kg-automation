---
work_package_id: WP04
title: Architecture doc sync
dependencies:
- WP03
requirement_refs:
- FR-014
- NFR-005
tracker_refs: []
planning_base_branch: kitty/mission-vikunja-client-and-habits-weekly-report-01KTKSFT
merge_target_branch: kitty/mission-vikunja-client-and-habits-weekly-report-01KTKSFT
branch_strategy: Planning artifacts for this mission were generated on kitty/mission-vikunja-client-and-habits-weekly-report-01KTKSFT. During /spec-kitty.implement this WP may branch from a dependency-specific base, but completed changes must merge back into kitty/mission-vikunja-client-and-habits-weekly-report-01KTKSFT unless the human explicitly redirects the landing branch.
base_branch: kitty/mission-vikunja-client-and-habits-weekly-report-01KTKSFT
base_commit: fa3fefcde43fecc284c2f650876d8f65f1add877
created_at: '2026-06-08T17:41:50.322433+00:00'
subtasks:
- T018
- T019
- T020
- T021
shell_pid: "42258"
history: []
authoritative_surface: docs/design/architecture/
execution_mode: code_change
owned_files:
- docs/design/architecture/data/service-inventory.json
- docs/design/architecture/data/signal-to-doc-map.json
- docs/design/architecture/service-inventory.md
- docs/runbooks/openclaw-agent-setup.md
tags: []
agent: "claude:sonnet:curator-carla:implementer"
---

# WP04: Architecture doc sync

## ⚡ Do This First: Load Agent Profile

Before reading anything else, load the agent profile assigned to this work package by running `/ad-hoc-profile-load` with the profile slug from this file's `agent_profile` frontmatter field. Apply the profile's identity, governance scope, boundaries, and initialization declaration to the rest of this session. If the field is absent, request a profile selection from the operator before proceeding.

## Objective

Update the architecture documentation surfaces touched by WP01-WP03's changes so they reflect the new VikunjaClient shared library, the new `query_active_habits_weekly.py` helper, the existing weekly-report cron, and the felix-admin-habits behavior contract change. Per Felix Constitution Directive 5 + CLAUDE.md standing directive on architecture doc updates.

This WP is doc-only — no behavioral changes, no risk of production regression. It is small and bounded but is required for the mission to merge per the standing directive.

## Context

- **Authority docs**: `spec.md` FR-014 + NFR-005; CLAUDE.md "Standing requirement" on architecture doc updates; `docs/design/architecture/change-control.md` for the protocol.
- **signal-to-doc-map.json**: Per `feedback_signal_driven_doc_audit.md` memory, this is THE map. Filter by `change_class` values matching this mission: `service-added-or-modified` (the new helper is service-adjacent), `systemd-unit-added-or-modified` (only if the cron's systemd unit metadata changes — likely no), `architecture-doc-added` (no), `runbook-modified` (yes — `openclaw-agent-setup.md` references AGENTS.md surfaces).
- **service-inventory.json**: lists deployed services. The weekly-report cron is a service entity. Verify it's listed and accurate.
- **service-inventory.md**: narrative companion to service-inventory.json.

## Branch Strategy

- Planning base: `main`
- Merge target: `main`
- Implementation command: `spec-kitty agent action implement WP04 --agent <name>` (depends on WP03)

---

## Subtask T018: Update service-inventory.json

**Purpose**: Reflect the weekly-report cron service (FR-014) + the new VikunjaClient shared lib in the canonical inventory.

**Steps**:
1. Read `docs/design/architecture/data/service-inventory.json` end-to-end. Identify the existing `habits-morning-checkin` entry (or whatever it's named) — the weekly-report entry is likely sibling-shaped.
2. Verify the `habits-weekly-report` cron entry:
   - If it exists: confirm `schedule` matches `0 22 * * 0` and `timezone` is `America/New_York`. Confirm `description` mentions the new deterministic-helper-backed behavior.
   - If it doesn't exist: add it, mirroring the morning-check-in entry's schema. Schedule + timezone per spec FR-014.
3. If the inventory tracks shared libs (depends on its existing structure): consider adding `scripts/common/vikunja_client.py` as a shared-library entry. If the inventory doesn't track libs, skip this — don't invent a new schema for one entry.

**Files**:
- `docs/design/architecture/data/service-inventory.json` (modified)

**Validation**:
- [ ] `python3 -c "import json; json.load(open('docs/design/architecture/data/service-inventory.json'))"` exits 0
- [ ] `habits-weekly-report` entry is present, accurate (schedule, timezone, description, owning_agent: felix-admin-habits)
- [ ] No unrelated entries modified

---

## Subtask T019: Update service-inventory.md narrative

**Purpose**: Keep the markdown narrative aligned with the JSON authority. Per Felix Constitution Directive 5 (machine-readable wins on conflict, but they should agree).

**Steps**:
1. Read `docs/design/architecture/service-inventory.md`.
2. Add/update the weekly-report cron section. Mention:
   - Schedule (`0 22 * * 0` America/New_York)
   - Owning agent (felix-admin-habits)
   - Data source (queries Vikunja API directly via the new shared client — NOT the sync cache; explain why: needs done_at history)
   - The output-discipline-backed rendering (link to AGENTS.md if appropriate)
3. Keep it brief — service-inventory.md is high-level orientation. Detail lives in the JSON.

**Files**:
- `docs/design/architecture/service-inventory.md` (modified — ~10-20 added lines)

**Validation**:
- [ ] service-inventory.md and service-inventory.json describe the same cron (no contradictions)
- [ ] Document validators pass (`python3 tooling/scripts/validate_docs.py` — if applicable to this surface)

---

## Subtask T020: Update signal-to-doc-map.json

**Purpose**: Per `feedback_signal_driven_doc_audit.md` memory, this is the canonical map. If this mission introduces a new doc surface OR new signal class, the map needs an update so future doc-audit runs can find the right docs.

**Steps**:
1. Read `docs/design/architecture/data/signal-to-doc-map.json` end-to-end.
2. Determine: did this mission introduce a NEW doc surface or signal class?
   - WP01's `scripts/common/vikunja_client.py` is a new shared-library file. Does the map already cover "shared-library-added"? If yes, ensure the doc_targets covers it. If no, this is a deliberate decision NOT to add the class (mission scope), and we document why.
   - WP02's `scripts/habits/query_active_habits_weekly.py` is a new helper. Map should already cover helper additions via `service-added-or-modified`.
   - WP03's AGENTS.md edits are covered by existing entries.
3. If gaps are found that the mission explicitly does NOT scope into this slice: leave a brief comment in the JSON OR note in the WP completion that the gap exists. Do not silently expand scope.

**Files**:
- `docs/design/architecture/data/signal-to-doc-map.json` (modified or noted as unchanged)

**Validation**:
- [ ] `python3 -c "import json; json.load(open('docs/design/architecture/data/signal-to-doc-map.json'))"` exits 0
- [ ] Either: a) map updated to cover new surfaces, OR b) gap noted in handoff with rationale for scope decision
- [ ] No unrelated entries modified

---

## Subtask T021: Update openclaw-agent-setup.md runbook

**Purpose**: The runbook describes the AGENTS.md / SOUL.md / IDENTITY.md surface for each openclaw agent. WP03's edits to habits + escalation + tasker AGENTS.md may warrant a runbook update — at minimum, verify the runbook still accurately describes the pattern.

**Steps**:
1. Read `docs/runbooks/openclaw-agent-setup.md` end-to-end.
2. Check: does it document the "Output Discipline" pattern (3 hard rules) as a required section?
   - If yes: verify the description matches what felix-admin-capture (the source) currently uses, and what habits now uses.
   - If no: add a brief reference. The pattern is now used by capture + habits + possibly escalation/tasker. The runbook should mention it as the standard for any agent that surfaces to user-facing WhatsApp.
3. Do NOT rewrite the whole runbook. Surgical addition of a short section or paragraph only.

**Files**:
- `docs/runbooks/openclaw-agent-setup.md` (modified — ~10-15 added lines OR confirmed accurate)

**Validation**:
- [ ] Runbook now references Output Discipline pattern as standard for user-facing surfaces (or already did and was confirmed accurate)
- [ ] Runbook does not contradict any agent's actual current AGENTS.md content
- [ ] No unrelated content modified

---

## Definition of Done

- [ ] All 4 subtasks complete with their validation items checked.
- [ ] All modified JSON files are valid JSON.
- [ ] service-inventory.md and service-inventory.json are consistent.
- [ ] No source code (`scripts/`, `tests/`) modified by this WP.

## Risks

1. **Inventory schema drift** — if service-inventory.json's schema has evolved since the cron was added, T018 might struggle to fit the new entry. Mitigation: mirror the existing morning-check-in entry's exact schema. Don't invent fields.
2. **signal-to-doc-map.json scope creep** — easy to over-expand to cover hypothetical future signals. T020 explicitly counsels surgical-only updates. If a gap exists, note it and leave it for a follow-up issue rather than expanding this WP's scope.
3. **Runbook duplication** — the openclaw runbook may already reference output discipline at a different level of detail. T021 should AVOID adding contradictory or duplicate text. When in doubt, leave the runbook alone and document that conclusion.

## Reviewer guidance

- Reviewer runs the JSON validators independently.
- Reviewer cross-checks service-inventory.json + service-inventory.md for narrative consistency.
- Reviewer checks signal-to-doc-map.json gap notes against the mission's actual changes — were any signal classes silently introduced that the map doesn't cover?
- Reviewer confirms no `scripts/` or `tests/` files were modified (WP04 is doc-only).

## Activity Log

- 2026-06-08T17:41:53Z – claude:sonnet:curator-carla:implementer – shell_pid=37983 – Assigned agent via action command
- 2026-06-08T17:48:27Z – claude:sonnet:curator-carla:implementer – shell_pid=37983 – WP04 doc sync: service-inventory.json (+16 lines, new config_files for helper + client, habits sub-agent depends_on updated), service-inventory.md (+18 lines, Habit Report row + Weekly-report helpers sub-section), openclaw-agent-setup.md (+28 lines, Output Discipline section). signal-to-doc-map.json deliberately unchanged — shared-library-added is a cross-mission concept, deferred to first follow-on shared-lib addition. validate_docs OK. JSON valid. No scripts/ or tests/ touched.
- 2026-06-08T17:48:35Z – codex:gpt-5:reviewer-renata:reviewer – shell_pid=40008 – Started review via action command
- 2026-06-08T17:55:13Z – user – shell_pid=40008 – Moved to planned
- 2026-06-08T17:55:53Z – claude:sonnet:curator-carla:implementer – shell_pid=42258 – Started implementation via action command
