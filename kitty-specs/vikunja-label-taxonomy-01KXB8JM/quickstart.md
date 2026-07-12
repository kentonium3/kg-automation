# Quickstart: Vikunja Label Taxonomy — operational run

The live run is a **post-merge** operational step (after `feat/vikunja-label-taxonomy`
merges to `main`, so office2 has the helper). It executes on office2 where
`VikunjaClient` resolves its token + base-URL config. Verifies SC-001..005.

## Preconditions

- Helper `scripts/vikunja/create_taxonomy_labels.py` merged to `main`; office2 checkout pulled it (felix-deployer git pull, ~5 min).
- Vikunja reachable; `vikunja-api` token valid (read/write).

## Step 1 — Dry-run pre-check (safe, no mutation)

```
ssh office2-claude 'cd <repo-checkout> && python3 -m scripts.vikunja.create_taxonomy_labels --dry-run --delete-legacy --backup-confirmed dry-run'
```
Confirm the **specific** planned actions (titles + action), not just counts. On
the audited current live state (2026-07-12) expect: 12 would-create, 3
would-delete (`personal`, `intentional`, `Duplicate`). If the live state has
drifted, verify the plan still targets exactly those titles before proceeding.

## Step 2 — Create pass (additive, safe)

```
ssh office2-claude 'cd <repo-checkout> && python3 -m scripts.vikunja.create_taxonomy_labels --json'
```
Capture stdout (outcomes + title→id map).

**Verify SC-001**: `GET /labels` shows all 12 taxonomy labels with correct
names + colors (normalize `#`).

## Step 3 — Confirm Restic backup (Tier-2 gate for deletion, C-002/SC-005)

Confirm a Restic backup within 24h exists; if not, trigger one first. Capture
the snapshot id (or an ISO timestamp) — it is a **required** argument to the
delete pass. **Do not proceed to Step 4 without this.**

## Step 4 — Delete pass (destructive, gated)

```
ssh office2-claude 'cd <repo-checkout> && python3 -m scripts.vikunja.create_taxonomy_labels --delete-legacy --backup-confirmed <snapshot-id-or-ts> --json'
```
The helper refuses to delete if `--backup-confirmed` is omitted; the ref is
echoed in the JSON output and recorded in the run notes.

**Verify SC-002**: `GET /labels` now returns exactly the 12 taxonomy labels;
`personal`, `intentional`, `Duplicate` are gone.

## Step 5 — Idempotent re-run (SC-003)

```
ssh office2-claude 'cd <repo-checkout> && python3 -m scripts.vikunja.create_taxonomy_labels --delete-legacy --backup-confirmed <snapshot-id-or-ts> --json'
```
**Verify SC-003**: every taxonomy label `already-present`, every legacy
`already-absent`; 0 creates, 0 deletes; exit 0.

## Step 6 — Record the map (SC-004)

Post the title→id map (from Step 2/4 JSON) as a comment on issue #715, and note
the run method + backup ref. The numeric ids are consumed by **task migration
(#717)**, which mutates tasks by label id. Note that **#716's habit-selector
move consumes the title `t:habit`** (`{"kind":"label","value":"t:habit"}` in
`vikunja_scope.py`), not the id — so #716 needs the label to *exist*, not the
id value.

## Rollback

If the delete pass misbehaves, restore labels from the Restic snapshot taken in
Step 3, or re-create the (only) intended labels — all label state is
reconstructable from the taxonomy constants (re-run Step 2) plus the snapshot
for any non-taxonomy data. Legacy labels, once deleted intentionally, are not
restored (that is the goal).

> Exact repo-checkout path on office2 is resolved at run time (the checkout the
> felix-deployer pulls). Placeholder `<repo-checkout>` above.
