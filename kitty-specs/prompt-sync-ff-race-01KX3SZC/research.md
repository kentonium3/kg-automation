# Research — Prompt-sync FETCH_HEAD race fix

Phase 0 output. Resolves the design decisions behind [plan.md](./plan.md). No
`[NEEDS CLARIFICATION]` markers remain; all decisions have sensible, codebase-
grounded defaults (mission run under auto-drive).

## Root-cause evidence (confirmed live, 2026-07-09)

- `felix-deployer` `_tick.py:341` runs a **bare** `git pull --ff-only` (no
  refspec) from `WorkingDirectory=/home/claude/kg-automation`. A bare pull
  fetches *all* heads per `remote.origin.fetch = +refs/heads/*:refs/remotes/origin/*`
  — `main` **plus** the stale `kitty/…-lane-a` branch — into the shared
  `.git/FETCH_HEAD`.
- `agent-prompt-sync` `deploy_agent_prompts.py:214 git_pull()` runs
  `git fetch origin main` then `git pull --ff-only origin main` from the **same**
  checkout.
- Both systemd timers fire ~every 5 min (observed offsets ~2 min; fetch/merge
  windows overlap when there is real work). Concurrent writers to the single
  `.git/FETCH_HEAD` leave **multiple for-merge entries** → `git pull --ff-only`
  reads >1 merge head → `fatal: Cannot fast-forward to multiple branches`.
- Reproduction confirms it is **not** the git commands or repo config: the manual
  two-step succeeds cleanly (single-entry FETCH_HEAD) with no concurrent actor.
  2319 failures, onset 2026-06-12, ongoing.

## D1 — Race-immune advance: merge the ref, not FETCH_HEAD

- **Decision**: Both actors advance via `git fetch origin main` **then**
  `git merge --ff-only origin/main`. The merge target is the remote-tracking
  **ref** `refs/remotes/origin/main`, never `FETCH_HEAD`.
- **Rationale**: `git fetch` updates `refs/remotes/origin/main` under git's own
  per-ref lockfile (atomic); a concurrent fetch cannot leave that ref in a
  multi-head state. `git merge --ff-only <ref>` reads exactly one commit. The
  only shared mutable file that caused the bug (`FETCH_HEAD`) is no longer on the
  merge path, so the race is structurally eliminated even before the lock.
- **Alternatives considered**:
  - `git fetch && git merge --ff-only FETCH_HEAD` — **rejected**: still reads the
    clobbered `FETCH_HEAD`.
  - `git pull --ff-only origin main` with a clean FETCH_HEAD — **rejected**:
    depends on no concurrent writer, which is exactly what we cannot guarantee.
  - `git reset --hard origin/main` — **rejected**: would silently discard any
    real local commit (violates FR-005 fail-loud on divergence).
- **Divergence detection (FR-005)**: after fetch, compute
  `behind = rev-list --count HEAD..origin/main` and
  `ahead = rev-list --count origin/main..HEAD`. `ahead > 0` ⇒ genuine divergence
  ⇒ do not merge; return `diverged=True` with both SHAs for a loud log + alert.

## D2 — Shared advisory lock (fcntl.flock)

- **Decision**: A `deploylock(path)` context manager using `fcntl.flock(fd,
  LOCK_EX | LOCK_NB)` with a bounded retry (a few short sleeps up to ~5 s), then
  **defer to next tick** if still unavailable. Both actors wrap their
  git-and-working-tree critical section in it. Lock path is a single well-known
  host path shared by both actors, overridable by env for tests.
- **Rationale**: Even with D1 eliminating the FETCH_HEAD race, two concurrent
  `git merge --ff-only` / working-tree updates on one checkout can still race the
  index/worktree. An advisory flock is the standard, dependency-free
  serialization; non-blocking + defer means a busy tick never blocks the other
  service past its own interval (NFR-002). `flock` auto-releases if the holder
  dies (no stale-lock wedging).
- **Lock path**: `/data/services/deploy/locks/office2-checkout.lock` (a neutral
  shared location, not owned by either actor's service dir). Directory created
  on first use. Env override `DEPLOY_CHECKOUT_LOCK` for tests. *(Exact path is a
  plan-level default; flagged for Codex/operator confirmation.)*
- **Alternatives considered**: a lock *inside* one service's dir (rejected —
  couples the two services / ownership ambiguity); OS-level `flock(1)` in the
  systemd unit (rejected — doesn't cover both units cleanly and is harder to
  test than an in-process context manager).

## D3 — Behind-N health signal

- **Decision**: A shared `health.py` maintains a per-actor JSON watermark
  `{consecutive_failures, last_success_head, last_alert_ts}`. Each advance calls
  `record(result)`; when `consecutive_failures >= N` (default **3** ≈ ~15 min of
  a 5-min cadence) **and** no alert was sent since the streak began, emit one
  ntfy alert and stamp `last_alert_ts`. A success resets the counter.
- **Rationale**: A silent multi-week stall (the actual #667 harm) must be
  impossible. Threshold-crossing + throttle avoids per-tick alert spam
  (IDLE-ping fatigue is a known Felix concern). N=3 balances noise vs latency
  (alert within one interval of crossing, NFR-003).
- **Transport**: reuse `scripts/deploy/felix-deployer/notify.py` (ntfy is the
  canonical push substrate). prompt-sync gains ntfy for the first time via this
  shared notifier.
- **Alternatives**: alert on every failure (rejected — spam); rely on the daily
  security audit only (rejected — up to 24 h blind, and #667 shows silent stalls
  persist for weeks).

## D4 — Fail-loud logging of ref state (NFR-004)

- **Decision**: Every non-success advance logs a structured record carrying
  `local_head` (short sha), `origin_head` (short sha of `origin/main`),
  `behind`, `ahead`, and `reason` (`diverged` | `fetch_failed` |
  `lock_unavailable` | `merge_failed`). felix-deployer keeps its existing
  `tick_skip`/`git_pull_failed` event shape but enriched with these fields;
  prompt-sync keeps its `GitPullResult`/audit-record shape enriched likewise.
- **Rationale**: the current logs say only "Cannot fast-forward to multiple
  branches" with no ref state — the diagnosis required live probing. Recording
  the observed SHAs makes future incidents self-diagnosing.

## D5 — Preserve each actor's existing contracts

- **Decision**: `advance_checkout()` returns an `AdvanceResult` exposing
  `pre_head`, `post_head`, `behind`, `ahead`, `diverged`, `advanced`, `reason`.
  - **felix-deployer** maps `pre_head`/`post_head` onto its existing
    `pre_pull_head`/`post_pull_head` so the **rebaseline range computation
    (#685) is unchanged**.
  - **prompt-sync** wraps `advance_checkout()` inside its existing
    `git_pull()` seam, keeping the `GitPullResult(success, head_sha, stderr,
    stage)` public shape and the JSONL audit-record contract.
- **Rationale**: locality of change + no regression to the #685/#688 rebaseline
  subsystem or the audit-log-jsonl contract. The git seam stays subprocess-mocked
  for tests.

## D6 — Stale lane-branch cleanup + deploy discipline

- **Decision**: Delete `kitty/mission-trustworthy-weekly-habit-report-01KV4GZ7-lane-a`
  from origin during deploy (`git push origin --delete …`). Author a
  `deploys/queued/00NN-prompt-sync-ff-race.yaml` manifest to **record** the
  deploy and drive the **audited-surface rebaseline** (`scripts/deploy/**`
  changed → repo-file signal present → felix-deployer's watermark observe-range
  auto-detects and rebaselines per #685). The manifest declares no destructive
  action; the code itself reaches office2 via the checkout's own `git pull`.
- **Rationale**: the orphan branch amplifies the bare-fetch surface and is dead
  (mission merged ~2026-06-16). Deploy discipline requires a manifest for
  office2 changes; here its role is record + rebaseline trigger, matching the
  self-updating-checkout pattern from #685/#688.
- **Open item for Codex/operator**: confirm whether the manifest must also set
  `expected_baselines` (only needed if drift lacks a repo-file signal — here the
  signal exists, so likely not) and whether felix-deployer deploying its *own*
  code needs any special sequencing. Flagged for the post-plan review.
- **Related gap (not fixed here)**: spec-kitty left the lane branch on origin at
  merge; that lane-cleanup gap is a tooling concern to track separately, not in
  this mission's scope.
