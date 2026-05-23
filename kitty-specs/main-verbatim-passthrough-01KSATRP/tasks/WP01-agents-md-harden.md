---
work_package_id: WP01
title: Harden main agent AGENTS.md with verbatim rule + trim
dependencies: []
requirement_refs:
- C-002
- FR-001
- FR-002
- FR-003
- FR-004
- FR-010
- NFR-003
planning_base_branch: main
merge_target_branch: main
branch_strategy: Planning artifacts for this feature were generated on main. During /spec-kitty.implement this WP may branch from a dependency-specific base, but completed changes must merge back into main unless the human explicitly redirects the landing branch.
base_branch: kitty/mission-main-verbatim-passthrough-01KSATRP
base_commit: 4cdfb5154ae552cb3a3a529ffd068f00e49d5e1f
created_at: '2026-05-23T16:36:05.221578+00:00'
subtasks:
- T001
- T002
- T003
- T004
history: []
authoritative_surface: scripts/openclaw/agents/main/
execution_mode: code_change
mission_id: 01KSATRP0S0TDA5HV995Y558JK
mission_slug: main-verbatim-passthrough-01KSATRP
owned_files:
- scripts/openclaw/agents/main/AGENTS.md
tags: []
agent: "codex:gpt-5:spec-kitty-review:reviewer"
shell_pid: "80457"
---

# WP01 — Harden main agent's AGENTS.md

## Objective

Add a new top-level §"Verbatim pass-through (ABSOLUTE)" to the `main` agent's standing orders (the file that the openclaw gateway loads as system prompt). Cross-reference it from each delegation section. Trim other sections to bring the file under the 14K source-char budget per memory `reference_openclaw_gotchas.md`.

## Context

- **Spec**: FR-001..FR-004 (HARD verbatim rule + worked examples + applies to all delegations), FR-010 (≤14K budget), NFR-003 (size target)
- **Plan**: D2 (trim strategy), D3 (rule placement + locked content)
- **Source file (repo)**: `scripts/openclaw/agents/main/AGENTS.md`
- **Deployed file (office2)**: `/data/services/openclaw/data/AGENTS.md` (operator copies during cutover; out of scope for this WP)
- **Pattern source**: existing "Privacy — absolute rule" pattern in `scripts/openclaw/agents/felix-admin-tasker/AGENTS.md` and `scripts/openclaw/agents/felix-admin-capture/AGENTS.md`

## Subtasks

### T001 — Reconcile deployed vs repo

Steps:
1. Read deployed AGENTS.md from office2: `ssh office2-claude 'cat /data/services/openclaw/data/AGENTS.md'`
2. Read repo copy: `scripts/openclaw/agents/main/AGENTS.md`
3. If they diverge: this WP's edits are made on the REPO copy. Note any drift in commit message so the operator knows to overwrite the deployed copy as part of cutover.

Validation:
- [ ] Drift documented (or absence confirmed) before edits

### T002 — Add §"Verbatim pass-through (ABSOLUTE)"

Steps:
1. Locate a good insertion point near the top of the repo AGENTS.md — after the agent identity/role section but before any delegation section. (Typical structure: identity → privacy → tools → delegations.)
2. Insert the LOCKED section text from research.md D3 verbatim:
   ```
   ## Verbatim pass-through (ABSOLUTE)

   When delegating Kent's reply to a sub-agent (`openclaw agent --agent ... --message ...`), forward the message TEXT VERBATIM. Do not paraphrase, rephrase, summarize, restructure, third-person rewrite, add context, or pre-interpret.

   ### Examples

   ❌ FORBIDDEN — paraphrasing
   Kent: "did 1 and 2, skipping 3"
   Wrong delegation: `--message "Kent reports completing tasks 1 and 2 and skipping task 3"`

   ✅ REQUIRED — verbatim
   Kent: "did 1 and 2, skipping 3"
   Correct delegation: `--message "did 1 and 2, skipping 3"`

   This rule exists because sub-agents have deterministic parsers (`parse_morning_reply`, escalation parser, etc.) that require Kent's exact phrasing. Paraphrased input is silently mis-parsed and the JSONL state-log substrate goes empty.
   ```

Validation:
- [ ] `grep "Verbatim pass-through (ABSOLUTE)" scripts/openclaw/agents/main/AGENTS.md` returns the new section
- [ ] `grep "FORBIDDEN" scripts/openclaw/agents/main/AGENTS.md` returns the example
- [ ] `grep "REQUIRED" scripts/openclaw/agents/main/AGENTS.md` returns the example

### T003 — Apply D2 trim cuts to stay ≤14K

Steps:
1. Identify low-information prose in §"Tools", §"Error handling", §"What this system is" (or equivalent headings in the current file). The plan D2 budgeted ~-1200 net chars.
2. Apply targeted cuts. Preserve all rules, all delegation logic, all guardrails. Cuts are to redundant explanatory paragraphs, verbose examples, multi-sentence intros that can compress.
3. After cuts + the new section from T002, check final size: `wc -c scripts/openclaw/agents/main/AGENTS.md` should be ≤14000.

Validation:
- [ ] `wc -c` ≤14000 source chars
- [ ] All existing delegation sections still present (grep for "Habit tracking delegation", "Escalation", and confirm sub-agent invocation patterns remain)
- [ ] No accidental removal of guardrails (privacy rule, output discipline, etc.)

### T004 — Cross-references from delegation sections

Steps:
1. In each delegation section (habits, escalation, and any future tasker section if present), add a one-line cross-reference to the new section:
   ```
   When delegating, follow the **Verbatim pass-through (ABSOLUTE)** rule at the top of this file.
   ```
2. Place it immediately before the `openclaw agent --message "<...>"` invocation block so the LLM sees the reminder right when it's about to construct the delegation command.

Validation:
- [ ] Each delegation section contains the cross-reference
- [ ] Cross-references DON'T duplicate the rule content (just a pointer)

## Definition of Done

- [ ] All 4 subtasks complete
- [ ] `wc -c scripts/openclaw/agents/main/AGENTS.md` ≤14000
- [ ] The 3 grep validations pass (T002 + T004)
- [ ] No regression: every delegation section in the previous file is still present + still has its `openclaw agent --message` invocation block
- [ ] Commit message documents any drift between deployed and repo (for operator's cutover step)

## Implementation Command

```bash
spec-kitty agent action implement WP01 --mission main-verbatim-passthrough-01KSATRP --agent claude:opus:python-implementer:implementer
```

## Activity Log

- 2026-05-23T17:24:29Z – unknown – Ready for review: verbatim section added, trim brings file to 13528 chars (under 14K), validation greps all pass
- 2026-05-23T17:25:59Z – codex:gpt-5:spec-kitty-review:reviewer – shell_pid=80457 – Started review via action command
- 2026-05-23T17:29:55Z – codex:gpt-5:spec-kitty-review:reviewer – shell_pid=80457 – Moved to planned
