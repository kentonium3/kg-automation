# Quickstart: operator live migration (post-merge, office2)

Run **after** the mission merges to main and office2's checkout has pulled it.
Authenticated as `kent` via the `vikunja-api-kent` token. This is a Tier-2
change (live DB state).

## 1. Confirm a fresh backup (NFR-002, Tier 2)

Verify a Restic snapshot of `vikunja.db` within the last 24h; if none, trigger one:

```
ssh office2-claude 'restic -r <repo> snapshots --json | tail'   # confirm recent vikunja.db snapshot
```

## 2. Dry-run (no mutations)

```
ssh office2-claude 'cd /home/claude/kg-automation && python3 -m scripts.vikunja.migrate_tasks'
```

Review the printed plan: 30 moves, 11 labels, 2 task-deletes, 6 project-deletes,
0 blocked. If any doomed project is `blocked` (non-empty), stop and reconcile the
manifest before applying.

## 3. Apply

```
# pass the verified Restic snapshot id (or ISO timestamp) from step 1 as backup evidence
ssh office2-claude 'cd /home/claude/kg-automation && python3 -m scripts.vikunja.migrate_tasks --apply --backup-ref <snapshot-id>'
```

## 4. Verify (SC-001..006)

- Re-run step 2 (dry-run) → must report **0** of everything (idempotent, SC-005).
- In Kent's Vikunja UI: the six legacy projects are gone (SC-001); topic projects
  hold the expected tasks with intact due dates/recurrence (SC-002); Habits tasks
  show `t:habit` (SC-003); test tasks #89/#44 are gone (SC-004).
- Confirm escalation + habit queries still run:
  `python3 -m scripts.escalation.enumerate_candidates` and the habit weekly query
  execute without referencing a deleted project id (SC-006).

## 5. Close out

Close #717 with the applied summary; update #714 epic and #718 (now unblocked).
