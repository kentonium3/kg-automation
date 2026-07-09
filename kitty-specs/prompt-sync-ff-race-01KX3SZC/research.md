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
- **Divergence detection (FR-005) — corrected per Codex (HIGH)**: after fetch,
  compute `behind = rev-list --count HEAD..origin/main` and
  `ahead = rev-list --count origin/main..HEAD`. felix-deployer is **routinely
  `ahead`** — it creates local bookkeeping commits (applied records, rebaseline
  stamps) and pushes them; between commit and a failed/late push it is
  legitimately ahead with `behind == 0`. So:
  - `behind == 0` ⇒ **clean no-op** (`ok=True, advanced=False`) regardless of
    `ahead` — an actor's own unpushed commits are not our concern here.
  - `behind > 0 and ahead == 0` ⇒ fast-forward via `git merge --ff-only origin/main`.
  - `behind > 0 and ahead > 0` ⇒ **true divergence** (both sides moved) ⇒ do not
    merge; `diverged=True` with both SHAs for a loud log + alert.
  The earlier `ahead > 0 ⇒ diverged` rule was wrong: it would wedge felix-deployer
  whenever it held unpushed bookkeeping commits.

## D2 — Shared advisory lock (fcntl.flock) — SCOPE CORRECTED per Codex (CRITICAL)

- **Decision**: `deploylock(path)` is a **standalone** context manager (its own
  module), NOT embedded inside `advance_checkout()`. Each actor wraps its
  **entire per-actor critical section** in it — not just the pull. This is the
  key correction: felix-deployer keeps mutating the same checkout/index *after*
  the pull (`git rm/add/commit`, `git push`, rebaseline stamp commits, watermark
  writes — `_tick.py` around lines 239/679/738). If prompt-sync could acquire the
  lock and fetch/merge while felix is mid-commit, we'd get exactly the residual
  `.git/index.lock`/worktree races the mission exists to kill.
  - **felix-deployer** holds the lock from **pre-head capture through watermark
    write** (the whole tick body that touches the checkout).
  - **prompt-sync** holds the lock across its **fetch/merge + prompt-copy**
    section.
  - `advance_checkout()` therefore takes `assume_locked: bool = False`; the
    actors call it with `assume_locked=True` from inside their already-held lock
    (so the lock is acquired once per tick at the actor level, not re-entered).
  Uses `fcntl.flock(fd, LOCK_EX | LOCK_NB)` with a bounded retry (~5 s), then
  **defer to next tick** if still unavailable. Single well-known host path shared
  by both actors, env-overridable for tests.
- **Rationale**: Even with D1 eliminating the FETCH_HEAD race, two concurrent
  `git merge --ff-only` / working-tree/index updates on one checkout still race —
  and felix's post-pull commit/push/stamp phase is the widest window. The lock
  must therefore bound the **actor-level** critical section, not the primitive.
  Non-blocking + defer means a busy tick never blocks the other service past its
  own interval (NFR-002). `flock` auto-releases if the holder dies (no stale-lock
  wedging).
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
  `{consecutive_failures, failure_streak_started_ts, last_success_head,
  last_success_ts, last_alert_ts}`. Each advance calls `record(result)`; when
  `consecutive_failures >= N` (default **3** ≈ ~15 min of a 5-min cadence) **and**
  no alert has fired since `failure_streak_started_ts`, emit one ntfy alert and
  stamp `last_alert_ts`. A success resets the counter, clears
  `failure_streak_started_ts`, and clears `last_alert_ts` (so a later streak can
  alert again).
- **Health counts only CONFIRMED failures — corrected per Codex (MEDIUM)**: a
  `lock_unavailable` result is a **benign defer** (the other actor simply held the
  lock), NOT a failure — it must NOT increment `consecutive_failures`, or a long
  felix tick would trigger false alerts while the checkout is perfectly current.
  Only `diverged | fetch_failed | merge_failed` count toward the streak.
  `failure_streak_started_ts` gives the throttle a real anchor (the earlier plan
  compared `last_alert_ts` to a streak-start that did not exist).
- **Rationale**: A silent multi-week stall (the actual #667 harm) must be
  impossible. Threshold-crossing + throttle avoids per-tick alert spam
  (IDLE-ping fatigue is a known Felix concern). N=3 balances noise vs latency
  (alert within one interval of crossing, NFR-003).
- **Transport — generalized per Codex (MEDIUM)**: the existing
  `notify.py:dispatch_failure_notification()` is **manifest-failure-shaped**
  (renders a manifest title, reads `FELIX_DEPLOYER_NTFY_TOPIC`) — not a generic
  health notifier. So we add a **generic** `dispatch_health_notification(actor,
  title, body, *, topic_env)` (either a new function in `notify.py` or in
  `health.py` reusing notify's redaction/curl internals) with: explicit
  topic/env ownership (prompt-sync gets its own `AGENT_PROMPT_SYNC_NTFY_TOPIC`,
  falling back to the shared deployer topic if unset — resolved at plan/impl and
  wired via the actor's env/service file), topic redaction in logs, and
  best-effort failure logging. prompt-sync gains ntfy for the first time; its
  systemd unit / env needs the topic wired (it has no env file today).
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

## D6 — Deploy via controlled bootstrap (NOT a queued manifest) — corrected per Codex (HIGH ×2, MEDIUM)

- **Decision**: Deploy through a **controlled operator bootstrap**, recorded as a
  `deploys/applied/` record — NOT a `deploys/queued/` manifest. Two Codex HIGH
  findings drive this:
  1. **Chicken-and-egg**: the fixed code can only arrive via the checkout's own
     `git pull`, which is the *exact broken path* being fixed. Relying on it to
     deliver its own fix is unsound.
  2. **Queued manifests are not record-only**: the manifest schema requires an
     executable entrypoint that felix-deployer runs with `--dry-run`/`--apply`
     (`scripts/deploy/lib/apply.py`); a "records nothing to run" manifest is
     invalid.
- **Bootstrap sequence** (detailed in [quickstart.md](./quickstart.md)): stop
  both timers (`agent-prompt-sync.timer`, `felix-deployer.timer`) → run
  `git fetch origin main && git merge --ff-only origin/main` **manually** on
  office2 → verify the new `scripts/deploy/lib/` files + modified actors are
  present → delete the stale origin lane branch → **manually reset the
  audited-surface baselines** (the new `scripts/deploy/lib/**` files change a
  monitored surface) → restart both timers. Record the whole thing as a
  `deploys/applied/00NN-prompt-sync-ff-race.yaml` (the manual-bootstrap /
  operator-applied pattern used for #659 Phase-2 and the felix-deployer
  bootstrap), not a queued manifest.
- **Stale lane-branch cleanup (FR-003)**: delete
  `kitty/mission-trustworthy-weekly-habit-report-01KV4GZ7-lane-a` from origin
  (`git push origin --delete …`) during the bootstrap. It is dead (mission merged
  ~2026-06-16) and amplifies the bare-fetch surface. (Note: strictly no longer
  *required* for correctness once neither actor merges from FETCH_HEAD — Codex
  confirmed — but it is worthwhile hygiene and removes a confusing orphan.)
- **Audited-surface scope — corrected per Codex (MEDIUM)**: the registry
  (`audited-surfaces.json` → `deploy-pipeline`) matches
  `deploys/{queued,applied,failed}/*.yaml` and **`scripts/deploy/lib/**`** — it
  does **NOT** match `scripts/deploy/felix-deployer/_tick.py`, `notify.py`, or
  `scripts/openclaw/deploy/**`. So the rebaseline obligation is triggered
  specifically by this mission's **new `scripts/deploy/lib/` primitives**
  (gitsync/deploylock/health), not by the actor edits. The earlier
  "`scripts/deploy/**` is audited" claim was too broad and is corrected in spec
  C-002. Because this is an out-of-band manual bootstrap (not the felix-deployer
  happy path), the rebaseline is a **manual** reset (out-of-band exception),
  confirmed drift-expected-only first.
- **Related gap (not fixed here)**: spec-kitty left the lane branch on origin at
  merge; that lane-cleanup gap is a tooling concern to track separately, not in
  this mission's scope.

## Post-plan Codex review (2026-07-09) — folds applied

Dispatched `codex exec -p spec-kitty-review` against the six mission artifacts +
the actual code. Codex confirmed the core race fix sound (verified locally that
`git fetch origin main` updates `refs/remotes/origin/main`, so
`git merge --ff-only origin/main` avoids the FETCH_HEAD multi-head race; ref-merge
and flock are both load-bearing for different risks). Findings folded:

| Sev | Finding | Fold |
|-----|---------|------|
| CRITICAL | Lock scoped to the pull, but felix mutates the checkout post-pull (commit/push/stamp/watermark) | D2: `deploylock` standalone; actors hold it across the **whole** critical section; `advance_checkout(assume_locked=True)` |
| HIGH | Rollout relies on the broken pull to deliver its own fix | D6 + quickstart: controlled operator **bootstrap** (stop timers → manual ff-merge → verify → restart) |
| HIGH | `ahead>0 ⇒ diverged` wedges felix (it is routinely ahead with unpushed commits) | D1: `diverged = behind>0 AND ahead>0`; `behind==0` ⇒ clean no-op |
| HIGH | Concurrency test only exercises the primitive, not the actor-level race | Test strategy: add an **actor-level** harness (see below); NFR-001 sharpened |
| HIGH | Queued manifest must name an executable entrypoint (not record-only) | D6: deploy as `deploys/applied/` bootstrap record, not a queued manifest |
| MED | `scripts/deploy/**` audited claim too broad | D6 + spec C-002: only `scripts/deploy/lib/**` is in the registry |
| MED | `lock_unavailable` (defer) wrongly counts as a health failure | D3: health counts only `diverged/fetch_failed/merge_failed` |
| MED | Alert throttle lacked `failure_streak_started_ts` | D3 + data-model: field added; cleared on success |
| MED | `notify.py` is manifest-shaped, not a generic health notifier | D3: add generic `dispatch_health_notification()` + topic/env ownership |

### Test strategy (fold of the HIGH concurrency finding)
NFR-001 is proven at **two** levels:
1. **Primitive**: N concurrent `advance_checkout()` against one temp repo → 0
   "multiple branches", consistent final HEAD (necessary, not sufficient).
2. **Actor-level integration harness** (the load-bearing proof): one shared temp
   checkout seeded with a stale extra origin branch; barrier-synchronized
   prompt-sync and felix-deployer tick bodies (both taking the *same* lock);
   ≥100 overlapped pairs; assert after each: clean worktree + index (no residual
   `.git/index.lock`), expected final HEAD, no "multiple branches" error,
   prompt-copy still lands, felix `pre_pull_head`/`post_pull_head` still correct
   for the rebaseline range, and prompt-sync audit records intact.
