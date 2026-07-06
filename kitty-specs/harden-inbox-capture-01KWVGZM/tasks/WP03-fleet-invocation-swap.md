---
work_package_id: WP03
title: Fleet invocation-form swap (escalation, habits, calendar, tasker, main)
dependencies:
- WP01
requirement_refs:
- FR-001
tracker_refs: []
planning_base_branch: feat/harden-inbox-capture
merge_target_branch: feat/harden-inbox-capture
branch_strategy: Planning artifacts for this mission were generated on feat/harden-inbox-capture. During /spec-kitty.implement this WP may branch from a dependency-specific base, but completed changes must merge back into feat/harden-inbox-capture unless the human explicitly redirects the landing branch.
subtasks:
- T020
- T021
- T022
- T023
- T024
- T025
agent: claude
history:
- 2026-07-06 authored from plan IC-02 (non-capture fleet)
agent_profile: curator-carla
authoritative_surface: scripts/openclaw/agents/felix-admin-escalation/
create_intent: []
execution_mode: code_change
model: claude-sonnet-4-6
owned_files:
- scripts/openclaw/agents/felix-admin-escalation/AGENTS.md
- scripts/openclaw/agents/felix-admin-habits/AGENTS.md
- scripts/openclaw/agents/felix-admin-calendar/AGENTS.md
- scripts/openclaw/agents/felix-admin-tasker/AGENTS.md
- scripts/openclaw/agents/felix-admin-tasker/AGENTS.md.tmpl
- scripts/openclaw/agents/main/AGENTS.md
role: implementer
tags: []
---

## ⚡ Do This First: Load Agent Profile

Before reading anything else, run `/ad-hoc-profile-load curator-carla` (role: implementer).
Then read this WP and `../contracts/invocation-form.md`.

## Objective

Apply the exec-sanitization-immune invocation form to the other five active agents so the whole
fleet stops failing under exec's stripped `PYTHONPATH`. Pure invocation-form swaps — **no model
changes, no rewording, no behavior changes** for these agents (only capture moves to sonnet, in
WP02). `felix-doc-auditor` is suspended — do NOT touch it.

**Depends on WP01** (checker accepts the new form). This WP + WP02 together make the fleet checker
report **ok**.

## Subtasks

For each file below, replace every helper invocation with the exact checkout-cd form:
- `cd "${PYTHONPATH:?PYTHONPATH unset}" && python[3] -m scripts.<pkg>.<mod> …`
  → `cd /home/claude/kg-automation && python[3] -m scripts.<pkg>.<mod> …`
- `cd "${PYTHONPATH:?…}" && python[3] scripts/<path>.py …`
  → `cd /home/claude/kg-automation && python[3] scripts/<path>.py …`
- any bare relative `scripts/<path>.py` or unanchored `python3 scripts/<path>.py`
  → prefix with `cd /home/claude/kg-automation && python3 …`.
Preserve every argument, `&&` chain, and surrounding prose. Use the EXACT path.

### T020 — `felix-admin-escalation/AGENTS.md` (8 occurrences)
### T021 — `felix-admin-habits/AGENTS.md` (8 occurrences; note the P2-bug filing line ~228 uses `python3 scripts/openclaw/agents/main/felix-file-issue.py` — anchor it too)
### T022 — `felix-admin-calendar/AGENTS.md` (4 occurrences)
### T023 — `felix-admin-tasker/AGENTS.md` (3) + `felix-admin-tasker/AGENTS.md.tmpl` (1)
### T024 — `main/AGENTS.md` (1 occurrence)

### T025 — Verify fleet checker

- `python3 -m scripts.openclaw.agents.env_assumptions` → **ok** across all active workspaces
  (assumes WP02 also landed; if run before WP02, only capture findings should remain).
- `grep -rn 'PYTHONPATH:?' scripts/openclaw/agents/*/AGENTS.md scripts/openclaw/agents/*/AGENTS.md.tmpl`
  → empty (excluding suspended felix-doc-auditor, which has none anyway).
- `pytest scripts/openclaw/agents/tests/ -q` green (incl. `test_agents_md_size.py`).

## Definition of Done

- [ ] All five agents' invocations use `cd /home/claude/kg-automation && …` (exact path).
- [ ] tasker `.tmpl` swapped; no `{{VAULT_*}}` or behavior changes.
- [ ] No model/identity/behavior changes for these agents (invocation form only).
- [ ] Fleet checker = ok (with WP02); `pytest` green.

## Reviewer guidance

- Diff should be invocation-prefix-only for each file — flag any incidental prose/behavior edits.
- Confirm the habits felix-file-issue.py line and any `log_action.py` lines are anchored.
- Confirm zero `${PYTHONPATH:?}` remain fleet-wide.

## Branch Strategy

Planning base `feat/harden-inbox-capture`; final merge target `feat/harden-inbox-capture`.
Branches from WP01; parallel with WP02/WP04. Command: `spec-kitty agent action implement WP03 --agent claude`.
