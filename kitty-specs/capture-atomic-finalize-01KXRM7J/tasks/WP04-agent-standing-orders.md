---
work_package_id: WP04
title: Agent standing-orders rewrite + IDLE-gate surfacing
dependencies:
- WP02
- WP03
requirement_refs:
- FR-005
- FR-014
- FR-016
tracker_refs: []
planning_base_branch: fix/capture-atomic-finalize
merge_target_branch: fix/capture-atomic-finalize
branch_strategy: Planning artifacts for this mission were generated on fix/capture-atomic-finalize. During /spec-kitty.implement this WP may branch from a dependency-specific base, but completed changes must merge back into fix/capture-atomic-finalize unless the human explicitly redirects the landing branch.
subtasks:
- T018
- T019
- T020
- T021
phase: Phase 3 - Integration
agent: "claude:sonnet:curator-carla:implementer"
shell_pid: "96267"
shell_pid_created_at: "1784316182.512466"
history:
- at: '2026-07-17T18:30:00Z'
  actor: system
  action: Prompt generated via /spec-kitty.tasks
agent_profile: curator-carla
authoritative_surface: scripts/openclaw/agents/felix-admin-capture
create_intent: []
execution_mode: code_change
model: claude-sonnet-5
owned_files:
- scripts/openclaw/agents/felix-admin-capture/AGENTS.md
- scripts/openclaw/agents/felix-admin-capture/AGENTS.md.tmpl
- scripts/openclaw/agents/felix-admin-capture/TOOLS.md
- scripts/openclaw/agents/felix-admin-capture/TOOLS.md.tmpl
role: implementer
tags: []
---

# Work Package Prompt: WP04 – Agent standing-orders rewrite + IDLE-gate surfacing

## ⚡ Do This First: Load Agent Profile

Use the `/ad-hoc-profile-load` skill to load the agent profile specified in the frontmatter, and behave according to its guidance before parsing the rest of this prompt.

- **Profile**: `curator-carla`
- **Role**: `implementer`
- **Agent/tool**: `claude`

---

## Branch Strategy

Planning branch: `fix/capture-atomic-finalize`. Merge target: `fix/capture-atomic-finalize`. Execution worktree per `lanes.json`.

## Objective

Rewrite the `felix-admin-capture` standing orders to the **note-level single-finalize
model** and make the new health rail reach Kent. After this WP, the agent classifies a
note's blocks, assembles a routing plan, and invokes **one** `route_and_finalize` per note;
it has no standalone way to mark a note processed.

**Read first**: `../contracts/route-and-finalize-cli.md` (the command the prompt now points
at), `../spec.md` (FR-005/FR-014/FR-016), the current
`scripts/openclaw/agents/felix-admin-capture/AGENTS.md` (Steps 1, 3, 4, 5, 5a/5b/5c and the
Output-Discipline hard rules), and `[[reference_felix_output_discipline_pattern]]`.

## Context

WP02 provides `python3 -m scripts.inbox.route_and_finalize --source-path <note> --plan-file
<plan.json>`. WP03 provides the `processed-without-routing-log` anomaly in
`PrescanResult.archive_anomalies`. This WP wires the prompt to both.

## Subtasks

### T018 — Rewrite routing steps to note-level single-finalize
- Replace the per-kind Step 3 route calls + Steps 5b (`append_routing_entry`) + 5c
  (`mark_processed`) with: **classify the note's blocks → assemble the routing plan JSON →
  invoke ONE `route_and_finalize` for the note**. Branch on the result `status`
  (`finalized` / `needs_clarification` / `error`) per the contract.
- Preserve: the calendar `needs_clarification` clarification flow; the parse-failure path
  (Step 6); the processing log (Step 7); the privacy boundary; the "never delete/move the
  note" invariant.
- Keep the `needs-review` direct-frontmatter-edit exception (the ONLY sanctioned non-finalize
  frontmatter write) — but note it never writes `processed_at`.

### T019 — Step 1 IDLE gate surfaces anomalies (FR-014)
- Update the Step 1 pre-scan gate: the agent may emit `[felix-admin-capture]: IDLE` only when
  `unprocessed_count == 0` AND `parse_failures` empty AND `marker_cleanup_needed` empty AND
  **`archive_anomalies` empty**. When `archive_anomalies` is non-empty (incl.
  `processed-without-routing-log`), the agent must NOT go IDLE — it reports the anomaly to Kent.

### T020 — TOOLS.md + `.tmpl` parity
- Remove the standalone `mark_processed` / `append_routing_entry` tool surfaces from
  `TOOLS.md`; add the single `route_and_finalize` command surface. Mirror every change into
  `TOOLS.md.tmpl` and `AGENTS.md.tmpl` (byte-for-byte parity of the relevant sections).

### T021 — Size cap + parity verification
- Confirm `AGENTS.md` stays under the 12,000-byte cap (`tests/openclaw/.../test_agents_md_size.py`
  or equivalent — locate it). The note-level single-command model should *reduce* size vs. the
  per-kind 5b/5c blocks; if near the cap, move mechanics to `TOOLS.md`.
- Verify `AGENTS.md` ↔ `AGENTS.md.tmpl` and `TOOLS.md` ↔ `TOOLS.md.tmpl` parity.

## Definition of Done
- The prompt describes exactly ONE finalize command per note; no standalone mark/append steps remain.
- Step 1 IDLE gate blocks on `archive_anomalies`.
- Size-cap test green; `.tmpl` mirrors updated.
- Output-Discipline hard rules and privacy boundary preserved verbatim.

## Risks / reviewer guidance
- This is prompt authoring, not code — but the size cap is a hard test. Keep the rewrite tight.
- Reviewer: confirm (a) no path lets the agent mark a note processed except via finalize;
  (b) the IDLE gate now includes archive_anomalies; (c) `.tmpl` parity; (d) the calendar
  clarification + parse-failure + privacy + no-delete invariants survive the rewrite.

## Activity Log

- 2026-07-17T19:23:35Z – claude:sonnet:curator-carla:implementer – shell_pid=96267 – Assigned agent via action command
