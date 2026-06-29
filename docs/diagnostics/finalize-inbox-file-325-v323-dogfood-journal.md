# Dogfood journal — mission for #325 on spec-kitty **3.2.3 @ git `7530597a`**

Third full attempt at a spec-kitty mission for issue #325
(`scripts/inbox/finalize_inbox_file.py`). Prior attempts:

- **2026-06-20, 3.2.1** — PAUSED at create→plan split-authority topology
  (upstream #1716 write-side + #2046 read-side). Journal:
  `finalize-inbox-file-01KVKG4S-dogfood-journal.md`.
- **2026-06-24, 3.2.2** — PAUSED one phase later at `finalize-tasks`
  (tasks-phase resolver split). Journal:
  `finalize-inbox-file-325-v322-dogfood-journal.md`. Then a release re-run
  reached `implement` and re-blocked at the planning→implement handoff
  (coord worktree empty); mission torn down.
- **2026-06-28 (this run)** — re-specified **fresh** on the latest `main` build
  with the **corrected in-place design** (#325 body rewritten: finalize in place,
  no `mv`, 7-day retention owned by `prescan.py`). The earlier attempts specced a
  `mv` to `02-Inbox-Processed/` that contradicted the retention invariant; that
  mission was abandoned 2026-06-28 on the design defect (not a tool failure).

## Why this run is instrumented three ways

Per Kent's direction, this mission is captured by three independent artifacts so
we can cross-check the narrative against the machine record:

1. **This narrative journal** — reconstructed event-by-event timeline (the past
   pattern).
2. **#2095 tracer files** — three *live-captured* companion logs under
   `kitty-specs/<mission>/traces/` (`tooling-friction-trace.md`,
   `approach-trace.md`, `design-trace.md`), seeded at planning and appended
   through implement. The retrospective generator **ingests** these
   automatically at close (FR-007, shipped in this build).
3. **spec-kitty-analyzer Customer Experience Report** — at close, run the
   analyzer (PR #9 build, `fix/failure-scan-channel-scoping` — channel-scoped
   failure detection) on this mission's own event log, then author a CX report
   modeled on `customer-experience-one-mission-3.2.3.md`.

- **Issue**: kentonium3/kg-automation#325 (P1-feature, `area/felix-core`, `spec: ready`)
- **Spec-kitty build**: version string `3.2.3`; **actual build = `git+…/spec-kitty.git@main` @ commit `7530597a`** (verified == upstream `main` HEAD, 2026-06-28 15:17 +0200, *"test(next): accept docs/adr/ in implement-prompt adr_pointer surface"*). The version string is **not granular enough** to express which from-`main` build is installed — pin by commit, not version.
- **Started**: 2026-06-28
- **Posture**: drive clean, no hand-cranking; STOP + capture on any genuine tool
  failure (a workaround destroys the capture signal).
- **Branch**: `feat/finalize-inbox-file-v2` (the prior `feat/finalize-inbox-file`
  is retained as the abandoned-mission evidence archive — no collision).
- **Mission handle**: _(minted at specify — recorded below)_

---

## Pre-flight state (2026-06-28, before specify)

- Repo: `kentonium3/kg-automation`, on `main`, working tree clean. `main` is 2
  commits ahead of `origin/main` (unpushed: 3.2.2→3.2.3 project upgrade + doctrine
  refresh). No active worktrees beyond root. No leftover `finalize-inbox`
  kitty-specs dir (prior teardown clean).
- Build verification: installed pipx commit `7530597a` == `git ls-remote … main`
  HEAD. We are on latest `main` — not behind. The local `~/repos/spec-kitty` clone
  is parked on contributor branch `feat/mission-cancel-cli` (`main` +1 unmerged
  commit `695d434b0` = the `mission cancel` feature), so source greps use the
  installed package or `git show 7530597a:` to avoid the +1 skew.

### Pre-flight friction observations (transcribed to tracers post-create)

- **F1 — version-string non-granularity.** `spec-kitty upgrade --agent-check
  --json` → `installed=3.2.3, latest=3.2.2 (pypi), action=none, reason=up_to_date`.
  The comparator reports the *latest PyPI tag* (3.2.2) as below our from-`main`
  install (3.2.3) and correctly says "up_to_date", but the version string cannot
  tell an operator *which* main build is present or what fixes it carries. Pin by
  commit. (Upstream-relevant tooling friction.)
- **F2 — tracer scaffolding gap (#2095).** The retrospective generator *ingests*
  `traces/*.md` (FR-007, shipped), but nothing *scaffolds or seeds* them and there
  is no `traces` CLI. The operator must hand-author the three files at the exact
  `kitty-specs/<mission>/traces/` path with the documented disposition-keyword
  entry format, or ingestion silently finds nothing. Candidate for auto-scaffold
  at `mission create` (the #2095 "if ROI positive" goal).
- **A1 (approach, positive).** `spec-kitty agent mission branch-context --json`
  was clean and deterministic — correctly flagged `current_is_primary=true` on
  `main` and recommended the feature-branch strategy with a clear reason. No git
  probing needed.

---

## Timeline

### Specify

**Startup Upgrade Check** → `action=none, up_to_date` (see F1).

**Branch-context helper** (`branch-context --json --target-branch feat/finalize-inbox-file-v2`):
`current_branch=main`, `current_is_primary=true`, `recommended_strategy=feature-branch`,
target/base/merge all `feat/finalize-inbox-file-v2`. Clean — no git probing (A1).

**Charter context** (`charter context --action specify --json`): `mode=compact`,
template `software-dev-default`, directives 001/003/010/024/031/033/034. Note a
pre-existing charter diagnostic (carried, not introduced by us): "Charter declared
additional tool(s) beyond the runtime registry: pytest, python" — the known
tool-registry vs DEFAULT_TOOL_REGISTRY mismatch.

**Brief detection:** no `.kittify/mission-brief.md` / `ticket-context.md`. The #325
issue body is the input (per the "issue is input, not the spec" rule).

**Discovery — two pre-identified design forks resolved (Kent, live):**
1. **Helper scope → FOLD into `mark_processed.py`.** No new `finalize_inbox_file.py`.
   `mark_processed.py` already does the atomic idempotent in-place `status: processed`
   write; we extend it with the orchestrator-facing `0/1/2` exit-code contract +
   single-line JSON stdout + detectability, and repoint Step-5 at it. **Deviation
   from the issue's literal "add finalize_inbox_file.py" title — recorded in spec.md
   per DIRECTIVE_010 (Specification Fidelity).**
2. **Detectability → status write + exit code is sufficient.** No separate finalize
   audit line (the move-era `02-Inbox-Processed/` per-file log signal is gone under
   no-move). prescan reads the atomic `status: processed`; orchestrator reads the
   non-zero exit.

These answers materially **shrink** the mission (the redesign memo predicted this:
"the mission may be much smaller than it looked"). Net scope: harden
`mark_processed.py` (atomicity already present; add exit-code contract + JSON stdout
+ error surfacing) + tests + Step-5 standing-orders cutover. **Not a bulk edit.**
Mission type: **software-dev**.

**Mission created** — `finalize-inbox-file-01KW8MSQ` (mid8 `01KW8MSQ`, ULID
`01KW8MSQ183M0QQWT5J2P55TRF`), `mission_type=software-dev`, `topology=coord`,
coordination branch `kitty/mission-finalize-inbox-file-01KW8MSQ`, on
`feat/finalize-inbox-file-v2`. spec.md scaffold written untracked (commit boundary
= mine).

**Tracers seeded** at `kitty-specs/finalize-inbox-file-01KW8MSQ/traces/`
(tooling-friction / approach / design), ingestion-shaped (bold-lead bullets +
disposition keywords) so the FR-007 retrospective ingestor auto-buckets them.

**Ground-truth finding (sharpened the spec).** The #325 body is **stale** on its
"replace the agent's fragile inline `Edit`" premise: `felix-admin-capture/AGENTS.md`
already (Jun 18) calls `python3 -m scripts.inbox.mark_processed --path <path>` at
Step 5c (line 125) and already carries the "do NOT delete; preserve in `01-Inbox/`"
invariant (line 113). `mark_processed.py` already does the atomic, mode-preserving,
idempotent in-place write with an existing **0/1/3** exit contract (3 = `_private/`
refusal). The genuine remaining gap: (1) a write `OSError` propagates as an
**uncaught traceback** — the literal 2026-05-18 silent-failure class is NOT closed;
(2) no JSON stdout success signal; (3) no inbox-root validation; (4) Step 5c defines
no exit-code handling. Recorded as spec A1/A2 fidelity notes (DIRECTIVE_010).

**Spec authored + committed.** 6 FR / 4 NFR / 4 C / SC-001..004; contract reconciled
to **0/1/2/3** (add unused exit 2 = fs-error; retain exit 3 = private). Architecture
Impact authored from `signal-to-doc-map.json` class `agent-prompt-changed` (doc
targets: service-inventory JSON+md, audited-surfaces, openclaw-agent-setup +
agent-prompt-sync-ops runbooks; rebaseline **not required** per gap #621). Quality
checklist passed iteration 1, no `[NEEDS CLARIFICATION]` markers.

**`spec-commit` → commit `b0bc1cb`, landed DIRECTLY on `feat/finalize-inbox-file-v2`**
(exactly the 5 authored files; no stray state). **This is the headline positive so
far:** starting the mission on a dedicated *unprotected* feature branch made
`spec-commit` commit directly, **sidestepping the protected-`main` coordination-
worktree materialization** whose read/write split paused all three prior attempts
(#1716/#2046/#2087/#2115 family). Watch whether this clean placement holds through
`tasks` → `implement` (the boundary where attempt-3 re-split).

### Plan

Charter context (plan): `mode=compact`, directives 001/003/010/024/031/033/034 +
project DIR-001..005. `context resolve --action plan` + `setup-plan` clean — entry
gate (spec committed+substantive) passed; first `setup-plan` correctly `blocked`
(plan.md Technical Context not yet substantive), expected. Branch contract restated:
all `feat/finalize-inbox-file-v2`, `branch_matches_target=True`.

Authored `plan.md` (Technical Context: Python 3.12/stdlib-only/pytest; Charter Check
PASS no violations; **Implementation Concern Map IC-01 helper hardening / IC-02
contract tests / IC-03 standing-orders cutover + doc updates**), `research.md`
(R-01 exit-code reconciliation 0/1/2/3 additive · R-02 OSError catch boundary ·
R-03 JSON stdout shape · R-04 inbox-root validation via `prescan.resolve_registry` ·
R-05 perm-denied test w/ root skip-guard), `data-model.md` (frontmatter + exit-code
+ stdout/stderr shapes + state transitions), `contracts/cli-contract.md` (the
orchestrator-facing 0/1/2/3 + Step-5c handling table), `quickstart.md`.

Second `setup-plan` → `phase_complete=True`, auto-committed `plan.md` (`b91349d6`).
Phase-1 artifacts committed via `spec-commit` (`5afb484`). **Still landing directly
on `feat` — no coord materialization through the entire plan phase.** Plan phase
hit its ⛔ MANDATORY STOP POINT cleanly (no tasks generated by the plan command).

**Phase scorecard so far (specify+plan): ZERO interventions, ZERO hand-cranking,
ZERO tool failures.** Markedly cleaner than attempts 1–3 (which had already paused
by this point). The single most important factor: starting on a dedicated
*unprotected* feature branch keeps every `spec-commit` direct, avoiding the
protected-`main` coordination read/write split. Open watch item: the tasks→implement
handoff, where attempt-3 re-split even after planning cohered.

### Tasks

`context resolve` + `check-prerequisites` clean (`branch_matches_target=True`,
`tasks_dir` resolved). Decomposed the IC map into **3 WPs**: WP01 harden
`mark_processed.py` + tests (lane-a, foundational, FR-001..004); WP02 Step 5c
cutover (lane-b, depends WP01, FR-005); WP03 architecture/doc updates (lane-c,
depends WP01, FR-006). Profiles pre-assigned: python-pedro / implementer-ivan /
curator-carla; impl agent `claude` / `claude-sonnet-4-6` (Codex reserved for the
adversarial review pass). `owned_files` non-overlapping; all `code_change`.

`map-requirements --batch` → **6/6 FRs mapped, `unmapped_functional: []`** (the exact
call that reported "all 14/10 FRs unmapped" in attempt 2). `finalize-tasks
--validate-only` → `validation_passed` (no cycles, no ownership conflicts).

🎯 **`finalize-tasks` (mutating) SUCCEEDED — commit `bbe12a6a`, lanes computed.**
This is the headline milestone: **all three prior attempts died at or before this
point** (attempt-1 create→plan #1716; attempt-2 `finalize-tasks` resolver split;
attempt-3 planning→implement handoff). v323 @ `7530597a` sailed through. Lanes:
`lane-a [WP01] pgroup0` → `lane-b [WP02] / lane-c [WP03] pgroup1` (parallel after
WP01) — exactly the designed fan-out; `collapse_report` shows 0 collapses (correct,
the WPs have distinct surfaces). Still committing directly to `feat`, **no coord
materialization through the entire planning arc**.

**Phase scorecard (specify→plan→tasks): ZERO interventions, ZERO hand-cranking,
ZERO tool failures, ZERO coord splits.** The single decisive factor remains the
unprotected feature-branch start.

### Implement

**Analysis gate** (`/spec-kitty.analyze`): `agent action implement WP01` correctly
gated on `analysis_report_required` (legit, not a block). Authored the
`analysis-findings/v1` carrier (2 LOW findings, verdict `ready`), `record-analysis`
→ `verdict: ready`. **Notably `record-analysis` did NOT trip the dirty-tree
preflight** (the example CX report's #2102 class) — `.worktrees/` is already
gitignored here (line 65) and the tree was clean. kg-automation is hardened against
that class.

**implement WP01 — no attempt-3 split.** First call hit the **auto-commit-disabled
gate** (commit planning artifacts first — a documented gate, tool printed the exact
remedy). Committed the residual workflow state → *"✓ Planning artifacts committed to
coordination branch"* (the #2106+ placement routing feat→coord on commit). Lane
worktree `.worktrees/…-lane-a` materialized cleanly, WP01→doing, claimed. **Crucially
implement FOUND the tasks** — not the attempt-3 "no tasks directory at empty coord
worktree" failure. The planning→implement handoff held.

**Implementation (python-pedro sub-agent, sonnet)** → commit `4fa8be6d`, 275 passed.
It also **caught a real bug in my WP01 prompt**: my perm-denied test used
`chmod(note, 0o444)`, but `os.replace` is governed by *parent-dir* write perms — so
the test would have falsely passed at exit 0. It used `chmod(parent, 0o555)` instead.
My orchestrator diff sanity-pass: judged clean (it was not — see below).

🎯 **MARQUEE RESULT — Codex adversarial review caught two HIGH bugs the implementer
AND my sanity pass both missed.** `codex exec -p spec-kitty-review` (sandbox_mode,
no --full-auto) on the WP01 diff, REPRODUCED both:
1. **HIGH** `inbox_root` not resolved before `is_relative_to` → false
   `outside_inbox_root` on `/var` vs `/private/var` (a legitimate in-inbox note exits
   1 instead of finalizing).
2. **HIGH** symlink note path passed raw to `mark_processed` → `os.replace` replaces
   the symlink, leaving the real target `unprocessed` **while exiting 0 + success
   JSON** — i.e. it re-introduced *the exact silent-failure class this WP exists to
   close*.
3. **MED** tests miss both. VERDICT: REQUEST-CHANGES. This is the live validation of
   the example CX report's thesis: independent (different-family) review catches what
   same-family review misses. Fixed in `c100acaa` (`inbox_root.resolve()`; pass
   canonical `candidate`) + 2 regression tests; 277 passed. **Codex re-review →
   APPROVE, no findings** (it even probed extra: private-path still exit-3 with a bad
   registry; a symlink pointing outside the inbox correctly rejected).

**Approve gate — #2115 coord/primary read-write split (worked around, operator-
directed).** `move-task WP01 --to approved` blocked: the gate reads `issue-matrix.md`
(populate-to-pass) from the **coord** branch, but my verdicts + the gate's own printed
`git commit` remedy land on **feat**. Following the tool literally can't clear it
(wrong side of the split) — the #2115/#2155/#1716 family, biting one phase earlier
than the example's `accept` variant. **Stopped + captured + surfaced to Kent**; Kent
directed the example's documented resolution (author the matrix in the coord
worktree). Also hit the matrix's `deferred-with-followup` validator (needs a `#NNN`
follow-up handle in evidence_ref) — added `Follow-up: #327 / #621`. **WP01 → approved.**

**Friction tally so far:** F1 version-string, F2 tracer-scaffold gap, F3 #2115
issue-matrix read-write split (the one real STOP point — operator-directed
workaround). Everything else was documented gates (analysis-required,
auto-commit-disabled, populate-to-pass) cleared by following the tool.

### Implement — WP02 + WP03 (parallel, depend on WP01)

_(in progress)_
