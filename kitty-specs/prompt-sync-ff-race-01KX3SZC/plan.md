# Implementation Plan: Prompt-sync FETCH_HEAD race fix

**Branch**: `fix/prompt-sync-ff-race` | **Date**: 2026-07-09 | **Spec**: [spec.md](./spec.md)
**Input**: Feature specification from `kitty-specs/prompt-sync-ff-race-01KX3SZC/spec.md`
**Mission**: `prompt-sync-ff-race-01KX3SZC` | **Issue**: kentonium3/kg-automation#667

## Summary

Two office2 deploy actors — `agent-prompt-sync`
(`scripts/openclaw/deploy/deploy_agent_prompts.py`) and `felix-deployer`
(`scripts/deploy/felix-deployer/_tick.py`) — run concurrent `git` fetch/pull on
the **same** `/home/claude/kg-automation` checkout on overlapping ~5-minute
timers. Their fetches clobber the single shared `.git/FETCH_HEAD`, so
`git pull --ff-only` intermittently sees multiple for-merge heads and dies
`Cannot fast-forward to multiple branches`, silently blocking prompt deploys.

**Technical approach:** replace each actor's `FETCH_HEAD`-dependent pull with a
race-immune advance — `git fetch` (updates the *atomic* remote-tracking ref
`refs/remotes/origin/main` under git's own ref lockfile) followed by
`git merge --ff-only origin/main` (merges the **ref**, never `FETCH_HEAD`) —
provided by a single shared library primitive both actors call. Wrap each
actor's git-and-working-tree critical section in a shared advisory file lock so
their working-tree mutations cannot interleave. Delete the stale origin lane
branch that amplifies the bare-fetch surface. Add a behind-N-ticks health signal
(reusing the ntfy pattern) so a silent multi-week stall becomes impossible, and
make a genuine divergence fail loudly with the observed ref state.

## Technical Context

**Language/Version**: Python 3.12 (office2 is python3-only; helpers import `scripts.*` and must be invoked `python3 -m scripts.<pkg>.<mod>`)
**Primary Dependencies**: standard library only — `subprocess` (git), `fcntl` (advisory lock), `json` (JSONL logs); existing in-repo `scripts/deploy/felix-deployer/notify.py` (ntfy) reused for alerts
**Storage**: git checkout state at `/home/claude/kg-automation`; JSONL logs (`/data/services/openclaw/deploy/agent-prompt-sync.jsonl`, felix-deployer `/data/services/felix-deployer/logs/<date>.jsonl`); a small JSON health watermark for consecutive-behind/fail tracking; a well-known advisory lock file shared by both actors
**Testing**: pytest with subprocess-mocked git (both actors already mock `git` via a thin `_git`/`git_pull` seam); concurrency test forces overlapping advance calls against a real temp git repo to assert 0 "multiple branches" failures (NFR-001)
**Target Platform**: Linux (Ubuntu 24.04, office2), systemd user timers, run as the `claude` user (no sudo)
**Project Type**: single project — Python helper scripts + shared library under `scripts/`
**Performance Goals**: lock acquisition adds ≤5 s per tick; behind-N alert fires within one tick interval (≤5 min) of crossing threshold (NFR-002/003)
**Constraints**: Tier 1 (deploy fabric) — verify prompt-deploy connectivity before/after; `scripts/deploy/**` is an audited surface → rebaseline on deploy; no OpenClaw config or agent-prompt content changes (locality); separate checkouts (#636) out of scope
**Scale/Scope**: 2 deploy actors, 1 shared checkout, ~5-min cadence; ~2 modified scripts + 1–2 new shared-lib modules + tests + 1 deploy manifest

## Charter Check

*GATE: Must pass before Phase 0 research. Re-check after Phase 1 design.*

Charter mode: compact (`software-dev-default`). Relevant directives and how this plan satisfies them:

- **DIRECTIVE_024 (Locality of Change)** — changes confined to the two deploy actors + shared `scripts/deploy/lib/`; no OpenClaw/prompt/config surface touched. ✅
- **DIRECTIVE_001 (Architectural Integrity)** — the race-immune advance + lock live behind one library seam reused by both actors; no duplicated git logic. ✅
- **DIRECTIVE_003 (Decision Documentation)** — design decisions D1–D6 recorded in [research.md](./research.md). ✅
- **DIRECTIVE_010 (Specification Fidelity)** — each FR/NFR maps to a concern below and a success criterion. ✅
- **Engineering Principles (repo):** deterministic plumbing (git advance, lock) pushed into a tested library primitive; the actors keep only orchestration. Idempotency: an advance that is already current is a clean no-op. Observability-per-feature: behind-N health signal + fail-loud ref-state logging. ✅
- **Change-risk taxonomy:** Tier 1 (deploy fabric) — pre/post connectivity verification required (quickstart). Audited-surface rebaseline obligation acknowledged. ✅

No charter violations. Complexity Tracking not required.

## Project Structure

### Documentation (this mission)

```
kitty-specs/prompt-sync-ff-race-01KX3SZC/
├── plan.md              # This file
├── research.md          # Phase 0 output — design decisions D1–D6
├── data-model.md        # Phase 1 output — entities & state
├── quickstart.md        # Phase 1 output — deploy/verify/rollback
├── contracts/           # Phase 1 output — shared-lib API + log schemas
└── tasks.md             # Phase 2 (/spec-kitty.tasks — NOT created here)
```

### Source Code (repository root)

```
scripts/deploy/lib/
├── gitsync.py           # NEW — race-immune advance_checkout(); AdvanceResult
├── deploylock.py        # NEW — advisory flock context manager (shared path)
└── health.py            # NEW — consecutive-behind/fail watermark + should_alert()

scripts/deploy/felix-deployer/
└── _tick.py             # MODIFY — replace bare `git pull --ff-only` with advance_checkout() under the lock; wire behind-N health

scripts/openclaw/deploy/
└── deploy_agent_prompts.py   # MODIFY — replace git_pull() internals with advance_checkout() under the lock; add ntfy + behind-N health

deploys/queued/
└── 00NN-prompt-sync-ff-race.yaml   # NEW — records the deploy + audited-surface rebaseline

tests/
├── deploy/lib/test_gitsync.py        # NEW — incl. concurrency test (NFR-001)
├── deploy/lib/test_deploylock.py     # NEW
├── deploy/lib/test_health.py         # NEW
├── deploy/felix-deployer/…           # UPDATE tick tests
└── openclaw/deploy/…                 # UPDATE prompt-sync tests
```

**Structure Decision**: Single project. The deterministic git-advance, lock, and
health primitives become tested modules under the existing shared
`scripts/deploy/lib/` (already home to apply/cron/manifest/snapshot/tier/verify).
Both actors import them via `python3 -m scripts.*` module form. This satisfies
FR-006 (one primitive, no duplication) and keeps the actor scripts thin.

## Implementation Concern Map

> Concerns, not work packages. `/spec-kitty.tasks` maps these to WPs.

### IC-01 — Race-immune git advance primitive

- **Purpose**: Provide one `advance_checkout()` that fast-forwards the shared checkout via the atomic `origin/main` ref (never `FETCH_HEAD`), returning pre/post HEAD, behind-count, and a `diverged` flag.
- **Relevant requirements**: FR-001, FR-005, FR-006, NFR-001, NFR-004.
- **Affected surfaces**: `scripts/deploy/lib/gitsync.py` (new) + tests.
- **Sequencing/depends-on**: none (foundation).
- **Risks**: `git fetch origin main` must reliably update `refs/remotes/origin/main` (it does, via the configured `+refs/heads/*:refs/remotes/origin/*` refspec) — cover in tests; distinguish ff-failure-from-divergence vs transient.

### IC-02 — Shared advisory lock

- **Purpose**: Mutually exclude the two actors' git/working-tree critical sections via a well-known advisory file lock (`fcntl.flock`), with bounded wait then defer-to-next-tick.
- **Relevant requirements**: FR-002, NFR-002.
- **Affected surfaces**: `scripts/deploy/lib/deploylock.py` (new) + tests.
- **Sequencing/depends-on**: none (foundation, parallel to IC-01).
- **Risks**: lock-file path must be identical for both actors and writable by `claude`; a stale lock must never permanently wedge a tick (use bounded non-blocking acquire).

### IC-03 — Behind-N health signal + fail-loud

- **Purpose**: Track consecutive behind/failed advances in a JSON watermark; when the count crosses N, emit an operator ntfy alert; on true divergence, log the observed ref state and alert.
- **Relevant requirements**: FR-004, FR-005, NFR-003, NFR-004.
- **Affected surfaces**: `scripts/deploy/lib/health.py` (new) + tests; reuses felix-deployer `notify.py`.
- **Sequencing/depends-on**: consumes IC-01's `AdvanceResult`.
- **Risks**: don't double-alert every tick (alert on threshold crossing, then throttle); prompt-sync has no ntfy today — wire the shared notifier.

### IC-04 — Actor integration (both deploy paths)

- **Purpose**: Replace `felix-deployer` `_tick.py` bare pull and `prompt-sync` `git_pull()` internals with `advance_checkout()` under the shared lock + health wiring, preserving each actor's existing contracts (felix-deployer's `pre_pull_head`/`post_pull_head` for rebaseline; prompt-sync's `GitPullResult` + JSONL audit records).
- **Relevant requirements**: FR-001, FR-002, FR-004, FR-005.
- **Affected surfaces**: `scripts/deploy/felix-deployer/_tick.py`, `scripts/openclaw/deploy/deploy_agent_prompts.py` + their tests.
- **Sequencing/depends-on**: IC-01, IC-02, IC-03.
- **Risks**: must not regress felix-deployer's rebaseline range computation (it relies on pre/post HEAD across the advance) or prompt-sync's audit-log contract; keep the git seam mockable.

### IC-05 — Stale lane-branch cleanup + deploy/rebaseline

- **Purpose**: Delete the orphan `kitty/…-lane-a` origin branch; author the `deploys/queued/` manifest that records the deploy and drives the audited-surface rebaseline; document the spec-kitty lane-cleanup gap.
- **Relevant requirements**: FR-003, C-002, C-003, C-005.
- **Affected surfaces**: origin (branch delete), `deploys/queued/00NN-prompt-sync-ff-race.yaml` (new), quickstart deploy steps.
- **Sequencing/depends-on**: IC-04 (code merged) before deploy; branch delete can happen independently.
- **Risks**: confirm no active mission uses that lane branch (verified: it's from a mission merged ~2026-06-16); rebaseline must confirm drift is expected-only before resetting baselines.
