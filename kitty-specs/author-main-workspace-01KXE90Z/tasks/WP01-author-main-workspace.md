---
work_package_id: WP01
title: Author main workspace files
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
tracker_refs: []
planning_base_branch: feat/author-main-workspace
merge_target_branch: feat/author-main-workspace
branch_strategy: Planning artifacts for this mission were generated on feat/author-main-workspace. During /spec-kitty.implement this WP may branch from a dependency-specific base, but completed changes must merge back into feat/author-main-workspace unless the human explicitly redirects the landing branch.
subtasks:
- T001
- T002
- T003
- T004
- T005
- T006
- T007
agent: "claude:opus:reviewer-renata:reviewer"
shell_pid: "25652"
shell_pid_created_at: "1783968976.342954"
history:
- '2026-07-13: authored from spec + plan (post-plan Codex folded; de-hardcode dropped per operator)'
agent_profile: curator-carla
authoritative_surface: scripts/openclaw/agents/main/
create_intent: []
execution_mode: code_change
owned_files:
- scripts/openclaw/agents/main/SOUL.md
- scripts/openclaw/agents/main/USER.md
- scripts/openclaw/agents/main/TOOLS.md
- scripts/openclaw/agents/main/IDENTITY.md
- scripts/openclaw/agents/main/AGENTS.md
- docs/design/openclaw-workspace-authoring-standard.md
role: implementer
tags: []
---

## ⚡ Do This First: Load Agent Profile

Before reading anything else, load your assigned agent profile:

```
/ad-hoc-profile-load curator-carla
```

Adopt that identity, governance scope, and boundaries for the whole work package.

## Objective

Re-author Felix's `main` (front-desk / orchestrator) OpenClaw workspace to the
**#587 authoring standard** so that (a) both shared invariants pass, (b) the two
factory-template files are intentionally authored, (c) `SOUL.md` is voice-only,
and (d) two approved improvements are folded in — **with zero loss of live
front-desk behavior**. `main` handles all direct WhatsApp conversation and
delegates to specialist sub-agents; a dropped rule here degrades every
conversation. Treat this as behavior-preserving except for the two explicit
improvements.

**Ground truth you MUST read before editing:**
- `docs/design/openclaw-workspace-authoring-standard.md` — the #587 contract (file-ownership table, the two invariants, filtered-USER).
- `kitty-specs/author-main-workspace-01KXE90Z/data-model.md` — the **content-conservation move-table** (every current heading → keep/move/drop) and the invariants. This is your authoritative map.
- `kitty-specs/author-main-workspace-01KXE90Z/research.md` — the decisions (esp. D7 adapted-block, D9 de-hardcode DROPPED, D10 byte budget, D11 main-scoped validation).
- Current files: `scripts/openclaw/agents/main/{SOUL,USER,TOOLS,IDENTITY,AGENTS,GOVERNANCE}.md`.
- `scripts/openclaw/agents/felix-admin-capture/AGENTS.md` — the Output Discipline source to **adapt** (not copy).
- `scripts/openclaw/agents/validate_workspace.py` — the checker (markers: `04-Growth/_private` for Invariant A in AGENTS **or** TOOLS; `output discipline` marker for Invariant B in AGENTS).

## Hard constraints (Codex-surfaced — do not violate)

1. **12K byte cap on `main/AGENTS.md`** (`scripts/openclaw/agents/tests/test_agents_md_size.py`, `size < 12000`). It is at 11,592 B now. You are ADDING a role statement + Output Discipline block + escalation/tasker routing, so you MUST offload to `TOOLS.md`:
   - Put the enforceable `04-Growth/_private/` privacy rule in **TOOLS.md** (Invariant A accepts TOOLS — saves AGENTS bytes).
   - Move delegation **mechanics** (the `openclaw agent --agent … --message …` bash blocks, the timelog bash block + status enum, the `felix-file-issue.py` invocation block) to **TOOLS.md**. Keep only the *rules* in AGENTS.
   - Keep the Output Discipline block lean (the validator only needs the `output discipline` marker + a real block).
   - Drop the `## Make It Yours` filler.
   - Target ≥ ~300 B headroom under 12,000.
2. **Invariant B block is ADAPTED, not mirrored** (D7). Capture's block is inbox/`[felix-admin-capture]: IDLE`-specific — do NOT copy it. Author a main-specific block under a `## Output discipline` heading following the fleet 3-Hard-Rules shape (as on habits/escalation/tasker), reconciled with main's `HEARTBEAT_OK` no-op (which is exempt from the identity-line rule).
3. **No behavior loss.** Every current `AGENTS.md` heading has a disposition in `data-model.md`. Load-bearing rules that MUST survive intact: Truthful Reporting, Verbatim pass-through, Governance tier-citation, No-Unrequested-Infra, cron-vs-ask relay (#263/#285), the #679 calendar boundary, timelog 13-status relay rules, and routing for **all six** specialist paths (capture, habits, escalation, tasker, calendar, timelog). Escalation + tasker currently live ONLY in the SOUL delegation table — they MUST survive into the AGENTS routing matrix.
4. **Message-identity line is UNCHANGED** (de-hardcode dropped per operator). Leave `Sent by main:sonnet` exactly as-is.
5. **GOVERNANCE.md content is UNCHANGED** — only add a one-line roster note to the #587 standard.
6. **No new deterministic work** — reuse the existing validator; no new helper/skill; no `deploys/queued/` manifest.

## Subtasks

### T001 — Author SOUL.md → voice-only + one-line privacy stance
- **Keep** the `## Voice` content (principles, words-to-avoid, "words that are Kent") — the keeper.
- **Remove** `## Purpose` (role → AGENTS T005; the Felix "why" → USER T002), `## Understanding Kent` (→ USER T002), `## Sub-agent delegation` (→ AGENTS routing matrix T005; **make sure escalation + tasker are carried there before deleting**), `## Heartbeat behavior` (AGENTS owns Heartbeats).
- **Reduce** `## Privacy boundary` to a one-line behavioral stance (e.g. "I work only where I'm invited"). The enforceable rule moves to TOOLS (T003).
- **Move** `## Red lines` into AGENTS `## Red Lines` (T005).
- **Result**: SOUL.md contains voice/stance only. Validator must NOT find `04-Growth/_private` as the enforceable rule here (a one-line stance is fine, but the enforceable rule lives in TOOLS).
- **Validation**: `grep -c "^## " main/SOUL.md` shows only Voice-family sections + a short stance; no role/delegation/heartbeat/understanding-kent.

### T002 — Author USER.md → filtered Kent-context + Felix "why"
- **Absorb** the filtered "Understanding Kent" content from SOUL (how Kent thinks, discomfort/growth, routine, values) — filtered to what main needs to orchestrate, not a full dossier.
- **Absorb** the Felix "why" (extraordinary-life / 10x-leverage mission) from SOUL `## Purpose` as Kent-context.
- **Resolve** the overlap between USER `## Communication style` and SOUL `## Voice`: Kent's *preferences* stay in USER; the *agent's voice* stays in SOUL. No duplicated content.
- Keep existing USER content (Notes, Active pursuits, Key people, What Felix is) — trim any duplication with the newly-absorbed "why".
- **Validation**: USER reads as a filtered view of Kent; the "why" reads as context, not agent voice.

### T003 — Author TOOLS.md → real surface + mechanics + enforceable privacy rule
- Replace the factory scaffold (`## What Goes Here` / `## Examples` cameras/TTS / `## Why Separate`) entirely.
- Author main's REAL surface: office2 paths, SSH hosts, the `openclaw agent --agent <name> --message … --json --timeout …` delegation mechanics, the timelog helper invocation (`cd … && /data/services/openclaw/felix-calendar/venv/bin/python -m scripts.google.timelog …`), the `felix-file-issue.py` invocation, relevant state files.
- **Carry the enforceable privacy rule here**: include the literal token `04-Growth/_private` with the never-touch rule (this satisfies Invariant A and keeps AGENTS under the cap).
- Use **pointers, not inlined lists**, for anything authoritative elsewhere (e.g. label taxonomy).
- **Validation**: `grep -c "04-Growth/_private" main/TOOLS.md` ≥ 1; no factory example content remains.

### T004 — Author IDENTITY.md → Felix identity card
- Replace the blank factory template. Name = **Felix**. Add creature / vibe / emoji drawn from the voice (sharp, direct, systems-minded — a capable front-desk operator, not a chatbot). Keep it a display card (≤ ~10 lines per the standard).
- **Note for reviewer/operator**: the exact vibe/creature/emoji is Kent-refinable at review — propose, don't over-commit.
- **Validation**: no `_(pick something you like)_` / placeholder text remains.

### T005 — Author AGENTS.md → role, adapted Output Discipline, routing matrix, consolidations (under 12K)
- **Add** a concise role/authority statement framing main as the **front-desk / EA-orchestrator** (direct conversation + delegation to specialists). Current reality only — NO speculative mail #165 behavior. (Improvement 1.)
- **Add** the adapted `## Output discipline` block (see Hard Constraint 2). Fixes Invariant B.
- **Add** a routing matrix covering all six specialist paths (capture / habits / escalation / tasker / calendar / timelog), each with its verbatim + relay rule. Escalation + tasker MUST appear (they only exist in the SOUL table today). Keep the RULES; the bash mechanics live in TOOLS (T003). (Improvement 2 = tighten delegation reliability: make verbatim-passthrough + cron-vs-ask unambiguous.)
- **Merge** SOUL's `## Red lines` into AGENTS `## Red Lines` (single owner).
- **Keep** (do not drop): First Run, Message identity (**unchanged**), Session Startup, Memory, Truthful Reporting, Verbatim pass-through, Governance pointer + tier-citation, No Unrequested Infra, Filing-issues rule (mechanics→TOOLS), External vs Internal, Group Chats, Tools pointer, Heartbeats (reconcile with Output Discipline), Cron-driven-output rule.
- **Drop**: `## Make It Yours` (filler, byte recovery).
- **Move to TOOLS** (mechanics only, keep rules here): the inbox/habit/calendar/timelog/issue-filing bash blocks.
- **STAY UNDER 12,000 BYTES.** Check with `wc -c`.
- **Validation**: `grep -io "output discipline" main/AGENTS.md` matches; `grep -o "felix-admin-[a-z]*" main/AGENTS.md | sort -u` shows capture/habits/escalation/tasker/calendar; `wc -c main/AGENTS.md` < 12000.

### T006 — Add GOVERNANCE.md roster note to the #587 standard
- In `docs/design/openclaw-workspace-authoring-standard.md`, add a one-line note (in the roster/validation area) that `main` carries an on-demand `GOVERNANCE.md` outside the five-file model and outside validator scope. Do NOT modify `GOVERNANCE.md` itself.

### T007 — Validate (main-scoped) + byte cap + suite + conservation
- Run `python3 -m scripts.openclaw.agents.validate_workspace --json`; confirm the **`main`** object is `ok:true` (both invariants). **Read main's object — the process exit is independently RED via `felix-admin-calendar`/#635, which is out of scope.**
- Run `python3 -m pytest scripts/openclaw/agents/tests/test_agents_md_size.py -q` (12K cap green).
- Run `python3 -m pytest scripts/openclaw/agents/tests/ -q` (full openclaw suite green).
- Conservation self-check: confirm every moved block landed in its destination and was removed from its source; confirm no load-bearing rule (Verbatim, cron-vs-ask, #679, all six routes) was dropped.

## Branch Strategy

- Planning/base branch: `feat/author-main-workspace`. Final merge target: `feat/author-main-workspace` (then a separate `feat → main` PR closes the mission).
- Execution worktrees are allocated per computed lane from `lanes.json` (single lane here). Work in your assigned lane worktree.

## Definition of Done

- All seven subtasks complete; all five files intentionally authored + the standard roster note added.
- Validator: `main` `ok:true`; `test_agents_md_size.py` green; full openclaw suite green.
- No behavior loss (conservation self-check passes; all six routes + load-bearing rules present); message-identity line unchanged; GOVERNANCE.md unchanged; no manifest created.
- `AGENTS.md` < 12,000 B.

## Risks & Reviewer Guidance

- **Byte cap**: reviewer should `wc -c main/AGENTS.md` and confirm < 12,000 with headroom.
- **Silent rule loss**: reviewer should diff current vs authored AGENTS and confirm every keep/move/drop matches `data-model.md`; specifically verify escalation + tasker routing survived, and Verbatim / cron-vs-ask / #679 rules are intact.
- **Adapted block**: reviewer confirms the Output Discipline block is main-specific (HEARTBEAT_OK reconciled), NOT capture's inbox text.
- **Invariant homes**: privacy rule in TOOLS (not just SOUL stance); `output discipline` marker in AGENTS.
- **Scope**: reviewer confirms GOVERNANCE.md unchanged, identity line unchanged, no `deploys/queued/` manifest, no speculative mail behavior.

## Activity Log

- 2026-07-13T18:41:54Z – claude:sonnet:curator-carla:implementer – shell_pid=21257 – Assigned agent via action command
- 2026-07-13T18:55:54Z – claude:sonnet:curator-carla:implementer – shell_pid=21257 – Ready for review: main authored to #587; main ok:true; AGENTS.md 11586B (<12K); full openclaw suite 72 passed; all six routes preserved; timelog section kept in AGENTS per test_timelog_prompt.py guard (pointer in TOOLS)
- 2026-07-13T18:56:25Z – claude:opus:reviewer-renata:reviewer – shell_pid=25652 – Started review via action command
