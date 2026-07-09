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
    lock_path: Path | None = None,   # None → shared default; passes through to deploylock
    git_runner: Callable[[list[str]], subprocess.CompletedProcess] | None = None,
) -> AdvanceResult:
    """Race-immune fast-forward of *repo_root* to <remote>/<branch>.

    Contract:
      1. Acquire the shared advisory lock (deploylock). If unavailable within the
         timeout → return AdvanceResult(ok=False, reason="lock_unavailable") — NOT
         an exception to the caller's tick.
      2. `git fetch <remote> <branch>` → updates refs/remotes/<remote>/<branch>
         atomically. On non-zero → ok=False, reason="fetch_failed".
      3. Compute behind = HEAD..<remote>/<branch>, ahead = <remote>/<branch>..HEAD.
      4. If ahead > 0 → diverged=True, ok=False, reason="diverged"; DO NOT merge.
      5. If behind == 0 → clean no-op: ok=True, advanced=False.
      6. Else `git merge --ff-only <remote>/<branch>` (NEVER FETCH_HEAD).
         On non-zero → ok=False, reason="merge_failed". On success → advanced=True.
      7. Populate pre_head/post_head/origin_head as short SHAs.

    `git_runner` seam allows subprocess mocking in tests (mirrors the existing
    `_git`/`git_pull` seams in both actors).
    """
```

**Behavioral guarantees (tested):**
- Never reads `.git/FETCH_HEAD` for the merge decision (grep-assertable: merge target is `<remote>/<branch>`).
- Concurrency: N concurrent `advance_checkout()` against one temp repo produce 0 `Cannot fast-forward to multiple branches` and a consistent final HEAD (NFR-001).
- Idempotent: calling when already current returns `ok=True, advanced=False` with no side effects.

## `scripts/deploy/lib/deploylock.py`

```python
class LockUnavailable(RuntimeError): ...

DEFAULT_LOCK_PATH = Path("/data/services/deploy/locks/office2-checkout.lock")

@contextmanager
def deploylock(path: Path | None = None, timeout_s: float = 5.0) -> Iterator[None]:
    """Advisory fcntl.flock(LOCK_EX|LOCK_NB) with bounded retry.

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

    - result.ok and result.advanced-or-current → reset consecutive_failures=0,
      update last_success_head/ts.
    - not result.ok → increment consecutive_failures.
    - Fire ntfy (via notifier) exactly once per streak when count crosses
      `threshold`; stamp last_alert_ts. `notifier` defaults to the felix-deployer
      ntfy sender; injectable for tests.
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

## Deploy-manifest contract

`deploys/queued/00NN-prompt-sync-ff-race.yaml` conforms to the existing manifest
schema (validated by the deploy lib). It records the deploy and triggers the
`scripts/deploy/**` audited-surface rebaseline; it declares no destructive file
operation (code arrives via the checkout's own `git pull`).
