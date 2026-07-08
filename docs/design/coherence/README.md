---
id: coherence-practice
doc_type: guide
title: "Felix Coherence Practice — Doctrine, Decisions & the Point-Cut Review"
status: active
level: howto
audience: agents_and_humans
owners: [kgale]
last_validated: '2026-07-08'
version: '0.1'
tags: [coherence, doctrine, governance, practice, bedrock, felix-core]
---

# Felix Coherence Practice

> **Foundation 3 (coherence) — the *practice* tier of the [Bedrock Stabilization](<../felix-bedrock-stabilization.md>)
> program (epic #673).** This is the anti-myopia substrate: a small, hand-curated set of
> cross-cutting invariants plus a decision corpus, read at spec/plan point-cuts so new work
> doesn't contradict a settled decision that lives where the decision process never looks
> (the #325/#662 failure mode). **~0 build by design** — flat files + a manual review. The
> deterministic selection/recording *machinery* is deferred to #643.

## What lives here

| File | What | Schema |
|---|---|---|
| [`doctrine.md`](<./doctrine.md>) | Canonical cross-cutting invariants | `INV-###` stanzas `{id, intent, when, rules, check}` |
| [`decisions.jsonl`](<./decisions.jsonl>) | Append-only decision corpus (one JSON object per line) | `{id, question, answer, status, date, invariants_touched, rationale, source_issue}` |

Invariants are inert data. **Nothing here calls an LLM** — Python (later, #643) only selects and
records; the agent does the thinking. The corpus is deliberately **graph-ready** (append-only,
stable ids, explicit `invariants_touched` + `source_issue` edges) so it can seed the future
vectorized-graph second brain without rework.

## Action-scoped injection map (which invariants a decision-type surfaces)

Consult *titles first*, pull bodies on demand. When a spec/plan touches one of these decision
types, surface the mapped invariants for the review:

| Decision type in the spec/plan | Surface |
|---|---|
| Agent capability / delegation / routing change | INV-002, INV-001 |
| Alerting / notification / observability / escalation | INV-003 |
| Status / completion reporting, or any infra-state logic | INV-001 |
| Agent workspace authoring (SOUL/USER/TOOLS/IDENTITY/AGENTS) | INV-004, INV-005 |
| File / vault access, ingestion, logging, or backup traversal | INV-005 |
| New tooling / service / substrate (over-engineering risk) | *(none yet — apply the anti-over-engineering decisions DEC-003/004/005)* |

Keep this map current as invariants are added. (This is the charter's pattern **B** at the
practice tier — a plain table; the machinery version, `actions/<type>/index.yaml` + loader,
is #643.)

## The point-cut coherence review (pattern D)

**Advisory, never a gate.** Run it by hand at two point-cuts in a mission:

1. **Post-specify** — once `spec.md` is drafted, before `/spec-kitty.plan`.
2. **Post-plan** — once `plan.md` is drafted, before `/spec-kitty.tasks`.

Procedure:

1. Identify the decision-types the spec/plan touches (capability change? alerting? workspace?
   infra-state logic? new tooling?).
2. Use the injection map to pull the relevant `INV` titles; read the bodies on demand.
3. Read related decisions in `decisions.jsonl` (filter by `invariants_touched` or `source_issue`).
4. Check the spec/plan for any **contradiction** with a surfaced invariant or a settled decision.
5. Emit findings as **advisory notes** — never block the mission. Surface material findings to
   the operator.

> **Why hand-cranked:** this is a *practice we follow*, not a workflow hook. It does **not** edit
> spec-kitty's own command files (upstream-managed). When spec-kitty gains user-customizable
> workflow adjustments, this review becomes the natural thing to wire in as a real point-cut.

## The significance gate (pattern E) — when to record a decision

After a decision is made (in a mission, an RFC, or ad-hoc), ask three booleans:

1. **Architectural?** — changes a boundary, ownership, substrate, or a cross-component contract.
2. **Irreversible?** — costly or hard to undo (a migration, an external commitment, a data shape).
3. **Cross-cutting?** — affects more than one agent, component, or domain.

**If *any one* is true → record a marker in `decisions.jsonl`.** Otherwise, no marker is needed.

## Recording a decision (by hand, for now)

1. Append one JSON object to `decisions.jsonl` with the next `DEC-###` id, `status`
   (`settled` / `open` / `superseded`), today's `date`, the `source_issue`, and a concise
   `rationale`.
2. Set `invariants_touched` to any `INV` the decision establishes or affects (`[]` if none).
3. If the decision establishes a *new durable rule*, also add (or update) the corresponding
   `INV-###` stanza in `doctrine.md` and cross-reference the `DEC` in its *Provenance* line.

Validate that `decisions.jsonl` stays one-object-per-line valid JSONL and that `doctrine.md`
stanzas keep the `{id, intent, when, rules, check}` shape.

## Deferred to #643 (the machinery tier)

The deterministic **selector** (given a spec/plan, surface the relevant invariants + prior
decisions) and **recorder** (append + validate markers) — the "Python selects/records, the
agent thinks" tooling — are built under #643, Sprint 2. Expected shape: domain-co-located
helpers under `scripts/coherence/` (`python3 -m scripts.coherence.<name>`) per
[helper-script-conventions § 9](<../helper-script-conventions.md>). Until then, this practice is
run by hand.
