---
work_package_id: WP01
title: 'Apply canonical Hard rule #1 across 4 AGENTS.md files'
dependencies: []
requirement_refs:
- C-005
- FR-001
- FR-002
- FR-003
- FR-004
- FR-005
- FR-006
- FR-007
- NFR-001
- NFR-002
- NFR-003
tracker_refs:
- kentonium3/kg-automation#592
planning_base_branch: feat/idle-cron-reply-agent-prefix
merge_target_branch: feat/idle-cron-reply-agent-prefix
branch_strategy: Planning artifacts for this mission were generated on feat/idle-cron-reply-agent-prefix. During /spec-kitty.implement this WP may branch from a dependency-specific base, but completed changes must merge back into feat/idle-cron-reply-agent-prefix unless the human explicitly redirects the landing branch.
subtasks:
- T001
- T002
- T003
- T004
- T005
history: []
agent_profile: implementer-ivan
authoritative_surface: scripts/openclaw/agents/
create_intent: []
execution_mode: code_change
mission_slug: idle-cron-reply-agent-prefix-01KV1BSS
owned_files:
- scripts/openclaw/agents/felix-admin-capture/AGENTS.md
- scripts/openclaw/agents/felix-admin-habits/AGENTS.md
- scripts/openclaw/agents/felix-admin-tasker/AGENTS.md
- scripts/openclaw/agents/felix-admin-escalation/AGENTS.md
role: implementer
tags: []
agent: "claude"
shell_pid: "67181"
---

## ⚡ Do This First: Load Agent Profile

Invoke `/ad-hoc-profile-load implementer-ivan` (or load the profile referenced in this WP's `agent_profile` frontmatter) BEFORE reading anything else in this prompt. The profile sets your identity, governance scope, boundaries, and initialization declaration. Without it, your behavior is unscoped and reviewable defects are likely.

## Objective

Replace the existing "Hard rule #1 — IDLE means the literal four-character string `IDLE`…" block in each of 4 in-scope Felix sub-agent AGENTS.md files with the canonical block from [`contracts/hard-rule-1.md`](../contracts/hard-rule-1.md), substituting the per-file `<agent-slug>` literal. Update any in-text reference to "the four characters IDLE" or "the bare IDLE marker" to reference the new byte format. Preserve everything else (Hard rule #2/#3, incident-anchor narrative, examples not directly tied to the IDLE byte form).

## Context

The full design context lives in [`spec.md`](../spec.md), [`plan.md`](../plan.md), and especially [`research.md`](../research.md) — read all three before editing. Key load-bearing points:

- **The canonical rule block is in `contracts/hard-rule-1.md`.** That is the single authoritative shape; do not paraphrase or restructure it across files. Per-file delta is limited to the `<agent-slug>` substitution.
- **The 4 in-scope files are explicit** (research R-01); do not modify any other AGENTS.md (including `felix-admin-calendar`, `felix-doc-auditor`, or `main`).
- **Anti-narrative invariants are preserved, not relaxed** (spec C-005, contract section "Notes on the prohibited-pattern enumeration"). The 2026-05-20 and 2026-06-09 incident anchors remain load-bearing.
- **Surrounding prose differs per file** (research R-04). Capture has the longest incident-anchor narrative; habits/tasker/escalation are tighter. The canonical block replaces only the **rule line(s)** — not the surrounding incident-anchor paragraphs, not Hard rule #2/#3 blocks, not the file's examples.
- **`<agent-slug>` substitution is exact**: 4 literal occurrences per file, all replaced with the same slug, no typos. Verify by `grep -c '<agent-slug>'` on each post-edit file returning `0` (template literal removed) and `grep -c '\[felix-admin-<area>\]: IDLE'` returning the expected count.

## Branch Strategy

- planning_base_branch: `feat/idle-cron-reply-agent-prefix`
- merge_target_branch: `feat/idle-cron-reply-agent-prefix`
- No prior WPs to wait on. Spec-kitty's `next` flow creates a lane worktree off `feat/idle-cron-reply-agent-prefix` HEAD; the workspace path will be in `lanes.json`.
- After this WP completes and review-approves, WP02 picks up from this WP's HEAD via the dependency chain.

## Subtask guidance

### T001 — Update `scripts/openclaw/agents/felix-admin-capture/AGENTS.md`

**Purpose**: Apply the canonical Hard rule #1 block + in-text reference updates to the capture sub-agent's standing-orders file.

**Pre-edit state to preserve**:

The capture AGENTS.md is the most prose-rich of the 4 files. Per research R-04, lines 29–44 contain:
- Line 29: The current Hard rule #1 (one long line, the canonical target of replacement).
- Lines 35–44: Detailed elaboration with the 2026-06-09 incident anchor, an example, and "the model's first emitted token is `I`, then `D`, then `L`, then `E`, then end-of-turn." narrative.

The narrative at lines 35–44 is load-bearing pedagogy from the original Hard rule #1 hardening; **preserve it verbatim except** for the surgical updates listed below.

**Steps**:

1. Open `scripts/openclaw/agents/felix-admin-capture/AGENTS.md`.
2. Locate the existing Hard rule #1 block (search for `Hard rule #1 — IDLE means`). It starts at approximately line 29.
3. Replace the single Hard rule #1 line with the canonical block from `kitty-specs/idle-cron-reply-agent-prefix-01KV1BSS/contracts/hard-rule-1.md` (section "The canonical block (BEGIN/END)"), substituting every literal `<agent-slug>` with `felix-admin-capture`. The substituted block contains 4 substitutions.
4. Scan the rest of the file for in-text references to the old format:
   - Any phrase like "the four characters `IDLE`" — update to reference the new byte form (`[felix-admin-capture]: IDLE`).
   - Any phrase like "the bare `IDLE` marker" or "the single token `IDLE`" — update similarly.
   - Any example block that shows a literal IDLE reply (look around line 35 and the "IDLE turn" example near the file's end, ~line 61) — update the literal to the new byte form, but preserve the surrounding pedagogy verbatim.
5. Do NOT modify Hard rule #2 or Hard rule #3 blocks.
6. Do NOT modify the `Sent by felix-admin-capture:haiku` identity examples (those are non-IDLE replies, out of scope per FR-007).

**Files**:
- `scripts/openclaw/agents/felix-admin-capture/AGENTS.md` (edit only; ~15,288 bytes pre)

**Validation**:
- [ ] `grep -n 'four characters' scripts/openclaw/agents/felix-admin-capture/AGENTS.md` returns no remaining references to the old format.
- [ ] `grep -c '\[felix-admin-capture\]: IDLE' scripts/openclaw/agents/felix-admin-capture/AGENTS.md` ≥ 4 (canonical block + at least one example).
- [ ] `wc -c scripts/openclaw/agents/felix-admin-capture/AGENTS.md` returns ≤ 15,788 bytes.
- [ ] No diff outside the Hard rule #1 block + the surgical in-text updates.

### T002 — Update `scripts/openclaw/agents/felix-admin-habits/AGENTS.md`

**Purpose**: Apply the canonical Hard rule #1 block + in-text reference updates to the habits sub-agent's standing-orders file.

**Pre-edit state to preserve**:

Per the research probe, habits' Hard rule #1 lives around line 32–35 with shorter surrounding prose than capture. Hard rule #2 immediately follows (around line 38). Line 109 references the IDLE marker in habits-specific context ("the helper writes 'All habits complete for today.'"); line 115 instructs "Reply with the single token `IDLE`" — both need surgical updates.

**Steps**:

1. Open `scripts/openclaw/agents/felix-admin-habits/AGENTS.md`.
2. Locate Hard rule #1 (search `Hard rule #1 — \`IDLE\` means`). It starts at approximately line 32.
3. Replace the Hard rule #1 block with the canonical block from `contracts/hard-rule-1.md`, substituting `<agent-slug>` → `felix-admin-habits`.
4. Update in-text references:
   - Line ~48: `the bare \`IDLE\` marker OR the final reply` → reference the new byte form.
   - Line ~63: the `IDLE turn` example → update the literal.
   - Line ~115: `Reply with the single token \`IDLE\`` → `Reply with the single byte string \`[felix-admin-habits]: IDLE\``.
   - Lines ~261–262: cross-reference labels (e.g., `Morning → IDLE (Step 3; C-004/NFR-006)`) — update the IDLE literal so the references are consistent with the new format.
5. Do NOT modify Hard rule #2 / #3 / weekly-report contract failure render line.

**Files**:
- `scripts/openclaw/agents/felix-admin-habits/AGENTS.md` (edit only; ~15,043 bytes pre)

**Validation**:
- [ ] `grep -n 'single token' scripts/openclaw/agents/felix-admin-habits/AGENTS.md` returns no remaining "single token `IDLE`" references.
- [ ] `grep -c '\[felix-admin-habits\]: IDLE' scripts/openclaw/agents/felix-admin-habits/AGENTS.md` ≥ 4.
- [ ] `wc -c …habits/AGENTS.md` ≤ 15,543 bytes.
- [ ] Hard rule #2 block byte-identical pre vs post.

### T003 — Update `scripts/openclaw/agents/felix-admin-tasker/AGENTS.md`

**Purpose**: Apply the canonical Hard rule #1 block + in-text reference updates to the tasker sub-agent's standing-orders file. Tasker has no cron (per research R-01) but the rule still applies to delegated-IDLE replies.

**Pre-edit state to preserve**:

Tasker's Hard rule #1 lives around lines 36–39 with the tightest surrounding prose of the 4. Line 51 references `the bare \`IDLE\` marker`. Otherwise the file is mostly about task-structuring logic and doesn't repeatedly invoke the IDLE format.

**Steps**:

1. Open `scripts/openclaw/agents/felix-admin-tasker/AGENTS.md`.
2. Locate Hard rule #1 (search `Hard rule #1 — \`IDLE\` means`). Approximately line 36.
3. Replace the Hard rule #1 block with the canonical block, substituting `<agent-slug>` → `felix-admin-tasker`.
4. Update in-text references:
   - Line ~51: `The ONLY assistant text is either the bare \`IDLE\` marker OR the` → reference the new byte form.
   - Line ~56: `Status preambles in front of \`IDLE\` or the identity line` — keep the rule pointer, but update the IDLE literal if it appears in a literal example.
5. Do NOT modify Hard rule #2 / #3 blocks.

**Files**:
- `scripts/openclaw/agents/felix-admin-tasker/AGENTS.md` (edit only; ~14,994 bytes pre)

**Validation**:
- [ ] `grep -c '\[felix-admin-tasker\]: IDLE' scripts/openclaw/agents/felix-admin-tasker/AGENTS.md` ≥ 4.
- [ ] `wc -c …tasker/AGENTS.md` ≤ 15,494 bytes.
- [ ] No remaining `the bare \`IDLE\` marker` phrase.

### T004 — Update `scripts/openclaw/agents/felix-admin-escalation/AGENTS.md`

**Purpose**: Apply the canonical Hard rule #1 block + in-text reference updates to the escalation sub-agent's standing-orders file.

**Pre-edit state to preserve**:

Escalation's Hard rule #1 lives around lines 45–49 with prose between lines 49 and 58. Line 70 references `the \`IDLE\` marker OR the final formatted alert`. Line 86 references `the bare four-character \`IDLE\``.

**Steps**:

1. Open `scripts/openclaw/agents/felix-admin-escalation/AGENTS.md`.
2. Locate Hard rule #1 (approximately line 45).
3. Replace the Hard rule #1 block with the canonical block, substituting `<agent-slug>` → `felix-admin-escalation`.
4. Update in-text references:
   - Line ~49: existing prose about `the four characters \`IDLE\` and nothing else` — replace the literal with the new byte form, preserve the "Silent run." preamble prohibition.
   - Line ~70: `the \`IDLE\` marker OR the final formatted alert starting with the` — reference the new byte form.
   - Line ~86: `the bare four-character \`IDLE\`` — reference the new byte form.
5. Do NOT modify Hard rule #2 / #3 blocks.

**Files**:
- `scripts/openclaw/agents/felix-admin-escalation/AGENTS.md` (edit only; ~12,366 bytes pre)

**Validation**:
- [ ] `grep -c '\[felix-admin-escalation\]: IDLE' scripts/openclaw/agents/felix-admin-escalation/AGENTS.md` ≥ 4.
- [ ] `grep -n 'four-character' scripts/openclaw/agents/felix-admin-escalation/AGENTS.md` returns no stale references.
- [ ] `wc -c …escalation/AGENTS.md` ≤ 12,866 bytes.

### T005 — Implementer self-check: shape parity + size budget

**Purpose**: Before submitting the WP for review, run the NFR-001 (shape parity) and NFR-002 (size budget) checks the contract requires the reviewer to enforce. Catching mismatches here saves a review-reject round.

**Steps**:

1. **Shape-parity check (NFR-001)**:
   - Extract just the new Hard rule #1 block from each of the 4 files (the lines from `**Hard rule #1` through the closing operator-rationale paragraph). Suggested: pipe each file through an awk/sed range filter, or do a manual visual diff.
   - For any two files A and B, the extracted blocks should differ only in the agent-slug literal. Verify by string-replacing the slug in A with B's slug and running `diff` — output should be empty.
   - Repeat for all 6 pairs of the 4 files.

2. **Size-budget check (NFR-002)**:
   - Pre-mission baselines (from research R-03): capture=15,288, habits=15,043, tasker=14,994, escalation=12,366.
   - Run `wc -c` on each updated file. For each, compute the delta vs the pre-mission baseline. The delta must be ≤ +500 bytes for every file.
   - Record the actual deltas in the WP's review summary (helpful for the reviewer's NFR-002 verdict).

3. **Anti-narrative invariant spot-check (C-005)**:
   - In each of the 4 files, confirm Hard rule #2 and Hard rule #3 blocks are byte-identical to their pre-mission state (verifiable by `git diff` showing zero hunks in those line ranges).

4. **Stale-reference spot-check**:
   - `grep -rn 'four characters\|four-character\|single token \`IDLE\`\|bare \`IDLE\` marker' scripts/openclaw/agents/felix-admin-{capture,habits,tasker,escalation}/AGENTS.md` should return no hits.

**Files**: no edits; this is a checking step.

**Validation**:
- [ ] All 6 pairwise shape-parity diffs are empty after slug substitution.
- [ ] All 4 size deltas ≤ +500 bytes.
- [ ] Hard rule #2 + #3 blocks byte-identical pre vs post for all 4 files.
- [ ] No stale "four characters" / "single token" / "bare IDLE marker" wording remaining in any of the 4 files.

## Definition of Done

- [ ] All 4 AGENTS.md files contain the canonical Hard rule #1 block with correct per-file slug substitution.
- [ ] All in-text references to the old "four characters" / "bare IDLE" / "single token" wording in the 4 files have been updated to reference the new byte form.
- [ ] All Hard rule #2 / #3 blocks are byte-identical pre vs post.
- [ ] All 4 size deltas ≤ +500 bytes (NFR-002).
- [ ] T005 self-check ran cleanly with all bullets green.
- [ ] No edits outside the 4 owned files.

## Risks (reviewer should verify)

- **Surrounding-prose deletion**: reviewer inspects each file's full diff and confirms no incidental removal of unrelated paragraphs.
- **Slug-substitution typos**: reviewer greps each file for `<agent-slug>` literal — should be 0 hits — and confirms the substituted slug matches the file's parent directory name.
- **Hard rule #2/#3 silently changed**: reviewer confirms those blocks are unchanged via `git diff` line-range inspection.
- **Token-budget regression beyond +500**: reviewer rejects if any file exceeds the threshold; implementer must compress before resubmit.

## Reviewer guidance

The contract at [`contracts/hard-rule-1.md`](../contracts/hard-rule-1.md) section "Compliance criteria" lists 6 explicit gates the file must meet. Mark the WP approved only if all 6 hold for all 4 files. Cite the specific gate that failed if rejecting.

## Activity Log

- 2026-06-13T23:45:28Z – claude – shell_pid=67181 – Assigned agent via action command
