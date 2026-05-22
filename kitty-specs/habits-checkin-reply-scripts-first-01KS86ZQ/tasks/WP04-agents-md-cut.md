---
work_package_id: WP04
title: AGENTS.md cut + audit
dependencies:
- WP01
- WP02
- WP03
requirement_refs:
- C-005
- FR-011
- NFR-004
planning_base_branch: main
merge_target_branch: main
branch_strategy: Planning artifacts for this feature were generated on main. During /spec-kitty.implement this WP may branch from a dependency-specific base, but completed changes must merge back into main unless the human explicitly redirects the landing branch.
created_at: '2026-05-22T16:30:00+00:00'
subtasks:
- T013
- T014
- T015
agent: "codex:gpt-5:spec-kitty-review:reviewer"
shell_pid: "79128"
history:
- at: '2026-05-22T16:30:00+00:00'
  actor: spec-kitty.tasks
  event: created
authoritative_surface: scripts/openclaw/agents/felix-admin-habits/
execution_mode: code_change
mission_id: 01KS86ZQE8GSZ77ZSGSSQMN08K
mission_slug: habits-checkin-reply-scripts-first-01KS86ZQ
owned_files:
- scripts/openclaw/agents/felix-admin-habits/AGENTS.md
tags: []
---

# WP04 — AGENTS.md cut + audit

## Objective

Rewrite the felix-admin-habits AGENTS.md to invoke the three new helpers via CLI and remove the prose that caused the #371 bug. Target: ≤14,000 source chars (vs. current 24,383) — staying within the openclaw effective budget per memory `reference_openclaw_gotchas.md` so the standing orders are no longer silently truncated.

## Context

- **Spec**: FR-007 (helpers are sole source of ordering), FR-011 (≤14K source chars), NFR-004 (no truncation warning post-deploy), C-005 (agent stays thin)
- **Plan**: Phase 0 D10 (cut targets), D11 (cutover sequence)
- **Data model**: Entity 5 (AGENTS.md target skeleton — use as the floor)
- **Current file**: `scripts/openclaw/agents/felix-admin-habits/AGENTS.md` — 24,383 chars / 647 lines (per #371 evidence)
- **Dependencies**: WP01, WP02, WP03 — CLI invocations MUST reference the actual `--help` output of the deployed helpers.
- **Branching**: planning_base=`main`, merge_target=`main`. Execution worktree per `lanes.json`.

## Subtasks

### T013 — Build new AGENTS.md

**Purpose**: Rewrite the file following data-model Entity 5's skeleton.

**Steps**:

1. Read the current `scripts/openclaw/agents/felix-admin-habits/AGENTS.md` end-to-end to identify which sections to preserve vs. cut.
2. Read data-model.md Entity 5 (skeleton) verbatim.
3. Read research.md D10 (cut targets) verbatim.
4. Construct the new file following Entity 5's structure:
   - Governance section (3-5 lines)
   - AGENTS.md header
   - Authority (2-3 lines)
   - Message identity (3-5 lines)
   - **Output discipline** — Hard rule #1 + Hard rule #2 + "Never include" list (preserve from current — these are general-purpose discipline)
   - Scope (3-5 lines)
   - **Morning check-in tick workflow** — exactly the steps from Entity 5:
     - Step 1: Invoke morning-list helper
     - Step 2: Relay helper's stdout verbatim
     - Step 3: On helper failure, file P2-bug + reply IDLE
   - **Completion marking (reply workflow)** — exactly:
     - Step 1: Invoke parser
     - Step 2: Route deterministic tuples via record_completion
     - Step 3: Handle judgment_required via disambiguator + ask Kent ONE clarifying question per cluster
     - Step 4: On parser hard-fail, file P2-bug + ask Kent to re-state
   - Tailscale connectivity (3-5 lines)
   - Reference section pointing at the mission spec
5. The new file MUST be ≤14,000 source chars (≤13,000 ideal for headroom).
6. The new file MUST include the EXACT CLI invocations from contracts/cli.md. Run `python3 -m scripts.habits.morning_checkin_list --help`, `parse_morning_reply --help`, and `disambiguate_reply --help` in the worktree FIRST to capture the verbatim flag names; embed them in the AGENTS.md.

**Files**: `scripts/openclaw/agents/felix-admin-habits/AGENTS.md` (modified — full rewrite, target ~10-13K chars).

**Validation**:
- [ ] `wc -c scripts/openclaw/agents/felix-admin-habits/AGENTS.md` ≤14,000.
- [ ] Every helper CLI example matches actual `--help` output (manually verify by running each helper).

---

### T014 — Audit grep + char-count verification

**Purpose**: Catch any residual fuzzy-match-by-title prose, in-prompt parsing instructions, or ordering generators.

**Steps**:

1. Audit grep:
   ```bash
   grep -nE "(parse|scan).*comment|match against.*list|fuzzy.*match|numbered list.*session|If Kent references numbers" scripts/openclaw/agents/felix-admin-habits/AGENTS.md
   ```
   Expected: no matches (or only explanatory cross-references to the migration note).
2. Verify NO "session-scoped" memory assumptions remain (e.g., "the previous check-in" / "earlier in this session" prose).
3. Verify NO enumeration of habit titles in the AGENTS.md (helpers fetch from Vikunja, not from AGENTS.md prose).
4. Verify NO inline-Python or pseudo-code for sorting / matching.
5. Verify the file has the C-001 / C-002 / C-003 protection language documented at least by reference: "the helpers consume `record_completion.py` as-is; do not duplicate its behavior."
6. Char count: `wc -c <file>`. Document in a commit message comment if very close to 14K (within 500 chars).

**Files**: same file (T013).

**Validation**:
- [ ] Audit grep returns no actionable matches.
- [ ] Char count ≤14,000.
- [ ] No leftover prose that re-implements parsing.

---

### T015 — Repo file update + lane move

**Purpose**: Land the new file in git.

**Steps**:

1. The previous subtasks operate on `scripts/openclaw/agents/felix-admin-habits/AGENTS.md` in the worktree — confirm.
2. `git diff` to confirm scope: only the AGENTS.md changed.
3. Commit:
   ```
   git add scripts/openclaw/agents/felix-admin-habits/AGENTS.md
   git commit -m "feat(WP04): cut AGENTS.md to ≤14K source chars; route through helpers

   - Remove level-determination algorithm prose (helper computes)
   - Remove fuzzy-match-by-title enumeration (helper does it)
   - Remove session-scoped numbered list instruction (the #371 bug line)
   - Add helper-invocation skeleton: morning_checkin_list, parse_morning_reply, disambiguate_reply
   - Preserve governance, output discipline, scope, fallback behavior

   Refs: #371 (P1-bug fix)"
   ```
4. Mark subtasks done + move to for_review per spec-kitty workflow.

**Files**: same file (T013).

**Validation**:
- [ ] Commit lands cleanly.
- [ ] No regression in other escalation or habits files.

---

## Branch Strategy

Planning_base=`main`, merge_target=`main`. Execution worktree per `lanes.json`.

## Test Strategy

This is a documentation/prompt WP. Verification is via:
- char count (`wc -c`)
- audit grep
- manual read for tick-workflow coherence
- cross-checking CLI examples against actual helper `--help` output

No automated test suite; the cutover (post-merge, in quickstart.md) is the integration test.

## Definition of Done

- [ ] All 3 subtasks complete.
- [ ] `wc -c scripts/openclaw/agents/felix-admin-habits/AGENTS.md` ≤14,000.
- [ ] Audit grep returns no actionable matches.
- [ ] Every CLI example in the file matches the helper's actual `--help` output.
- [ ] Commit lands cleanly.

## Risks

- **Over-cut**: removing the wrong section breaks the tick workflow. Mitigation: use data-model Entity 5's skeleton as the FLOOR — don't go below it.
- **CLI flag drift**: if the AGENTS.md examples don't match WP01/WP02/WP03's actual flags, the agent will invoke the helpers wrong. Mitigation: run `--help` on each helper in the worktree before finalizing this WP.
- **Under-cut**: if the file is still over 14K, truncation warnings persist. Mitigation: target ≤13K with deliberate headroom; verify with `wc -c` before commit.

## Reviewer Guidance

1. Read the new AGENTS.md end-to-end. Does it tell the agent everything it needs without re-implementing helper logic in prose?
2. Run each helper's `--help` and cross-check the AGENTS.md CLI examples.
3. Run the audit grep yourself.
4. Diff against pre-WP04 — confirm cuts align with research D10.
5. Confirm char count ≤14,000.

## Implementation Command

```bash
spec-kitty agent action implement WP04 --mission habits-checkin-reply-scripts-first-01KS86ZQ --agent claude:opus:python-implementer:implementer
```

## Activity Log

- 2026-05-22T17:29:24Z – claude:opus:python-implementer:implementer – shell_pid=77918 – Started implementation via action command
- 2026-05-22T17:34:22Z – claude:opus:python-implementer:implementer – shell_pid=77918 – Cycle 0 ready — final char count 13,557 (under 14K cap); audit grep clean of actionable matches; CLI examples cross-checked against actual --help output of morning_checkin_list, parse_morning_reply, disambiguate_reply, record_completion. v1->v2 transition note included.
- 2026-05-22T17:35:13Z – codex:gpt-5:spec-kitty-review:reviewer – shell_pid=79128 – Started review via action command
