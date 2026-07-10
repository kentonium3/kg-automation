---
work_package_id: WP01
title: Fleet truthful-reporting doctrine + main infra guardrail
dependencies: []
requirement_refs:
- FR-001
- FR-002
- FR-003
- NFR-003
tracker_refs: []
planning_base_branch: fix/felix-truthful-reporting
merge_target_branch: fix/felix-truthful-reporting
branch_strategy: Planning artifacts for this mission were generated on fix/felix-truthful-reporting. During /spec-kitty.implement this WP may branch from a dependency-specific base, but completed changes must merge back into fix/felix-truthful-reporting unless the human explicitly redirects the landing branch.
subtasks:
- T001
- T002
- T003
- T004
- T005
phase: Phase 1 - Prevention doctrine
assignee: ''
agent: claude
history:
- at: '2026-07-10T18:45:00Z'
  actor: system
  action: Prompt generated via /spec-kitty.tasks
authoritative_surface: scripts/openclaw/agents/
create_intent:
- scripts/openclaw/agents/tests/test_truthful_doctrine.py
execution_mode: code_change
owned_files:
- scripts/openclaw/agents/main/AGENTS.md
- scripts/openclaw/agents/felix-admin-capture/AGENTS.md
- scripts/openclaw/agents/felix-admin-capture/AGENTS.md.tmpl
- scripts/openclaw/agents/felix-admin-habits/AGENTS.md
- scripts/openclaw/agents/felix-admin-tasker/AGENTS.md
- scripts/openclaw/agents/felix-admin-tasker/AGENTS.md.tmpl
- scripts/openclaw/agents/felix-admin-escalation/AGENTS.md
- scripts/openclaw/agents/felix-admin-calendar/AGENTS.md
- scripts/openclaw/agents/felix-doc-auditor/AGENTS.md
- scripts/openclaw/agents/tests/test_truthful_doctrine.py
role: implementer
tags: []
---

## ⚡ Do This First: Load Agent Profile

Before reading anything else, load your assigned agent profile so you adopt the
right identity, governance scope, and boundaries for this work package. Run the
`/ad-hoc-profile-load` skill (or `spec-kitty ad-hoc-profile-load`) for the
`implementer` role. Do **not** begin editing files until the profile is loaded
and its initialization declaration is applied. Only then proceed to the Branch
Strategy and Context sections below.

## Branch Strategy

- **planning_base_branch**: `fix/felix-truthful-reporting`
- **merge_target_branch**: `fix/felix-truthful-reporting`
- All changes in this WP must merge back into `fix/felix-truthful-reporting`.

Do **not** create or switch branches yourself, and do **not** run `git worktree`
by hand. The execution workspace/lane for this WP is resolved and materialized by
`/spec-kitty.implement`; commits are routed by the workflow. Your job is to make
the file edits described below inside whatever checkout the workflow hands you.

## Objectives & Success Criteria

This WP is the **prevention layer** of the mission: doctrine/prompt only. It adds
the truthful-reporting + mechanism-fidelity doctrine fleet-wide and the
no-unrequested-infrastructure guardrail to `main`. **No code enforcement, no
`openclaw.json` changes, no capability restriction** — those are explicitly out
of scope (C-001, C-003).

Requirement mapping:

- **FR-001** (truthful reporting): agents report an action as done only when they
  actually performed it and can cite a verifiable result; otherwise report what
  they did / could not do. No assumed or forecast completions stated as fact.
  Fleet-wide.
- **FR-002** (mechanism fidelity): when a request names a specific mechanism
  (e.g. "create a Vikunja task"), the agent fulfils **that** mechanism or
  explicitly reports it could not — never a silent substitution. Fleet-wide.
- **FR-003** (no unrequested infrastructure): `main` must not create/modify
  scheduled or standing infrastructure (e.g. OpenClaw crons) unless the request
  explicitly asked for it. `main`-focused.
- **SC-004** (acceptance): truthful-reporting + mechanism-fidelity doctrine is
  present in **all 7** fleet agent prompts; the no-unrequested-infrastructure
  guardrail is present in `main`'s prompt.

**Success = all three doctrine additions present in the correct scope, the
fleet-guard test green, and no AGENTS.md pushed over its prompt budget.**

## Context & Constraints

- **Spec**: [../spec.md](../spec.md) — see FR-001/FR-002/FR-003, SC-004, and the
  "Scope decisions" (enforcement is doctrine + prompt only; agent scope is split).
- **Plan**: [../plan.md](../plan.md) — this WP implements **IC-01**
  (fleet truthful-reporting & mechanism-fidelity doctrine) and **IC-02**
  (no-unrequested-infrastructure guardrail on `main`). IC-03/IC-04/IC-05
  (the detection subsystem) are other WPs — do **not** touch detector code here.
- **Base pattern**: The existing **Felix Output-discipline pattern** already
  mirrored across several agent prompts is the base this doctrine **extends**, not
  a new invention. Match the imperative register of the existing "Red Lines" and
  "Verbatim pass-through (ABSOLUTE)" blocks in `main/AGENTS.md` (short, absolute,
  no hedging). See also the "Output discipline" / "Hard rule" blocks in
  `felix-admin-capture/AGENTS.md` for the fleet tone.

Constraints:

- **C-001 / C-003 — doctrine only.** No hard capability restriction, no
  approval-gating, **no `openclaw.json` edits**, no removal of the cron-creation
  capability. Prompt text only.
- **NFR-003 — prompt budget.** Each edited `AGENTS.md` must stay within its
  effective prompt budget (~12k rawChars; the hard cap enforced in
  `test_agents_md_size.py` is **12,000 bytes** for `main` and
  `felix-admin-calendar`). **Critical current headroom** (measured 2026-07-10):
  - `main/AGENTS.md` = **11,967 bytes** — only **33 bytes** under the 12,000 cap.
  - `felix-admin-calendar/AGENTS.md` = **11,984 bytes** — **16 bytes** of headroom.
  Both `main` and `felix-admin-calendar` are effectively **at the cap**. You
  cannot naively append multi-line blocks to these two. Keep the doctrine block
  **as terse as possible**, and for `main` and `felix-admin-calendar` you will
  need to **reclaim space** by tightening nearby prose (without changing meaning)
  so the file lands **under 12,000 bytes after** the additions. Terseness is a
  hard requirement, not a preference.
- **C-004 — audited but UNMONITORED surface → NO rebaseline.** These `AGENTS.md`
  files are a listed audited surface, but per gap **#621** `audit.sh` does **not**
  hash deployed `AGENTS.md`, so no baseline is written when they change.
  **Do not perform or request a security-baseline rebaseline for this WP.** The
  mission merge commit will record `Rebaseline: not required — <reason>`.
- **Consistency requirement**: the truthful-reporting + mechanism-fidelity block
  text must be **identical** across all 7 agents so the fleet-guard test can
  assert a single canonical string. (See T001.)

## Subtasks & Detailed Guidance

### T001 — Draft the canonical truthful-reporting + mechanism-fidelity block

**Purpose**: Author one short, canonical doctrine block that will be inserted
verbatim into every fleet agent prompt. Deciding **one shared block text reused
across all agents** (recommended) over per-file bespoke wording makes the
fleet-guard test trivial and prevents drift — adopt the shared-block approach.

**Content** — exactly two rules, in the imperative register of the existing
"Red Lines" / "Verbatim pass-through (ABSOLUTE)" blocks:

- **(a) Truthful reporting** — Report an action as done **only** if you actually
  performed it and can cite the result. If you did not (or could not) perform it,
  say exactly what you did and what you could not do. **Never** state an assumed,
  planned, or forecast completion as if it were fact.
- **(b) Mechanism fidelity** — If a request names a specific mechanism (e.g.
  "create a Vikunja task"), fulfil **that** mechanism or explicitly say you could
  not. **Never** silently substitute a different mechanism (no "I scheduled a cron
  instead").

**Steps**:
1. Write the block as a single markdown section with a stable heading, e.g.
   `## Truthful Reporting & Mechanism Fidelity (ABSOLUTE)`.
2. Keep it to a handful of lines — this text is added to **7** files, two of
   which are at the byte cap. Every extra sentence costs budget 7×.
3. Fix the **exact byte string** of the block now; it becomes the literal the
   fleet-guard test (T005) asserts. Record it once (in T005's test as a module
   constant or fixture) so there is a single source of truth.

**Files**: none yet (drafting only). **Notes**: choose one heading and one body;
do not vary punctuation between agents.

### T002 — Insert the canonical block into all 7 fleet AGENTS.md (+ .tmpl)

**Purpose**: Land the T001 block, verbatim, in every fleet agent prompt so the
doctrine is fleet-wide (FR-001, FR-002, SC-004).

**Steps**:
1. Insert the **identical** T001 block into each of the 7 agent prompts:
   - `scripts/openclaw/agents/main/AGENTS.md`
   - `scripts/openclaw/agents/felix-admin-capture/AGENTS.md`
   - `scripts/openclaw/agents/felix-admin-habits/AGENTS.md`
   - `scripts/openclaw/agents/felix-admin-tasker/AGENTS.md`
   - `scripts/openclaw/agents/felix-admin-escalation/AGENTS.md`
   - `scripts/openclaw/agents/felix-admin-calendar/AGENTS.md`
   - `scripts/openclaw/agents/felix-doc-auditor/AGENTS.md`
2. Also update the **`.tmpl`** variants so the template and the deployed file do
   not drift. Confirmed present today (verify before editing, in case more were
   added):
   - `scripts/openclaw/agents/felix-admin-capture/AGENTS.md.tmpl`
   - `scripts/openclaw/agents/felix-admin-tasker/AGENTS.md.tmpl`
   Insert the same canonical block into each `.tmpl` at the position matching its
   deployed counterpart. (The other 5 agents have no `.tmpl` today — do not create
   one.)
3. Place the block consistently — a natural home is **near the existing "Red
   Lines" / "Output discipline" block** in each file so related doctrine sits
   together. Same relative placement in every file aids review.
4. **Budget discipline (hard)**: after editing, `main/AGENTS.md` and
   `felix-admin-calendar/AGENTS.md` must remain **< 12,000 bytes**. Since both
   start within ~30 bytes of the cap, reclaim space by tightening adjacent prose
   (collapse redundant sentences, drop filler) **without changing meaning** —
   do not delete any existing rule. Verify each file's size after editing.

**Files**: the 7 `AGENTS.md` + the 2 `.tmpl` files listed above.
**Notes**: keep the block byte-for-byte identical across all 9 insertions
(7 md + 2 tmpl) so T005 can assert one literal.

### T003 — Add the no-unrequested-infrastructure block to `main` ONLY

**Purpose**: Encode FR-003 in the one agent that holds infrastructure-creation
capability. This block is **scoped to `main` only** — do not add it to any other
agent.

**Steps**:
1. Add a second, `main`-only block to `scripts/openclaw/agents/main/AGENTS.md`,
   e.g. `## No Unrequested Infrastructure (main)`.
2. Content: **Never** create or modify scheduled/standing infrastructure (e.g.
   OpenClaw crons, systemd units, standing jobs) unless the request **explicitly**
   asked for it. A request to be **reminded** to do something means create the
   requested **Vikunja task**, **not** a cron. If a standing job seems warranted
   but was not asked for, surface the suggestion — do not create it.
3. Cross-reference the existing GOVERNANCE.md tiering already in `main` (cron
   changes are Tier 2/3) rather than restating it — one line, terse.
4. Respect the byte cap: `main` must still land **< 12,000 bytes** after both
   T002 and this block. Reclaim space by tightening prose as needed.

**Files**: `scripts/openclaw/agents/main/AGENTS.md` only. **Notes**: this block
must **not** appear in the other 6 agents; T005 asserts main-only scoping.

### T004 — Point agents at the completion-assertion helper (bypass path only)

**Purpose**: Give agents the one-line pointer they need for the manual/bypass
path of the completion-assertion ledger (FR-004 grounding). The normal path
auto-emits from creation helpers, so this line is **only** for when an agent
creates an artifact by **bypassing** a wrapped helper.

**Steps**:
1. Add **one line** to the canonical truthful-reporting doctrine block (so it
   propagates to all 7 agents via the shared text): when you create an artifact by
   bypassing a wrapped creation helper, record a completion-assertion via
   `python3 -m scripts.trust.completion_assertion` so the claim is grounded. The
   normal helper path emits this automatically — this is only for the bypass case.
2. Reference the path/command **only** — do **not** implement, import, or invoke
   the helper here. `scripts/trust/completion_assertion.py` is **delivered by
   WP03** (IC-04). This is a forward pointer in prose, nothing more.

**Files**: folded into the shared block, so it lands in all 7 `AGENTS.md`
(+ the 2 `.tmpl`). **Notes**: keep it to a single sentence — budget. If including
this line pushes `main`/`felix-admin-calendar` over cap, reclaim adjacent prose;
do not drop the line.

### T005 — Fleet-guard test `test_truthful_doctrine.py`

**Purpose**: Lock the doctrine in place with a deterministic prompt-content test
(SC-004) and guard the prompt budget.

**Steps**:
1. Create `scripts/openclaw/agents/tests/test_truthful_doctrine.py` (pytest).
   Reuse the existing `repo_root` session fixture from
   `scripts/openclaw/agents/tests/conftest.py` (resolves the repo root).
2. Define the canonical T001 block text once (module constant) — the single
   source of truth for the literal.
3. Assert the following:
   - The truthful-reporting + mechanism-fidelity block (the canonical literal, or
     a stable substring of it that covers both rule (a) and rule (b) and the
     T004 assertion-helper line) is **present in every one of the 7** agents'
     `AGENTS.md`. Iterate over the 7 agent directory names.
   - The no-unrequested-infrastructure block is **present in `main`** and
     **absent from the other 6** agents (assert main-only scoping).
   - **Budget**: no `AGENTS.md` exceeds its budget. **Borrow the approach from the
     sibling `scripts/openclaw/agents/tests/test_agents_md_size.py`** — that file
     asserts `main` and `felix-admin-calendar` are `< 12_000` bytes via
     `p.stat().st_size`. Apply the same 12,000-byte ceiling here across the agents
     you touched (at minimum `main` and `felix-admin-calendar`, the two at-cap
     files; covering all 7 is fine and cheap).
4. Keep assertions on the raw file bytes/text (no OpenClaw runtime needed).

**Files**: `scripts/openclaw/agents/tests/test_truthful_doctrine.py` (new — in
`create_intent`). **Notes**: do not modify `test_agents_md_size.py`; the two
tests are complementary. If you factored the canonical block into a shared
constant, import or duplicate it deliberately so the literal stays authoritative.

## Test Strategy

- Framework: **pytest** (matches the existing agent test suite).
- Run the new fleet-guard test:
  ```
  python3 -m pytest scripts/openclaw/agents/tests/test_truthful_doctrine.py -v
  ```
- Also run the existing size guard to confirm budget is not blown:
  ```
  python3 -m pytest scripts/openclaw/agents/tests/test_agents_md_size.py -v
  ```
- Both must be green before this WP is done. Tests are deterministic (raw file
  reads) — no OpenClaw, Vikunja, or network dependency.

## Definition of Done

- [ ] Canonical truthful-reporting + mechanism-fidelity block (T001) present,
      byte-for-byte identical, in all **7** agent `AGENTS.md`.
- [ ] Same block added to the **2** existing `.tmpl` variants (capture, tasker).
- [ ] No-unrequested-infrastructure block present in **`main` only** (absent from
      the other 6).
- [ ] Completion-assertion helper pointer (bypass path) present in the shared
      block (`python3 -m scripts.trust.completion_assertion`), referenced by path
      only (helper itself is WP03).
- [ ] `scripts/openclaw/agents/tests/test_truthful_doctrine.py` created and
      **green**.
- [ ] Existing `test_agents_md_size.py` still **green** — no `AGENTS.md` over
      12,000 bytes (esp. `main` and `felix-admin-calendar`).
- [ ] No `openclaw.json` edits; no detector/code changes; no rebaseline performed.

## Risks

- **Prompt-budget overflow (highest risk).** `main` (11,967 B) and
  `felix-admin-calendar` (11,984 B) are essentially at the 12,000-byte cap. Adding
  blocks naively will blow the cap and fail `test_agents_md_size.py`. Mitigation:
  keep the canonical block minimal and reclaim adjacent prose (meaning-preserving)
  in those two files. Verify sizes after every edit.
- **Do not touch `openclaw.json`.** This WP is doctrine/prompt only (C-003). Any
  capability/config change is out of scope.
- **Do not add code enforcement.** No approval-gating, no capability removal, no
  detector logic here (C-001). Those live in other WPs / deferred F0/#704.
- **`.tmpl` drift.** Forgetting the `.tmpl` variants would let the template and
  deployed prompt diverge. Update both capture and tasker templates.
- **Forward reference only for WP03.** Referencing
  `scripts/trust/completion_assertion` before WP03 lands is intentional (prose
  pointer). Do not import or execute it here.

## Reviewer Guidance

- Confirm the truthful-reporting + mechanism-fidelity block text is **identical**
  across all 7 `AGENTS.md` and the 2 `.tmpl` files (diff them; no per-agent
  wording drift).
- Confirm the no-unrequested-infrastructure block is present in **`main` only**
  and absent from the other 6 agents.
- Confirm the block matches the register of the existing "Red Lines" /
  "Verbatim pass-through (ABSOLUTE)" doctrine — imperative, absolute, terse.
- Confirm **no** capability or config changes: no `openclaw.json` edits, no
  detector code, no approval-gating, no capability removal.
- Confirm the completion-assertion pointer references the WP03 helper by path
  only and is not invoked.
- Confirm prompt budget respected: run both `test_truthful_doctrine.py` and
  `test_agents_md_size.py`; every touched `AGENTS.md` is `< 12,000` bytes.
- Confirm **no rebaseline** was performed (unmonitored audited surface, #621).
