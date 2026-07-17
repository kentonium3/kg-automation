---
work_package_id: WP05
title: Agent wiring (capture and main prompts)
dependencies:
- WP02
- WP04
requirement_refs:
- FR-004
- FR-006
tracker_refs: []
planning_base_branch: feat/task-intake-validation-loop
merge_target_branch: feat/task-intake-validation-loop
branch_strategy: Planning artifacts for this mission were generated on feat/task-intake-validation-loop. During /spec-kitty.implement this WP may branch from a dependency-specific base, but completed changes must merge back into feat/task-intake-validation-loop unless the human explicitly redirects the landing branch.
subtasks:
- T020
- T021
- T022
phase: Phase 4 - Integration
agent: claude
history:
- at: '2026-07-17T21:55:00Z'
  actor: system
  action: Prompt generated via /spec-kitty.tasks
agent_profile: curator-carla
authoritative_surface: scripts/openclaw/agents
create_intent: []
execution_mode: code_change
model: claude-sonnet-5
owned_files:
- scripts/openclaw/agents/felix-admin-capture/AGENTS.md
- scripts/openclaw/agents/felix-admin-capture/AGENTS.md.tmpl
- scripts/openclaw/agents/main/AGENTS.md
- scripts/openclaw/agents/main/TOOLS.md
role: implementer
tags: []
---

# Work Package Prompt: WP05 — Agent wiring (capture and main prompts)

## ⚡ Do This First: Load Agent Profile

Use `/ad-hoc-profile-load` to load the profile and behave per its guidance first.

- **Profile**: `curator-carla` · **Role**: `implementer` · **Agent/tool**: `claude`

---

## Branch Strategy

Planning branch / merge target: `feat/task-intake-validation-loop`. Worktree per `lanes.json`.

## Objective

Wire the two deterministic helpers into the agents. The **capture** agent (inbox cron)
runs the scan after `route_and_finalize` and includes the digest in its WhatsApp output.
The **main** DM agent recognizes an intake reply (content-based correlation), invokes the
apply helper, and confirms per-line results. Keep the LLM strictly to framing + proposing
canonical names for genuinely unresolved tokens (Directive-6 boundary).

**FIRST verify the exact deploy-source paths** — agent slug ≠ deploy dir. Confirm the real
`AGENTS.md`/`TOOLS.md`(+`.tmpl`) template sources for `felix-admin-capture` and `main` under
`scripts/openclaw/agents/` (or the vault-template source that `agent-prompt-sync` renders);
adjust `owned_files` if the real paths differ (record a one-line rationale). **capture uses a
`.tmpl`** render source (edit `AGENTS.md.tmpl` and regenerate the rendered `AGENTS.md` so they
stay byte-consistent — a stale `.tmpl` is a live landmine, #746); **main has no `.tmpl`** and is
edited directly (`AGENTS.md` / `TOOLS.md`).

Read first: spec FR-004/006 + research R1/R5/R6, `contracts/helpers.contract.md`, the existing
capture `AGENTS.md` (route_and_finalize flow + Output Discipline block), the main `AGENTS.md`/
`TOOLS.md` (DM-reply handling), and `docs/design/reference_felix_output_discipline_pattern`
conventions.

## Subtasks

### T020 — Capture agent: scan + emit digest (FR-004)
After the note-level `route_and_finalize` step, the capture agent runs
`python3 -m scripts.intake.scan_inbox --json` and, if `incomplete > 0`, includes the single
numbered `digest_text` in its WhatsApp output (one batched message; N tasks → 1 message per
Output Discipline). `incomplete == 0` → no intake message. Update both `.tmpl` and rendered `.md`.

### T021 — Main agent: correlate + apply + confirm (FR-004/006)
Teach the main agent to recognize an intake reply (numbered shorthand lines correlated to the
most-recent digest, content-based — WhatsApp quote-reply is NOT available, research R1). It
invokes `python3 -m scripts.intake.apply_reply --reply - --json`, passing a constrained
`--unresolved` map **only** for tokens the parser could not resolve (canonical name only, never
an id), and confirms the per-line results (applied / echoed_back / overload_flagged / etc.).
Update main `AGENTS.md` + `TOOLS.md` directly (mechanics in TOOLS, rules in AGENTS; main has no `.tmpl`).

### T022 — Byte-cap + Directive-6 leak check
Verify each edited `AGENTS.md` stays under the 12,000-byte hard cap (`test_agents_md_size.py`)
with headroom; rebalance AGENTS↔TOOLS if needed. Confirm no deterministic work leaked to the LLM
(the agent only frames + proposes canonical names; scan/parse/apply are the helpers).

## Definition of Done
- Capture prompt runs the scan + emits the digest; main prompt correlates + applies + confirms.
- `.tmpl` and rendered `.md` byte-consistent; all AGENTS.md under the byte cap.
- No Directive-6 leak; the LLM never injects ids/labels.

## Risks / reviewer guidance
- **Reviewer:** confirm `.tmpl`↔`.md` parity (#746 landmine), byte-cap headroom, content-based correlation (not quote-reply), and the constrained fallback. Verify Output Discipline (one digest message).

## Implementation command
`spec-kitty agent action implement WP05 --agent claude`
