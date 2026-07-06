---
work_package_id: WP02
title: Capture prompt hardening (invocation swap + reword + sonnet identity)
dependencies:
- WP01
requirement_refs:
- FR-001
- FR-003
- FR-004
- FR-005
tracker_refs: []
planning_base_branch: feat/harden-inbox-capture
merge_target_branch: feat/harden-inbox-capture
branch_strategy: Planning artifacts for this mission were generated on feat/harden-inbox-capture. During /spec-kitty.implement this WP may branch from a dependency-specific base, but completed changes must merge back into feat/harden-inbox-capture unless the human explicitly redirects the landing branch.
subtasks:
- T010
- T011
- T012
- T013
- T014
agent: "claude"
shell_pid: "43742"
history:
- 2026-07-06 authored from plan IC-02/IC-03 (capture portion; owns the whole capture prompt to avoid an ownership split)
agent_profile: curator-carla
authoritative_surface: scripts/openclaw/agents/felix-admin-capture/
create_intent: []
execution_mode: code_change
model: claude-sonnet-4-6
owned_files:
- scripts/openclaw/agents/felix-admin-capture/AGENTS.md
- scripts/openclaw/agents/felix-admin-capture/AGENTS.md.tmpl
role: implementer
tags: []
---

## ⚡ Do This First: Load Agent Profile

Before reading anything else, run `/ad-hoc-profile-load curator-carla` (role: implementer).
Then read this WP, `../contracts/invocation-form.md`, and `../research.md` (D1/D2).

## Objective

Make `felix-admin-capture` reliable and hallucination-proof by owning the **entire** capture
prompt: (a) swap every helper invocation to the exec-sanitization-immune self-contained form,
(b) reword the line-74 prose so no model can read "helpers live at `<path>`" and negate it, and
(c) update the `:haiku` identity to `:sonnet`. All three land together because they touch the
same file (no ownership split with WP03).

**Depends on WP01** — the inverted checker must accept the new form. After this WP, capture must
pass `python3 -m scripts.openclaw.agents.env_assumptions`.

## Subtasks

### T010 — Swap all invocations to the checkout-cd form

In `scripts/openclaw/agents/felix-admin-capture/AGENTS.md`, replace **every** helper invocation:
- `cd "${PYTHONPATH:?PYTHONPATH unset}" && python3 -m scripts.inbox.<mod> …`
  → `cd /home/claude/kg-automation && python3 -m scripts.inbox.<mod> …`
  (Steps 1, 1a, 3, 5a, 5b, 5c, 6; the calendar-clarification flow; the Task-bridge fallback.)
- `cd "${PYTHONPATH:?…}" && python scripts/openclaw/observation/log_action.py …`
  → `cd /home/claude/kg-automation && python scripts/openclaw/observation/log_action.py …`
- **Line ~97 (Codex HIGH-1)**: the `github_issue` route currently says *invoke*
  `scripts/openclaw/agents/main/felix-file-issue.py` — a bare relative path with no `cd`/`python3`.
  Rewrite to `cd /home/claude/kg-automation && python3 scripts/openclaw/agents/main/felix-file-issue.py …`.
- Grep-sweep afterward: **zero** `${PYTHONPATH:?}` and zero bare `scripts/…py` invocations remain.
- Use the EXACT path `/home/claude/kg-automation` (never `~`, `$PYTHONPATH`, or another user).

### T011 — Reword line 74 (FR-003)

Current: *"Helpers under `scripts/inbox/` do the deterministic work. Invoke via `python3 -m
scripts.inbox.<helper>` form (`--help` for any helper's CLI)."* — haiku reads this as a
location claim and negates it ("helpers don't exist"). Reword so it:
- references helpers ONLY as opaque, self-contained commands (the checkout-cd form), and
- states that a non-zero helper exit means report the actual stderr — never speculate that
  infrastructure is "missing/not deployed/not implemented."
Do not name a directory the model can then assert is absent.

### T012 — Identity `:haiku`→`:sonnet` (FR-004)

Replace `Sent by felix-admin-capture:haiku` → `Sent by felix-admin-capture:sonnet` at every
occurrence (message-identity section, calendar-clarification example, tasker-delegation payload).

### T013 — Apply the same swaps to `AGENTS.md.tmpl`

The `.tmpl` is scanned by `validate_workspace`/`env_assumptions` (both `AGENTS.md` and `.tmpl`).
Swap every `${PYTHONPATH:?}` invocation in the `.tmpl` to the checkout-cd form so the scan stays
clean. **Scope note**: the `.tmpl` is stale (923 lines vs the 223-line deployed `AGENTS.md`); do
NOT attempt a full re-sync here — only fix the invocation-form occurrences (a full `.tmpl`
re-sync is a separately-filed follow-up). Do NOT change `{{VAULT_*}}` markers.

### T014 — Verify

- `python3 -m scripts.openclaw.agents.env_assumptions` reports no capture findings.
- `pytest scripts/openclaw/agents/tests/ -q` green (esp. `test_agents_md_size.py` — capture
  `AGENTS.md` must stay within the size budget; the reword must not blow the char limit).
- Grep: `grep -n 'PYTHONPATH:?' scripts/openclaw/agents/felix-admin-capture/AGENTS.md*` → empty.

## Definition of Done

- [ ] Every capture invocation uses `cd /home/claude/kg-automation && …` (incl. felix-file-issue.py).
- [ ] Line-74 prose reworded per FR-003; no negatable location claim; stderr-on-failure rule stated.
- [ ] Identity is `:sonnet` everywhere in the capture prompt.
- [ ] `.tmpl` invocation forms swapped; `{{VAULT_*}}` untouched; no full re-sync.
- [ ] Capture passes the inverted checker; `pytest` green; size budget respected.
- [ ] FR-005 non-regression: the calendar clarification flow (Step 3 + `handle_clarification_state`)
      is preserved — the reword/swap must not remove or alter the ask-and-reply loop logic.

## Reviewer guidance

- Confirm zero `${PYTHONPATH:?}` / bare `scripts/…py` remain in capture `AGENTS.md` and `.tmpl`.
- Confirm the line-74 reword cannot be read as "helpers are at X" (then negated).
- Confirm the clarification flow (FR-005) is intact and the size budget holds.

## Branch Strategy

Planning base `feat/harden-inbox-capture`; final merge target `feat/harden-inbox-capture`.
Branches from WP01. Command: `spec-kitty agent action implement WP02 --agent claude`.

## Activity Log

- 2026-07-06T12:21:47Z – claude – shell_pid=40163 – Assigned agent via action command
- 2026-07-06T12:28:23Z – claude – shell_pid=40163 – Capture: 14 invocation swaps + line-74 reword + sonnet identity + .tmpl; checker clean, grep empty, size ok, FR-005 intact
- 2026-07-06T12:28:28Z – claude – shell_pid=43742 – Started review via action command
