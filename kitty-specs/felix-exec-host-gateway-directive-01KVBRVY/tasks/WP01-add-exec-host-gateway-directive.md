---
work_package_id: WP01
title: Add exec host=gateway directive to the four Felix sub-agent AGENTS.md files
dependencies: []
requirement_refs:
- FR-001
- FR-002
- FR-003
- FR-004
- FR-005
- NFR-001
- NFR-002
tracker_refs:
- kentonium3/kg-automation#603
planning_base_branch: fix/felix-exec-host-gateway-directive
merge_target_branch: fix/felix-exec-host-gateway-directive
branch_strategy: Planning artifacts for this mission were generated on fix/felix-exec-host-gateway-directive. During /spec-kitty.implement this WP may branch from a dependency-specific base, but completed changes must merge back into fix/felix-exec-host-gateway-directive unless the human explicitly redirects the landing branch.
base_branch: kitty/mission-felix-exec-host-gateway-directive-01KVBRVY
base_commit: 287d67ae786a3b7735607a50f17a972442b54dd0
created_at: '2026-06-17T22:23:58.577570+00:00'
subtasks:
- T001
- T002
- T003
- T004
- T005
agent: claude
shell_pid: '68140'
history: []
agent_profile: implementer-ivan
authoritative_surface: scripts/openclaw/agents/
create_intent: []
execution_mode: code_change
owned_files:
- scripts/openclaw/agents/felix-admin-capture/AGENTS.md
- scripts/openclaw/agents/felix-admin-habits/AGENTS.md
- scripts/openclaw/agents/felix-admin-tasker/AGENTS.md
- scripts/openclaw/agents/felix-admin-escalation/AGENTS.md
role: implementer
tags: []
---

## ⚡ Do This First: Load Agent Profile

Before reading anything else, load your agent profile:
`/ad-hoc-profile-load implementer-ivan` (role: implementer). Adopt its identity,
governance scope, and boundaries for this work package.

## Objective

Add one identical hard-rule section to each of the four Felix sub-agent
`AGENTS.md` standing-orders files instructing the agent to always use
`host=gateway` for the OpenClaw `exec` tool and never `host=node`. This removes
the model's non-deterministic host selection that causes false-positive
cron-failure alerts (issue #603).

Read first: `../spec.md` (FR-001..FR-005, NFR-001), `../plan.md` (IC-01),
`../research.md` (R-03, R-04).

## Context

OpenClaw's `exec` tool exposes two `host` values: `host=gateway` (runs
in-process on office2 — works) and `host=node` (delegates to a paired
companion/node host — **no node host is paired on office2, so it always
errors**). The Felix sub-agents' standing orders don't say which to use, so
haiku-4.5 picks non-deterministically. When it picks `host=node` first, the call
errors (`exec host=node requires a paired node (none available)`), OpenClaw marks
the whole run `status=error`, and a false-positive "cron failed" WhatsApp alert
is delivered — even though the agent retries with `host=gateway` and completes
its work. We eliminate the non-determinism by making `host=gateway` a standing
hard rule in every sub-agent's prompt.

All four files share a consistent top structure:
`## Governance` → `# AGENTS.md — Standing orders: …` → `## Authority` →
`## Message identity` → `## Output discipline`. Insert the new section at the
**same anchor in every file**: immediately after the `## Message identity`
section and immediately before `## Output discipline`. This guarantees identical
placement and makes the four files trivially consistent.

## The exact section to add (byte-identical in all four files)

Insert exactly this block (a blank line before and after it), with no
agent-specific changes:

```markdown
## Tool use — exec host

**Hard rule — every `exec` tool call MUST use `host=gateway`; never use `host=node`.** No node/companion host is paired on office2, so `host=node` always fails with `exec host=node requires a paired node (none available)`. That first-call failure marks the entire run `status=error` and fires a false-positive cron-failure alert even when the run self-recovers by retrying. Pass `host=gateway` (in-process execution on office2) on the first and every `exec` call. Do not select, retry with, or fall back to `host=node` under any circumstance.
```

## Subtasks

### T001 — felix-admin-capture/AGENTS.md
- **File**: `scripts/openclaw/agents/felix-admin-capture/AGENTS.md`
- **Step**: Insert the section above between the `## Message identity` section and `## Output discipline` (after the message-identity body, before the `## Output discipline` heading).
- **Validation**: The `## Tool use — exec host` heading appears exactly once, directly before `## Output discipline`; no existing lines changed.

### T002 — felix-admin-habits/AGENTS.md
- **File**: `scripts/openclaw/agents/felix-admin-habits/AGENTS.md`
- **Step**: Same insertion at the same anchor (after `## Message identity`, before `## Output discipline`).
- **Validation**: Heading present once; existing content untouched.

### T003 — felix-admin-tasker/AGENTS.md
- **File**: `scripts/openclaw/agents/felix-admin-tasker/AGENTS.md`
- **Step**: Same insertion at the same anchor.
- **Validation**: Heading present once; existing content untouched.

### T004 — felix-admin-escalation/AGENTS.md
- **File**: `scripts/openclaw/agents/felix-admin-escalation/AGENTS.md`
- **Step**: Same insertion at the same anchor.
- **Validation**: Heading present once; existing content untouched.

### T005 — Verify identical directive across all four files
- **Steps**:
  ```bash
  grep -l "host=gateway" scripts/openclaw/agents/felix-admin-*/AGENTS.md | wc -l   # expect 4
  # confirm the added section is byte-identical across the four files:
  for a in capture habits tasker escalation; do
    awk '/^## Tool use — exec host$/{f=1} f{print} /^## Output discipline$/{if(f) exit}' \
      scripts/openclaw/agents/felix-admin-$a/AGENTS.md | sha256sum
  done   # expect four identical hashes
  ```
- **Validation**: count is 4; all four section hashes match.

## Branch Strategy

- **Merge target**: `fix/felix-exec-host-gateway-directive` (PR-bound; a PR `fix → main` lands the change afterward).
- Planning artifacts live on the coordination branch; this WP's execution
  worktree is allocated per the computed lane from `lanes.json` during
  `/spec-kitty.implement`. Completed changes merge back into the mission target
  unless the human explicitly redirects the landing branch.

## Definition of Done

- [ ] All four `AGENTS.md` files contain the `## Tool use — exec host` section, byte-identical, at the shared anchor (FR-001, FR-003, NFR-001).
- [ ] The directive states the reason (`host=node` unpaired → errors) (FR-002).
- [ ] No existing content in any of the four files was changed (FR-005).
- [ ] T005 verification passes (count=4; four identical section hashes).
- [ ] No new files created; only the four owned files modified.

## Notes for reviewer

- Confirm the section is identical across all four files (run T005's hashes).
- Confirm placement is consistent (after `## Message identity`, before `## Output discipline`) in each file.
- Confirm no unrelated edits crept into the four files (diff should show only the added block per file).
- FR-004 (deploy via `agent-prompt-sync.service`) and the #557/#618 rebaseline are **automated post-merge**; they are not implemented here — see `../quickstart.md` for the post-merge verification recipe.
