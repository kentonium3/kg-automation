---
work_package_id: WP03
title: Convert felix-admin-habits + felix-admin-escalation invocations
dependencies:
- WP01
requirement_refs:
- FR-005
- FR-006
tracker_refs: []
planning_base_branch: feat/agent-runtime-env-guardrails
merge_target_branch: feat/agent-runtime-env-guardrails
branch_strategy: Planning artifacts for this mission were generated on feat/agent-runtime-env-guardrails. During /spec-kitty.implement this WP may branch from a dependency-specific base, but completed changes must merge back into feat/agent-runtime-env-guardrails unless the human explicitly redirects the landing branch.
subtasks:
- T011
- T012
- T013
- T014
agent: "claude"
shell_pid: "7663"
history:
- 2026-07-05 authored from plan IC-04 (habits + escalation)
agent_profile: implementer-ivan
authoritative_surface: scripts/openclaw/agents/felix-admin-habits/
create_intent: []
execution_mode: code_change
model: claude-sonnet-4-6
owned_files:
- scripts/openclaw/agents/felix-admin-habits/AGENTS.md
- scripts/openclaw/agents/felix-admin-escalation/AGENTS.md
role: implementer
tags: []
---

## ⚡ Do This First: Load Agent Profile
Run `/ad-hoc-profile-load implementer-ivan` (role: implementer). Then read this WP.

## Objective
Convert habits (hardcoded-`cd` + abs-path) and escalation (bare `-m scripts.` + 1 abs-path)
to the canonical form. Read `../research.md` R-02 for the form; note habits is the agent that
ALREADY hardcodes `cd /home/claude/kg-automation` — that hardcode is itself a violation (the
checkout-path assumption #658 kills), so it must change to `cd "${PYTHONPATH:?…}"`.

## Subtasks
- **T011 — habits `cd` de-hardcode.** Replace all 5 `cd /home/claude/kg-automation && python3 -m scripts.habits.…`
  (lines ~93, 133, 180, 196, 215) with `cd "${PYTHONPATH:?PYTHONPATH not set — run under openclaw-gateway or export the checkout root}" && python3 -m scripts.habits.…`.
- **T012 — habits abs-path.** Convert the 3 `python3 /home/claude/kg-automation/scripts/openclaw/agents/main/felix-file-issue.py`
  invocations (lines ~114, 167, 228) to `cd "${PYTHONPATH:?…}" && python3 scripts/openclaw/agents/main/felix-file-issue.py`.
- **T013 — escalation.** Convert the 7 bare `python3 -m scripts.escalation.…` (indented inside
  numbered lists, lines ~114, 136, 153, 189, 198, 208, 221) + any abs-path `python /home/claude/...`
  (scan; Codex noted `:265`) to the canonical cd form. Preserve list indentation/structure.
- **T014 — self-verify.** Run WP01's checker over both files → 0 findings. Confirm helper args
  absolute (habits `--input-file`/`--date` args — ensure they resolve absolutely or are passed
  as absolute paths / stdin, not cwd-relative; Codex HIGH-3).

## Branch Strategy
Base/merge: `feat/agent-runtime-env-guardrails`. Lane worktree from `lanes.json`.

## Definition of Done
- habits + escalation `AGENTS.md` scan clean (0 findings). No hardcoded checkout anywhere.
- habits' relative-arg helpers verified cwd-safe under the cd form (args absolute).
- No behavioral change beyond env-anchoring.

## Reviewer guidance
- Confirm EVERY habits `cd /home/claude/kg-automation` is gone (grep the file).
- Confirm escalation's indented invocations keep their list structure and are all converted.
- Run WP01 checker → 0 findings; spot-check one habits helper for absolute-arg safety.

## Activity Log

- 2026-07-05T22:33:37Z – claude – shell_pid=7663 – Assigned agent via action command
