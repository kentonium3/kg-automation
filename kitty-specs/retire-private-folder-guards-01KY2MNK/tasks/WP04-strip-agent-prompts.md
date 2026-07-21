---
work_package_id: WP04
title: Strip the _private red-line from agent prompts
dependencies:
- WP02
requirement_refs:
- FR-003
tracker_refs: []
planning_base_branch: feat/retire-private-folder-guards
merge_target_branch: feat/retire-private-folder-guards
branch_strategy: Planning artifacts for this mission were generated on feat/retire-private-folder-guards. During /spec-kitty.implement this WP may branch from a dependency-specific base, but completed changes must merge back into feat/retire-private-folder-guards unless the human explicitly redirects the landing branch.
subtasks:
- T015
- T016
agent: "claude:sonnet:reviewer-renata:reviewer"
history: []
agent_profile: implementer-ivan
authoritative_surface: scripts/openclaw/agents/main/
create_intent: []
execution_mode: code_change
owned_files:
- scripts/openclaw/agents/main/**
- scripts/openclaw/agents/felix-admin-capture/**
- scripts/openclaw/agents/felix-admin-escalation/**
- scripts/openclaw/agents/felix-admin-habits/**
- scripts/openclaw/agents/felix-admin-tasker/**
- scripts/openclaw/agents/felix-admin-calendar/**
- scripts/openclaw/agents/felix-doc-auditor/**
role: implementer
tags: []
shell_pid: "42682"
shell_pid_created_at: "1784652540.659992"
---

## ⚡ Do This First: Load Agent Profile

Load your profile via `/ad-hoc-profile-load implementer-ivan` before anything else.

## Objective

Remove the enforceable `04-Growth/_private` privacy red-line from the agent prompts. Repo-side edit
only — deployment to office2 + smoke is **post-merge acceptance**, not part of this WP. Authoritative
detail: `data-model.md` IC-03 rows; FR-003. **Depends on WP02** (the workspace validator must accept a
prompt without the red-line first, or `test_validate_workspace` fails).

## Subtasks

- **T015** — For the 6 deployed agents — `main`, `felix-admin-capture`, `felix-admin-escalation`,
  `felix-admin-habits`, `felix-admin-tasker`, `felix-admin-calendar` — grep each workspace for the
  `04-Growth/_private` enforceable line and remove it from whichever owner file carries it
  (AGENTS.md / SOUL.md / TOOLS.md / USER.md — varies per agent; calendar carries its block in SOUL.md
  per #805). Remove ONLY the privacy red-line; leave the rest of each prompt intact. Removing text
  only frees byte budget (safe against the `main/AGENTS.md` 12K/headroom guard).
- **T016** — `felix-doc-auditor`: strip the same red-line from its prompt files for repo consistency.
  **Note:** felix-doc-auditor is suspended (#539) and NOT in the agent-prompt-sync roster — this is a
  **repo-only** edit; expect no deployed parity or smoke for it (post-plan Codex LOW-1).

## Definition of Done

- `grep -rn "04-Growth/_private\|_private" scripts/openclaw/agents/*/` returns zero enforceable-red-line hits.
- `pytest scripts/openclaw/agents/tests/test_validate_workspace.py -q` passes (requires WP02 merged/in-lane).
- Each edited prompt is otherwise unchanged (diff shows only the red-line removal).

## Risks & reviewer guidance

- Only the file(s) that actually carry the line are edited — confirm per agent by grep, don't assume
  the owner file.
- Reviewer: confirm no non-privacy content was removed; confirm felix-doc-auditor is treated repo-only.
- Post-merge (NOT this WP): agent-prompt-sync deploy + 6-agent smoke + `drift_check.py report`.

## Activity Log

- 2026-07-21T16:42:29Z – claude:sonnet:implementer:implementer – shell_pid=40022 – Assigned agent via action command
- 2026-07-21T16:49:15Z – claude:sonnet:implementer:implementer – shell_pid=40022 – WP04 in lane (add89fb9); red-line stripped from all 7 agents, grep-zero, 15 tests pass. From primary per #710.
- 2026-07-21T16:49:27Z – claude:sonnet:reviewer-renata:reviewer – shell_pid=42682 – Started review via action command
