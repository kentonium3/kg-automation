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
agent: "claude:opus:reviewer-renata:reviewer"
shell_pid: "2301"
shell_pid_created_at: "1784317287.09685"
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

### T020 — TOOLS.md (+ close TOOLS.md.tmpl twin)
- Remove the standalone `mark_processed` / `append_routing_entry` tool surfaces from
  `TOOLS.md`; add the single `route_and_finalize` command surface (with the plan shape).
- `TOOLS.md` and `TOOLS.md.tmpl` are close twins (~1.1 KB each) — mirror the change into
  `TOOLS.md.tmpl` for consistency. **`AGENTS.md` is the authoritative, deployed artifact**
  (the deploy pipeline `deploy_agent_prompts.py` copies `AGENTS.md`/`TOOLS.md` literally and
  **skips `*.tmpl`**). `AGENTS.md.tmpl` is a **stale, non-deployed, structurally-divergent**
  older generation (42 KB vs the 21.5 KB deployed AGENTS.md, pre-#737) — do **NOT** mirror
  finalize edits into it (that deepens the Frankenstein). Leave `AGENTS.md.tmpl` untouched;
  the AGENTS.md/.tmpl divergence is pre-existing debt tracked as a separate follow-up.

### T021 — Size discipline + parity verification
- **There is no 12,000-byte cap on `felix-admin-capture/AGENTS.md`** (the CAP=12000 in
  `scripts/openclaw/agents/tests/test_agents_md_size.py` covers only `main/` and
  `felix-admin-calendar/` — a different mission's NFR). AGENTS.md is already ~21.5 KB in
  production and deployed fine. Requirement: the rewrite must **not materially grow** the
  file; removing per-kind Step 3 route calls + Steps 5b/5c should **trim** it. Report the
  before/after `wc -c`. Keep the Output-Discipline hard rules verbatim (do NOT tear the file
  down to hit an inapplicable cap).
- Run `python3 -m pytest scripts/openclaw/agents/tests/test_agents_md_size.py -q` — must stay
  green (it does not cover capture, so any capture size passes; this just confirms no regression
  to main/calendar).
- Verify `TOOLS.md` ↔ `TOOLS.md.tmpl` parity.

## Definition of Done
- The prompt describes exactly ONE finalize command per note; no standalone mark/append steps remain.
- Step 1 IDLE gate blocks on `archive_anomalies`.
- AGENTS.md not materially grown (before/after wc -c reported); size-cap test green (no main/calendar regression); `TOOLS.md.tmpl` mirrored; AGENTS.md.tmpl left as pre-existing debt.
- Output-Discipline hard rules and privacy boundary preserved verbatim.

## Risks / reviewer guidance
- This is prompt authoring, not code. No hard byte cap applies to capture; keep the rewrite tight and trim where 5b/5c is removed.
- Reviewer: confirm (a) no path lets the agent mark a note processed except via finalize;
  (b) the IDLE gate now includes archive_anomalies; (c) `.tmpl` parity; (d) the calendar
  clarification + parse-failure + privacy + no-delete invariants survive the rewrite.

## Activity Log

- 2026-07-17T19:23:35Z – claude:sonnet:curator-carla:implementer – shell_pid=96267 – Assigned agent via action command
- 2026-07-17T19:41:42Z – claude:sonnet:curator-carla:implementer – shell_pid=96267 – Ready for review: note-level single-finalize standing orders; AGENTS.md trimmed to 21015B; IDLE gate surfaces anomalies; T018b verbatim-content; commit f8b62bc5
- 2026-07-17T19:41:58Z – claude:opus:reviewer-renata:reviewer – shell_pid=2301 – Started review via action command
- 2026-07-17T19:46:11Z – user – shell_pid=2301 – Review passed (reviewer-renata): note-level single-finalize; no mark-processed path outside finalize; verbatim-content load-bearing note present; invariants verbatim; AGENTS.md trimmed to 21015B.
