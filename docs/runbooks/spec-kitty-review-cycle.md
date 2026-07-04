---
id: spec-kitty-review-cycle
doc_type: runbook
title: Spec-Kitty Mission Review Cycle
status: approved
level: reference
owners: [kgale]
audience: agents_and_humans
last_updated: '2026-07-04'
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

Both Codex passes use the Codex CLI with the `spec-kitty-review` profile:

```bash
codex exec -p spec-kitty-review -C <worktree> --add-dir "$(pwd)" -o <result.md> - < <prompt.md>
```

Never pass `--full-auto` — it overrides the profile's `sandbox_mode` and breaks `.git/`
writes (see the `reference_codex_speckitty_profile` note / kentonium3/kg-automation#330).
