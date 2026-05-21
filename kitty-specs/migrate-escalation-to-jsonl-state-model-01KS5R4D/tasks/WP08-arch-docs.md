---
work_package_id: WP08
title: Architecture documentation
dependencies: []
requirement_refs:
- C-004
planning_base_branch: main
merge_target_branch: main
branch_strategy: Planning artifacts for this feature were generated on main. During /spec-kitty.implement this WP may branch from a dependency-specific base, but completed changes must merge back into main unless the human explicitly redirects the landing branch.
base_branch: kitty/mission-migrate-escalation-to-jsonl-state-model-01KS5R4D
base_commit: 7e73197665540941ac21b6fc6073d05b20e659f6
created_at: '2026-05-21T19:22:03.851589+00:00'
subtasks:
- T024
- T025
- T026
shell_pid: "79560"
agent: "claude:opus:python-implementer:implementer"
history:
- at: '2026-05-21T17:45:30+00:00'
  actor: spec-kitty.tasks
  event: created
authoritative_surface: docs/design/architecture/
execution_mode: code_change
mission_id: 01KS5R4D79WQQWY2MCHZVCT85G
mission_slug: migrate-escalation-to-jsonl-state-model-01KS5R4D
owned_files:
- docs/design/architecture/data/service-inventory.json
- docs/design/architecture/data/data-flows.json
- docs/design/architecture/services.view.md
- docs/design/architecture/data-flows.view.md
tags: []
---

# WP08 — Architecture documentation

## Objective

Update the JSON arch docs (`service-inventory.json`, `data-flows.json`) for the new `scripts/escalation/*` surfaces. Update the markdown views to match. Implements C-004 (in-mission doc updates) and Felix Constitution Directive 5 (JSON authoritative, markdown views match).

This WP is fully parallel — no code dependencies. Can start as soon as the mission begins.

## Context

- **Mission spec**: C-004 (architecture docs updated in same mission), Felix Constitution Directive 5
- **CLAUDE.md standing requirement**: "Any feature that changes deployed services, credentials, data flows, or network topology must update the relevant files in `docs/design/architecture/` and `docs/design/architecture/data/`."
- **Existing pattern**: `docs/design/architecture/data/service-inventory.json` — read it to understand the entry shape. Look at the `felix-admin-habits` entry as the closest analogue.
- **Habits Phase 3 precedent**: that mission updated `service-inventory.json` for the new `scripts/habits/*` surfaces. Read the commit `231e8801` (or whichever was the Phase 3 squash) to see the diff.
- **Validation**: `tooling/scripts/validate_docs.py` enforces JSON ↔ markdown consistency.
- **Branching**: planning_base=`main`, merge_target=`main`. Execution worktree per `lanes.json`.

## Subtasks

### T024 — Update `docs/design/architecture/data/service-inventory.json`

**Purpose**: Register the new `scripts/escalation/*` helpers as services.

**Steps**:

1. Open `docs/design/architecture/data/service-inventory.json`. Understand the schema by reading existing entries (especially `felix-admin-habits`).
2. Add entries for each new helper:
   - `escalation-record-completion` — script, no daemon, invoked by skill
   - `escalation-reconcile-completions` — script, invoked at tick start
   - `escalation-derive-state` — library + debug CLI
   - `escalation-backfill-from-comments` — one-time helper
   - `escalation-hard-fail` — library helper for bug filing
3. For each entry include:
   - `name`, `kind` (one of "script", "library"), `path` (relative to repo root)
   - `description` (1-2 sentences)
   - `runs_on`: `["office2"]`
   - `invoked_by`: link to the `felix-admin-escalation` agent entry or `kent_via_cli` for backfill
   - `writes_to`: JSONL paths, Vikunja API
   - `reads_from`: JSONL paths, Vikunja API
   - `credentials`: `["vikunja-api"]`
   - `updated_by`: `"#309"`
4. UPDATE the existing `felix-admin-escalation` agent entry:
   - Update `consumes` or `depends_on` list to include the new helpers.
   - Update `description` to note the v2 (JSONL state) shape post-#309.
   - `updated_by`: `"#309"`
5. Run `python3 tooling/scripts/validate_docs.py docs/design/architecture/data/` (or the project's standard validator) to confirm JSON is well-formed.

**Files**:
- `docs/design/architecture/data/service-inventory.json` (modified — ~5 new entries + 1 updated entry)

**Validation**:
- [ ] `python3 -c "import json; json.load(open('docs/design/architecture/data/service-inventory.json'))"` succeeds.
- [ ] All new entries have `updated_by: "#309"`.
- [ ] Existing `felix-admin-escalation` entry includes the new helpers in `depends_on` (or equivalent field).

---

### T025 — Update `docs/design/architecture/data/data-flows.json`

**Purpose**: Register the new write paths (record → Vikunja + JSONL) and read paths (derive_state ← JSONL).

**Steps**:

1. Open `docs/design/architecture/data/data-flows.json`. Read the schema.
2. Add new flow entries:
   - **record_event → Vikunja API**: from `scripts/escalation/record_completion.py`, to `vikunja@office2`, via Tailscale HTTP, auth via `vikunja-api` token. Triggers: agent tick, kent_reply via OpenClaw.
   - **record_event → JSONL state**: from `scripts/escalation/record_completion.py`, to `/data/services/openclaw/state/escalation/project-<id>-escalation-history.jsonl`. Triggers: same as above.
   - **derive_state ← JSONL state**: read-only, from JSONL files. Triggers: every tick.
   - **reconcile_completions ← Vikunja API**: GET /tasks/{id} reads. Triggers: every tick.
   - **reconcile_completions → JSONL state**: synthetic record writes via `record_event`. Triggers: drift detection.
   - **backfill ← Vikunja API**: GET /tasks/{id}/comments. Triggers: one-time, operator-invoked.
   - **backfill → JSONL state**: replay writes. Triggers: same.
   - **backfill → snapshot file**: write `pre-phase6-snapshot.json`. Triggers: same.
   - **hard_fail → GitHub API**: subprocess to `gh` for dedup query AND issue filing. Triggers: Q10 trigger conditions.
3. UPDATE existing flows referencing `felix-admin-escalation` to add `since: "#309"` notes for the v2 state source.
4. Add `updated_by: "#309"` to each new entry.

**Files**:
- `docs/design/architecture/data/data-flows.json` (modified — ~9 new flow entries + updates to existing)

**Validation**:
- [ ] JSON parses.
- [ ] Every new flow has `updated_by: "#309"`.
- [ ] All paths reference real on-disk locations (cross-check against contracts/api.md module constants).

---

### T026 — Update markdown architecture views

**Purpose**: Per Felix Constitution Directive 5: when JSON updates, markdown views must match.

**Steps**:

1. Identify the markdown views derived from `service-inventory.json` and `data-flows.json`. Likely candidates:
   - `docs/design/architecture/services.view.md` (or similar)
   - `docs/design/architecture/data-flows.view.md`
   - `docs/design/architecture/system-overview.md` (if it diagrams services)
2. For each affected view:
   - Add markdown sections for each new helper (matching the JSON entries).
   - Update the felix-admin-escalation row in any table to note v2.
   - If the views include Mermaid diagrams, add nodes for new helpers and arrows for new data flows.
   - Add `updated_by: '#309'` to the frontmatter if present.
3. Run the project's doc sync/validate tool (if any — check `tooling/scripts/kg_sync_docs.py` per CLAUDE.md).

**Files**:
- `docs/design/architecture/services.view.md` (modified — list/table entries for new helpers)
- `docs/design/architecture/data-flows.view.md` (modified — flow descriptions for new entries)
- Other architecture markdown files if they contain inventoried services or flows

**Validation**:
- [ ] `tooling/scripts/validate_docs.py` passes for the touched files.
- [ ] Markdown views mention every new entry from JSON.
- [ ] No new orphaned entries in either side (JSON entry without markdown counterpart, or vice versa).

---

## Branch Strategy

- Planning/base branch: `main`
- Merge target: `main`
- Execution worktree allocated per `lanes.json` after `finalize_tasks`.

## Test Strategy

Doc-only WP. Validation via:
- JSON parse + schema (manual or via `tooling/scripts/validate_docs.py`)
- Markdown ↔ JSON consistency check (project's existing tool)
- Reviewer reads both JSON and markdown to confirm matched coverage

## Definition of Done

- [ ] T024-T026 subtasks complete with all validations green.
- [ ] All new JSON entries have `updated_by: "#309"`.
- [ ] Markdown views mention every new helper.
- [ ] `tooling/scripts/validate_docs.py` passes.

## Risks

- **JSON ↔ markdown drift**: the validate_docs tool is the safety net. If it doesn't catch a specific mismatch class, the reviewer must.
- **Existing `service-inventory.json` schema**: read it first. If the schema requires fields this WP doesn't anticipate (e.g., `port`, `health_check`), the new entries must include them.
- **Mermaid diagram updates**: easy to miss. Grep the view files for `mermaid` blocks; if found, update them.

## Reviewer Guidance

1. Read each updated JSON file end-to-end. Confirm new entries are well-formed AND `updated_by` is set.
2. Cross-check JSON entries against markdown views — every JSON entry should be discoverable in the markdown.
3. Run `tooling/scripts/validate_docs.py` and confirm clean exit.

## Implementation Command

```bash
spec-kitty agent action implement WP08 --mission migrate-escalation-to-jsonl-state-model-01KS5R4D --agent claude:opus:python-implementer:implementer
```

## Activity Log

- 2026-05-21T19:22:06Z – claude:opus:python-implementer:implementer – shell_pid=79560 – Assigned agent via action command
- 2026-05-21T19:29:51Z – claude:opus:python-implementer:implementer – shell_pid=79560 – Ready for review — JSON arch docs + markdown views updated for new escalation helpers
