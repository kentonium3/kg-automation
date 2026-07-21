# Implementation Plan: Life Lattice Viability Spike

**Branch**: `feat/life-lattice-viability-spike` | **Date**: 2026-07-21 | **Spec**: [spec.md](./spec.md)
**Input**: Feature specification from `kitty-specs/life-lattice-viability-spike-01KY37JY/spec.md`

## Summary

Stand up a **throwaway, isolated** Graphiti + FalkorDB sandbox on office2; hand-seed a manufactured-but-realistic Purpose→Outcome→Project→Task chain carrying three deliberately-constructed stress scenarios; then answer the four make-or-break questions, proving **Q2 (temporal-reasoning payoff) first**. Q2 is tested via an **A/B design** (decision `graph_value_isolation`): the same seeded data is reasoned over twice — once through Graphiti graph/temporal retrieval, once via a flat full-context dump baseline — so a "go" reflects the *substrate's* contribution (or at minimum parity + a scale path), not just Claude's ability to read structured text. The deliverable is a `findings.md` go/no-go verdict; on **go**, the rollout ladder is confirmed and the epic sequenced.

## Technical Context

**Language/Version**: Python 3.12 (spike harness scripts: seed loader, A/B reasoning runner, footprint sampler)
**Primary Dependencies**: Graphiti (Zep) as the bi-temporal graph framework; FalkorDB as the graph store; Anthropic Claude API (native, per the #692 design) for entity extraction + reasoning; Docker Compose for the isolated sandbox
**Storage**: FalkorDB inside a throwaway Docker volume (isolated); no persistence beyond the spike; torn down at end
**Testing**: Observational/evidence-based (research mission) — harness scripts carry light self-checks (seed loaded, queries return); the acceptance signal is Kent's Q2 usefulness judgment + recorded evidence, not a passing test suite
**Target Platform**: office2 (Ubuntu 24.04 LTS), Docker via the `docker` group; Tailscale-bound; `claude` user has no sudo (privileged steps surface to Kent)
**Project Type**: single — a self-contained, throwaway spike harness under the mission's research workspace
**Performance Goals**: N/A for throughput — the only measured number is Q1 resource footprint (peak mem/CPU/disk of the sandbox alongside the stack)
**Constraints**: Zero production contact (NFR-001); isolated Docker network + distinct ports; fully reversible/torn down (NFR-002); synthetic content only (C-002); no write-back or decision-influence (C-001); time-box ~2–4 focused sessions (NFR-003)
**Scale/Scope**: Small hand-seeded slice (order of dozens of nodes across the tier model) plus 3 stress scenarios — deliberately sized to prove reasoning usefulness, explicitly NOT to prove graph-necessity-at-scale (which the findings frame as a design argument the small spike can only partially probe)

## Charter Check

*GATE: Must pass before Phase 0 research. Re-check after Phase 1 design.*

Derived from `spec-kitty charter context --action plan` (template set `software-dev-default`; directives active):

- **DIRECTIVE_001 (Architectural Integrity)** — PASS. The sandbox is fully isolated behind its own Docker network/volume; no coupling to production surfaces.
- **DIRECTIVE_003 (Decision Documentation)** — PASS. Material decisions are captured in `decisions/` (e.g. `graph_value_isolation`) and synthesized in `findings.md`.
- **DIRECTIVE_010 (Specification Fidelity)** — PASS. Plan traces every activity to an FR; deviations would be documented in findings.
- **DIRECTIVE_024 (Locality of Change)** — PASS. All spike artifacts live under `kitty-specs/<mission>/`; no production `src/` is touched.
- **DIRECTIVE_031 (Context-Aware Design)** — PASS. Canonical Lattice vocabulary (from the design docs) is used throughout; the sandbox is a distinct bounded context from production Felix.
- **Felix Constitution Directive 6 (deterministic vs stochastic)** — the seed loader, A/B query harness, and footprint sampler are deterministic helper scripts; only the reasoning judgment (traversal answer, conflict interpretation) is stochastic. Split recognized.
- **Change-risk / deploy discipline** — the sandbox is deliberately OUTSIDE the production deploy-manifest discipline (C-003); a carve-out to that discipline for throwaway sandboxes is a tracked follow-up, not a violation to justify here.

No violations requiring Complexity Tracking.

## Project Structure

### Documentation (this mission)

```
kitty-specs/life-lattice-viability-spike-01KY37JY/
├── plan.md              # This file
├── research.md          # Phase 0 output (methodology + dependency decisions)
├── data-model.md        # Phase 1 output (the seeded chain ontology slice)
├── quickstart.md        # Phase 1 output (stand-up → seed → A/B → teardown runbook)
├── findings.md          # Deliverable (go/no-go writeup — authored during the mission)
└── tasks.md             # Phase 2 output (/spec-kitty.tasks — NOT created here)
```

### Source Code (spike harness, under the mission's research workspace)

```
kitty-specs/life-lattice-viability-spike-01KY37JY/
├── sandbox/
│   └── docker-compose.yml   # isolated Graphiti + FalkorDB (distinct network + ports)
├── harness/
│   ├── seed_lattice.py      # loads the manufactured chain + stress scenarios
│   ├── reason_ab.py         # A/B runner: graph-retrieval path vs flat-dump baseline
│   └── measure_footprint.py # samples container mem/CPU/disk during the run
└── data/
    └── seed_chain.yaml      # the manufactured P→O→P→T + Principle/Constraint slice
```

**Structure Decision**: The spike is self-contained under the mission directory (research workspace per the research mission's path conventions). Nothing lands in production `src/`. The sandbox itself runs on office2 in a throwaway location and is torn down; only the reproducible harness + seed data + findings are retained as the research record.

## Implementation Concern Map

> Concerns, not work packages — `/spec-kitty.tasks` translates these into WPs.

### IC-01 — Isolated sandbox stand-up & teardown

- **Purpose**: Bring up Graphiti + FalkorDB on office2 in full isolation, and guarantee clean teardown.
- **Relevant requirements**: FR-001, NFR-001, NFR-002, C-003
- **Affected surfaces**: `sandbox/docker-compose.yml`; office2 Docker (throwaway network/volume/ports)
- **Sequencing/depends-on**: none (first)
- **Pre-standup gates**: (a) R-06a provider-path gate — confirm+document the all-Claude/non-OpenAI LLM+embedder+outbound-hosts config, else mark Q3/Q2-arch-fit blocked; (b) R-06b spike-scoped key hygiene; (c) R-06c headroom check.
- **Isolation definition (Codex HIGH-5)**: "zero production contact" = no reads, writes, mounts, shared Docker networks, env reuse, prod credentials, or service discovery against production — not merely zero writes. A **preflight+teardown evidence checklist** records the sandbox's Docker networks, volumes, mounts, env vars, listening ports, and outbound hosts, and re-checks them empty after teardown.
- **Risks**: Port/network collision with the existing stack; privileged steps need Kent (no sudo for `claude`). Teardown must leave zero residue (verified, not assumed).

### IC-02 — Manufactured seed chain

- **Purpose**: Author a life-shaped Purpose→Outcome→Project→Task chain (+ Principle/Constraint nodes) embedding a week-conflict, a trade-off, and a chronic-defer pattern.
- **Relevant requirements**: FR-002, C-002
- **Affected surfaces**: `data/seed_chain.yaml`, `harness/seed_lattice.py`
- **Sequencing/depends-on**: IC-01 (needs a store to load into) for loading; authoring can start in parallel
- **Risks**: Content too clean/toy → unfair Q2 test; stress scenarios must be genuinely hard, not decorative.

### IC-03 — A/B reasoning harness

- **Purpose**: Run upward traversal ("why this task?") and conflict/trade-off surfacing two ways — Graphiti graph/temporal retrieval vs flat full-context dump — on identical data, **with validity controls** (research R-01b): fixed prompts (only context differs), temperature 0 and/or N repeated runs, captured raw contexts per arm, randomized arm order. Scores surfaced conflicts against the hidden `data/oracle.yaml` (research R-01c), never against pre-loaded tension edges (there are none — data-model hidden-oracle rule).
- **Relevant requirements**: FR-003, FR-004; decision `graph_value_isolation`; research R-01a/b/c
- **Affected surfaces**: `harness/reason_ab.py`, `data/oracle.yaml`
- **Sequencing/depends-on**: IC-01, IC-02
- **Risks**: Graph path silently degenerating to a dump (assert it actually issues graph/temporal queries — see the required chronic-defer retrieval query); prompt asymmetry; LLM nondeterminism swamping the signal (mitigated by temp 0 + repeats).

### IC-04 — Q2 usefulness evaluation (the gate)

- **Purpose**: Present the two arms' traversal answers + surfaced conflicts to Kent **blinded** (arm labels hidden/randomized), and capture his explicit usefulness judgment scored against the **pre-registered rubric** (research R-01a): a GO requires the graph arm to be materially better/more reliable on ≥1 temporal stress case AND judged genuinely useful; indistinguishable arms → `inconclusive`/no-go-for-Q2, a valid outcome. De-blind after scoring.
- **Relevant requirements**: FR-005; SC-002; research R-01a/R-01b
- **Affected surfaces**: `findings.md` (Q2 section — rubric written BEFORE the runs)
- **Sequencing/depends-on**: IC-03
- **Risks**: This is the make-or-break; a NO-GO/inconclusive here stops the spike before IC-05/06 deepen. Evaluator bias (mitigated by blinding).

### IC-05 — Footprint measurement (Q1)

- **Purpose**: Record the sandbox's footprint across its full lifecycle (Codex MED-8): office2 **baseline** (before stand-up), **cold start**, **post-seed indexing**, **A/B run peak**, **idle-after-run**, and **post-teardown residue** — reported as deltas against baseline, with explicit headroom thresholds for the acceptability judgment.
- **Relevant requirements**: FR-006, NFR-004; SC-003
- **Affected surfaces**: `harness/measure_footprint.py`, `findings.md` (Q1 section)
- **Sequencing/depends-on**: IC-01 (baseline before; samples across IC-02/IC-03; residue after teardown)
- **Risks**: Attribution of usage to the sandbox vs the stack (baseline delta addresses this); missing cold-start/indexing spikes if only peak-during-A/B is sampled.

### IC-06 — Privacy/extraction posture (Q3) + ontology fit (Q4)

- **Purpose**: Q3 — document the actual extraction LLM + embedder + every outbound host + data-boundary path (fed by the R-06a gate) and confirm the post-#848 "verify not present" posture. Q4 — record ontology-tier friction, **separated into three buckets (Codex MED-10)**: (i) genuine *ontology* friction (the tier model doesn't fit), (ii) *engine/API* friction (Graphiti/FalkorDB import or query limitations), (iii) *seed-authoring* friction (author bias / modeling mistakes) — with a concrete example for each, so engine workaround pain is never misreported as an ontology failure.
- **Relevant requirements**: FR-007, FR-008; C-004; research R-06a
- **Affected surfaces**: `findings.md` (Q3/Q4 sections)
- **Sequencing/depends-on**: IC-02 (Q4 observed during seeding), IC-03 (Q3 observed during extraction/reasoning)
- **Risks**: Q3 silently green on a fallback (OpenAI) embedder → the R-06a gate prevents this; Q4 conflating ontology vs engine vs authoring → the three-bucket split prevents it. Q4 stays a slice observation, not a survey.

### IC-07 — Findings synthesis & go/no-go

- **Purpose**: Synthesize per-question evidence into a single go/no-go verdict; on go, confirm the shadow→advisory→gated→autonomous ladder, sequence #693→#698, and frame the membrane-topology decision for #696.
- **Relevant requirements**: FR-009, FR-010; SC-001, SC-004
- **Affected surfaces**: `findings.md`
- **Sequencing/depends-on**: IC-04, IC-05, IC-06
- **Risks**: Keeping the verdict honest about the scale caveat; not over-claiming from a small slice.
