# Approach Evolution

> Track how your approach changed as the mission progressed.

**Prompting questions**
- What approach did you start with (as stated in the spec or plan)?
- What changed during implementation, and why?
- What would you try differently on a similar mission?

---

## Seed context (2026-07-05)

Starting approach: auto-drive the full spec-kitty arc (specify → plan → tasks →
implement → review → accept → merge) with no hand-cranking; STOP + capture on any
genuine tool failure (a workaround destroys the diagnostic signal). Two mandatory
Codex review-and-fix checkpoints: **post-plan** (before tasks) and **post-merge**
(before feat→main). Land via a real **feat→main PR** (first PR-involved workflow we
journal). This is a multi-objective diagnostic run: complete #658 + journal (superset)
+ tracers + post-mission analyzer gap-analysis.

## Entries

- `[2026-07-05][specify]` All-in-one scope chosen over bounded/fast-follow — Kent's goal
  is "Felix reliable, consistently implemented, no cruft in this area" — so this mission
  converts EVERY in-scope invocation across all four felix-admin agents, not a subset.
  Trade-off accepted: larger mission / more WPs / more redeploys, in exchange for a fully
  cleared area + richer friction corpus.
- `[2026-07-05][specify]` PR-landing DECOUPLED from the Stijn/#2341 trial — originally
  planned to double as data for Stijn's maintainer-PR-landing-approach trial; realized
  #658-as-PR lands our OWN mission output (no fork, no contributor adjudication) so it's a
  hollow #2341 trial — the #2341 trial now runs separately on a real spec-kitty-family PR.
  #658 keeps the feat→main PR purely for OUR journaling/analyzer research.
- `[2026-07-05][plan]` Design-phase LIVE code scan was the highest-value plan work — it
  overturned the issue body's clean "~30 `-m scripts.`" framing (found fleet inconsistency +
  a third abs-path shape + already-clean HOME writes), reshaping scope + the canonical form.
  Lesson reinforced: probe the real code during plan; don't trust the issue's inventory.
- `[2026-07-05][implement]` Dispatched the 3 conversion WPs + WP06 to parallel implementer
  sub-agents (per lane worktree) with the canonical form + checker self-verify inlined — kept
  orchestrator context lean and parallelized the mechanical conversions. Worked well; each agent
  self-verified before committing.
- `[2026-07-05][implement] LESSON` Per-WP approval on the DOMAIN checker alone was insufficient —
  I approved the conversion WPs on `env_assumptions` checker-clean, but a verbose guard message
  bloated 2 AGENTS.md past a prior mission's independent 12K size cap (caught only at WP05 by the
  full `pytest` suite). Next time: run the WHOLE test suite at each WP review, not just the
  feature's own verifier. Fixed by shortening the canonical message globally.
- `[2026-07-05][plan]` Post-plan Codex review returned 3 HIGH + 5 MED + 1 LOW, ALL valid,
  ALL folded — including one real design reversal (cd form) and one implement-breaking bug
  (`.ok` vs `.passed`). The mandatory checkpoint paid for itself on this run. Approach note:
  ran codex read-only (not the `-p spec-kitty-review` profile) because a review needs no
  `.git` writes — simpler + sidesteps the unregistered-profile snag.
