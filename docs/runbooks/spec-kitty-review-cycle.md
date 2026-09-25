---
id: spec-kitty-review-cycle
doc_type: runbook
title: Spec-Kitty Mission Review Cycle
status: approved
level: reference
owners: [kgale]
audience: agents_and_humans
last_updated: '2026-09-25'
last_validated: '2026-07-04'
version: '1.0'
tags: [spec-kitty, review, codex, workflow, governance]
---

# Spec-Kitty Mission Cycle — with Independent Codex Review Checkpoints

A view of the full spec-kitty mission arc, showing where two **independent Codex reviews**
sit relative to the tool's own built-in checks. The two Codex passes are a standing
practice (see the "Codex review checkpoints" block in the global `~/.claude/CLAUDE.md` and
the auto-drive section of this repo's `CLAUDE.md`): an independent model, with fresh eyes,
that looks at the *whole* at a natural altitude — and **fixes** what it finds — bracketing
the two most expensive-to-reverse transitions in the arc (decompose-into-work-packages, and
land-on-main).

---

## The full cycle

```
/spec-kitty.specify
   → spec.md
      → /spec-kitty.plan
         → plan.md, research.md, data-model.md, quickstart.md
            → ★ Codex review #1 (independent design critique)  ── review-AND-fix
                 spec+plan+research+data-model: gaps, risky assumptions,
                 better approaches, missed edge cases → fold back into the plan
               → /spec-kitty.tasks
                  → tasks.md + WP prompt files
                     → ○ /spec-kitty.analyze (self-run, mechanical)  ── report-only, GATE
                          consistency + coverage across spec/plan/tasks;
                          any high/critical → "blocked"
                        → /spec-kitty.implement  (per WP, dependency-ordered)
                           ┌─ per-WP loop ────────────────────────────────┐
                           │  implement (e.g. sonnet)                      │
                           │     → for_review                              │
                           │        → ○ per-WP review (e.g. codex)         │
                           │             scope = ONE WP's diff             │
                           │           ├─ approved → next WP               │
                           │           └─ rejected → re-implement          │
                           │                (cycle ≤3, then arbiter)       │
                           └──────────────────────────────────────────────┘
                           → spec-kitty accept   (○ readiness gate)
                              → spec-kitty merge  (WPs → mission → feature branch)
                                 → ★ Codex review #2 (independent, WHOLE DIFF) ── review-AND-fix
                                      cross-WP integration bugs, inconsistencies,
                                      quality/security no single WP could see
                                      → fix findings IN the feature branch
                                    → ○ spec-kitty-mission-review (optional)
                                         spec→code fidelity / FR coverage
                                       → feat → main  (merge + push, CI)
                                          → deploy + verify (parity + smoke)
                                             → close issue + retrospective
```

### Legend

- **★ independent Codex pass** — a *different model*, fresh context, no authorship
  attachment, that **fixes** what it finds. The two review-and-fix checkpoints.
  - **#1** = design correctness, *before* the plan is decomposed into work packages.
  - **#2** = whole-diff correctness, *before* the branch lands on main.
- **○ self-run / mechanical** — the same driving model, or a bookkeeping check; it
  *reports* or *gates*, it doesn't independently critique.
  - `analyze` (consistency + coverage), per-WP review (one WP's slice), `accept`
    (readiness), `mission-review` (code-matches-spec fidelity).

---

## Why the two Codex passes aren't redundant with the built-in checks

The ○ checks are **narrow or self-referential**: `analyze` checks the artifacts against
each other; each per-WP review sees only its own slice; `mission-review` checks that the
code matches the spec. None of them is an *independent judgment looking at the whole.*

The ★ Codex passes are the only two points where an outside model evaluates the entire
design (before tasks) and the entire diff (before main).

### Codex review #1 vs. `/spec-kitty.analyze`

They look similar but are complementary, with only a thin overlap:

| | `/spec-kitty.analyze` (○) | Codex review #1 (★) |
|---|---|---|
| **Reviewer** | Same model that authored the artifacts (self-review) | Independent model (fresh eyes) |
| **Nature** | Consistency + coverage auditor: duplicates, leftover TODOs, terminology drift, requirements with no task, charter-MUST conflicts | Design critic: is this the right approach? what's conceptually missing? which assumption is shaky? |
| **Timing** | *After* tasks (needs `tasks.md` to check coverage) | *Before* tasks (fix design gaps before decomposition) |
| **Action** | Non-remediating (report only) | Review-and-fix |
| **Artifacts** | spec + plan + tasks | spec + plan + research + data-model |

The overlap (both can flag a gap or a risky assumption) is *worth* the redundancy: a
second **independent** model flagging the same gap is a far stronger signal than one model
flagging it twice. And each does something the other can't — `analyze` checks
requirement→task coverage (tasks don't exist yet for Codex #1); Codex #1 questions the
design itself (which self-review tends to accept as given).

### Codex review #2 vs. `spec-kitty-mission-review`

Same complementary pattern at the other end of the arc: `mission-review` verifies
spec→code *fidelity and coverage* (bookkeeping); Codex #2 hunts for actual *cross-WP bugs*
the per-WP reviews structurally couldn't see.

---

## Practical ordering

Let them run in their natural sequence rather than compete:

1. **Codex #1** (independent design critique) → fix the plan
2. `/spec-kitty.tasks` (decompose the improved plan)
3. **`/spec-kitty.analyze`** (mechanical consistency + coverage on the now-improved set) — gate
4. implement + per-WP reviews
5. merge to feature branch
6. **Codex #2** (independent whole-diff review) → fix in the feature branch
7. land on main → deploy

Both Codex passes are **review-and-fix, not advisory**, and are treated as standing steps
in the arc — not optional extras.

## Dispatch

Both Codex passes use the Codex CLI **sandboxed and read-only** — `--sandbox read-only`,
*not* `-p spec-kitty-review`. **Capture the FULL stdout to a log file — do NOT rely on
`-o` / `--output-last-message`.** On agentic
runs (Codex explores the tree with many tool calls before the synthesis) the last-message
capture comes back empty or truncated, which is the entire reason Codex has *looked*
unreliable as a reviewer (kentonium3/kg-automation#790). The full stdout is reliable; the
review synthesis is the block after the **last** line that is exactly `codex`, up to the
`tokens used` footer.

```bash
# Prompt via stdin; full stdout+stderr → a log; run in the background and poll
# byte-growth for liveness (never `| tail`, never `-o`). See the never-hide-codex SOP.
codex exec --sandbox read-only -C <worktree> --add-dir "$(pwd)" - < <prompt.md> \
  > <log.md> 2>&1 &
# Liveness: while <log.md> keeps growing, Codex is alive. If it stalls for a few minutes
# (no byte growth), it is wedged (usually stdin-wait) — kill and fix the invocation.
# When it exits, extract the synthesis: the text after the LAST `^codex$` line.
```

Never pass `-o` / `--output-last-message` (unreliable on agentic runs — read the full log
instead), and never pass `--full-auto` — it overrides `sandbox_mode` entirely (see the
`reference_codex_speckitty_profile` note / kentonium3/kg-automation#330).

**Why read-only rather than the `spec-kitty-review` profile.** That profile is a single
line — `sandbox_mode = "danger-full-access"` — and has nothing to do with review quality.
Its only purpose is to let Codex write `.git/spec-kitty-locks` and `~/.spec-kitty/` when
it must record a WP verdict *itself*. A review pass only reads and emits findings, so
granting it write access to `.git/` is strictly worse than not granting it. Prefer
removing even the verdict-recording need: have the orchestrator record the verdict through
the deterministic seam (`spk-run-verdict-capture` → `spec-kitty agent tasks move-task`),
leaving Codex purely advisory.

Verified 2026-07-18 that the *invocation* works and that only the output-capture pattern
was ever at fault (#790) — that finding stands and is why full-stdout capture is
mandatory. Re-verified 2026-09-19-20 on the #989 arc: four consecutive review passes run
with `codex exec --sandbox read-only` and the prompt piped via stdin returned clean
synthesis every time, finding real defects each round. Read-only costs nothing in review
quality.

**Opus fallback.** If Codex hits its usage/rate limit, switch that review function to an
independent Opus reviewer (e.g. `reviewer-renata`) with the same adversarial prompt on the
same artifacts, and fix its findings the same way. Codex stays the default; Opus is the
automatic fallback, so the review discipline is never dropped just because Codex is out of
hours.

**Prompt wording for guard / scanner / isolation / determinism reviews (added 2026-09-25,
team-lead ruling on the #849 arms-run WP04 cycle).** State the PROPERTY to confirm and the
inputs or seeds to confirm it under; never ask Codex to find a way past the guard. On
2026-09-25 a review of a static scanner phrased as "find a path that yields X without passing
the check" was aborted by OpenAI's content classifier (`ERROR: This content was flagged for
possible cybersecurity risk …`, exit 0, no verdict); the identical checklist phrased as
"confirm the classification is identical under both seeds" completed normally. If a prompt is
flagged anyway, rephrase ONCE with the checklist intact; if the second run is flagged, that
review function falls back to the independent (non-implementing) Claude reviewer and the
fallback is recorded in the WP's review artifact — same rule as rate-limit exhaustion. Detect
a real abort by the line `^ERROR: This content was flagged` — the phrase alone also appears in
review artifacts Codex may read. Under `--sandbox read-only`, tests that bind sockets or spawn
children fail with `PermissionError`; that is environment, not a finding — judge by Codex's
direct probes.
