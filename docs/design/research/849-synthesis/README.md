---
title: "#849 synthesis — what was built, how to run it, and what it is not"
doc_type: research
status: draft
owner: claude-office4
last_updated: 2026-09-24
---

# #849 synthesis

The authoring worksheet ([`849-lattice-scenario-arcs.md`](../849-lattice-scenario-arcs.md), Kent,
2026-09-23) was split into the two artifacts the run needs: a **seed** both arms may see, and a
**hidden oracle** neither may. This is the record of what exists and how to check it.

The mission was synthesis only. Building the loader, the three arms and the run harness is #849's
next phase — see [What this is not](#what-this-is-not).

## Artifacts

| | path | what |
|---|---|---|
| **seed** | [`seed/`](seed/) | 8 YAML files — the primitives both arms may see |
| **oracle** | [`oracle/`](oracle/) | 8 per-question artifacts + 1 appendix. **Never loaded into any arm.** |
| **narrative** | [`00-context-chains.md`](00-context-chains.md), [`01-cast.md`](01-cast.md) | the reasoning behind the chains and the cast |
| **rubric** | [`../849-rubric.md`](../849-rubric.md) | design-lead owned; the run's pre-registration |
| **traceability** | [`../849-traceability.md`](../849-traceability.md) | design-lead owned; every oracle point → its primitive |

Rendered corpus, at full scale: **5,750 events, 66 entities**, deterministic between runs.

```
email 4917 · mail-client 387 · vikunja 263 · journal 76 · calendar 34
note 24 · episode 20 · slack 14 · git 14 · config 1
```

## Running it

```bash
python3 -m scripts.research.render_849_corpus          # writes build/849-corpus/
python3 -m scripts.research.check_849_seed             # seed contracts
python3 -m scripts.research.check_849_oracle           # oracle contract (rubric §3.1)
python3 -m scripts.research.check_849_freeze           # the gate — run this last
```

`check_849_freeze` is the one that matters: it runs on the **rendered** corpus, which is what an
arm sees, and it invokes all five recoverability probes. Use `--scale N` to shrink generated
volume for a fast loop; a scaled corpus records `valid_for_run: false` in its manifest and must
not be used for a run.

## The four contracts

Each exists because something got through without it.

**1. Seeds assert primitives only.** No conflict, drift or pattern is ever written; all of it must
be inferable. Enforced by forbidden vocabulary and per-arc structural checks — Arc C's
`OUT_LAUNCH` may not carry completion, nothing may point at `COM_DESIGN_REVIEW`, Arc F may have no
Outcome.

**2. `meta.emits` is two-way.** A seed declares the rendered-event ids its generator must produce;
oracle traceability may name a seed id or a declared emit and nothing else. The renderer fails if
a declared id is never produced, and if it produces an id that is neither declared nor a seed id.
A trailing `*` declares a **family** — `GEN_B_WK*` — because enumerating generated ids creates a
list that drifts from its own source. A declared family with no members fails exactly as an
unproduced literal does.

**3. The stream is default-deny.** `STREAM_FIELDS` lists what an arm may see on an event.
Everything else is stripped and **reported** — a stripped field is either new corpus vocabulary
that belongs on the list, or a leak that was just prevented. Loader wiring (`mentions`) is held
apart from the stream: it is how the graph arm links episodes to entities, and putting it in the
dump would hand the flat arms the traversal the graph arm has to earn.

**4. Every oracle point is recoverable and every required value is present.** The first is the
recoverability probe; the second is its inverse. A leak makes a point too easy; a missing required
value makes it *impossible*, and both are silent.

## What the checks have actually caught

Not documentation. Each of these was a real defect in a real artifact:

- **Four missing primitives** — oracle points with no seed behind them (#844 Threats §1): Arc A's
  "paid, hard to reschedule", Arc B's halfway-point rule (the arc's *centre*), Arc F's email-first
  mornings, Arc E's real-bill-vs-fake-loan grounding. In each case an arm could have reasoned
  correctly and been scored wrong for not knowing something the corpus never carried.
- **Ten leaks**, of which four were one shape — an internal field reaching the output (`emit`,
  `week`, `over_travel_block_min`, `label_in_corpus`). None was vocabulary and none was a comment,
  so every check that existed passed them. That is why the allowlist is default-deny.
- **Three answer leaks in text**: Arc B's reason strings stated the miss and the collision; Arc E's
  consequences were rendered as *descriptions* rather than artifacts; the conditioning rule carried
  B1's coaching move. A summary is the finding stated rather than shown.
- **A contradiction between two correct rules.** "Completions only" and "every declared emit is
  produced" collided: three emit ids were declared for silent misses, which by definition have no
  event. An oracle point whose evidence is an **absence** must cite the stream the absence is
  visible in, never a per-instance id.
- **Two over-broad checks of its own** — one banned the word "checkpoint" and rejected the very
  episode it existed to require; one counted inbound emails as occupying a meeting slot.

## What this is not

- **Not a harness.** No loader, no arms, no run. The loader-side structural pass the design lead
  specified is **owed, not done**: the gate checks the rendered stream and entities, not a graph a
  loader emitted.
- **Not frozen.** Freezing is the design lead's call (rubric §9) at a named commit.
- **Not scored.** The grader notes in each oracle record judgements that must survive to scoring
  time — notably that Arc A's "counter-offer Thursday at 15:15" is a hard fail rather than partial
  credit, because it is exactly what an arm produces when it has the overlap and not the missing
  travel time.

## Dependencies the findings must state

- **An adapter assumption.** Arc E's five-phase session shape is recoverable only if the mail
  adapter observes read / move / delete / star / reply events. Recorded in `arc-e.yaml`.
- **A regime caveat.** Any cost gap measured on this corpus is a **lower bound**: it measures a
  system lacking capacities Kent intends to use, so a "does not pay off yet" reading would be
  regime-bound the way #844's was. This must be stated before the run, not discovered after.
