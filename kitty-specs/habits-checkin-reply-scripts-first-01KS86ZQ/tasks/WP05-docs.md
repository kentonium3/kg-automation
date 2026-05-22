---
work_package_id: WP05
title: Architecture docs + ops runbook
dependencies: []
requirement_refs:
- C-004
- C-007
planning_base_branch: main
merge_target_branch: main
branch_strategy: Planning artifacts for this feature were generated on main. During /spec-kitty.implement this WP may branch from a dependency-specific base, but completed changes must merge back into main unless the human explicitly redirects the landing branch.
base_branch: kitty/mission-habits-checkin-reply-scripts-first-01KS86ZQ
base_commit: a846b5836c1f09b4c471f6c3f9adfe063fd4dd4d
created_at: '2026-05-22T16:24:29.502316+00:00'
subtasks:
- T016
- T017
- T018
- T019
shell_pid: "63655"
agent: "codex:gpt-5:spec-kitty-review:reviewer"
history:
- at: '2026-05-22T16:30:00+00:00'
  actor: spec-kitty.tasks
  event: created
authoritative_surface: docs/
execution_mode: code_change
mission_id: 01KS86ZQE8GSZ77ZSGSSQMN08K
mission_slug: habits-checkin-reply-scripts-first-01KS86ZQ
owned_files:
- docs/design/architecture/data/service-inventory.json
- docs/design/architecture/data/data-flows.json
- docs/design/architecture/service-inventory.md
- docs/design/architecture/data-flows.md
- docs/design/architecture/data-flows.view.md
- docs/design/architecture/service-dependencies.view.md
- docs/runbooks/habits-ops.md
tags: []
---

# WP05 — Architecture docs + ops runbook

## Objective

Update the JSON arch docs (service-inventory, data-flows) for the new `scripts/habits/*` helpers + the new `morning-checkin-<date>.json` state file class. Update markdown views to match. Rewrite the habits ops runbook to reflect the v2 scripts-first flow. Implements C-007 (in-mission doc updates).

## Context

- **Spec**: C-007 (arch docs in-mission)
- **Plan**: Project Structure section enumerates doc files
- **Pattern source**: mission #309's WP08 did the same shape for escalation — refer to its commits for the JSON entry style
- **Branching**: planning_base=`main`, merge_target=`main`. Execution worktree per `lanes.json`.

## Subtasks

### T016 — service-inventory.json updates

**Purpose**: Register the three new helpers + update felix-admin-habits entry.

**Steps**:

1. Read existing `docs/design/architecture/data/service-inventory.json`. Find the existing `felix-admin-habits` entry under `openclaw-gateway` (or wherever the openclaw agents live).
2. Identify the existing `habit-checkin` config_files block — it lists current habits helpers (record_completion, query_active_habits_v2, etc.). This is the same place to add the new entries.
3. Add 3 new helper entries to the config_files (or equivalent — match mission #309's pattern):
   - `morning_checkin_list` — kind=script, path=`scripts/habits/morning_checkin_list.py`, runs_on=["office2"], invoked_by=felix-admin-habits agent (cron), writes_to=`/data/services/openclaw/state/habits/morning-checkin-<date>.json`, reads_from=`vikunja-api`, credentials=`["vikunja-api"]`, introduced_by=`"#371"`, updated_by=`"#371"`.
   - `parse_morning_reply` — kind=script, reads_from=morning-checkin JSON + Vikunja read-only via passthrough, writes_to=none (caller routes outputs).
   - `disambiguate_reply` — kind=library + CLI, path=`scripts/habits/judgment/disambiguate_reply.py`, invoked_by=felix-admin-habits agent, reads_from=`/data/services/openclaw/secrets/anthropic`, calls=`api.anthropic.com`, credentials=`["anthropic-api"]`.
4. Update the existing felix-admin-habits entry:
   - `last_updated: "2026-05-22"`
   - `updated_by: "#371"`
   - `purpose` field updated to note v2 (scripts-first morning + reply flow per #371).
   - `depends_on` extended to include the 3 new helpers.

**Files**: `docs/design/architecture/data/service-inventory.json` (modified).

**Validation**:
- [ ] `python3 -c "import json; json.load(open('docs/design/architecture/data/service-inventory.json'))"` succeeds.
- [ ] Every new entry has `introduced_by: "#371"` / `updated_by: "#371"`.

---

### T017 — data-flows.json updates

**Purpose**: Register new write/read paths.

**Steps**:

1. Read existing `docs/design/architecture/data/data-flows.json`.
2. Add new flow entries:
   - `habits-morning-list-write` — from `scripts/habits/morning_checkin_list.py`, to `/data/services/openclaw/state/habits/morning-checkin-<date>.json`. Trigger: morning cron tick.
   - `habits-morning-list-read` — from `scripts/habits/parse_morning_reply.py`, to morning-checkin JSON. Trigger: reply received.
   - `habits-disambiguator-llm` — from `scripts/habits/judgment/disambiguate_reply.py`, to `api.anthropic.com`. Trigger: parser emitted judgment_required.
   - `habits-vikunja-query` (if not already present) — from `scripts/habits/morning_checkin_list.py`, to `vikunja@office2`. Trigger: cron tick.
3. Each new entry: `introduced_by: "#371"`, `updated_by: "#371"`, `since: "#371"`.
4. Update any existing flows referencing felix-admin-habits to note v2 (since #371).

**Files**: `docs/design/architecture/data/data-flows.json` (modified).

**Validation**:
- [ ] JSON parses.
- [ ] Every new flow has `introduced_by: "#371"`.

---

### T018 — Markdown views match JSON

**Purpose**: Per Felix Constitution Directive 5 — when JSON updates, markdown views must match.

**Steps**:

1. Identify which markdown views derive from service-inventory + data-flows. Candidates (verify which exist):
   - `docs/design/architecture/service-inventory.md`
   - `docs/design/architecture/data-flows.md`
   - `docs/design/architecture/data-flows.view.md` (Mermaid)
   - `docs/design/architecture/service-dependencies.view.md`
2. For each view that exists:
   - Add bullet/row entries for the 3 new helpers (mirroring JSON entries' purpose + reads_from + writes_to + invoker).
   - Update the felix-admin-habits row/section to note the v2 shape.
   - If a Mermaid diagram is present: add nodes for the 3 new helpers + the morning-checkin JSON store + the api.anthropic.com endpoint; draw arrows for the new flows.
3. If the validator script `tooling/scripts/validate_docs.py` exists, run it. Don't introduce NEW errors (pre-existing errors out of scope).

**Files**:
- `docs/design/architecture/service-inventory.md` (modified)
- `docs/design/architecture/data-flows.md` (modified)
- `docs/design/architecture/data-flows.view.md` (modified)
- `docs/design/architecture/service-dependencies.view.md` (modified, if it has agent-service nodes)

**Validation**:
- [ ] Every new JSON entry has a corresponding markdown narrative + (if applicable) Mermaid node.
- [ ] No new validate_docs.py errors.

---

### T019 — Rewrite docs/runbooks/habits-ops.md

**Purpose**: Operator-facing doc for the v2 flow.

**Steps**:

1. Read existing `docs/runbooks/habits-ops.md`. Identify content to preserve vs. replace.
2. New structure (target ~200-260 lines, mirror escalation-ops.md):
   - Frontmatter: `id: habits-ops`, `doc_type: runbook`, `status: approved`, `level: 2`, `last_validated: 2026-05-22`, `updated_by: "#371"`, `version: "2.0.0"`.
   - **Overview**: 2-3 paragraphs describing the habits subsystem post-#371. Mention #309 as the architectural sibling.
   - **Daily operation (steady state)**:
     - Tick cadence (cron UUID `3082343c-bc7f-47ee-916b-ee070b1e50dc`, 7:05 AM ET daily)
     - Where state lives (per-date `morning-checkin-<date>.json` + per-habit history JSONL from Phase 3+5)
     - How to query current state via derive (none — the parser is invocation-driven; for inspection, `cat /data/services/openclaw/state/habits/morning-checkin-<date>.json | jq`)
   - **Cutover procedure** — cross-reference `kitty-specs/habits-checkin-reply-scripts-first-01KS86ZQ/quickstart.md`. Do NOT duplicate.
   - **Verification & monitoring**:
     - Cron success check (`openclaw cron runs --id 3082343c-... --since "1 day ago"`)
     - JSONL growth check (record_completion outputs)
     - Truncation-warning check (`journalctl --user -u openclaw-gateway.service --since "1 day ago" | grep "truncat"` — should be empty)
   - **Rollback procedure** — cross-reference quickstart.md § Rollback.
   - **Maintenance**:
     - When to rotate the morning-checkin JSON files (none currently — manual cleanup if needed after ~30 days)
     - How to inspect a single day's state
     - How to manually correct a botched record (per the Out of Scope of #371 spec — Kent edits JSONL by hand)
   - **Cross-references**: #371, #309, ADR-0002, the helper scripts.
3. Every CLI example in the runbook MUST match contracts/cli.md. Run `--help` on each helper to verify.

**Files**: `docs/runbooks/habits-ops.md` (rewritten).

**Validation**:
- [ ] Frontmatter has `updated_by: "#371"`, version 2.0.0.
- [ ] Every CLI example matches actual helper `--help`.
- [ ] No references to v1 fuzzy-match prose or session-scoped numbered lists.
- [ ] Cross-reference to quickstart.md works (no broken markdown links).

---

## Branch Strategy

Planning_base=`main`, merge_target=`main`. Execution worktree per `lanes.json`.

## Test Strategy

Doc-only WP. Validation via:
- JSON parse (`python3 -c "import json; json.load(...)"`)
- Markdown ↔ JSON cross-check (manual + project's validator if available)
- Reviewer walks the runbook end-to-end as if executing the cutover

## Definition of Done

- [ ] All 4 subtasks complete.
- [ ] JSON files parse and have `updated_by: "#371"` on touched entries.
- [ ] Markdown views match JSON sources.
- [ ] Runbook is readable end-to-end and all CLI examples match contracts/cli.md.

## Risks

- **JSON ↔ markdown drift**: easy to update one and forget the other. The validator catches some classes; manual review catches the rest.
- **CLI-flag drift mid-mission**: WP01/WP02/WP03 may have changed flag names from the contracts. Run `--help` on the deployed helpers (or the worktree builds) before finalizing runbook examples.

## Reviewer Guidance

1. Cross-check every new JSON entry has a markdown counterpart.
2. Verify the runbook references quickstart.md (not duplicating cutover steps).
3. Run `--help` on the three helpers and compare against runbook examples.
4. Confirm `updated_by: "#371"` on all touched entries.

## Implementation Command

```bash
spec-kitty agent action implement WP05 --mission habits-checkin-reply-scripts-first-01KS86ZQ --agent claude:opus:python-implementer:implementer
```

## Activity Log

- 2026-05-22T16:24:32Z – claude:opus:python-implementer:implementer – shell_pid=60663 – Assigned agent via action command
- 2026-05-22T16:34:31Z – claude:opus:python-implementer:implementer – shell_pid=60663 – Ready for review — JSON + markdown + runbook updated for v2
- 2026-05-22T16:35:03Z – codex:gpt-5:spec-kitty-review:reviewer – shell_pid=63655 – Started review via action command
- 2026-05-22T16:40:02Z – codex:gpt-5:spec-kitty-review:reviewer – shell_pid=63655 – Review passed: docs-only WP; JSON provenance, markdown coverage, runbook contract alignment, and known validator output checked
