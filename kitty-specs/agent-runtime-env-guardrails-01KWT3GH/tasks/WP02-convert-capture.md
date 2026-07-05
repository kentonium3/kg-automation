---
work_package_id: WP02
title: Convert felix-admin-capture invocations
dependencies:
- WP01
requirement_refs:
- FR-005
tracker_refs: []
planning_base_branch: feat/agent-runtime-env-guardrails
merge_target_branch: feat/agent-runtime-env-guardrails
branch_strategy: Planning artifacts for this mission were generated on feat/agent-runtime-env-guardrails. During /spec-kitty.implement this WP may branch from a dependency-specific base, but completed changes must merge back into feat/agent-runtime-env-guardrails unless the human explicitly redirects the landing branch.
subtasks:
- T007
- T008
- T009
- T010
agent: "claude"
shell_pid: "7663"
history:
- 2026-07-05 authored from plan IC-04 (capture)
agent_profile: implementer-ivan
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
Run `/ad-hoc-profile-load implementer-ivan` (role: implementer). Then read this WP.

## Objective
Convert every in-scope invocation in `felix-admin-capture/AGENTS.md` (14 bare `-m scripts.`)
and its `AGENTS.md.tmpl` (1 `-m scripts.` + several `python3 /home/claude/...` abs-path calls)
to the canonical form. Keep `.tmpl` and rendered `AGENTS.md` in lockstep.

**Canonical form** (see `../research.md` R-02, `../data-model.md`):
`cd "${PYTHONPATH:?PYTHONPATH not set — run under openclaw-gateway or export the checkout root}" && python3 -m scripts.inbox.<mod> [absolute args]`
and for abs-path: `cd "${PYTHONPATH:?…}" && python3 scripts/inbox/<file>.py [absolute args]`.
NO hardcoded `/home/claude/kg-automation`. Helper args must be absolute (tempfiles/vault paths
already are — verify).

## Subtasks
- **T007** — In `AGENTS.md`, convert all 14 `python3 -m scripts.inbox.…` invocations (lines
  ~78, 82, 90, 94-96, 113, 115, 127, 131, 135, 152, 221 — verify by scanning) to the cd form.
  Preserve the surrounding prose/imperative structure ("Invoke `…`") — only the command inside
  the backticks changes. Do NOT touch the `<helper>` placeholder doc line (~74).
- **T008** — In `AGENTS.md.tmpl`, convert the abs-path `python3 /home/claude/kg-automation/scripts/inbox/*.py`
  invocations (prescan.py, handle_marker_cleanup.py, append_routing_entry.py, handle_parse_failures.py —
  scan for all) to `cd "${PYTHONPATH:?…}" && python3 scripts/inbox/<file>.py`.
- **T009** — Convert the `.tmpl`'s `-m scripts.` invocation; ensure the `.tmpl` and the rendered
  `AGENTS.md` express the SAME commands (lockstep — the v323 regression lesson). If a render
  step exists, note it; otherwise edit both by hand to match.
- **T010** — Self-verify: `PYTHONPATH="$(git rev-parse --show-toplevel)" python3 -c "from scripts.openclaw.agents.env_assumptions import scan_file; from pathlib import Path; [print(f) for p in ['scripts/openclaw/agents/felix-admin-capture/AGENTS.md','scripts/openclaw/agents/felix-admin-capture/AGENTS.md.tmpl'] for f in scan_file(Path(p))]"` → prints nothing (0 findings). Confirm helper args are absolute.

## Branch Strategy
Base/merge: `feat/agent-runtime-env-guardrails`. Lane worktree allocated from `lanes.json`.

## Definition of Done
- capture `AGENTS.md` + `AGENTS.md.tmpl` scan clean (0 findings via WP01's checker).
- `.tmpl` ↔ `AGENTS.md` command parity. No hardcoded checkout. Args absolute.
- No semantic change to the agent's behavior — only the invocation env-anchoring changes.

## Reviewer guidance
- Diff each converted line: canonical `cd "${PYTHONPATH:?}" && …`, no `/home/claude/kg-automation`.
- Confirm the `<helper>` placeholder doc line is untouched, and `.tmpl`↔rendered parity.
- Run WP01's checker over both files → expect 0 findings.

## Activity Log

- 2026-07-05T22:33:21Z – claude – shell_pid=7663 – Assigned agent via action command
