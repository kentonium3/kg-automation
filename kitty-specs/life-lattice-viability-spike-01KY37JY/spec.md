# Feature Specification: Life Lattice Viability Spike

**Mission type**: research (Deep Research Kitty)
**Mission**: life-lattice-viability-spike-01KY37JY
**Source issue**: #844 · **Parent epic**: #692 · **Program**: #833
**Status**: Draft

## Overview

A time-boxed, **throwaway, zero-production-contact** research spike to de-risk the **Life Lattice** — the vectorized *temporal* graph that is the cognitive substrate of the Executive Assistant program (#833) — **before** committing to the full #693→#698 build. The spike converts four make-or-break unknowns into evidence-backed learnings and produces a **go / no-go** verdict that gates the epic's build.

The make-or-break question is **temporal-reasoning payoff (Q2)**: does reasoning over a hand-seeded, life-shaped chain produce something Kent judges *genuinely useful* — not merely technically returned? If it does not pay off, the spike stops at NO-GO and nothing above it matters.

## Domain Language

| Canonical term | Meaning | Avoid |
|---|---|---|
| **Life Lattice** (short: Lattice) | The structured, vectorized, bi-temporal graph binding *why* (Purpose) + *what* (Outcome→Task) + *when* (temporal). The cognitive substrate. | "the graph" (ambiguous), "second brain" |
| **Episode** | One raw unstructured input unit (capture / note / message / event / decision). | "record", "entry" |
| **Membrane** | The selective admit/promote gate between raw episodes and Lattice structure. | "filter", "importer" |
| **Adapter** | An interchangeable I/O surface (Vikunja, calendar, email) — source of truth for operational state, not the substrate. | "integration" |
| **Second brain** | The curated Obsidian vault (knowledge warehouse), distinct from the Lattice (canon). | conflating with the Lattice |

## User Scenarios & Testing

**Primary actor**: Kent (with Claude Code as the executing agent).

**Trigger**: Before building the Life Lattice, we need a defensible go/no-go — there is no staging environment, so we de-risk cheaply on an additive, isolated sandbox.

**Happy path (go):**
1. An isolated Graphiti + FalkorDB sandbox is stood up on office2 with zero production contact.
2. A manufactured-but-realistic Purpose→Outcome→Project→Task chain is hand-seeded, with deliberately-constructed stress scenarios (a real week-conflict, a trade-off, a "deferred 4× since March" pattern).
3. The sandbox answers "why this task?" by traversing upward to the Purpose it serves, and surfaces at least one genuine conflict/trade-off that was not hand-fed.
4. Kent judges the reasoning *genuinely useful*. Footprint is measured; privacy posture and ontology fit are confirmed on the slice.
5. A `findings.md` go/no-go writeup is produced; on **go**, the rollout ladder is confirmed and the epic sequenced, with the membrane-topology decision teed up for #696.

**Exception / NO-GO path**: The upward traversal and conflict-surfacing run, but Kent judges the reasoning not genuinely useful → the spike records **NO-GO** as a first-class outcome and stops before Q1/Q3/Q4 deep-dives matter.

**Rule that must always hold**: The sandbox never touches production services, credentials, or real vault content; no write-back or decision-influence path is exercised; the sandbox is reversible and torn down.

## Requirements

### Functional Requirements

| ID | Requirement | Status |
|---|---|---|
| FR-001 | The spike MUST stand up an isolated Graphiti + FalkorDB sandbox on office2 with no connection to production services or the real second-brain vault. | Draft |
| FR-002 | The spike MUST hand-seed a manufactured-but-realistic Purpose→Outcome→Project→Task chain (representative of Kent's actual life, not a toy) that deliberately embeds at least three stress scenarios: a genuine week-conflict, a trade-off, and a chronic-defer ("deferred 4× since March") pattern. | Draft |
| FR-003 | The spike MUST demonstrate upward traversal — given a leaf task, return a coherent "why this task?" answer that surfaces the Purpose it serves. | Draft |
| FR-004 | The spike MUST surface at least one genuine conflict or trade-off from the seeded chain that was reasoned from primitives (constraints, capacity, priorities, temporal facts), not hand-fed. The loaded graph MUST contain no asserted `CONFLICTS_WITH`/`TRADES_OFF` edges for evaluated scenarios; expected conflicts live in a hidden oracle used only for scoring. | Draft |
| FR-005 | The spike MUST capture Kent's explicit usefulness judgment on Q2 — the make-or-break gate — after he has seen the FR-003 traversal and the FR-004 conflict **presented blinded** (arm labels hidden), scored against a **rubric pre-registered before the runs**: a GO requires the graph/temporal arm to be materially better or more reliable than the flat baseline on ≥1 temporal stress case AND judged genuinely useful; indistinguishable arms yield `inconclusive`/no-go-for-Q2 (a valid outcome). | Draft |
| FR-006 | The spike MUST measure the office2 resource footprint (memory, CPU, disk) of the sandbox running alongside the existing stack (Q1). | Draft |
| FR-007 | The spike MUST document which LLM performs entity extraction and whether any episode content crosses the Tailscale boundary, and confirm the post-#848 "verify sensitive content is not present" posture (Q3). | Draft |
| FR-008 | The spike MUST record whether hand-seeding the slice reveals friction in the ontology tier model (Q4), separating findings into ontology friction vs engine/API friction vs seed-authoring friction (with an example of each) — an empirical answer on a slice, not an exhaustive survey. | Draft |
| FR-009 | The spike MUST produce a `findings.md` go/no-go writeup with per-question evidence and a single overall verdict. | Draft |
| FR-010 | On a **go** verdict, the spike MUST confirm the phased rollout ladder (shadow → advisory → gated → autonomous) as the build/validation plan, sequence the epic (#693 → #694 → #695 → #696 → #697 → #698), frame the membrane-topology decision for #696, and record a **scale-caveat / residual-risk** section naming which questions remain unproven at larger scale. | Draft |

### Non-Functional Requirements

| ID | Requirement | Measurable threshold | Status |
|---|---|---|---|
| NFR-001 | Zero production contact. | No reads, writes, mounts, shared Docker networks, env reuse, production credentials, or service discovery against any production surface — not merely zero writes; verified by a preflight + teardown checklist recording the sandbox's networks, volumes, mounts, env vars, listening ports, and outbound hosts. | Draft |
| NFR-002 | Reversibility / throwaway. | After teardown, 0 residual sandbox services, containers, or data volumes remain on office2. | Draft |
| NFR-003 | Time-box. | Reach a go/no-go verdict within approximately 2–4 focused working sessions. | Draft |
| NFR-004 | Footprint acceptability. | Memory/CPU/disk sampled across the full lifecycle (baseline before stand-up, cold start, post-seed indexing, A/B run, idle-after-run, post-teardown residue) as deltas vs baseline, judged against explicit office2 headroom thresholds; acceptability decision recorded. | Draft |

### Constraints

| ID | Constraint | Status |
|---|---|---|
| C-001 | No write-back or decision-influence path is exercised — those are the dangerous moments and stay out of the spike entirely. | Draft |
| C-002 | Synthetic content only. No real second-brain / vault data is ingested; the reasoning test runs entirely on manufactured content. | Draft |
| C-003 | The sandbox is deliberately outside the production deploy-manifest discipline (which governs production code); a throwaway/isolated-sandbox carve-out to that discipline is a tracked follow-up. | Draft |
| C-004 | Q3 is bounded by the post-#848 physical-exclusion posture — private content is physically excluded from every agent-reachable surface, so the check is "verify not present," not a folder-guard gate. | Draft |

## Success Criteria

| ID | Criterion |
|---|---|
| SC-001 | A go/no-go verdict is produced with documented evidence. On a Q2 GO, evidence covers all four questions; on a Q2 NO-GO/inconclusive (which stops the deep-dives), the minimum evidence is the Q2 result, teardown proof, and the provider/privacy (Q3) path, with any skipped question explicitly marked skipped. |
| SC-002 | For Q2, Kent renders an explicit usefulness judgment against the pre-registered rubric, seeing the blinded arms' upward-traversal answers and reasoned (not hand-fed) conflicts/trade-offs. |
| SC-003 | The office2 footprint is recorded as concrete numbers and judged against available headroom. |
| SC-004 | On a go verdict, the six-rung build sequence and the shadow→advisory→gated→autonomous ladder are confirmed, and the membrane-topology decision is framed for #696. |
| SC-005 | The sandbox leaves zero residual footprint on office2 after teardown. |

## Key Entities

- **Life Lattice** — the temporal graph under test (Graphiti + FalkorDB engine).
- **Seeded chain** — the manufactured Purpose→Outcome→Project→Task structure plus embedded Principle/Constraint nodes and the three stress scenarios.
- **Episode** — the raw-input unit primitive (not exercised for real content in the spike; relevant to Q3/membrane framing only).
- **Findings writeup** — `findings.md`, the go/no-go deliverable.

## Assumptions

- office2 can host isolated Graphiti + FalkorDB containers alongside the existing stack without disturbing it — this is Q1 itself, so it is measured rather than assumed.
- Manufactured-but-realistic content is sufficient to prove Q2; no real Lattice content exists yet and none is needed for the reasoning test.
- The privacy boundary is already resolved (#848 physical exclusion), so cloud-LLM extraction on synthetic content is not privacy-gated; Q3 confirms rather than re-decides this.
- The `claude` user on office2 has no sudo; any privileged sandbox setup is surfaced to Kent for manual execution (Docker access is via the `docker` group).

## Out of Scope

- The full build (#693–#698) and any production wiring — those follow a **go** verdict.
- Exhaustive hierarchy survey (#367) — the tier model is validated empirically on a slice here instead.
- Any write-back, decision-influence, or real vault ingest.
