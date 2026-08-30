---
work_package_id: WP06
title: Documentation, drift caveat, and operator handoff
dependencies:
- WP02
- WP05
requirement_refs:
- C-002
- FR-011
planning_base_branch: feat/934-pointer-key-ledger
merge_target_branch: feat/934-pointer-key-ledger
branch_strategy: Planning artifacts for this mission were generated on feat/934-pointer-key-ledger. During /spec-kitty.implement this WP may branch from a dependency-specific base, but completed changes must merge back into feat/934-pointer-key-ledger unless the human explicitly redirects the landing branch.
subtasks:
- T030
- T031
- T032
- T033
history:
- at: '2026-08-30T03:54:28Z'
  actor: tasks
  note: Generated from plan v2 IC-05.
agent_profile: curator-carla
authoritative_surface: docs/runbooks/restic-backup-ops.md
create_intent: []
execution_mode: code_change
model: claude-sonnet-4-6
owned_files:
- docs/runbooks/restic-backup-ops.md
- docs/INDEX.md
- docs/DEVELOPER_PORTAL.md
role: implementer
tags: []
tracker_refs: []
---

## ⚡ Do This First: Load Agent Profile

```
/ad-hoc-profile-load curator-carla
```

## Objective

Record the contract where an operator will actually look, state plainly the caveat that bounds its
guarantee, and hand over the install step that only the operator can perform.

## Context you need

Two things make this WP more than routine doc maintenance.

**The guarantee is easy to overstate — the spec had to be corrected for exactly that.** What the
mechanism buys is: *silent inertness becomes impossible; deliberate inertness becomes a line in a
diff.* It does not remove the reviewer from the loop. `diagnostic_only` is still an escape hatch; it
now costs a written reason. Write the runbook to that claim, not a larger one.

**The ledger binds the repo copy, not the deployed producer.** These are independent files: the live
producer is `/data/services/backup/scripts/backup.sh`, `deployed_by: manual`, root-owned. A separate
component, `backup-script-drift`, exists *because they once diverged* — and it is **observe-only by
design**, so it can never converge them. The ledger's guarantee about live behaviour is therefore void
while that comparator reports drift. Nobody reading the runbook today would know this.

## Subtasks

### T030 — Runbook: the contract, and what bounds it

**Steps**:
1. In `docs/runbooks/restic-backup-ops.md`, add a section describing the key ledger: where it lives
   (`health_check.key_ledger` in `service-inventory.json`), what the two categories mean, and how a
   key gets adjudicated or excluded.
2. Document each of the four **new** keys and why it exists — especially `last_integrity_check_utc`,
   whose purpose (detecting that verification *stopped*, as distinct from "did not run today") is the
   least obvious and the one a future reader will most likely mistake for redundant with
   `integrity_check_run`.
3. Update the existing schema/field documentation: fourteen keys, `schema_version: 2`. Check for and
   correct any stale claim about the field list — a stale enumeration is precisely the rot this
   mission is about, and leaving one here would be self-refuting.
4. **State the drift caveat prominently**, not in a footnote: the ledger is enforced against the repo
   copy; the live producer is installed manually; the guarantee is void while `backup-script-drift`
   reports the copies diverged. Include the command to check it.
5. Add a short "what this does not cover" note: the canary's own liveness is self-observed, so a
   stopped runner cannot report itself (spec R-001), and the other 16 pointer components have no
   ledger (#937).

### T031 — Navigation docs [P]

**Steps**:
1. Consult `docs/design/architecture/data/signal-to-doc-map.json` for the canonical doc targets for
   this change class. Filter for `match.source == "mission-architecture-impact"` and the classes that
   fit: `runbook-modified`, and `service-added-or-modified` if the inventory change qualifies.
2. Update whatever that map names — typically `docs/INDEX.md` and `docs/DEVELOPER_PORTAL.md`.
3. Do **not** guess the targets. This lookup exists because navigation docs are routinely missed; #492
   is the precedent that motivated formalising it.

### T032 — The operator handoff

**Purpose**: The producer change does not reach office2 by itself, and the mission is not complete
until it does.

**Steps**:
1. Add a clearly-marked operator section to the runbook containing the exact install command:

   ```bash
   ssh office2-kgale
   ```

   ```bash
   sudo install -m 755 -o root -g root ~/kg-automation/scripts/office2/restic-backup.sh /data/services/backup/scripts/backup.sh
   ```

2. State **why** it is manual, with the facts: `/data/services/backup/scripts/` is `root:root
   drwxr-xr-x`, felix-deployer runs as `claude`, and `claude` has no passwordless sudo. Without the
   reason, someone will later "fix" this by trying to automate it and be puzzled when it fails.
3. State the Tier-2 pre-flight: confirm a Restic snapshot ≤24 h old before installing.
4. Give the verification steps: `backup-script-drift` reports converged, and the next real run emits
   all fourteen keys.
5. Note that until this is done, the deployed producer emits ten keys while the ledger declares
   fourteen — so the **live** component will read unhealthy on the absent adjudicated keys. That is
   correct behaviour (absence is unhealthy by design) but it will look alarming, and an operator who
   is not warned will think the mission broke the backup.

   ⚠️ **This is a real sequencing consequence — call it out in the runbook and in the mission
   close-out.** Merging the repo change without promptly installing the producer produces a live alert.

### T033 — Mission close-out records

**Steps**:
1. Prepare the merge-commit record lines the charter requires:
   - `Rebaseline: not required — no audited surface touched`. Verify with
     `tooling/scripts/check_audited_surface_drift.py` against the mission's full diff rather than
     copying this line on trust.
   - The live-verification record: the charter's gate is a **defined and recorded** verification, and
     the plan's post-merge operator canary is that definition. Record its outcome, not just its
     existence.
2. Draft the closing comment for #934: what shipped, what remains open (spec R-001, the unwatched
   alerter), and the follow-up (#937).
3. Add a note to #913 that the shared mechanism is now available and where its reuse entry point is
   (`tests/canary/ledger_reconcile.py` plus `scripts/canary/ledger.py`), so the office4 build consumes
   rather than reimplements.

## Branch Strategy

`feat/934-pointer-key-ledger`, `single_branch`. Work in the lane workspace provided.

## Test Strategy

No new tests. Docs CI (`validate_docs.py`) gates frontmatter compliance and the secret scan on every
commit; that is the applicable check. Verify locally before finishing:

```bash
.venv/bin/python tooling/scripts/validate_docs.py
```

## Definition of Done

- [ ] The runbook explains the ledger, the four new keys, and the fourteen-key schema-2 document.
- [ ] The drift caveat is prominent, with the command to check it.
- [ ] The "what this does not cover" note names the self-observation gap and #937.
- [ ] The operator install section carries the exact command, the reason it is manual, the Tier-2
      pre-flight, and the verification steps.
- [ ] The pre-install live-alert consequence is called out.
- [ ] Navigation docs updated per `signal-to-doc-map.json` — looked up, not guessed.
- [ ] Close-out records drafted, with the rebaseline line **verified** rather than assumed.
- [ ] `validate_docs.py` passes.

## Risks and Review Guidance

1. **Check the guarantee is not overstated.** If the runbook says the ledger makes it impossible to
   forget a field, reject — it makes *silently* forgetting impossible. That distinction is the
   mission's own honesty test and the spec had to be corrected for getting it wrong.
2. **Check the drift caveat is present and prominent.** Its absence was a finding against the plan; a
   reader who does not know the ledger binds the repo copy will over-trust it.
3. **Check no stale field enumeration survives.** Grep the runbook for the old ten-key list and for
   `schema_version` claims.
4. **Check the navigation-doc targets were looked up** in `signal-to-doc-map.json`, not guessed.
5. **Check the rebaseline line was verified** with the tool against the real diff. Copying it from the
   plan is exactly the proxy-inference failure this mission keeps finding.
