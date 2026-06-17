# Contract: Rebaseline Lifecycle v1

Behavioral contract for felix-deployer's deferred-confirm rebaseline. All steps
run locally on office2 as the `claude` user. The tick NEVER crashes on a
rebaseline sub-step — failures become observability events + ntfy alerts.

## C1 — Observe (per tick, after `git pull --ff-only`)
- Compute pulled range: `pre_pull_head .. post_pull_head`. If equal (nothing pulled), skip.
- `changed = git diff --name-only <range>`; `matches = shared_matcher(changed, registry)`.
- If `matches` non-empty: write/merge the pending token (union new `surface_ids`/`expected_baselines`; keep earliest `pending_since_utc`). Log `pending_set`.
- If empty: log `not_required` (no token write).

## C2 — Reconcile (per tick, if pending token exists)
- Run read-only audit (`sg docker -c <audit.sh>` with baselines present) → parse drifted-baseline set `D`.
- Apply drift classification (data-model.md):
  - `D == ∅` → delete token, log `cleared_clean`.
  - `D ⊆ E, D ≠ ∅` → **C3 rebaseline**.
  - `D ⊄ E` → emit `unexpected_drift` ntfy (once), leave token, log `unexpected_drift`. Do NOT reset (FR-009).
- If audit output cannot be parsed into `D`, treat as inconclusive: leave token, no reset.
- Update `last_check_utc`. If `now - pending_since_utc > MAX_AGE` and not yet alerted → emit `stale` ntfy (once), log `stale`.

## C3 — Rebaseline + verify
- `rm /data/services/security-monitor/baselines/* && sg docker -c <audit.sh>` (the documented `rebaseline_command`).
- Verify: regenerated `baseline count == registry.expected_baseline_count` AND audit output reports clear.
  - Success → delete token, log `completed` (with `rebaselined_at_utc`, `baseline_count`).
  - Failure → emit `rebaseline_failed` ntfy (once), keep token for visibility, log `failed`. Applied code is untouched (no rollback).

## C4 — Invariants
- Rebaseline fires only via C3, only on `D ⊆ E, D ≠ ∅` (FR-007: confirmed expected drift).
- Exactly one ntfy per event key per token (dedup via `alerts_emitted`).
- Happy path (observe → expected drift → completed) requires zero human interaction (NFR-004).
- The daily security audit is unchanged and remains the backstop for out-of-band changes (NFR-003).

## C5 — ntfy payloads (reuse notify.py substrate)
Topic/subject mirror security-monitor convention. Event keys: `rebaseline_failed`,
`unexpected_drift`, `stale`. Body includes `surface_ids`, drifted baselines, and
the manual `rebaseline_command` from the registry for the operator.
