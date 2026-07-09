No files modified. Findings below are ranked by severity.

**Findings**
CRITICAL: Lock scope is under-specified and likely under-scoped.
Location: [contracts/lib-api.md](/Users/kentgale/repos/kg-automation/kitty-specs/prompt-sync-ff-race-01KX3SZC/contracts/lib-api.md:33), [data-model.md](/Users/kentgale/repos/kg-automation/kitty-specs/prompt-sync-ff-race-01KX3SZC/data-model.md:70), [spec.md](/Users/kentgale/repos/kg-automation/kitty-specs/prompt-sync-ff-race-01KX3SZC/spec.md:58); code at [_tick.py](/Users/kentgale/repos/kg-automation/scripts/deploy/felix-deployer/_tick.py:239), [_tick.py](/Users/kentgale/repos/kg-automation/scripts/deploy/felix-deployer/_tick.py:679), [_tick.py](/Users/kentgale/repos/kg-automation/scripts/deploy/felix-deployer/_tick.py:738).
Why it matters: the contract puts the lock inside `advance_checkout()`, but felix-deployer keeps mutating the same checkout/index after the initial pull: `git rm`, `git add`, `git commit`, `git push`, rebaseline stamp commits, and watermark selection. Prompt-sync could acquire the lock and fetch/merge while felix is mid-commit, leaving residual `.git/index.lock`/worktree races.
Recommendation: split `deploylock` from `advance_checkout()` or support “caller already holds lock”; define actor-level critical sections. Felix likely needs the shared checkout lock from pre-head capture through watermark write, or an explicitly proven narrower repo-mutation lock. Add tests that interleave prompt-sync with felix applied-record/stamp commits.

HIGH: Rollout depends on the broken pull path delivering its own fix.
Location: [quickstart.md](/Users/kentgale/repos/kg-automation/kitty-specs/prompt-sync-ff-race-01KX3SZC/quickstart.md:21), current code [_tick.py](/Users/kentgale/repos/kg-automation/scripts/deploy/felix-deployer/_tick.py:341), [deploy_agent_prompts.py](/Users/kentgale/repos/kg-automation/scripts/openclaw/deploy/deploy_agent_prompts.py:230).
Why it matters: the first fixed code only arrives if the existing race-prone pulls succeed. That is the exact failure mode being fixed.
Recommendation: make deploy a controlled bootstrap: stop or serialize both timers, delete the stale branch if desired, run `git fetch origin main && git merge --ff-only origin/main` manually on office2, verify fixed files are present, then restart timers.

HIGH: Divergence detection treats all `ahead > 0` as true divergence, but felix-deployer can intentionally be ahead.
Location: [research.md](/Users/kentgale/repos/kg-automation/kitty-specs/prompt-sync-ff-race-01KX3SZC/research.md:42), [_tick.py](/Users/kentgale/repos/kg-automation/scripts/deploy/felix-deployer/_tick.py:267), [_tick.py](/Users/kentgale/repos/kg-automation/scripts/deploy/felix-deployer/_tick.py:281).
Why it matters: felix creates local bookkeeping commits and then pushes. If commit succeeds but push fails, the current code treats that as a recoverable next-tick condition; the plan’s `ahead > 0 => diverged` could wedge the applier before it can reconcile or report usefully.
Recommendation: distinguish `ahead_only` from true divergence (`ahead > 0 && behind > 0`) and define deployer-specific policy for unpublished own commits: retry push, alert with recovery instructions, or intentionally block with a clear manual rollback path.

HIGH: The concurrency test does not prove the actor-level race is fixed.
Location: [plan.md](/Users/kentgale/repos/kg-automation/kitty-specs/prompt-sync-ff-race-01KX3SZC/plan.md:33), [contracts/lib-api.md](/Users/kentgale/repos/kg-automation/kitty-specs/prompt-sync-ff-race-01KX3SZC/contracts/lib-api.md:51), [spec.md](/Users/kentgale/repos/kg-automation/kitty-specs/prompt-sync-ff-race-01KX3SZC/spec.md:68).
Why it matters: `N concurrent advance_checkout()` calls only test the primitive. It does not prove both real actors share the same lock, preserve felix rebaseline range, avoid prompt-sync audit regressions, or survive felix’s later git mutations.
Recommendation: add an actor-level harness with one shared temp checkout, stale extra origin branch, barrier-synchronized prompt-sync and felix ticks, ≥100 overlapped pairs, and assertions for clean worktree, final HEAD, no multiple-branches error, prompt copy behavior, and `pre_pull_head`/`post_pull_head`.

HIGH: The queued deploy manifest is described as record-only, but the pipeline requires and executes an entrypoint.
Location: [contracts/lib-api.md](/Users/kentgale/repos/kg-automation/kitty-specs/prompt-sync-ff-race-01KX3SZC/contracts/lib-api.md:103), [manifest-v1.schema.json](/Users/kentgale/repos/kg-automation/deploys/schema/manifest-v1.schema.json:8), [apply.py](/Users/kentgale/repos/kg-automation/scripts/deploy/lib/apply.py:247).
Why it matters: the plan says the manifest “declares no destructive file operation,” but normal queued manifests must name an executable entrypoint and felix runs it with `--dry-run` and `--apply`.
Recommendation: specify the exact no-op/verification entrypoint and Tier-1 verification block, or change the deploy story to a manual/bootstrap applied record. Do not leave this to task authors.

MEDIUM: Audited-surface assumptions are broader than the actual registry.
Location: [spec.md](/Users/kentgale/repos/kg-automation/kitty-specs/prompt-sync-ff-race-01KX3SZC/spec.md:77), [audited-surfaces.json](/Users/kentgale/repos/kg-automation/docs/design/architecture/data/audited-surfaces.json:94).
Why it matters: artifacts say `scripts/deploy/**` is audited, but the registry matches `deploys/queued|applied|failed` and `scripts/deploy/lib/**`, not `scripts/deploy/felix-deployer/_tick.py` or `notify.py`. This mission probably triggers through new `scripts/deploy/lib` files, but the claim is inaccurate.
Recommendation: either update the registry to include felix-deployer surfaces or narrow the plan and add a test proving this mission’s actual changed files produce the intended rebaseline token.

MEDIUM: Lock defer semantics conflict with behind-N health semantics.
Location: [data-model.md](/Users/kentgale/repos/kg-automation/kitty-specs/prompt-sync-ff-race-01KX3SZC/data-model.md:31), [contracts/lib-api.md](/Users/kentgale/repos/kg-automation/kitty-specs/prompt-sync-ff-race-01KX3SZC/contracts/lib-api.md:80).
Why it matters: lock timeout is “not an error,” but `lock_unavailable` is `ok=False`, and health increments on `not result.ok`. A long felix tick could create false health alerts even when the checkout is current.
Recommendation: represent defer separately, or have health count only confirmed behind/diverged/fetch/merge failures. Test repeated lock defers when current and when origin advances.

MEDIUM: Alert throttle state is insufficient.
Location: [data-model.md](/Users/kentgale/repos/kg-automation/kitty-specs/prompt-sync-ff-race-01KX3SZC/data-model.md:41), [data-model.md](/Users/kentgale/repos/kg-automation/kitty-specs/prompt-sync-ff-race-01KX3SZC/data-model.md:50).
Why it matters: the rule compares `last_alert_ts` to “current failure streak’s start,” but no `failure_streak_started_ts` exists. That invites either duplicate alerts or suppressed later-streak alerts.
Recommendation: add `failure_streak_started_ts` or clear `last_alert_ts` on success with explicit tests for one alert per streak and re-alert after recovery.

MEDIUM: Reusing `notify.py` for prompt-sync health is not yet an API.
Location: [research.md](/Users/kentgale/repos/kg-automation/kitty-specs/prompt-sync-ff-race-01KX3SZC/research.md:80), [notify.py](/Users/kentgale/repos/kg-automation/scripts/deploy/felix-deployer/notify.py:141), [agent-prompt-sync.service](/Users/kentgale/repos/kg-automation/scripts/openclaw/deploy/agent-prompt-sync.service:41).
Why it matters: existing notifier is manifest-failure shaped and reads `FELIX_DEPLOYER_NTFY_TOPIC`; prompt-sync has no env file/topic wiring.
Recommendation: define a generic health notification function, topic/env ownership, redaction, failure logging, and tests.

**No-Issue Confirmations**
- I verified locally that `git fetch origin main` updates `refs/remotes/origin/main` with this repo’s `+refs/heads/*:refs/remotes/origin/*` refspec, so `git merge --ff-only origin/main` avoids the `FETCH_HEAD` multi-head race.
- The ref-merge and flock are both load-bearing but for different risks: ref-merge fixes `FETCH_HEAD`; flock protects shared index/worktree mutation.
- Deleting the stale lane branch is useful cleanup but not required once neither actor merges from `FETCH_HEAD`.
- Preserving felix `pre_pull_head`/`post_pull_head` is correctly identified as required for #685/#688; the plan just needs corrected lock/deploy details around it.