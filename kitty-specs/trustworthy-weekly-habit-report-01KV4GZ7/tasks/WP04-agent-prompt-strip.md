---
work_package_id: "WP04"
title: "felix-admin-habits AGENTS.md simplification"
subtasks: ["T017", "T018", "T019"]
dependencies: ["WP02"]
planning_base_branch: "main"
merge_target_branch: "main"
branch_strategy: "lane-from-coord"
owned_files:
  - "scripts/openclaw/agents/felix-admin-habits/AGENTS.md"
authoritative_surface: "scripts/openclaw/agents/felix-admin-habits/AGENTS.md"
execution_mode: "code_change"
agent_profile: "implementer-ivan"
role: "implementer"
agent: "claude"
requirement_refs: ["FR-005", "FR-010", "C-005"]
history:
  - at: "2026-06-15T02:33:00Z"
    actor: "spec-kitty agent mission tasks"
    event: "WP created from /spec-kitty.tasks"
---

## ⚡ Do This First: Load Agent Profile

Before reading anything else in this prompt, load your assigned agent profile via `/ad-hoc-profile-load implementer-ivan` (or the equivalent profile loader in your harness).

## Objective

Strip in-prompt rendering rules from the felix-admin-habits AGENTS.md weekly-tick section. After WP02 ships, the helper emits `rendered_text`; the agent's weekly role collapses to: invoke helper, post `rendered_text` verbatim to WhatsApp, preserve the `Sent by felix-admin-habits:<model>` identity line, render contract-failure on non-zero exit. Update the cron-schedule references to match WP05's Monday 06:00 ET new schedule. Verify the AGENTS.md character budget stays comfortable.

## Context

Per Felix Constitution Directive 6 ([engineering-principles.md](../../docs/design/engineering-principles.md)), deterministic work belongs in helpers; the agent's role is sequencing and judgment. The weekly rendering is fully deterministic — same JSON → same text. Once WP02 implements `rendered_text` in the helper, any in-prompt rendering rules are not just redundant but a regression risk (Haiku can drift them).

Read before starting:

- `kitty-specs/trustworthy-weekly-habit-report-01KV4GZ7/spec.md` (FR-005, FR-010)
- `kitty-specs/trustworthy-weekly-habit-report-01KV4GZ7/plan.md` (IC-04)
- `kitty-specs/trustworthy-weekly-habit-report-01KV4GZ7/research.md` (R-05 + R-06 — which lines to edit and which to leave)
- `scripts/openclaw/agents/felix-admin-habits/AGENTS.md` (the file you edit)
- Memory `reference_openclaw_gotchas.md` — AGENTS.md effective char budget context (~14-15K source after openclaw's ~26% inflation)

## Subtasks

### T017 — Strip in-prompt rendering from the weekly-tick section

Locate the "Weekly report (tick workflow)" section in AGENTS.md (currently around line 117 per the planning grep, but verify with `grep -n "Weekly report" scripts/openclaw/agents/felix-admin-habits/AGENTS.md`).

The post-edit weekly section keeps:
- The bullet listing the weekly tick in the agent's overall cron summary.
- "Weekly report (tick workflow)" header.
- Step 1: invoke the weekly helper (the existing command `cd /home/claude/kg-automation && python3 -m scripts.habits.query_active_habits_weekly` — verify the exact module form per memory `feedback_helper_m_invocation_form`).
- Step 2 (NEW): post the helper's `rendered_text` field verbatim to WhatsApp, preserving the `Sent by felix-admin-habits:<model>` identity line (FR-010).
- The contract-failure render path: `Weekly report unavailable: <one-line error class + stripped path>`, no preamble, no in-turn retry. Operator behavior on failure is unchanged.
- The existing output-discipline references (no preamble, no between-tool-calls narration).

The post-edit weekly section DROPS:
- Any percentage-formatting template or rules.
- Any trend-arrow logic (`↑` / `↓` decision).
- Any "parse JSON and emit formatted text" instructions.
- Anything that describes how the WhatsApp message body looks (that lives in the helper now).

**Preserve heading structure** to keep diffs reviewable. Don't renumber unrelated sections.

### T018 — Update cron-schedule references

Per `research.md` R-06, there are at least two cron-schedule references in AGENTS.md:
- A bullet near line 76 listing the weekly cron (likely "Sunday 22:00 ET cron — deterministic helper, agent renders").
- The workflow-section header near line 119 (likely "Weekly cron fires Sunday 22:00 America/New_York (`0 22 * * 0`, ...)").

Update both (and any others surfaced by `grep -nE "(22:00|0 22 |Sunday)" scripts/openclaw/agents/felix-admin-habits/AGENTS.md`) to:
- Schedule string: `0 6 * * 1`
- Wall-clock label: `Monday 06:00 America/New_York`
- The reasoning sentence (if any) should now say "after the reporting window has fully closed" instead of "before end of week."

Verify alignment with WP05's deploy manifest — both surfaces must agree on the schedule string. Coordinate naming if WP05 is being authored concurrently (check `deploys/queued/reschedule-felix-admin-habits-weekly-cron.yaml` if it exists).

### T019 — Verify AGENTS.md effective character budget

Per memory `reference_openclaw_gotchas.md`, AGENTS.md has ~26% rawChars inflation in the openclaw context window, so an effective budget around 20K rawChars translates to roughly 14-15K source chars.

Post-edit, run:

```bash
wc -c < scripts/openclaw/agents/felix-admin-habits/AGENTS.md
```

Record the result in your WP completion summary. The current file is 282 lines / well under budget; the weekly-section strip should reduce it modestly. The expected post-edit char count should be lower than the pre-edit count by a measurable amount (50–500 chars depending on how much rendering text was inline).

If for any reason the file has GROWN (you accidentally added more than you removed), revert and investigate.

## Branch strategy

- Planning base branch: `main`
- Merge target branch: `main`
- This WP lands on its computed lane worktree.
- Depends on WP02 — the agent prompt assumes `rendered_text` exists in the helper output, which is WP02's deliverable.

## Test strategy

This WP is a documentation edit; the formal test surface is grep-based verification:

```bash
# Verify new schedule appears
grep -E "(0 6 \* \* 1|Monday 06:00)" scripts/openclaw/agents/felix-admin-habits/AGENTS.md

# Verify old schedule does NOT appear
grep -E "(0 22 \* \* 0|Sunday 22:00)" scripts/openclaw/agents/felix-admin-habits/AGENTS.md
# Expected: no matches

# Verify rendering template language is gone
grep -iE "(percentage|template|↑|↓|trend.*arrow)" scripts/openclaw/agents/felix-admin-habits/AGENTS.md
# Expected: no matches in the weekly section (other sections may legitimately mention symbols)
```

There's no pytest target for this WP. The audited-surface obligation (#557) requires the rebaseline at mission close (operator action; not part of this WP).

## Definition of Done

- [ ] AGENTS.md weekly-tick section no longer contains percentage-formatting rules, trend-arrow logic, or in-prompt rendering templates.
- [ ] AGENTS.md weekly-tick section explicitly instructs the agent to post the helper's `rendered_text` field verbatim.
- [ ] All cron-schedule references updated to `0 6 * * 1 America/New_York` / Monday 06:00 ET.
- [ ] `grep` checks above confirm the new schedule appears and the old does not.
- [ ] `wc -c` shows the file is under budget (record the value in the PR description).
- [ ] Contract-failure render path preserved.
- [ ] Identity line preservation (FR-010) explicitly stated in the new instruction.
- [ ] No edits outside the weekly-tick section (morning-tick and reply-tick paragraphs untouched per C-003).

## Risks

- **Coordination with WP05**: both WPs reference the cron schedule string. The strings must agree byte-for-byte. If WP05 author writes the manifest before WP04 lands, the AGENTS.md edit can adopt the manifest's exact format; if WP04 lands first, WP05 inherits.
- **Memory budget regression**: AGENTS.md is at 282 lines today, well under budget. Don't add new prose where it isn't needed — the goal is to shrink rendering instructions, not expand them.
- **Morning-tick collateral edits**: C-003 declares the morning-tick rendering refactor out of scope. Resist the temptation to "fix the morning tick while I'm here" — that's a follow-up mission.
- **Identity line confusion**: the `Sent by felix-admin-habits:<model>` identity is the agent's responsibility (not the helper's). Be explicit in the new instruction so a future author doesn't move it into the helper by accident.
- **Helper invocation form**: per memory `feedback_helper_m_invocation_form.md`, helpers importing `scripts.common.*` MUST be invoked as `python3 -m scripts.habits.query_active_habits_weekly` (NOT `python3 scripts/habits/query_active_habits_weekly.py`). The latter form fails `ModuleNotFoundError`. Verify the invocation line uses `-m` form.

## Reviewer guidance

Reviewers verify:

1. The strip is contained to the weekly-tick section. Morning and reply sections are untouched.
2. The new instruction is unambiguous: "post the helper's `rendered_text` field verbatim" — no wiggle room for the agent to re-render.
3. Cron-schedule references are updated everywhere they appear in the file.
4. The helper invocation uses the `-m` form.
5. Identity line is still the agent's responsibility (FR-010).
6. File size shrunk (or at least did not grow).

If reviewer finds the agent prompt now contains contradictory instructions (e.g., one section says "render percentages" and another says "post rendered_text verbatim"), request a revision.

## Implementation command

```bash
spec-kitty agent action implement WP04 --agent claude
```
