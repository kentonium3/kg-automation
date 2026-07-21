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
- `CONFLICTS_WITH` / `TRADES_OFF` — emergent or asserted tension edges (what the reasoning should surface, not what we hand-feed the answer from).
- **Bi-temporal fields on every edge**: `valid_from` / `valid_until` (world time) + ingestion time — the substrate for "deferred 4× since March" and week-conflict reasoning.

## The three stress scenarios (deliberately constructed)

1. **Week-conflict**: Two Projects under *different* Purposes each have a Task with a hard Constraint (deadline) inside the same week, and their time demands exceed the available capacity. The reasoning should surface the collision and the competing Purposes behind it.
2. **Trade-off**: One Outcome can be advanced by either of two Projects that draw on the same scarce resource; advancing one defers the other. A Principle (`hard` or `soft`) tips the trade-off. The reasoning should name the trade-off and the governing Principle.
3. **Chronic-defer ("deferred 4× since March")**: A Task whose `valid_from`/scheduling has been pushed four times across bi-temporal history, while its parent Outcome stays high-priority. The reasoning should detect the pattern (temporal signal), not just the current state.

## Validation / invariants the seed must satisfy

- Every Task traces upward to exactly one Purpose (no floating nodes).
- At least one `hard` Principle and one `soft` Principle present (to exercise the constraint dimension).
- The three stress scenarios are present and genuinely hard (not answerable from a single node's fields).
- Content is synthetic and life-*shaped* (opaque handles for anything that would be sensitive) — never real private content (C-002, C-004).

## Not modeled (out of scope for the slice)

- Full ontology breadth (Q4 is a slice observation, not a survey).
- Episode/membrane ingestion of real content — the spike seeds structured nodes directly; the raw-episode→membrane path is only *reasoned about* for Q3, not exercised.
