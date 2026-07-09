# Prompt-sync FETCH_HEAD race fix

**Mission**: `prompt-sync-ff-race-01KX3SZC`
**Type**: software-dev (bug fix)
**Source**: kentonium3/kg-automation#667
**Purpose (TL;DR)**: Stop the office2 prompt-sync deploy path from silently failing under a git concurrency race.

## Purpose & Context

Agent prompt changes reach office2 through a timer (`agent-prompt-sync`) that
git-pulls a shared checkout. A second deploy actor (`felix-deployer`) pulls the
**same** checkout on an overlapping timer. Both write the single shared
`.git/FETCH_HEAD`; when their fetch/merge windows overlap, `git pull --ff-only`
sees multiple for-merge heads and dies `Cannot fast-forward to multiple
branches`. The result: merged prompt changes intermittently never reach the
running Felix agents, and the failure is silent (2319+ failures over ~4 weeks,
onset 2026-06-12; observed 28 commits behind origin during the #662 deploy).

The fix makes both actors' fast-forward merges independent of the mutable shared
`FETCH_HEAD`, serializes their working-tree mutation, removes the stale lane
branch that amplifies the race, and adds a health signal so a silent multi-week
stall becomes impossible. Separating the two actors into distinct checkouts
(#636) is the deeper architectural fix and is explicitly **out of scope** here.

## User Scenarios & Testing

### Primary scenario (happy path)
A prompt change is merged to `main`. The prompt-sync tick fetches and
fast-forwards the office2 checkout and copies the updated prompt to the running
agent — **even though** the felix-deployer tick is fetching/pulling the same
checkout at the same time. The change reaches the agents within one sync
interval, with no `Cannot fast-forward to multiple branches` failure.

### Exception scenario (true divergence)
The office2 checkout holds a local commit not present on origin (real
divergence, not a race artifact). The actor cannot fast-forward. It **fails
loudly** — records the exact observed ref state (local HEAD, `origin/main`) and
raises the behind/diverged health signal — rather than silently logging a
generic error and no-op looping.

### Edge cases
- **Stale/extra origin branches**: additional `kitty/*` lane branches on origin
  no longer cause an actor's fetch to pull multiple for-merge heads into the
  merge decision.
- **Concurrent ticks with no new commits**: overlapping ticks when the checkout
  is already current complete as clean no-ops (no failure, no spurious alert).
- **Lock held by the other actor**: an actor that cannot immediately acquire the
  shared lock waits or defers to its next tick without corrupting state or
  double-mutating the working tree.

## Requirements

### Functional Requirements

| ID | Requirement | Status |
|----|-------------|--------|
| FR-001 | Both deploy actors (agent-prompt-sync and felix-deployer) MUST advance the shared checkout to origin's latest commit using the atomic remote-tracking ref (`origin/main`) as the merge target, not the mutable shared `.git/FETCH_HEAD`. | Draft |
| FR-002 | The two actors' git-and-working-tree critical sections MUST be mutually excluded (a shared advisory lock) so their working-tree mutations cannot interleave on the shared checkout. | Draft |
| FR-003 | The stale origin lane branch `kitty/mission-trustworthy-weekly-habit-report-01KV4GZ7-lane-a` MUST be removed, leaving no orphaned mission lane branches on origin. | Draft |
| FR-004 | When either actor falls more than a configured number of consecutive ticks behind origin, an operator-visible health signal MUST be emitted. | Draft |
| FR-005 | When an actor genuinely cannot fast-forward (true divergence), it MUST fail loudly with a diagnostic capturing the observed ref state, rather than silently no-op looping. | Draft |
| FR-006 | The race-immune advance logic and the shared lock MUST be provided as a shared library primitive reused by both actors, not duplicated per script. | Draft |

### Non-Functional Requirements

| ID | Requirement | Threshold | Status |
|----|-------------|-----------|--------|
| NFR-001 | Concurrency correctness | Across ≥100 deliberately-overlapped tick pairs in test, 0 occurrences of `Cannot fast-forward to multiple branches` and 0 corrupted working trees. | Draft |
| NFR-002 | Lock-induced latency bound | Shared-lock acquisition adds ≤ 5 s to a tick; a lock-blocked actor never blocks longer than one tick interval (≤ 5 min) before deferring. | Draft |
| NFR-003 | Health-signal latency | The behind-N health signal fires within one tick interval (≤ 5 min) of crossing the configured threshold. | Draft |
| NFR-004 | Observability of failure | Every failed advance records the exact observed ref state (local HEAD short-sha + `origin/main` short-sha) in its structured log line. | Draft |

### Constraints

| ID | Constraint | Status |
|----|-----------|--------|
| C-001 | Changes are confined to `scripts/openclaw/deploy/`, `scripts/deploy/felix-deployer/`, the shared `scripts/deploy/lib/`, and their tests. No OpenClaw config or agent-prompt content changes. (Locality of change) | Draft |
| C-002 | `scripts/deploy/**` is an audited surface — deploying this change triggers the rebaseline obligation. | Draft |
| C-003 | The felix-deployer change MUST deploy via the manifest pipeline (`deploys/queued/<name>.yaml`) per deploy discipline; the prompt-sync change auto-syncs on merge to main. | Draft |
| C-004 | Giving the two actors separate checkouts (#636) is out of scope; this mission converges the shared-checkout path only. | Draft |
| C-005 | Tier 1 change (connectivity/deploy fabric): connectivity of the prompt deploy path MUST be verified before and after deploy. | Draft |

## Success Criteria

- **SC-001**: Over a 48-hour post-deploy observation window, zero new
  `git_pull_failed` "Cannot fast-forward to multiple branches" entries appear in
  the prompt-sync log.
- **SC-002**: A prompt change merged to main is confirmed, end-to-end, to reach
  the running office2 agents within one sync interval.
- **SC-003**: A simulated multi-tick fall-behind produces an operator-visible
  alert within one tick interval.
- **SC-004**: The office2 checkout stays current with origin/main across the
  observation window with no manual `git` intervention.

## Key Entities

- **Shared checkout** — the single office2 working copy (`/home/claude/kg-automation`) both actors operate on.
- **Deploy actors** — the `agent-prompt-sync` timer and the `felix-deployer` timer, each on a ~5-minute cadence.
- **Merge target** — the atomic remote-tracking ref `origin/main` (replaces reliance on the shared mutable `.git/FETCH_HEAD`).
- **Shared advisory lock** — the mutual-exclusion primitive guarding the git/working-tree critical section.
- **Behind-N watermark / health signal** — the operator-visible indicator that a deploy actor has stalled.

## Assumptions

- felix-deployer and agent-prompt-sync continue to share the `/home/claude/kg-automation` checkout for the lifetime of this mission (separate-checkout restructuring is deferred to #636).
- The office2 checkout tracks `origin/main` on `branch.main` with the standard `+refs/heads/*:refs/remotes/origin/*` fetch refspec.
- An advisory file lock (flock-style) is available and honored by both actor processes running as the `claude` user.

## Out of Scope

- Separate checkouts per deploy actor (#636).
- Any change to OpenClaw agent prompts, agent models, or `openclaw.json`.
- Fixing spec-kitty's lane-branch cleanup at merge (noted as a related upstream/tooling gap; this mission only deletes the existing orphan).
