---
work_package_id: WP06
title: Architecture documentation
dependencies:
- WP05
requirement_refs:
- C-006
- C-008
planning_base_branch: main
merge_target_branch: main
branch_strategy: Lane-allocated worktree from main; merges into main
subtasks:
- T018
- T019
- T020
history:
- event: created
  at: '2026-05-12T20:55:30Z'
  by: 'spec-kitty.tasks (auto-drive via #185)'
authoritative_surface: docs/design/architecture/
execution_mode: code_change
owned_files:
- docs/design/architecture/data/service-inventory.json
- docs/design/architecture/service-inventory.md
- docs/runbooks/inbox-ops.md
tags: []
---

# WP06 — Architecture documentation

## Objective

Update the live architecture documents to reflect the new routing-log state file + the agent's new behavior per C-008.

## Context

- **Spec** anchor: C-008 (same-change-set arch-doc update).
- **Plan** anchor: §"Source Code (repository root)" lists the three doc files.

## Branch Strategy

- Planning/base branch: `main`
- Merge target branch: `main`

## Subtasks

### T018 — service-inventory.json: add routing log to felix-admin-capture entry

**Purpose**: Authoritative JSON record reflects the new state file + behavioral change.

**Steps**:

1. Find the `felix-admin-capture` agent sub-block in `docs/design/architecture/data/service-inventory.json` (currently nested under `openclaw-gateway.agents.felix-admin-capture`).
2. Update the sub-block to add a new `state_files` array (or extend `components` if that's where state files live in this schema; verify against the existing schema shape during implementation):
   ```json
   "state_files": [
     {
       "path": "~/second-brain/agents/state/inbox-routing.jsonl",
       "format": "jsonl",
       "purpose": "Routing log — load-bearing dedup substrate. Each line: {filename, issue_number, vikunja_task_id, routed_at, note_excerpt}. Append-only. NOT git-tracked.",
       "deployed_by": "#185"
     }
   ]
   ```
3. Update the agent's `notes` (if present) or add a `notes` field describing the new dedup mechanism + parse-failure handling:
   > "As of #185 (2026-05-12): routes are deduped via a filename-keyed routing log at the path in state_files above. Notes with malformed frontmatter halt routing and surface via a batched 'Inbox quality:' GitHub issue + an Obsidian callout marker injected at the top of the affected note."
4. Update the agent's `updated_by` field (if present) to `#185`.
5. Bump file-level `last_updated` and extend `updated_by` to include `#185-inbox-capture-dedup`.

**Files**: `docs/design/architecture/data/service-inventory.json` (modify).

**Validation**:

- `python3 -c "import json; json.load(open('docs/design/architecture/data/service-inventory.json'))"` exits 0.
- `python3 tooling/scripts/validate_docs.py` exits 0.

---

### T019 — service-inventory.md narrative

**Purpose**: Match the JSON in the human-readable view.

**Steps**:

1. Find the §"Felix Admin Capture Agent" section in `docs/design/architecture/service-inventory.md` (around line 116).
2. Add a new bullet (or paragraph) describing the dedup mechanism + state file:
   - **Routing log (#185)**: `~/second-brain/agents/state/inbox-routing.jsonl`. Append-only JSONL. Each line records one successful route (filename, issue#, task ID, routed_at). The agent consults this log before filing any GitHub issue — already-routed filenames are skipped. Load-bearing dedup, independent of frontmatter parseability.
   - **Parse-failure handling (#185)**: notes with malformed frontmatter halt routing and surface via a batched `Inbox quality:` GitHub issue + an Obsidian callout marker (`> [!error] felix-capture: ...`) injected at the top of each affected note. Markers auto-strip when the agent next reads a cleanly-parseable version of the same note.

**Files**: `docs/design/architecture/service-inventory.md` (modify).

---

### T020 — docs/runbooks/inbox-ops.md operator workflow update

**Purpose**: Capture the new operator-facing workflow.

**Steps**:

1. Check whether `docs/runbooks/inbox-ops.md` exists. If not, this subtask is reduced to a stub-create or skipped per the implement-phase agent's call (the original Plan footprinted this file but didn't confirm existence — code archaeology in implement phase confirms).
2. Add a new section: "When you see an 'Inbox quality' issue":
   ```markdown
   ## When you see an "Inbox quality" issue (#185)

   The `felix-admin-capture` agent files a batched issue with title prefix `Inbox quality:` when one or more inbox notes have unparseable frontmatter. To resolve:

   1. Open the issue. Each row in the table identifies an affected note by filename and the specific malformation.
   2. Open each affected note in Obsidian. The agent has injected a `> [!error] felix-capture:` callout at the top showing the same error.
   3. Fix the malformation. Common cases:
      - **Leading whitespace before `---`** — delete blank lines / spaces / BOM before the opening `---`.
      - **UTF-8 BOM** — re-save the file in UTF-8 without BOM.
      - **Missing closing `---`** — add the closing fence.
      - **Invalid YAML** — fix the syntax (mismatched quotes, unescaped colons).
   4. Save. The next cron tick will:
      - Re-classify the note as well-formed
      - Auto-strip the callout marker
      - Route the note normally
   5. Once all listed notes are fixed (or moved out of `01-Inbox/`), close the Inbox-quality issue manually. The agent files a new one only if more parse failures appear; it does NOT auto-update the existing issue.
   ```

3. Add a brief mention of the routing log:
   > "Routing dedup state lives at `~/second-brain/agents/state/inbox-routing.jsonl` on office2 (per Restic backup nightly). If a note is mistakenly skipped, inspect this file via `cat | jq` and remove the offending entry; the next tick will re-route normally."

**Files**: `docs/runbooks/inbox-ops.md` (modify or stub-create).

---

## Definition of Done

- All three subtasks complete.
- `python3 tooling/scripts/validate_docs.py` exits 0.
- `service-inventory.json` has the new `state_files` entry for `felix-admin-capture` plus an updated_by field referencing `#185`.
- `service-inventory.md` describes the routing log + parse-failure surface.
- `inbox-ops.md` (or equivalent runbook) has the operator workflow.
- Commit prefix: `docs(WP06):` referencing #185.

## Risks

- **`inbox-ops.md` may not exist**: verify at the start of T020. If absent, decide between stub-create or defer — discuss with the implementing agent if unclear.
- **`service-inventory.json` schema variance**: the `state_files` field may not match an existing convention. If `components` is the existing pattern for state-file-like artefacts, use that instead. Verify against the existing felix-admin-capture sub-block during implementation.

## Reviewer guidance

- Verify: file-level `last_updated` is bumped in `service-inventory.json`.
- Verify: file-level `updated_by` extends the existing chain (no overwrite of prior credits).
- Verify: the runbook update is operator-friendly (concrete steps, not internal jargon).

## Suggested implement command

```bash
spec-kitty agent action implement WP06 --agent <name>
```
