---
work_package_id: WP02
title: Prompts + runbook + architecture data cleanup
dependencies:
- WP01
requirement_refs:
- FR-009
- FR-010
- FR-011
- FR-012
- FR-013
- NFR-002
- C-002
- C-004
planning_base_branch: main
merge_target_branch: main
branch_strategy: Planning artifacts for this feature were generated on main. During /spec-kitty.implement this WP may branch from a dependency-specific base, but completed changes must merge back into main unless the human explicitly redirects the landing branch.
base_branch: kitty/mission-remove-escalation-v1-parity-01KT4VTD
base_commit: f4f07bee9f7dc80de77f8ef6aab2a371223a59be
created_at: '2026-06-03T02:11:14.257135+00:00'
subtasks:
- T007
- T008
- T009
- T010
- T011
shell_pid: "78915"
agent: "claude"
history:
- timestamp: '2026-06-02T19:30:00Z'
  actor: claude:opus-4-7:planner
  action: created
authoritative_surface: scripts/openclaw/
execution_mode: code_change
owned_files:
- scripts/openclaw/agents/felix-admin-escalation/AGENTS.md
- scripts/openclaw/agents/felix-admin-escalation/TOOLS.md
- scripts/openclaw/skills/escalation/SKILL.md
- docs/runbooks/escalation-ops.md
- docs/design/architecture/data/data-flows.json
- docs/design/architecture/data/service-inventory.json
- docs/design/architecture/data-flows.md
- docs/design/architecture/service-inventory.md
tags: []
---

# WP02 — Prompts + runbook + architecture data cleanup

**Mission**: `remove-escalation-v1-parity-01KT4VTD` — [spec.md](../spec.md), [plan.md](../plan.md), [contracts/escalation-side-effects.contract.md](../contracts/escalation-side-effects.contract.md)
**Depends on**: [WP01](WP01-code-and-tests-cleanup.md) (code + tests cleanup)

## Objective

Update every non-code surface that referenced the v1 parity behavior or the phantom-subscription detection: the felix-admin-escalation agent prompts, the operator runbook, the machine-readable architecture data (data-flows.json, service-inventory.json), and the markdown views derived from that data.

## Context

WP01 deleted the code that wrote v1 comments and the code that read them for phantom detection. WP02 brings the documentation surface in line. Per spec C-004, both WPs must land in the same merge so the deployed agent prompts match the deployed code behavior.

## Branch Strategy

- Planning base branch: `main`
- Final merge target: `main`
- Execution worktree: allocated automatically by `spec-kitty next` per `lanes.json`. Starts after WP01 is `approved`.

---

## Subtask T007 — Strip v1 parity language from agent prompts

**Purpose**: Update the three deployed prompt artifacts for `felix-admin-escalation` to remove all references to v1 parity behavior, the C-001 parity period, the soak window, and the phantom-subscription detector.

**Steps**:

1. Open `scripts/openclaw/skills/escalation/SKILL.md`. Read it end-to-end. Identify and edit:
   - The "v1 comment format vocabulary" section (the table that maps event_types to `[Felix-Escalation] YYYY-MM-DD | …` strings) — delete entirely. JSONL is the canonical record; the agent does not need to know the comment vocabulary.
   - Any sentence that says "during the soak we also write a `[Felix-Escalation]` comment" or "in parity with v1" — delete.
   - Any reference to phantom-subscription detection — delete.
   - Keep all JSONL-as-canonical framing untouched.
2. Open `scripts/openclaw/agents/felix-admin-escalation/AGENTS.md`. Apply the same surgical edits — delete v1 parity language, soak references, phantom-subscription references. Keep the operating-mode framing, output-discipline rules, and JSONL canonicality untouched.
3. Open `scripts/openclaw/agents/felix-admin-escalation/TOOLS.md`. Apply the same edits. This file typically lists the tools the agent can call — remove any tool listing or note that referenced the comment-write or phantom detection behavior.
4. After each file edit, re-read the surrounding sections to verify coherence. The post-edit text should read as if v1 parity never existed.
5. Grep within each file to confirm no surviving references to `Felix-Escalation`, `C-001 parity`, `comment-write`, `phantom_subscription`, `phantom subscription`, or `soak`.

**Files**:
- `scripts/openclaw/skills/escalation/SKILL.md`
- `scripts/openclaw/agents/felix-admin-escalation/AGENTS.md`
- `scripts/openclaw/agents/felix-admin-escalation/TOOLS.md`

**Validation**:
- [ ] `grep -nE "Felix-Escalation|C-001 parity|phantom_subscription|phantom subscription" scripts/openclaw/skills/escalation/SKILL.md scripts/openclaw/agents/felix-admin-escalation/AGENTS.md scripts/openclaw/agents/felix-admin-escalation/TOOLS.md` returns zero matches.
- [ ] Each file remains internally coherent — no dangling references to deleted sections.
- [ ] File sizes stay within the ~14K-char effective budget per OpenClaw's per-file injection budget (verified by character count; per memory `reference_openclaw_gotchas`).

---

## Subtask T008 — Strip parity content from the operator runbook

**Purpose**: Remove the "check comments match JSONL" parity verification queries and any phantom-subscription operator guidance from the runbook. JSONL-only verification queries remain.

**Steps**:

1. Open `docs/runbooks/escalation-ops.md`. Read it end-to-end.
2. Identify sections to edit:
   - Any "Soak-period verification" section that compares JSONL records to `[Felix-Escalation]` comments — delete.
   - Any "Phantom-subscription investigation" section — delete.
   - Any introductory paragraph that frames the substrate as "JSONL with parity comments for rollback" — update to "JSONL canonical".
3. Preserve all JSONL-native operator queries (the ones that look at `project-*-escalation-history.jsonl` directly).
4. Update any cross-references that point at deleted sections.

**Files**:
- `docs/runbooks/escalation-ops.md`

**Validation**:
- [ ] `grep -nE "Felix-Escalation|phantom_subscription|phantom subscription|parity" docs/runbooks/escalation-ops.md` returns zero matches.
- [ ] No broken internal links remain.

---

## Subtask T009 — Remove `escalation-event-write-vikunja` from data-flows.json

**Purpose**: The architecture data flow that documented the v1 parity write must be removed. The markdown view (`data-flows.md`) must be regenerated to match.

**Steps**:

1. Open `docs/design/architecture/data/data-flows.json`.
2. Locate the entry with `flow_id: "escalation-event-write-vikunja"` (added in #309 WP08).
3. Delete that entry from the `flows` array.
4. Confirm any other flow entry that mentions `[Felix-Escalation]` is also updated — typically the JSONL-write flow (`escalation-event-write-jsonl` or similar) might reference parity in its description. Trim those references.
5. Add `updated_by: "#376"` (the source issue) to the top-level metadata or to the affected entries, following the project's existing convention. If the convention is per-entry, add to each entry that's modified.
6. Regenerate the markdown view at `docs/design/architecture/data-flows.md`. Check the repo's existing pattern (likely there's a regeneration script or convention); if regeneration is manual, edit the markdown view to match the new JSON state.

**Files**:
- `docs/design/architecture/data/data-flows.json`
- `docs/design/architecture/data-flows.md`

**Validation**:
- [ ] `jq '[.flows[] | select(.flow_id == "escalation-event-write-vikunja")] | length' docs/design/architecture/data/data-flows.json` returns `0`.
- [ ] `tooling/scripts/validate_docs.py` exits 0 (defer the full sweep to T011, but spot-check on this file).
- [ ] The markdown view reflects the JSON state.

---

## Subtask T010 — Strip v1 parity reference from service-inventory.json

**Purpose**: The `felix-admin-escalation` entry in service-inventory.json mentions v1 parity in its purpose description. Update it to drop that reference. Regenerate the markdown view.

**Steps**:

1. Open `docs/design/architecture/data/service-inventory.json`.
2. Locate the entry for `felix-admin-escalation`.
3. Edit the `purpose` (and any other field) to remove references to v1 parity, soak-period behavior, or the comment-write substrate. The new description should accurately describe the post-cleanup agent: "Generates and dispatches daily escalation alerts; writes JSONL state for each event."
4. Add `updated_by: "#376"` per the project's existing convention.
5. Regenerate the markdown view at `docs/design/architecture/service-inventory.md` to match.

**Files**:
- `docs/design/architecture/data/service-inventory.json`
- `docs/design/architecture/service-inventory.md`

**Validation**:
- [ ] `jq '.services[] | select(.id == "felix-admin-escalation") | .purpose' docs/design/architecture/data/service-inventory.json` does NOT contain "parity", "soak", "v1", or "[Felix-Escalation]".
- [ ] `tooling/scripts/validate_docs.py` exits 0.
- [ ] Markdown view reflects the JSON state.

---

## Subtask T011 — Run `validate_docs.py` + final grep sweep

**Purpose**: Confirm the entire codebase is free of v1 parity references in active surfaces.

**Steps**:

1. Run the docs validator:
   ```
   python tooling/scripts/validate_docs.py
   ```
2. Run the final grep sweep — this is the comprehensive NFR-002 check:
   ```
   grep -rnE "Felix-Escalation|_format_v1_comment|_COMMENT_PREFIX|_COMMENT_MARKER|_count_escalation_comments|phantom_subscription|C-001 parity|comment.*parity" \
     scripts/ docs/runbooks/ docs/design/architecture/data/ tests/escalation/ tests/enrichment/
   ```
   Expected: zero matches.
3. If any match remains in an active surface, return to the appropriate subtask. Note: matches in `kitty-specs/`, `docs/archive/`, ADR-0002, the d6 survey, and `vikunja-task-model-research.md` are permitted (historical record).
4. If `validate_docs.py` reports any error, address by editing the relevant JSON/markdown file.

**Validation**:
- [ ] `tooling/scripts/validate_docs.py` exits 0.
- [ ] Final grep returns zero matches in active surfaces.

---

## Definition of Done

- [ ] All five subtasks marked done.
- [ ] Agent prompts, runbook, and architecture data no longer reference v1 parity behavior or phantom-subscription detection.
- [ ] `validate_docs.py` is green; final grep returns zero matches in active surfaces.
- [ ] No unrelated edits to code (WP01's domain).

## Reviewer guidance

A reviewer should verify, in order:

1. **Each of the three agent prompts reads coherently** after edits — no dangling references, no orphan sections.
2. **The runbook still serves operators** for JSONL-native verification queries; only parity-specific queries are removed.
3. **`data-flows.json` no longer contains `escalation-event-write-vikunja`** and the matching markdown view is in sync.
4. **`service-inventory.json`'s felix-admin-escalation entry** describes the post-cleanup behavior accurately.
5. **The final grep sweep is clean** across all active surfaces.

## Risks

- **Markdown view regeneration drift**: if the markdown views are hand-maintained (rather than script-regenerated), there's risk the markdown and JSON drift out of sync. T009 and T010's validation steps catch this.
- **OpenClaw agent prompt size limits**: per memory `reference_openclaw_gotchas`, AGENTS.md has ~26% rawChars inflation in OpenClaw's accounting. The edits in T007 should reduce file size, but verify the post-edit AGENTS.md stays comfortably under the ~14K-char effective budget.
- **Runbook fragmentation**: if the runbook references the soak doc (`escalation-soak-window.md`, which we updated retroactively today), confirm the cross-reference still makes sense post-edit.

## Activity Log

- 2026-06-03T02:11:16Z – claude – shell_pid=71001 – Assigned agent via action command
- 2026-06-03T02:23:51Z – claude – shell_pid=71001 – WP02 implementation done; grep clean; validate_docs OK; 320 tests pass
- 2026-06-03T02:23:54Z – codex – shell_pid=74387 – Started review via action command
- 2026-06-03T02:29:18Z – claude – shell_pid=76445 – Started implementation via action command
- 2026-06-03T02:29:21Z – claude – shell_pid=76445 – cycle-1 fix; deprecated entries deleted; phantom wording out of runbook
- 2026-06-03T02:29:24Z – codex – shell_pid=76445 – Started review via action command
- 2026-06-03T02:36:18Z – claude – shell_pid=78915 – Started implementation via action command
- 2026-06-03T02:36:22Z – claude – shell_pid=78915 – cycle-2 fix; current-state prose; grep clean
