---
work_package_id: WP01
title: 'Author felix-admin-habits workspace to #587 + weekly-report doc-sync'
dependencies: []
requirement_refs:
- FR-001
- FR-002
- FR-003
- FR-004
- FR-005
- FR-006
- FR-007
- FR-008
- FR-009
- FR-010
- FR-011
- FR-012
tracker_refs: []
planning_base_branch: feat/author-habits-workspace
merge_target_branch: feat/author-habits-workspace
branch_strategy: Planning artifacts for this mission were generated on feat/author-habits-workspace. During /spec-kitty.implement this WP may branch from a dependency-specific base, but completed changes must merge back into feat/author-habits-workspace unless the human explicitly redirects the landing branch.
subtasks:
- T001
- T002
- T003
- T004
- T005
- T006
phase: Phase 1 - Author
assignee: ''
agent: "claude"
shell_pid: "27940"
shell_pid_created_at: "1784470341.522141"
history:
- at: '2026-07-19T13:50:00Z'
  actor: system
  action: Prompt generated via /spec-kitty.tasks
agent_profile: curator-carla
authoritative_surface: scripts/openclaw/agents/felix-admin-habits/
create_intent: []
execution_mode: code_change
model: claude-sonnet-5
owned_files:
- scripts/openclaw/agents/felix-admin-habits/SOUL.md
- scripts/openclaw/agents/felix-admin-habits/USER.md
- scripts/openclaw/agents/felix-admin-habits/TOOLS.md
- scripts/openclaw/agents/felix-admin-habits/AGENTS.md
- docs/design/architecture/service-inventory.md
role: implementer
tags: []
task_type: implement
---

# Work Package Prompt: WP01 – Author felix-admin-habits workspace to #587 + weekly-report doc-sync

## ⚡ Do This First: Load Agent Profile

Before reading anything else, load your assigned profile:

```
/ad-hoc-profile-load curator-carla
```

You are **curator-carla** (knowledge-base / doctrine maintenance) acting as implementer for a
**behavior-preserving** workspace authoring refactor. This is content curation on a LIVE daily
agent — precision and conservation matter more than cleverness. Do not fold in behavior changes.

## Objective

Re-home `felix-admin-habits`'s workspace content to its #587-canonical owner file, correct one
stale scope claim, de-inline volatile Vikunja IDs, fix a repo-wide weekly-report doc drift, and
prove the set stays invariant-green and behavior-preserving. The authoritative design is in
`kitty-specs/author-habits-workspace-01KXX9JZ/data-model.md` (the move-table) — follow it exactly.

## Context you must read first

1. `kitty-specs/author-habits-workspace-01KXX9JZ/spec.md` — FRs + NFRs.
2. `kitty-specs/author-habits-workspace-01KXX9JZ/data-model.md` — the row-by-row move-table (source of truth).
3. `kitty-specs/author-habits-workspace-01KXX9JZ/research.md` — Decision 3 (the corrected de-inline mechanism).
4. `kitty-specs/author-habits-workspace-01KXX9JZ/quickstart.md` — the conservation checklist + validation steps.
5. `docs/design/openclaw-workspace-authoring-standard.md` — the #587 concern→file ownership contract.
6. The current files: `scripts/openclaw/agents/felix-admin-habits/{SOUL,USER,TOOLS,AGENTS,IDENTITY}.md`.

## Hard rules

- **Behavior-preserving.** No new instructions, no changed workflows, no "improvements" beyond the
  named corrections. The AGENTS.md tick/reply workflows must stay byte-identical except FR-009.
- **Conservation.** Every block is keep / move / reduce-to-stance / delete per the move-table.
  Nothing substantive may be silently dropped.
- **Scoped edits only.** Touch only the 5 `owned_files`. Do NOT edit IDENTITY.md.
- **Scoped `git add`** — never `git add -A`.

---

### Subtask T001 — SOUL.md → voice + one-line privacy stance (FR-001..FR-004)

**Purpose**: Reduce SOUL to its #587 concern (voice/stance) only.

**Steps**:
1. **Keep** `## Voice — write as Kent` in full: the Principles list, "Words and phrases to avoid",
   "Words and phrases that are Kent". This is the keeper.
2. In the "Structured and chunked" principle bullet, **trim** the "Kent has ADD and processes best…"
   justification clause; keep the style rule itself ("Use headers and short sections. No walls of text.").
   (The neutral "ADD (managed)" fact stays in USER, not SOUL — see #584/#585 precedent.)
3. **Delete** `## Purpose` entirely — the role is owned by AGENTS `## Authority`/`## Scope`.
4. **Delete** `## Weekly report — out of scope` entirely — AGENTS `## Weekly report — out of scope`
   is the single authoritative home. (Do NOT delete it from AGENTS.)
5. **Reduce** `## Privacy boundary` to a single one-line behavioral stance, e.g.
   `I work only where I'm invited — the private growth vault does not exist to me.`
   Remove the enforceable rule text, the filesystem path, and the mission-026/#152 changelog
   parenthetical from SOUL. (The enforceable rule already lives in AGENTS + TOOLS — leave those.)

**Validation**:
- [ ] SOUL contains `## Voice` (intact) + a one-line privacy stance and nothing else substantive.
- [ ] No `04-Growth/_private/` path or enforceable rule text remains in SOUL.
- [ ] No `## Purpose` / role text and no `## Weekly report` block remain in SOUL.

---

### Subtask T002 — USER.md → filtered person-view, correct scope (FR-005, FR-006)

**Purpose**: Keep USER a filtered person-view; remove operational mechanics; fix a false claim.

**Steps**:
1. **Keep** the person profile: Name / What to call / Timezone / Notes (retain "ADD (managed)"
   as a neutral fact).
2. **Correct** `## Context`: remove the claim that the agent will "report on patterns over time."
   The true scope: *deliver daily habit check-ins via WhatsApp and record completions in Vikunja.*
   Keep the concise-WhatsApp guidance. (Weekly pattern reporting is owned by the deterministic
   `felix-habits-weekly` timer, #723 — NOT this agent.)
3. **Move** `## Date handling` out of USER (it lands in TOOLS in T003) — remove it from USER.

**Validation**:
- [ ] USER has no timezone/offset operational mechanics.
- [ ] USER `## Context` no longer claims the agent reports on patterns; scope text is accurate.

---

### Subtask T003 — TOOLS.md → de-inline IDs, receive date-handling (FR-007, FR-008)

**Purpose**: Document the real surface without volatile IDs; receive the date-handling content.

**Steps**:
1. **Keep** `## Vikunja API` (skill pointer + `openclaw skills info vikunja_api`).
2. **De-inline** the volatile IDs: remove the `(id=13)` parenthetical from the "Habits project"
   line and **delete** the "**Habit task IDs**: 14-20 (…)" line. Replace with a pointer that the
   canonical project-id source is `scripts/common/vikunja_refs.json` (the deterministic helpers
   resolve there — see research.md Decision 3), and that the agent's own ad-hoc habit operations
   resolve the project by NAME via the `vikunja_api` skill. Do NOT inline any numeric ids.
3. **Keep** `## Habit completion storage` verbatim in substance (one task per habit; comment
   format `[Felix] YYYY-MM-DD | {complete|rescheduled|will-not-do} | optional note`; idempotent
   search-before-create).
4. **Keep** `## Privacy` byte-unchanged (enforceable path — Invariant A home).
5. **Receive** the date-handling section moved out of USER (T002): America/New_York resolution,
   `TZ=America/New_York date`, ET offset (-04:00 EDT / -05:00 EST), never the `Z` suffix for due
   dates. Preserve its substance.

**Validation**:
- [ ] No `id=13` or `14-20` literal anywhere in TOOLS.
- [ ] TOOLS names `vikunja_refs.json` as the canonical id source; agent ad-hoc path = name-based.
- [ ] Completion-storage contract retained; date-handling present in TOOLS.

---

### Subtask T004 — AGENTS.md → narrow truthfulness fix only if warranted (FR-009)

**Purpose**: Keep AGENTS the operating-rules home; only correct a stale self-reference.

**Steps**:
1. Grep AGENTS.md for any sentence that names `SOUL.md` as a privacy-**enforcement** home
   (e.g. "enforced in SOUL.md, AGENTS.md, and TOOLS.md").
2. **If present**: correct it to reflect that SOUL now carries only a stance (enforcement in
   AGENTS.md + TOOLS.md). **If absent**: make NO change to AGENTS.md.
3. Do not touch any other AGENTS content — the Weekly-out-of-scope block, Output discipline,
   Privacy rule, and tick/reply workflows stay byte-identical.

**Validation**:
- [ ] AGENTS is byte-unchanged except (at most) the one privacy-home truthfulness sentence.

---

### Subtask T005 — service-inventory.md → weekly-report rows match the JSON (FR-012)

**Purpose**: Fix the repo-wide weekly-report doc drift (post-plan Finding 4).

**Steps**:
1. Read the weekly-report rows in `docs/design/architecture/service-inventory.md` (the rows that
   describe a **weekly OpenClaw cron via `felix-admin-habits`**) and compare to the authoritative
   `docs/design/architecture/data/service-inventory.json`, which attributes weekly reporting to
   the `felix-habits-weekly` timer (#723).
2. Correct the `.md` narrative rows to match the JSON authority (weekly reporting is a deterministic
   systemd timer, not an OpenClaw cron on the habits agent). Bounded to the weekly-report lines.
3. Do not alter any other service-inventory content.

**Validation**:
- [ ] `service-inventory.md` weekly-report rows agree with `service-inventory.json` (no residual
  "weekly cron via felix-admin-habits").
- [ ] `validate_architecture_data` passes (the pre-commit hook runs it).

---

### Subtask T006 — Validate, conserve, prove behavior-preserving (NFR-001, NFR-003, NFR-004)

**Purpose**: Prove the set is invariant-green, conserved, and behavior-preserving before review.

**Steps**:
1. **Invariant gate**: `python3 -m scripts.openclaw.agents.validate_workspace --json`; assert the
   `felix-admin-habits` object has `ok: true` (all four checks). Do NOT rely on whole-fleet exit
   code (calendar/#635 fails Invariant B, out of scope).
2. **Conservation**: walk the `quickstart.md` §3 row-by-row checklist against the final files —
   every keep/move/reduce/delete confirmed; enforceable privacy token in AGENTS+TOOLS and absent
   from SOUL; weekly-out-of-scope in AGENTS and absent from SOUL; date-handling in TOOLS absent
   from USER.
3. **Behavior preservation (two guards, NFR-004)**:
   (a) **scope-creep guard** — confirm no helper/config file was touched (the diff is only the 5
   owned files); a prompt-only change cannot alter deterministic helper output.
   (b) **prompt-behavior guard** — static-diff AGENTS.md: the tick/reply workflow commands, the
   relay-verbatim rule, the Output Discipline block, the completion-marking flow, and the
   habit-management rules are byte-identical (except the FR-009 sentence, if any).
4. Confirm **FR-011**: after T001 step 4, exactly one authoritative weekly-out-of-scope statement
   remains (in AGENTS); no in-workspace contradiction.

**Validation**:
- [ ] validator habits `ok: true`.
- [ ] conservation checklist fully ticked.
- [ ] AGENTS workflow byte-unchanged (except FR-009 sentence if present).

---

## Branch Strategy

Planning artifacts were generated on `feat/author-habits-workspace`. This WP's completed changes
merge back into `feat/author-habits-workspace`. Execution worktrees are allocated per computed lane
from `lanes.json`. The feature branch merges to `main` at mission end (single-branch topology, C-008).

## Definition of Done

- All six subtasks' validation boxes checked.
- `validate_workspace.py` reports habits `ok: true`; `validate_architecture_data` passes.
- The diff touches only the 5 `owned_files` (+ nothing else).
- Post-merge deploy/parity/smoke are operator-owned (quickstart §5–9) — NOT part of this WP.

## Reviewer guidance

- Verify conservation against `data-model.md` row by row — the top risk is a silently dropped block.
- Verify SOUL no longer carries the enforceable privacy rule but AGENTS + TOOLS still do (Inv-A).
- Verify no numeric Vikunja id remains in TOOLS and the mechanism pointer is correct (research Decision 3).
- Verify AGENTS is byte-unchanged except at most the FR-009 sentence.
- Verify `service-inventory.md` weekly rows now match the JSON.

## Activity Log

- 2026-07-19T14:12:43Z – claude – shell_pid=27940 – Assigned agent via action command
- 2026-07-19T14:22:10Z – claude – shell_pid=27940 – Ready for review
- 2026-07-19T14:28:34Z – user – shell_pid=27940 – reviewer-renata APPROVE: all 9 checks pass; 1 non-blocking pre-existing note → follow-up
