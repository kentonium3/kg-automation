---
work_package_id: WP07
title: Agent surface token refs + obsolete in-code comment reconciliation (#831)
dependencies:
- WP01
requirement_refs:
- FR-006
tracker_refs: []
planning_base_branch: feat/vikunja-token-seam-kent-cutover
merge_target_branch: feat/vikunja-token-seam-kent-cutover
branch_strategy: Planning artifacts for this mission were generated on feat/vikunja-token-seam-kent-cutover. During /spec-kitty.implement this WP may branch from a dependency-specific base, but completed changes must merge back into feat/vikunja-token-seam-kent-cutover unless the human explicitly redirects the landing branch.
subtasks:
- T017
- T018
phase: Phase 2 - Docs
history: []
agent_profile: python-pedro
authoritative_surface: scripts/openclaw/
create_intent: []
execution_mode: code_change
owned_files:
- scripts/openclaw/skills/vikunja-api/SKILL.md
- scripts/openclaw/skills/escalation/SKILL.md
- scripts/openclaw/agents/felix-admin-tasker/TOOLS.md
- scripts/openclaw/agents/felix-admin-tasker/AGENTS.md
- scripts/intake/scan_inbox.py
- scripts/sync/systemd/felix-vikunja-sync.service
- tests/intake/test_scan_inbox.py
role: implementer
tags: []
agent: "claude"
shell_pid: "73940"
shell_pid_created_at: "1784864327.692636"
---

# Work Package Prompt: WP07 — Agent surface + comment reconciliation

## ⚡ Do This First: Load Agent Profile
Load your assigned agent profile (`agent_profile` frontmatter) via `/ad-hoc-profile-load` before anything else.

## Branch Strategy
- Planning/base + merge target: `feat/vikunja-token-seam-kent-cutover`. `/spec-kitty.implement` sets the worktree base.

## Objective
Update the agent-facing skill/tool docs to the single kent-token model and fix the stale SKILL header +
health-check (resolves #831), and reconcile obsolete **in-code invariant comments** that would contradict
the flipped default.

## Subtasks

### T017 — Agent skill/tool token references (#831)
- `scripts/openclaw/skills/vikunja-api/SKILL.md`: change token guidance from the felix-bot `vikunja-api`
  to the kent `vikunja-api-kent` path (all `cat .../vikunja-api` examples); fix the stale **`v0.24.6`→`v2.4.0`**
  header and the health-check example (this is the concrete #831 fix).
- `scripts/openclaw/skills/escalation/SKILL.md:14` and `scripts/openclaw/agents/felix-admin-tasker/{TOOLS.md:24,
  AGENTS.md}`: update the `vikunja-api` token references to the kent token / single-token model.

### T018 — Obsolete in-code invariant comments
- `scripts/intake/scan_inbox.py` `_build_client` docstring states the scan "must NEVER use the kent write
  token" per the #715 two-token model — **that invariant is exactly what #860 retires.** Rewrite the
  docstring/comment to the single-token reality (the client default is now kent; scan reads Inbox=1, visible
  to kent). This is a **comment/docstring change only** — no behavior change (scan_inbox already uses the
  client default and inherits the flip). Confirm `tests/intake/test_scan_inbox.py` still green (should be
  unaffected; update only if a test asserts the old comment/text).
- `scripts/sync/systemd/felix-vikunja-sync.service:20` comment references `.../vikunja-api` — update to note
  the runtime token is now the kent credential (resolved via the seam).
- Grep siblings for the same stale "reads = felix-bot / never kent" language and fix any found.

## Definition of Done
- SKILL/TOOLS/AGENTS reference the kent token; SKILL is on v2.4.0 with a correct health-check example (#831).
- `scan_inbox._build_client` docstring + sync systemd comment reflect the single-token reality; no code behavior change.
- `python3 -m pytest tests/intake/test_scan_inbox.py -q` green.

## Reviewer guidance
- Verify scan_inbox change is comment-only (no logic diff) and no longer contradicts the kent default.
- Verify the SKILL health-check example actually works against v2.4.0 (this is the observable #831 fix).

## Activity Log

- 2026-07-24T03:39:03Z – claude – shell_pid=73940 – Assigned agent via action command
