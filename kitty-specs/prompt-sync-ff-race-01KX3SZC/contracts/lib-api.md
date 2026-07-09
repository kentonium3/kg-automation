# Contracts — shared-lib API + behaviors

This mission has no HTTP/REST surface. The "contracts" are the shared-library
Python API both deploy actors depend on, plus the git-behavior and log-schema
contracts they must uphold.

## `scripts/deploy/lib/gitsync.py`

```python
@dataclass(frozen=True)
class AdvanceResult:
    ok: bool
    advanced: bool
    pre_head: str
    post_head: str
    origin_head: str
    behind: int
    ahead: int
    diverged: bool
    reason: str | None = None      # diverged|fetch_failed|lock_unavailable|merge_failed
    stderr: str = ""

def advance_checkout(
    repo_root: Path,
    *,
    remote: str = "origin",
    branch: str = "main",
    assume_locked: bool = False,     # True when the caller already holds deploylock (actor-level)
    lock_path: Path | None = None,   # only used when assume_locked=False
    git_runner: Callable[[list[str]], subprocess.CompletedProcess] | None = None,
) -> AdvanceResult:
    """Race-immune fast-forward of *repo_root* to <remote>/<branch>.

    Lock scope (Codex CRITICAL): the actors hold `deploylock` around their ENTIRE
    critical section and call this with assume_locked=True. This function only
    self-acquires the lock when assume_locked=False (e.g. standalone/test use).

    Contract:
      1. If not assume_locked: acquire deploylock; on timeout → return
         AdvanceResult(ok=False, reason="lock_unavailable") — a benign defer, NOT
         an exception to the caller's tick, and NOT a health failure.
      2. `git fetch <remote> <branch>` → updates refs/remotes/<remote>/<branch>
         atomically. On non-zero → ok=False, reason="fetch_failed".
      3. Compute behind = HEAD..<remote>/<branch>, ahead = <remote>/<branch>..HEAD.
      4. If behind == 0 → clean no-op: ok=True, advanced=False (regardless of
         ahead — an actor's own unpushed commits are fine).
      5. Elif ahead > 0 (and behind > 0) → true divergence: diverged=True,
         ok=False, reason="diverged"; DO NOT merge.
      6. Else (behind > 0, ahead == 0) → `git merge --ff-only <remote>/<branch>`
         (NEVER FETCH_HEAD). On non-zero → ok=False, reason="merge_failed".
         On success → advanced=True.
      7. Populate pre_head/post_head/origin_head as short SHAs.

    `git_runner` seam allows subprocess mocking in tests (mirrors the existing
    `_git`/`git_pull` seams in both actors).
    """
```

**Behavioral guarantees (tested):**
- Never reads `.git/FETCH_HEAD` for the merge decision (grep-assertable: merge target is `<remote>/<branch>`).
- Concurrency (primitive level): N concurrent `advance_checkout()` against one temp repo produce 0 `Cannot fast-forward to multiple branches` and a consistent final HEAD.
- **Concurrency (actor level — the load-bearing NFR-001 proof)**: an integration
  harness runs barrier-synchronized prompt-sync and felix-deployer tick bodies
  (both taking the *same* `deploylock`) against one shared temp checkout seeded
  with a stale extra origin branch, ≥100 overlapped pairs, asserting after each:
  clean worktree + no residual `.git/index.lock`, expected final HEAD, no
  multiple-branches error, prompt-copy lands, felix `pre_pull_head`/`post_pull_head`
  correct, prompt-sync audit records intact.
- Idempotent: calling when already current returns `ok=True, advanced=False` with no side effects (even if `ahead>0`).
- Divergence: `ahead>0` with `behind==0` is a clean no-op; only `behind>0 AND ahead>0` yields `diverged`.

## `scripts/deploy/lib/deploylock.py`

```python
class LockUnavailable(RuntimeError): ...

DEFAULT_LOCK_PATH = Path("/data/services/deploy/locks/office2-checkout.lock")

@contextmanager
def deploylock(path: Path | None = None, timeout_s: float = 5.0) -> Iterator[None]:
    """Advisory fcntl.flock(LOCK_EX|LOCK_NB) with bounded retry.

    Held at the ACTOR level around the whole checkout-mutating critical section
    (not inside advance_checkout). felix-deployer wraps pre-head-capture →
    queue-apply → git commit/push → rebaseline stamp → watermark write.
    prompt-sync wraps fetch/merge → prompt-copy.

    Resolves path: explicit arg → env DEPLOY_CHECKOUT_LOCK → DEFAULT_LOCK_PATH.
    Creates the parent dir if missing. Raises LockUnavailable on timeout.
    Releases (and the OS auto-releases on process death) on exit.
    """
```

## `scripts/deploy/lib/health.py`

```python
def record(actor: str, result: AdvanceResult, *, state_path: Path,
           threshold: int = 3, notifier: Callable[[str, str], None] | None = None) -> bool:
    """Update the per-actor watermark from *result*; return True iff an alert fired.

    - result.ok (success or clean no-op) → reset consecutive_failures=0, clear
      failure_streak_started_ts and last_alert_ts, update last_success_head/ts.
    - result.reason == "lock_unavailable" → NO-OP for the streak (benign defer);
      do not increment, do not alert.
    - result.reason in {"diverged","fetch_failed","merge_failed"} → increment
      consecutive_failures; set failure_streak_started_ts if starting a streak.
    - Alert (via notifier) exactly once per streak when consecutive_failures
      crosses `threshold` AND (last_alert_ts is null OR < failure_streak_started_ts);
      stamp last_alert_ts. `notifier` injectable for tests.
    State file written atomically (temp + rename).
    """


# Generic health notifier (NOT the manifest-shaped dispatch_failure_notification).
def dispatch_health_notification(actor: str, title: str, body: str, *,
                                 topic_env: str) -> None:
    """Send an ntfy health alert for *actor*. Resolves the topic from `topic_env`
    (prompt-sync: AGENT_PROMPT_SYNC_NTFY_TOPIC, falling back to
    FELIX_DEPLOYER_NTFY_TOPIC if unset). Reuses notify.py redaction/curl
    internals; best-effort (logs on failure, never raises into the tick).
    """
```

## Git-behavior contract (both actors)

| Before | After |
|--------|-------|
| `git fetch origin main` + `git pull --ff-only origin main` (prompt-sync) | `advance_checkout()` → `git fetch origin main` + `git merge --ff-only origin/main`, under the shared lock |
| `git pull --ff-only` (felix-deployer, bare — fetched all heads) | `advance_checkout()` (explicit `origin main`, ref-merge), under the shared lock |

## Log-schema contract

Failure records in both JSONL streams MUST include `local_head`, `origin_head`,
`behind`, `ahead`, and `reason`. Existing success/summary record shapes are
preserved. felix-deployer's rebaseline-critical `pre_pull_head`/`post_pull_head`
values are sourced from `AdvanceResult.pre_head`/`post_head` unchanged.

## Deploy contract (bootstrap applied record — corrected per Codex)

Deploy is a **controlled operator bootstrap**, NOT a queued manifest (a queued
manifest must name an executable entrypoint felix-deployer runs with
`--dry-run`/`--apply`; and relying on the broken pull to deliver its own fix is
unsound). The bootstrap (stop timers → manual `git fetch && git merge --ff-only
origin/main` → verify → delete stale branch → manual audited-surface rebaseline →
restart timers) is recorded as `deploys/applied/00NN-prompt-sync-ff-race.yaml`
(operator-applied pattern, cf. #659 Phase-2 / felix-deployer bootstrap). The
audited-surface rebaseline is triggered specifically by the new
`scripts/deploy/lib/**` files (the only mission paths in the `deploy-pipeline`
registry) and is reset **manually** (out-of-band exception), drift-confirmed
first.
