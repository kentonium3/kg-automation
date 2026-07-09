# Data Model — Prompt-sync FETCH_HEAD race fix

Phase 1 output. The mission is plumbing, so the "entities" are in-process value
objects and small on-disk state files, not database records.

## Value objects

### AdvanceResult
Returned by `advance_checkout()`. Immutable dataclass.

| Field | Type | Meaning |
|-------|------|---------|
| `advanced` | bool | True if the checkout moved to a new HEAD this call |
| `pre_head` | str | short SHA of local HEAD before the advance ("" if unresolved) |
| `post_head` | str | short SHA of local HEAD after the advance ("" if unresolved) |
| `origin_head` | str | short SHA of `origin/main` after fetch |
| `behind` | int | commits `HEAD..origin/main` (0 when current) |
| `ahead` | int | commits `origin/main..HEAD` (an actor's own unpushed commits when `behind==0`) |
| `diverged` | bool | True **only** when `behind > 0 AND ahead > 0` — advance refused, fail loud |
| `ok` | bool | True when the advance succeeded OR was a clean no-op (already current, even if `ahead>0`) |
| `reason` | str \| None | on non-ok: `diverged` \| `fetch_failed` \| `lock_unavailable` \| `merge_failed` |
| `stderr` | str | truncated git stderr on failure (≤200 chars) |

**Invariants**: `ok` is False iff `reason` is set. `advanced ⇒ post_head != pre_head`. `diverged ⇒ not advanced and reason == "diverged"`. A clean no-op ⇒ `ok=True, advanced=False, behind==0` (regardless of `ahead`). **`ahead>0` alone is NOT divergence** — felix-deployer is routinely ahead with `behind==0` (unpushed bookkeeping commits); only `behind>0 AND ahead>0` is true divergence. `lock_unavailable` is a benign defer, not a failure for health purposes (see health rule).

### DeployLock (context manager) — actor-level scope
`deploylock(path, timeout_s=5.0)` — advisory `fcntl.flock` on a well-known file.
**Standalone** (its own module), acquired at the **actor level** around the whole
critical section, NOT inside `advance_checkout()`. felix-deployer holds it from
pre-head capture through watermark write (covering its post-pull commit/push/stamp
mutations); prompt-sync holds it across fetch/merge + prompt-copy.
`advance_checkout(assume_locked=True)` runs inside the already-held lock.

| Aspect | Behavior |
|--------|----------|
| Acquire | `LOCK_EX \| LOCK_NB`, retried over ≤ `timeout_s` |
| On timeout | raises `LockUnavailable` (caller records `reason="lock_unavailable"`, defers to next tick — a benign defer, **not** a health failure) |
| Release | on context exit; auto-released by the OS if the holder dies |
| Path | shared constant, env-overridable (`DEPLOY_CHECKOUT_LOCK`); parent dir created on demand; must be writable by `claude` |

## On-disk state

### Health watermark (per actor)
Small JSON, one per actor, atomic-written.

| Field | Type | Meaning |
|-------|------|---------|
| `actor` | str | `agent-prompt-sync` \| `felix-deployer` |
| `consecutive_failures` | int | counts only CONFIRMED failures (`diverged`/`fetch_failed`/`merge_failed`); `lock_unavailable` does NOT increment; reset to 0 on any success/clean-no-op |
| `failure_streak_started_ts` | str \| null | UTC time the current streak began (null when no streak); the throttle anchor |
| `last_success_head` | str | short SHA of the last successful advance |
| `last_success_ts` | str (ISO-8601 UTC) | time of last success |
| `last_alert_ts` | str \| null | time the behind-N alert last fired (throttle) |
| `updated_ts` | str (ISO-8601 UTC) | last write |

**Alert rule**: emit iff `consecutive_failures >= N` (default 3) AND (`last_alert_ts` is null OR `last_alert_ts < failure_streak_started_ts`). On success/clean-no-op: reset `consecutive_failures=0`, clear `failure_streak_started_ts` and `last_alert_ts` — so a later streak can alert again. `lock_unavailable` results leave the streak untouched (benign defer). Atomic write (temp + rename).

### Advisory lock file
Zero-length file at the shared lock path. Content is irrelevant; only the flock matters.

## Log records (enriched, existing JSONL streams)

Both actors keep their current streams; failure records gain ref-state fields.

**felix-deployer** (`/data/services/felix-deployer/logs/<date>.jsonl`) — existing `tick_skip`/`git_pull_failed` events gain:
```
{"event":"tick_skip","reason":"diverged|fetch_failed|lock_unavailable|merge_failed",
 "local_head":"<sha>","origin_head":"<sha>","behind":<n>,"ahead":<n>,"stderr":"<...>"}
```

**agent-prompt-sync** (`/data/services/openclaw/deploy/agent-prompt-sync.jsonl`) — existing `git_pull_failed` record gains the same `local_head`/`origin_head`/`behind`/`ahead`/`reason` fields; the `stage` field maps to `reason`.

## Relationships

```
advance_checkout()  ──uses──▶ deploylock(path)      (IC-02, mutual exclusion)
        │
        ├── returns ─▶ AdvanceResult
        │                   │
        │                   └── consumed by ─▶ health.record(actor, result)  (IC-03)
        │                                            │
        │                                            └── should_alert ─▶ notify.py (ntfy)
        │
        └── called by ─▶ felix-deployer _tick.py   AND   prompt-sync git_pull()   (IC-04)
```

## No schema migrations

No database, no existing serialized-config changes. The health watermark and lock
file are new runtime artifacts created on first tick. The deploy manifest
(`deploys/queued/00NN-prompt-sync-ff-race.yaml`) conforms to the existing manifest
schema.
