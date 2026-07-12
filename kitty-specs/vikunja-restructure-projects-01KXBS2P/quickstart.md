# Quickstart: Vikunja Project Restructure

## What it does

Reconciles Vikunja's project structure to the canonical design and removes the
five legacy saved filters. Additive-only for projects (never deletes a
task-bearing project). Idempotent.

## Prerequisites

- The `vikunja-api-kent` token is provisioned on office2
  (`/data/services/openclaw/secrets/vikunja-api-kent`, registered in #715).
- `VIKUNJA_BASE_URL` resolvable (env or canonical config) → the office2
  Tailscale HTTPS endpoint.
- For the destructive filter-delete pass: a recent **Restic backup** confirmed
  (Tier-2). Vikunja is on the snapshot-required tier.

## Run

Additive pass only (create projects, verify Inbox — no deletes):
```
python3 -m scripts.vikunja.reconcile_projects
```

Full reconcile incl. legacy-filter deletion (requires backup confirmation):
```
python3 -m scripts.vikunja.reconcile_projects --backup-confirmed
```

Point at the kent token explicitly if the default client token is felix-bot:
```
python3 -m scripts.vikunja.reconcile_projects --backup-confirmed --token-path /data/services/openclaw/secrets/vikunja-api-kent
```

## Verify (maps to Success Criteria)

- **SC-001/SC-002**: In Kent's Vikunja sidebar, confirm `Inbox`,
  `Felix / kg-automation`, `Personal`, and `Clients` with `PointerHealth` +
  `spec-kitty` nested under it.
- **SC-003**: Confirm `Today`, `Upcoming`, `Overdue`, `Goals`, `Completed`
  filters are gone; `Favorites` remains.
- **SC-004**: Re-run the command — output reports no changes (idempotent).
- **SC-005**: `Habits` project and its daily/weekly WhatsApp prompts still work.
- **SC-006**: `docs/design/vikunja-configuration-design.md` matches the live
  structure.

## Rollback

- Created projects can be deleted in the UI if needed (they hold no tasks at
  creation).
- Deleted filters are restored from the Restic snapshot taken before the run
  (the reason the delete pass is backup-gated).
