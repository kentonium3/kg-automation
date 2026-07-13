# Data Model: Author main agent workspace

No runtime data schema — this mission authors prompt files. The "model" is the
**content-conservation model**: which content block belongs in which owner file,
and the invariants that must hold after authoring. Post-plan Codex review folded
in (2026-07-13): the table below now enumerates **every current heading** in all
five files with an explicit keep / move / drop / add disposition, so no live
front-desk behavior is silently lost.

## Owner files (post-authoring)

| File | Owns |
|------|------|
| `IDENTITY.md` | Display card: name (Felix), creature, vibe, emoji |
| `SOUL.md` | Voice/stance only + one-line privacy stance |
| `USER.md` | Filtered view of Kent + the Felix "why" |
| `TOOLS.md` | Real tool surface + **mechanics** (delegation bash, paths, helper invocations) + **the enforceable privacy path (Invariant A home)** |
| `AGENTS.md` | Role/authority, SOP **rules**, routing matrix, enforceable policy, **adapted Output Discipline block** |

Out of model (unchanged): `GOVERNANCE.md`, `felix-file-issue.py`.

## Byte-budget rebalance (Codex F4 — CONFIRMED hard constraint)

`main/AGENTS.md` is 11,592 B; `scripts/openclaw/agents/tests/test_agents_md_size.py`
enforces a **hard 12,000 B cap** (`size < 12000`) → ~408 B headroom. The mission
adds a role statement, an Output Discipline block, and escalation/tasker routing.
To stay under the cap, the rebalance is:
- **Enforceable privacy rule → `TOOLS.md`** (Invariant A accepts AGENTS *or* TOOLS; the validator token is `04-Growth/_private`). Zero AGENTS cost.
- **Delegation command mechanics** (the `openclaw agent --agent … --message …` bash blocks, timeouts, log paths), the **timelog** bash block + status enum, and the **felix-file-issue.py** invocation block → move to `TOOLS.md`; AGENTS keeps only the *rules* (who handles what, verbatim, cron-vs-ask) and a pointer.
- **Output Discipline block** stays lean (the validator only requires the `output discipline` marker in AGENTS + a real, adapted block — not capture's full inbox-specific text).
- **`## Make It Yours`** filler → drop.
Acceptance: `test_agents_md_size.py` green (AGENTS < 12,000 B, target ≥ ~300 B headroom).

## AGENTS.md — every current heading, disposition (Codex F1)

| Current heading | Disposition | Destination / note |
|-----------------|-------------|--------------------|
| First Run | keep | BOOTSTRAP handling |
| Message identity | **keep (unchanged)** | de-hardcode DROPPED (operator 2026-07-13); `Sent by main:sonnet` left as-is |
| Session Startup | keep | |
| Memory | keep | |
| Red Lines | **keep + merge** | absorb SOUL `## Red lines` (single owner, FR-008) |
| Truthful Reporting & Mechanism Fidelity | keep | fleet doctrine (ABSOLUTE) |
| Verbatim pass-through | keep | load-bearing delegation reliability (INV-5) |
| Governance — read GOVERNANCE.md | keep (concise) | pointer + tier-citation rule; GOVERNANCE.md itself unchanged |
| No Unrequested Infrastructure | keep | |
| Filing issues — felix-file-issue.py | keep rule; **mechanics → TOOLS** | keep the "use the helper, don't compose gh" rule; move the bash block |
| External vs Internal | keep | |
| Group Chats | keep | |
| Tools | keep | pointer to TOOLS |
| Heartbeats | keep | reconcile with Output Discipline (`HEARTBEAT_OK` is exempt) |
| Make It Yours | **drop** | filler; byte recovery |
| Inbox processing delegation | keep rule; **mechanics → TOOLS** | |
| Habit tracking delegation | keep rule; **mechanics → TOOLS** | |
| Calendar event creation delegation | keep rule; **mechanics → TOOLS** | #679 boundary rule stays |
| Calendar clarification reply delegation | keep rule | |
| Time-logging (option A) | keep rule; **mechanics → TOOLS** | 13-status relay rules stay as rules; bash block → TOOLS |
| Cron-driven sub-agent output | keep | #263/#285 relay rule (INV-5) |
| *(add)* Role / authority — EA-orchestrator | **add** | FR-005; front-desk/orchestrator framing, current reality only |
| *(add)* Output discipline (adapted) | **add** | FR-006 / Inv-B; adapted to main (see below) |
| *(add)* Routing matrix (all specialists) | **add** | FR-007 / F2 |

## SOUL.md — every current heading, disposition

| Current heading | Disposition | Destination |
|-----------------|-------------|-------------|
| Purpose | **split** | role → AGENTS; the Felix "why" → USER (FR-001/002/005) |
| Understanding Kent (+ 5 subsections) | **move** | USER (filtered) (FR-002) |
| Voice (+ subsections) | **keep** | SOUL (the keeper) (FR-001) |
| Sub-agent delegation (table) | **drop** | AGENTS routing matrix supersedes; escalation+tasker MUST survive into it (F2) |
| Heartbeat behavior | **drop** | AGENTS `## Heartbeats` owns it |
| Privacy boundary (full rule) | **reduce** | one-line stance in SOUL; enforceable rule → TOOLS (FR-006/Inv-A) |
| Red lines | **move** | merge into AGENTS `## Red Lines` (FR-008) |

## TOOLS.md / USER.md — disposition

| Current heading | Disposition |
|-----------------|-------------|
| TOOLS: What Goes Here / Examples / Why Separate (factory) | **replace** with real surface + mechanics + enforceable privacy path (FR-003) |
| USER: Notes / Active pursuits / Key people / What Felix is | keep; **add** filtered "Understanding Kent" + Felix "why"; resolve `Communication style` vs SOUL `Voice` overlap (FR-002) |

## Routing matrix (Codex F2 — all specialists must survive)

| Message type | Specialist / path | Verbatim? |
|--------------|-------------------|-----------|
| Inbox processing | `felix-admin-capture` | yes |
| Habit check-in / completion / management | `felix-admin-habits` (`parse_morning_reply`) | yes |
| Task escalation response | `felix-admin-escalation` (escalation parser) | yes |
| Task structuring / enrichment | `felix-admin-tasker` | yes |
| Calendar event / clarification | `felix-admin-calendar` (#679 boundary) | yes |
| Time-logging | direct helper (option A — main calls `timelog.py`, **not** a sub-agent) | n/a |

## Adapted Output Discipline block (Codex F3)

Do **not** literal-mirror capture's block (it is inbox-cron / `[felix-admin-capture]: IDLE`
specific). Author a lean block for main under the heading `## Output discipline`
(the validator marker) with main's role: identity-line-first (no preamble), no
between-tool narration, no delivery meta-commentary, and an explicit
`HEARTBEAT_OK` reconciliation (main's no-op reply is the literal `HEARTBEAT_OK`,
which is exempt from the identity-line rule). Follow the fleet 3-Hard-Rules shape
(as installed on habits / escalation / tasker), not capture's inbox text.

## Invariants (must hold after authoring)

- **INV-1 (Invariant A)**: `04-Growth/_private` enforceable rule present in `TOOLS.md` (and/or AGENTS); SOUL carries only the one-line stance. Validator `privacy_boundary` → ok.
- **INV-2 (Invariant B)**: `AGENTS.md` carries the `output discipline` marker + adapted block. Validator `output_discipline` → ok.
- **INV-3 (single owner)**: every shared concern in exactly one owner file; no cross-file duplication.
- **INV-4 (no placeholder)**: no factory-template / `[fill this in]` text remains.
- **INV-5 (delegation fidelity)**: verbatim-passthrough, cron-vs-ask relay, #679 calendar boundary, and all six routing entries survive intact.
- **INV-6 (deploy parity)**: after agent-prompt-sync, `/data/services/openclaw/data/` copies match repo (md5).
- **INV-7 (no scope creep)**: `GOVERNANCE.md` unchanged; no `deploys/queued/` manifest; no speculative mail behavior.
- **INV-8 (byte cap)**: `main/AGENTS.md` < 12,000 B (`test_agents_md_size.py` green).
- **INV-9 (session freshness)**: post-deploy and post-rollback, the live `main` session is rotated (`rotate_main_session.py`) before smoke, so the test exercises the new prompt, not the cached one.

## State transitions

None. One-shot author → validate → deploy → rotate → verify.
