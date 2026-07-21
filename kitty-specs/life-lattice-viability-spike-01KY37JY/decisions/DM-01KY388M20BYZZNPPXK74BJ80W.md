# Decision Moment `01KY388M20BYZZNPPXK74BJ80W`

- **Mission:** `life-lattice-viability-spike-01KY37JY`
- **Origin flow:** `plan`
- **Slot key:** `plan.methodology.graph-value-isolation`
- **Input key:** `graph_value_isolation`
- **Status:** `resolved`
- **Created:** `2026-07-21T21:10:46.080679+00:00`
- **Resolved:** `2026-07-21T21:11:56.102031+00:00`
- **Opened by:** `cli`
- **Other answer:** `false`

## Question

How should the spike ensure Q2 tests the temporal graph's value, not just an LLM reading dumped nodes?

## Options

- AB-compare graph-retrieval vs flat-dump
- Graph-retrieval only
- LLM full-context dump only

## Final answer

A/B compare graph-retrieval-mediated reasoning vs flat-context-dump baseline on identical seeded data. Go-evidence: graph path matches flat quality (no signal lost) AND offers the scale path flat cannot. Findings must explicitly state that graph-necessity-at-scale is a design argument the small-scale spike can only partially probe.

## Rationale

_(none)_

## Change log

- `2026-07-21T21:10:46.080679+00:00` — opened
- `2026-07-21T21:11:56.102031+00:00` — resolved (final_answer="A/B compare graph-retrieval-mediated reasoning vs flat-context-dump baseline on identical seeded data. Go-evidence: graph path matches flat quality (no signal lost) AND offers the scale path flat cannot. Findings must explicitly state that graph-necessity-at-scale is a design argument the small-scale spike can only partially probe.")
