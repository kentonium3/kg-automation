# Specification: Harden Inbox Capture on Sonnet

**Mission**: harden-inbox-capture-01KWVGZM
**Type**: software-dev
**Status**: Draft
**Source**: kentonium3/kg-automation#662 (Phase 1)

## Overview

Felix's inbox-capture agent (`felix-admin-capture`) is responsible for reading
free-form notes Kent captures on his phone and routing each note to its correct
destination (a journal entry, a "someday" note, a Vikunja task, or a Google
Calendar event), asking a clarifying question when a note is ambiguous. The agent
is an interactive assistant: comprehension, routing decisions, and conversational
follow-up are its job.

Today the agent runs on a weak model (`claude-haiku-4-5`) that intermittently
fails at that job in a specific, damaging way: it *reasons about the plumbing it
should never touch*. It reads prose in its own prompt describing where helper
scripts live, then hallucinates that those helpers "are not implemented" or "do
not exist at `<invented path>`", refuses to run, and emits a false
"system broken" alarm to Kent's phone. Separately, a successful run frequently
surfaces a `show > failed` warning because the primary WhatsApp announce falls
back to a secondary path.

This mission fixes the reliability failure at the **control-model layer** without
sacrificing interactivity. Two moves: (1) move capture from haiku to a
sonnet-class model, and (2) harden the prompt so the model invokes helpers as
opaque commands and never reasons about their paths or existence. It also fixes
the false `show > failed` announce so a processed note reliably confirms to Kent.

This is **Phase 1** (the reliability fix, FR-001..FR-004). Phase 2 of #662 —
richer LLM-driven multi-intent decomposition (the original FR-5) — is explicitly
split into a separate follow-up issue and is out of scope here.

## The governing principle: two layers, model in only one

- **Plumbing / mechanics — deterministic; the LLM must NEVER touch it.** Where
  files live, how a helper is invoked, dedup, state persistence, delivery
  transport. The helpers self-resolve every path and are invoked as opaque
  `python3 -m scripts.inbox.<helper>` calls. *No guessing at paths, ever.* The
  current hallucination is the LLM leaking into this layer.
- **Comprehension / judgment / interaction — the LLM's actual job.** Read the
  note, decide routing, ask a clarifying question, confirm the outcome. This is
  core to Felix being an interactive agent and must be preserved.

## User Scenarios & Testing

### Primary scenario — a note is captured and routed reliably
1. Kent dictates a note on his phone; it syncs to the vault `01-Inbox`.
2. A scheduled (or on-demand) capture run picks it up.
3. The agent comprehends the note, decides the destination, and invokes the
   appropriate helper as an opaque command — never inspecting or asserting where
   the helper lives.
4. The note is routed correctly and Kent receives a single, reliable WhatsApp
   confirmation (no `show > failed` warning).

### Exception scenario — empty inbox
1. A scheduled run fires with no unprocessed notes.
2. The agent emits `[felix-admin-capture]: IDLE` and nothing else — no
   "not implemented / not deployed" text, no invented path, no false alarm.

### Exception scenario — a helper genuinely fails
1. A helper exits non-zero.
2. The agent reports the actual stderr from that helper and does not speculate
   about "missing infrastructure" or invented paths.

### Interactivity scenario — calendar clarification (non-regression)
1. A note implies a calendar event but omits a time.
2. The agent asks Kent a clarifying question over WhatsApp.
3. Kent's reply resolves the ambiguity and the event is created — identical to
   current behavior.

## Functional Requirements

| ID | Requirement | Status |
|----|-------------|--------|
| FR-001 | The capture agent MUST run on a sonnet-class model instead of `claude-haiku-4-5`, configured through the OpenClaw agent configuration and deployed to office2. | Approved |
| FR-002 | The capture agent prompt MUST be rewritten so the model invokes helpers as opaque commands and never states, infers, or negates where helpers live or whether they exist. The prompt MUST NOT contain any prose the model can read as "helpers are at `<path>`" and then negate. | Approved |
| FR-003 | A successful capture run MUST deliver its summary confirmation reliably over WhatsApp with no `show > failed` warning and without relying on the delivery fallback. The primary announce path is fixed/robustified; run-summaries stay on WhatsApp (no channel change). | Approved |
| FR-004 | The conversational clarification loop MUST be preserved: a note missing a required detail (e.g. a calendar time) still triggers a WhatsApp clarifying question, and Kent's reply resolves and routes the note. No regression versus current behavior. | Approved |

## Non-Functional Requirements

| ID | Requirement | Threshold | Status |
|----|-------------|-----------|--------|
| NFR-001 | Cost + spend observability MUST be assessed before the model change ships, given the May-2026 spend-cap incident that originally motivated haiku. | A rough per-run cost estimate (sonnet vs haiku) and a confirmation that spend is observable are recorded in the plan/research artifacts before merge. | Approved |
| NFR-002 | Hallucination-free behavior MUST be demonstrable on an empty inbox. | 5 consecutive triggered runs over an empty inbox each emit `IDLE` with zero "not deployed/implemented" or invented-path output. | Approved |
| NFR-003 | Delivery robustness MUST be demonstrable. | 5 consecutive capture runs deliver their summary with no `show > failed` warning and no `fallbackUsed: true`. | Approved |

## Constraints

| ID | Constraint | Status |
|----|-----------|--------|
| C-001 | The LLM must never guess, infer, or assert helper paths or helper existence. The plumbing/comprehension boundary is absolute. | Approved |
| C-002 | All changes reach office2 only through a `deploys/queued/<name>.yaml` manifest consumed by felix-deployer. No direct edits on office2. | Approved |
| C-003 | The model change edits `openclaw.json`, a **monitored** audited surface (`audit.sh` hashes it). The security-monitor baseline MUST be rebaselined for this deploy; the merge commit records `Rebaseline: completed at <ts>` (felix-deployer auto-rebaselines on the pipeline happy path). | Approved |
| C-004 | The 14 existing `scripts/inbox/` helpers are reused unchanged. No new helpers are introduced; this is a model-config + prompt + delivery change. | Approved |
| C-005 | Risk tier: Tier 3 (agent prompt/config) + Tier 4 (architecture docs). | Approved |
| C-006 | Architecture docs MUST be updated in the same mission: `data/service-inventory.json` (+ md) capture `model` field haiku→sonnet, `docs/constitution/AGENT-REGISTRY.md`, and the relevant runbooks reviewed. | Approved |

## Success Criteria

- **SC-001**: `openclaw cron runs --id <inbox job>` shows `model: claude-sonnet-*` for capture runs after deploy.
- **SC-002**: A capture run over a real inbox note routes it correctly (journal / someday / task / calendar) with **no** "not implemented / not deployed" hallucination.
- **SC-003**: 5 consecutive empty-inbox runs emit `IDLE` with zero invented-path or "not deployed" output (satisfies NFR-002).
- **SC-004**: 5 consecutive successful runs deliver their WhatsApp summary with no `show > failed` warning and no `fallbackUsed: true` (satisfies NFR-003).
- **SC-005**: A calendar note missing a time still triggers the clarification question and Kent's reply routes it (FR-004 non-regression).
- **SC-006**: The merge records `Rebaseline: completed at <ts>`; `service-inventory.json` (+ md) and `AGENT-REGISTRY.md` reflect the new model.

## Key Entities

- **felix-admin-capture** — the OpenClaw inbox-capture agent (deploy dir: `inbox-agent` on office2). Owns comprehension + routing + interaction.
- **`felix-admin-capture/AGENTS.md` (+ `.tmpl`)** — the agent prompt, the surface hardened in FR-002.
- **`openclaw.json`** — OpenClaw config carrying the per-agent `model` field (FR-001); a monitored audited surface (C-003).
- **`scripts/inbox/` helpers (×14)** — the deterministic plumbing, reused unchanged (C-004), invoked as `python3 -m scripts.inbox.<helper>`.

## Assumptions

- Infrastructure is healthy: `python3 -m scripts.inbox.prescan --self-check` returns ok and the gateway exports `PYTHONPATH` — confirmed by behavioral testing 2026-07-06. The remaining failure is purely model-comprehension.
- A sonnet-class model is affordable at ~4 scheduled runs/day + on-demand because the deterministic work now lives in helpers (fewer/shorter model turns than when haiku was chosen). NFR-001 verifies this before ship.
- #658 (invocation anchoring) is merged + deployed and does not need to be redone here; it is a complementary layer.

## Out of Scope

- **FR-5 / Phase 2** — richer LLM-driven multi-intent decomposition (segmenting a note into ≥2 intents). Split into a separate follow-up issue.
- **Fleetwide model-selection framework** — deciding which model serves which LLM task across the agent fleet. Surfaced by this work but deferred; model choice stays per-agent in `openclaw.json` for now.
- **The `scripts/inbox/` helpers, routing destinations, and vault layout** — reused unchanged.
- **Future email / research intents** — design-compatible but not built here.
