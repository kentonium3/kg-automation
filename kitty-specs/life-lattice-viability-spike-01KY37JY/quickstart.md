# Quickstart: Running the Life Lattice Viability Spike

Operational runbook for the throwaway spike. All office2 actions run as the `claude` user (`ssh office2-claude`); Docker via the `docker` group; anything needing sudo is surfaced to Kent. **Nothing here touches production** — isolated network, volume, and ports; full teardown at the end.

## 0. Pre-flight (before stand-up)

- Confirm office2 headroom for the extra containers (R-06c) — brief mem/disk check against current stack usage.
- Confirm an Anthropic API key is available to the sandbox, isolated from prod credentials (R-06b).
- Confirm Graphiti can be configured for an all-Claude / non-OpenAI extraction + embedder path (R-06a).

## 1. Stand up the isolated sandbox (IC-01)

- Bring up `sandbox/docker-compose.yml` as its own compose project (dedicated network + volume + non-default ports) on office2.
- Verify FalkorDB is reachable *only* inside the sandbox network and Graphiti connects to it.
- Record the compose project name for a clean teardown later.

## 2. Seed the manufactured chain (IC-02)

- Author `data/seed_chain.yaml` per [data-model.md](./data-model.md): the P→O→P→T backbone + Principle/Constraint nodes + the three stress scenarios (week-conflict, trade-off, chronic-defer).
- Load it with `harness/seed_lattice.py`. Verify: every Task traces upward to a Purpose; both a `hard` and a `soft` Principle exist; the three scenarios are present.

## 3. Run the A/B reasoning (IC-03) — prove Q2 FIRST

- `harness/reason_ab.py` runs both arms on identical data:
  - **Arm A (graph)**: Graphiti graph/temporal retrieval pulls the relevant subgraph → Claude reasons.
  - **Arm B (flat)**: the same nodes are dumped into Claude's context directly.
- For each arm capture: the "why this task?" upward-traversal answer, and any surfaced conflict/trade-off.
- Sample footprint during the runs with `harness/measure_footprint.py` (IC-05).

## 4. Q2 usefulness gate (IC-04) — the make-or-break

- Present to Kent: the traversal answer + the surfaced conflict (both arms).
- **Kent renders the explicit usefulness judgment.** If NOT genuinely useful → record **NO-GO** in `findings.md` and skip to teardown. Nothing above Q2 matters.

## 5. Remaining questions (IC-05/06), only if Q2 is a go

- **Q1 footprint**: finalize peak mem/CPU/disk vs office2 headroom.
- **Q3 privacy/extraction**: document which LLM extracted, whether content crossed Tailscale, and confirm the post-#848 "verify not present" posture.
- **Q4 ontology fit**: note any tier-model friction seen while seeding.

## 6. Findings & verdict (IC-07)

- Synthesize per-question evidence into `findings.md` with one overall go/no-go.
- On **go**: confirm the shadow→advisory→gated→autonomous ladder, sequence #693→#698, and frame the membrane-topology decision for #696.
- Be explicit about the scale caveat: the small slice proves *reasoning usefulness*, and graph-necessity-at-scale is argued, not measured.

## 7. Teardown (IC-01) — mandatory

- Tear down the compose project: containers + volume + network removed.
- Verify **zero residual** sandbox services/volumes remain on office2 (NFR-002, SC-005).
- The reproducible harness + seed data + `findings.md` remain as the research record; the running sandbox does not.
