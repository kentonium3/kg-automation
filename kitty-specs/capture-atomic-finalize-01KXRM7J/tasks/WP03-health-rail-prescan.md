---
work_package_id: WP03
title: Health rail + prescan terminal-state hygiene
dependencies:
- WP01
requirement_refs:
- FR-008
- FR-013
- NFR-001
tracker_refs: []
planning_base_branch: fix/capture-atomic-finalize
merge_target_branch: fix/capture-atomic-finalize
branch_strategy: Planning artifacts for this mission were generated on fix/capture-atomic-finalize. During /spec-kitty.implement this WP may branch from a dependency-specific base, but completed changes must merge back into fix/capture-atomic-finalize unless the human explicitly redirects the landing branch.
subtasks:
- T014
- T015
- T016
- T017
phase: Phase 2 - Core
agent: "claude:sonnet:python-pedro:implementer"
shell_pid: "87927"
shell_pid_created_at: "1784314727.75145"
history:
- at: '2026-07-17T18:30:00Z'
  actor: system
  action: Prompt generated via /spec-kitty.tasks
agent_profile: python-pedro
authoritative_surface: scripts/inbox/prescan
create_intent:
- tests/inbox/test_prescan_health_rail.py
execution_mode: code_change
model: claude-sonnet-5
owned_files:
- scripts/inbox/prescan.py
- tests/inbox/test_prescan_health_rail.py
role: implementer
tags: []
---

# Work Package Prompt: WP03 – Health rail + prescan terminal-state hygiene

## ⚡ Do This First: Load Agent Profile

Use the `/ad-hoc-profile-load` skill to load the agent profile specified in the frontmatter, and behave according to its guidance before parsing the rest of this prompt.

- **Profile**: `python-pedro`
- **Role**: `implementer`
- **Agent/tool**: `claude`

---

## Branch Strategy

Planning branch: `fix/capture-atomic-finalize`. Merge target: `fix/capture-atomic-finalize`. Execution worktree per `lanes.json`.

## Objective

Make the silent-loss signature **visible** and stop reprocessing loops: add a
`processed-without-routing-log` anomaly to `prescan`, make inbox `needs-review` terminal,
and shift the note-level dedup from routing-log-presence to note `status`.

**Read first**: `../research.md` (D9 dedup shift, D13), `../data-model.md` (ArchiveAnomaly),
and the current `scripts/inbox/prescan.py` (`scan_archive_anomalies`, `classify_file`,
`PrescanResult`, how `unprocessed_paths` is built).

## Subtasks

### T014 — `processed-without-routing-log` anomaly
- Add a new `ArchiveAnomaly` classification `processed-without-routing-log`: a note whose
  status IS `processed` but whose blocks are **not represented** in the routing log
  (cross-reference `RoutingLogReader` — use WP01's note-level `has(filename)` for the
  presence check; a processed note must have ≥1 routing-log entry, and `empty`-disposition
  notes have a `kind=empty` entry so they pass).
- Scan **both** `01-Inbox/` (processed notes await the 7-day archive there) and
  `02-Inbox-Processed/`. Reuse `ARCHIVE_SCAN_CAP` and the `inbox-processing-` daily-log exclusion.
- Read-only; no remediation. Warning text: "status:processed but no routing-log entry
  (silent-loss signature #746)".

### T015 — `needs-review` terminal + dedup shift
- Classify inbox `needs-review` notes as **terminal**: exclude them from `unprocessed_paths`
  so they don't reprocess every tick (FR-008). They are also excluded from the T014 anomaly
  (not `processed`).
- Shift the note-level dedup: prescan should treat a note as done based on its `status`
  (`processed`/`needs-review` terminal), not merely on routing-log-filename presence. The
  per-block idempotency now lives in WP02's finalize (`has_block`), so the old note-level
  log dedup is redundant and conflicts with the new invariant — remove/replace it carefully.

### T016 — Surface into `PrescanResult`
- Ensure the new anomaly rides in `PrescanResult.archive_anomalies` (already a field) so the
  agent's Step 1 IDLE gate (WP04) can read and surface it. Confirm the JSON output carries it.

### T017 — Tests (`tests/inbox/test_prescan_health_rail.py`)
- Inject a `processed` note absent from the routing log → anomaly reported.
- A correctly-finalized corpus (all blocks logged, empty note with kind=empty) → **zero** anomalies.
- A `needs-review` note in `01-Inbox/` → NOT in `unprocessed_paths`, NOT an anomaly.
- Cap + daily-log exclusion still honored.

## Definition of Done
- `pytest tests/inbox/test_prescan_health_rail.py` + existing prescan tests green.
- No false positives on empty-logged or needs-review notes.
- `needs-review` no longer reprocesses.

## Risks / reviewer guidance
- The dedup shift is delicate: ensure a note whose blocks are mid-flight (unprocessed, some
  blocks logged from a prior failed tick) is still listed for reprocessing so WP02's finalize
  can reconcile and complete it. Terminal = `processed` or `needs-review` ONLY.
- Reviewer: confirm the invariant check matches WP02's logging (a processed note always has
  a routing-log entry, incl. empty) so the rail has zero legitimate false positives.

## Activity Log

- 2026-07-17T18:59:04Z – claude:sonnet:python-pedro:implementer – shell_pid=87927 – Assigned agent via action command
