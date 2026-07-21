# Data Model: The Seeded Chain Slice (Phase 1)

The manufactured content the spike loads. This is the *slice* under test — sized to prove reasoning usefulness, not to survey the full ontology. Structure follows the #692 ontology (`docs/design/second-brain-graph-layer.md`).

## Node tiers (definitional → operational)

| Tier | Node type | Role in the slice |
|---|---|---|
| Definitional | **Purpose** | Top of every chain; the "why" a task ultimately serves. Invariant: every node connects upward to a Purpose. |
| Definitional | **Principle** | Cross-cutting constraint (`hard`/`soft`) — what Kent will/won't accept. Constrains decisions rather than directing them. |
| Directional | **Domain** → **Outcome** → **Objective** | The goal backbone under a Purpose. |
| Operational | **Project** → **Task** | Executable work; the leaf tasks are where "why this task?" traversal starts. |
| Cross-cutting | **Constraint** | Hard-temporal limits (deadlines, windows) that create the conflicts. |

## Edges

- `SERVES` / `CONTRIBUTES_TO` — upward links (Task→Project→Objective→Outcome→Domain→Purpose). Traversed for "why this task?".
- `SCOPED_TO` / `GOVERNED_BY` / `VIOLATES` — Principle relationships.
- **Bi-temporal fields on every edge**: `valid_from` / `valid_until` (world time) + `observed_at` / `ingested_at` (ingestion time) — the substrate for "deferred 4× since March" and week-conflict reasoning.

### Hidden-oracle rule (Codex HIGH-3 — makes FR-004 honest)

**`CONFLICTS_WITH` / `TRADES_OFF` edges MUST NOT be present in the loaded graph for any scenario being evaluated.** If we assert the conflict as an edge, the reasoning is reading the answer, not inferring it. Instead:

- The loaded graph contains only the *primitives* — Constraints (deadlines/windows), capacity limits, priorities, Principles, and temporal facts — from which a conflict/trade-off must be **inferred**.
- The expected conflicts/trade-offs live in a **separate hidden oracle file** (`data/oracle.yaml`, NOT loaded into the graph and NOT shown to the reasoner) used only to score whether each arm surfaced them.
- FR-004's "reasoned (not hand-fed)" is satisfied only when a surfaced conflict was derived from primitives, never from a pre-loaded tension edge.

## The three stress scenarios (deliberately constructed)

1. **Week-conflict**: Two Projects under *different* Purposes each have a Task with a hard Constraint (deadline) inside the same week, and their time demands exceed the available capacity. The reasoning should surface the collision and the competing Purposes behind it.
2. **Trade-off**: One Outcome can be advanced by either of two Projects that draw on the same scarce resource; advancing one defers the other. A Principle (`hard` or `soft`) tips the trade-off. The reasoning should name the trade-off and the governing Principle.
3. **Chronic-defer ("deferred 4× since March")**: A Task rescheduled four times while its parent Outcome stays high-priority. The reasoning should detect the *pattern* (temporal signal), not just current state. **Concrete representation (Codex MED-9):** each defer is a distinct temporal record — `{observed_at, ingested_at, previous_planned_date, new_planned_date, current_validity}` — so the history is four retrievable rescheduling events, not just a single mutated `valid_from`. A required harness query MUST prove the four-event pattern is retrievable from the store (confirming Graphiti's bi-temporal model actually captures rescheduling history, not merely fact-validity). If it is not retrievable, that is itself a Q2/Q4 finding.

## Seed-quality checklist (Codex MED-7 — operationalizes "manufactured-but-realistic")

The seed is not accepted until ALL hold:

- Every Task traces upward to exactly one Purpose (no floating nodes).
- ≥1 `hard` Principle and ≥1 `soft` Principle present.
- **Multiple Purposes** compete (the week-conflict spans two different Purposes).
- **Scarce capacity** exists (task time demands exceed available capacity in the conflict week).
- **Ambiguous priority** — at least one pair where the "right" choice is not obvious from a single field.
- **Stale temporal state** — the chronic-defer pattern is present with four distinct events.
- **A misleading surface answer** — at least one case where the naive single-node reading differs from the temporally-informed reasoning (so the graph arm has something to *win*).
- The three stress scenarios are genuinely hard (not answerable from a single node's fields) and their conflicts are NOT asserted as edges (hidden-oracle rule above).
- Content is synthetic and life-*shaped* (opaque handles for anything sensitive) — never real private content (C-002, C-004).
- **Kent validates** the abstractions are realistic (representative of how his life is actually shaped) without exposing real private content.

## Not modeled (out of scope for the slice)

- Full ontology breadth (Q4 is a slice observation, not a survey).
- Episode/membrane ingestion of real content — the spike seeds structured nodes directly; the raw-episode→membrane path is only *reasoned about* for Q3, not exercised.
