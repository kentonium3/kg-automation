# Quickstart — deploy, verify, rollback

Tier 1 change (deploy fabric). Verify prompt-deploy connectivity before and after.

## Pre-deploy (Tier 1 pre-flight)

1. Confirm current failure baseline on office2:
   ```
   ssh office2-claude 'grep -c git_pull_failed /data/services/openclaw/deploy/agent-prompt-sync.jsonl'
   ```
2. Confirm the stale lane branch still present (target for FR-003):
   ```
   ssh office2-claude 'cd /home/claude/kg-automation && git ls-remote --heads origin "kitty/*"'
   ```
3. Confirm a recent Restic snapshot exists (Tier-1 dependent-service safety; the
   checkout is Tier-2-adjacent state) — the felix-deployer nightly backup covers
   `/home/claude`.

## Deploy sequence

1. **Merge the mission** to `main` (after `feat/prompt-sync-ff-race` → `main`).
   The new `scripts/deploy/lib/` primitives + both modified actors reach office2
   via the checkout's own `git pull` on the next tick.
2. **Delete the stale origin lane branch (FR-003)** — one command, run once:
   ```
   git push origin --delete kitty/mission-trustworthy-weekly-habit-report-01KV4GZ7-lane-a
   ```
3. **felix-deployer picks up the queued manifest** `00NN-prompt-sync-ff-race.yaml`
   on its next tick; because `scripts/deploy/**` changed in the pulled range, the
   watermark observe-range auto-rebaselines (per #685). Confirm the applied
   record + `rebaseline:` stamp (#688).

## Post-deploy verification (maps to Success Criteria)

- **SC-001** — over 48 h, no *new* `git_pull_failed` "multiple branches" entries:
  ```
  ssh office2-claude 'grep "Cannot fast-forward to multiple branches" /data/services/openclaw/deploy/agent-prompt-sync.jsonl | tail -1'
  ```
  (timestamp of the last such entry should predate the deploy)
- **SC-002** — end-to-end prompt reaches agents within one interval: touch a
  benign prompt change, merge, confirm the deployed prompt md5 updates on office2
  within ~5 min.
- **SC-003** — simulated fall-behind fires an alert: with the health threshold,
  force N consecutive failed advances in a scratch harness and confirm one ntfy.
- **SC-004** — checkout stays current with no manual git:
  ```
  ssh office2-claude 'cd /home/claude/kg-automation && git rev-list --count HEAD..origin/main'
  ```
  should read `0` across the window.

## Connectivity check (Tier 1, before AND after)

Confirm both deploy actors still advance the checkout and the prompt-sync copy
step still lands files:
```
ssh office2-claude 'systemctl --user list-timers | grep -E "deployer|prompt-sync"'
ssh office2-claude 'tail -3 /data/services/openclaw/deploy/agent-prompt-sync.jsonl'
```

## Rollback

The change is code-only on the shared checkout. To roll back: revert the merge on
`main`; both actors pull the revert on their next tick and resume the prior
behavior. The new lock file and health watermark are inert once the code is gone.
Re-run the audited-surface rebaseline after the revert deploys.

## Rebaseline obligation

`scripts/deploy/**` is an audited surface. On the happy path felix-deployer
auto-rebaselines from the observe-range (repo-file signal present). Confirm via
the applied record's `rebaseline:` stamp; if it did not fire, reset manually per
`docs/runbooks/security-baseline-ops.md`. The mission merge commit records
`Rebaseline: completed at <ts>` (or `not required — <reason>`).
