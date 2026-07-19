---
id: spec-kitty-workflow-fault-protocol
doc_type: runbook
title: Spec-Kitty Workflow-Fault Detour Protocol
status: active
level: reference
owners: [kent]
last_validated: 2026-07-18
version: 1.0.0
---

# Spec-Kitty Workflow-Fault Detour Protocol

**What this is.** The single, canonical response to an unexpected spec-kitty (or
sibling-tooling) **workflow fault** hit while running a mission — the sequence
Kent has dictated ad-hoc dozens of times. Canonized here (issue #795) so the
detour runs **autonomously** without re-instruction, stopping only where Kent's
judgment is genuinely required.

**When it triggers.** ANY unexpected spec-kitty workflow condition during a
mission: missing/inconsistent state; authority confusion (which checkout/branch/
actor owns a step); source/location errors; ambiguous direction forcing retries;
permissions issues; unexpected git conditions (branch/worktree/index/stale); a
command that fails/blocks/produces unexpected output; a gate that won't pass.
(Same trigger set as the "Stop-and-capture" standing rule — this protocol is
*how* you respond to it in the named repo set.)

**Where it applies (the named repo set).** `kg-automation`, `spec-kitty`,
`spec-kitty-analyzer`, `spec-kitty-saas`, `spec-kitty-telescope`, `vikunja-harness`
— the spec-kitty mission-running repos + the Vikunja harness. Outside this set,
the general **stop-and-surface** rule applies (stop, capture, ask Kent).

## Autonomy contract

Run the steps below **autonomously**. The evidence-preservation duty is
**unchanged** — it is met by the diagnose+track steps (1–3), *not* by halting.
The **only** stops are:

- **[STOP-A]** before posting ANY upstream comment/draft — Kent reviews the exact copy.
- **[STOP-B]** when there is **no pre-known workaround** — present continue-vs-abandon.

Everything else proceeds without asking "how should I proceed."

> **Guardrail — what "pre-known workaround" means.** A workaround is *pre-known*
> only if it is **documented**: in the Known-Workarounds Registry below, in a
> tracked issue (kg-automation or upstream), in an upstream issue/PR, or in
> project memory. **If a workaround must be improvised, it is NOT pre-known** —
> applying an improvised workaround is a *silent workaround* and is prohibited
> (it destroys the evidence that is the only way the tooling gets better). An
> improvised-only situation is a **[STOP-B]**.

## The protocol

### 1. Stop the failing action and fully diagnose the root cause
While the evidence exists and context is fresh. Capture the exact command +
error, the state (git/worktree/event-log/status), and read the tooling source if
needed. **No band-aid before the cause is understood.** Note the spec-kitty build
(SHA / version — see `reference_speckitty_version_history`) so recurrence can be
pinned to a build.

### 2. Local tracking issue (kg-automation)
- **Exists** → add a comment noting the **recurrence on the current build**; if
  it recurs on a *newer* build than the issue was filed against, note the
  **persistence on the newer build**.
- **None** → **create one** per the dual-track runbook
  [`spec-kitty-bug-reporting.md`](spec-kitty-bug-reporting.md) (internal template
  `.github/ISSUE_TEMPLATE/spec-kitty-bug.md`; Directive-8 symptom/observer/cost).
- Internal kg-automation posts need **no** pre-review (repo-scoped exception).

### 3. Upstream check (Priivacy-ai/spec-kitty or the sibling upstream)
Search for an existing report — ours **or** someone else's.
- **Exists** → add a comment confirming **recurrence on the same build** or
  **persistence on a newer build** (compare the build it was reported against to
  ours). **If the upstream issue is CLOSED**, `@mention` **that program/repo's
  current maintainer** as a safety check / reopen request — **do NOT hardcode a
  name**: ownership is per-program and evolving (spec-kitty-CLI, spec-kitty-SaaS,
  spec-kitty-analyzer + spec-kitty-telescope [Kent], and Vikunja are separately
  owned). Resolve the owner from the repo's `CODEOWNERS` / the issue's author or
  assignee; if it's unclear, surface that to Kent rather than guessing. The
  `@mention` is part of the upstream copy Kent signs off at [STOP-A].
  **[STOP-A: show Kent the exact comment copy before posting.]**
- **None** → prep the upstream copy as an **embed in the local tracking issue**
  per `spec-kitty-bug-reporting.md` (external template; 4-backtick fence; drop any
  "Suggested Fix"). **[STOP-A: Kent reviews the copy before it is filed.]**

*(Upstream etiquette is unchanged: high-diligence pristine repro before any
upstream claim; per-action copy sign-off; no `@mentions` of outsiders in local
tracking.)*

### 4. Apply the known workaround
If a workaround is **pre-known** (per the guardrail) → **apply it and continue
the mission.** Record what was applied (in the local issue comment / commit / the
mission's running report).

### 5. No known workaround
**[STOP-B]** Present Kent the options: **continue** the mission with a scoped
manual step, or **abandon** the mission. Include the diagnosis + why no workaround
is known.

---

## Known-Workarounds Registry

The concrete list that makes step 4 autonomous. Add to it whenever a new fault's
workaround is confirmed. (Each row: fault → pre-known workaround → tracking.)

| Workflow fault (symptom) | Pre-known workaround | Tracking |
|---|---|---|
| `move-task … --to <lane>` fails `Illegal transition: <from> -> <to>` when run from **inside a lane worktree** (status board shows the correct lane) | Run the `move-task` transition from the **primary checkout** (orchestrator owns transitions; subagents own implement/review). `--force` from the worktree also completes it. | kg #710; upstream #2647 (closed→regressed on 3.2.6), #2534-adjacent |
| Pre-review gate prints `gate authorities unavailable … tests.architectural._gate_coverage not importable` | **Non-blocking warn** — ignore it (consumer repos lack that spec-kitty-internal module; `review.fail_on_pre_review_regression` defaults False). Not the hard failure. | kg #710; upstream #2534 |
| `move-task … --to approved` fails: `WP has a rejected review artifact (review-cycle-1.md)` after a genuine later-cycle APPROVE | `move-task … --to approved --skip-review-artifact-check --note "<arbiter override rationale>"` | kg #574; upstream #1817 |
| **Merge** gate refuses an approved WP due to a prior `verdict:rejected` review-cycle artifact | Cycle-N+1 no-op marker commit (see `reference_speckitty_issue_1817`) | kg #574; upstream #1817 |
| Coord/flatten friction (split-authority: primary vs coord vs lane) on a `--pr-bound` mission | **Prevention:** pre-cut `feat/<slug>` off main + `mission create` **without** `--pr-bound` → `single_branch`. If already stuck: flatten per the coord-flatten runbook. | kg #731; upstream #2533/#2549; `reference_speckitty_coord_flatten_workaround` |
| Dashboard `/api/kanban` shows stale state during coord missions | Use `spec-kitty agent tasks status` instead of the dashboard scanner | kg #577; upstream #1824; `reference_speckitty_dashboard_scanner_bug` |
| Codex reviewer "hangs" / empty output | Not a Codex bug — never `-o`/`--output-last-message`; stream full stdout to a file, poll byte-growth, stdin `-` form, self-kill watchdog; extract synthesis after the last `^codex$` line. On genuine usage-exhaustion → reviewer-renata (Opus). | `feedback_never_hide_codex_activity`; runbook `spec-kitty-review-cycle.md` |
| Codex usage/rate-limit exhausted at a mandatory checkpoint | Switch that review function to an **Opus reviewer** (reviewer-renata) with the same adversarial prompt on the same artifacts/diff. | `feedback_speckitty_codex_review_checkpoints` |
| Acceptance-matrix / issue-matrix verdict `pending` blocks `accept`/approve | Fill the matrix verdicts (issue-matrix: `fixed`/`verified-already-fixed`/`deferred-with-followup`/`in-mission`; acceptance-matrix: per-FR pass + evidence). Expected authoring step, not a fault. | `reference_speckitty_324_arc_gotchas` |

## Cross-references
- Dual-track filing mechanics: [`spec-kitty-bug-reporting.md`](spec-kitty-bug-reporting.md).
- The always-on directive that invokes this runbook: `.agents/rules/cross-repo-standing-rules.md` → "Spec-kitty workflow-fault detour protocol".
- Reconciled with (narrows, for the named set): the "Stop-and-capture on unexpected spec-kitty behavior" standing rule.
- Build comparison for recurrence notes: `reference_speckitty_version_history` (project memory).
