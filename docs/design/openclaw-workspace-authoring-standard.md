---
title: OpenClaw Workspace Authoring Standard
doc_type: standard
status: approved
audience: agents_and_humans
owners: [kgale]
last_updated: '2026-07-04'
last_validated: '2026-07-04'
version: '1.0'
tags: [openclaw, agents, workspace, authoring, 587, 167, 553]
---

# OpenClaw Workspace Authoring Standard

The file-ownership contract and shared-invariant rules that every Felix OpenClaw
agent workspace is authored against. This is the standard the per-agent authoring
children of [#167](https://github.com/kentonium3/kg-automation/issues/167) (starting
with felix-admin-capture, #584) are written to, and the contract the workspace
validation helper (`scripts/openclaw/agents/validate_workspace.py`) enforces.

**Source issue**: [#587](https://github.com/kentonium3/kg-automation/issues/587)
**Prior decision**: [#553](https://github.com/kentonium3/kg-automation/issues/553) — workspaces are self-contained (retained, not factored out)

## Why this standard exists

Felix agent workspaces were authored ad hoc. The same concern (privacy boundary,
role statement, voice) landed in different files on different agents, and shared
hard boundaries were checked by eye. [#553](https://github.com/kentonium3/kg-automation/issues/553)
established that these files are *deliberately* per-agent — OpenClaw does not
inherit them — so the fix is not deduplication but **intentional authoring against
a written contract, with the shared invariants mechanically checked.**

## Principle 1 — Workspaces are self-contained (no inheritance)

OpenClaw loads each configured agent's prompt files strictly from that agent's own
workspace directory. It does **not** fall back to `defaults.workspace` for a
configured agent. This was source-verified during #553:

- `plan.js` workspace setup loads `path.join(workspaceDir, "SOUL.md")` — no fallback.
- The `bootstrap-extra-files` hook carries a "must stay inside the workspace"
  realpath constraint, ruling it out for cross-workspace sharing.
- Recognized bootstrap basenames: `AGENTS.md`, `SOUL.md`, `TOOLS.md`, `IDENTITY.md`,
  `USER.md`, `HEARTBEAT.md`, `BOOTSTRAP.md`, `MEMORY.md`.

**Consequence:** every applicable workspace must carry its shared invariants
*in its own files*. Shared truths are expressed and validated **intentionally per
workspace**, never collapsed into a single inherited file. The `defaults.workspace/`
directory is OpenClaw's factory scaffold for *unconfigured* agents; it is not a base
layer that configured Felix agents inherit from.

## Principle 2 — File-ownership contract

Each file owns exactly one concern, and those concerns change at different rates.
Content belongs in exactly one owner file; duplication across files is prohibited
(a stale copy is a drift hazard). Grounded in the OpenClaw templates
(`docs.openclaw.ai/concepts/soul`, `/reference/templates/{USER,TOOLS}`) and
established Felix practice.

| File | Owns | Explicitly NOT | Change rate |
|---|---|---|---|
| **IDENTITY.md** | Agent name, emoji/creature, one-line vibe. What `openclaw agents` displays. | Personality, voice, role. If it exceeds ~10 lines, personality content has leaked in — move it to SOUL. | Rare |
| **SOUL.md** | Voice, tone, stance, brevity, bluntness, boundaries **as behavioral stance**. "Write as Kent." | Role/purpose (→ AGENTS), enforceable policy (→ AGENTS/TOOLS), biography/changelog, operational mechanics. | Rare (most stable) |
| **USER.md** | The human, filtered to what *this* agent needs: name, address, pronouns, timezone, notes, and a `Context` section scoped to the agent's responsibility. | A full dossier. Operational mechanics (date/timezone handling → TOOLS). Content identical across agents — each view is filtered. | Slow |
| **TOOLS.md** | Environment/tool surface: paths, endpoints, SSH hosts, API skills, operational mechanics (e.g. date handling), operating constraints, failure behavior. The enforceable privacy path. | Behavioral rules ("always be concise" is behavioral → SOUL/AGENTS). Inlined lists that go stale (e.g. label taxonomies — keep a pointer, not a copy). | Medium |
| **AGENTS.md** | Operating rules / SOP: role & authority, processing workflow, routing logic, enforceable policy (privacy rule, Output Discipline), and routing-adjacent reference (e.g. the label taxonomy beside the issue-routing step). | Voice/personality (→ SOUL). Becoming a catch-all "ball of mud" dump. | Frequent |

**Anti-patterns this contract bans:**

- **Duplication** — the same rule stated in two files. Exactly one owner.
- **Ball of mud** — AGENTS.md as a dump for anything operational. It owns rules and
  workflow, not environment specifics (those are TOOLS) or voice (that is SOUL).
- **Staleness traps** — inlining a list that lives authoritatively elsewhere (e.g.
  the GitHub label taxonomy). Keep a pointer to the source; put routing-time policy
  beside the routing step in AGENTS.md.
- **Personality leak into IDENTITY** — IDENTITY is a display card, not a persona.

## Principle 3 — Shared invariants (present per workspace, validated)

These truths must appear in **every applicable workspace**, in their owner file.
They are intentionally repeated per workspace (Principle 1) and checked mechanically
so drift is loud, not silent.

### Invariant A — Privacy boundary

The `04-Growth/_private/` never-touch rule. Its **enforceable form** lives in
`AGENTS.md` (and may also appear in `TOOLS.md` as the environment path) — this is the
mechanically-checked home. `SOUL.md` may carry only a one-line behavioral **stance**
("I work only where I'm invited"); the stance never substitutes for the enforceable
rule. A workspace with the stance but no enforceable rule fails validation.

### Invariant B — Output Discipline

Any agent that emits **user-facing WhatsApp** must carry the Output Discipline
(Hard Rules) block in `AGENTS.md` (the canonical source is felix-admin-capture's
block). An agent that does **not** emit user-facing WhatsApp must instead carry an
explicit annotation — the literal marker **`no user-facing WhatsApp`** — so the
absence is a deliberate, declared choice rather than an oversight. The validation
check is **presence-or-annotation**: block present *or* annotation present passes;
neither fails.

## Principle 4 — Filtered, not identical (USER.md)

`USER.md` is a per-agent **filtered view** of Kent, scoped to what that agent's role
needs to interpret its work — not a global identical profile. capture needs enough
context to interpret terse inbox captures; tasker needs task-intelligence context;
they legitimately differ. "Filtered view, not dossier, not clone."

## Active roster and out-of-roster handling

The standard and its validation apply to the **active** Felix agent workspaces:

| Workspace | Validated? | Notes |
|---|---|---|
| `main` | Yes | Front-desk / orchestrator; user-facing WhatsApp. |
| `felix-admin-capture` | Yes | Inbox processor; user-facing WhatsApp. Canonical Output Discipline source. |
| `felix-admin-habits` | Yes | Habit check-ins; user-facing WhatsApp. |
| `felix-admin-tasker` | Yes | Task intelligence; user-facing WhatsApp. |
| `felix-admin-escalation` | Yes | Escalation; user-facing WhatsApp. |
| `felix-admin-calendar` | Yes | Calendar subagent (post-#579); user-facing WhatsApp. |
| `felix-doc-auditor` | **No — suspended** | Refactored to a scripts-first Python driver (#343); no live OpenClaw agent session. Its workspace directory is retained as history but is **not** deployed or validated. Re-add to the roster only if it is reactivated as a live agent. |

New agents join the roster by being authored to this standard and added to the
validation helper's discovery (any workspace directory containing `AGENTS.md`, minus
the suspended set). See `docs/runbooks/openclaw-agent-setup.md`.

## Validation

`scripts/openclaw/agents/validate_workspace.py` is the deterministic checker. It
reports, per active workspace, pass/fail for Invariant A (privacy boundary) and
Invariant B (Output Discipline presence-or-annotation), and exits non-zero if any
active workspace fails. Run:

```bash
python3 -m scripts.openclaw.agents.validate_workspace --json
```

The checker enforces **presence** of the shared invariants (the drift-dangerous
surface, per #553). It does not re-derive per-file ownership beyond the enforceable
homes above — ownership discipline is authored per Principle 2 and reviewed per
agent during authoring (#584 and siblings). The checker is a repo/CI artifact; it is
not deployed to office2.

## Relationship to reconciliation

This standard governs **how workspace files are authored**. The
[agent workspace reconciliation](<../runbooks/agent-workspace-reconciliation.md>)
system governs **how authored files stay in sync** between the repo and office2
(three-way diff, last-author-wins). They are complementary: author to this standard,
reconcile with that system.

## References

- [#587](https://github.com/kentonium3/kg-automation/issues/587) — this standard + validation
- [#553](https://github.com/kentonium3/kg-automation/issues/553) — self-contained workspace decision
- [#167](https://github.com/kentonium3/kg-automation/issues/167) — epic: intentionally author every workspace
- OpenClaw docs: `concepts/soul`, `reference/templates/USER`, `reference/templates/TOOLS`
- [`docs/runbooks/openclaw-agent-setup.md`](<../runbooks/openclaw-agent-setup.md>) — setup + deploy
- [`docs/runbooks/agent-workspace-reconciliation.md`](<../runbooks/agent-workspace-reconciliation.md>) — drift enforcement
