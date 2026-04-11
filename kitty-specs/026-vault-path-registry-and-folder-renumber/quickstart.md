# Quickstart: Mission 026 Execution

**Mission:** `026-vault-path-registry-and-folder-renumber`
**Audience:** The operator executing this mission
**Purpose:** Condensed end-to-end runbook. Use this as a driver's seat reference during execution. For full detail, see `plan.md`, `contracts/`, and `research.md`.

## Pre-flight (before WP01)

1. **Confirm workspace is clean.**
   ```bash
   cd /Users/kentgale/repos/kg-automation
   git status
   # Expect: on main, no uncommitted changes
   ```

2. **Confirm spec-kitty workflow state is good.**
   ```bash
   spec-kitty status --mission 026-vault-path-registry-and-folder-renumber
   # Expect: mission exists, phase: plan-complete, ready for tasks
   ```

3. **Confirm the inbox is in a quiescent state.**
   ```bash
   ssh office2-claude 'ls /home/kgale/second-brain/notes/00-Inbox | wc -l'
   # Note the count; zero unprocessed is ideal but not required
   ```

4. **Confirm Obsidian wikilink auto-update works on your system.** If you have NEVER renamed a top-level vault folder via Obsidian UI before, do a practice run on a throwaway folder first. This is the one assumption the mission depends on heavily (validated in discovery but worth sanity-checking).

5. **Confirm Restic backup status.** Skip for now — WP05 will enforce this as a hard gate.

## Execution order

The mission is strictly sequential. Each WP gates on the previous one. Do not skip ahead.

### WP01 — Registry Extension and Deploy Wrapper

**What you're doing:** Extending `paths.json` with all 10 logical names, extending `targets.json` with all migration targets, creating `deploy-f026.sh`.

**Key commands:**
```bash
# After editing paths.json, verify it parses and resolves correctly
python3 scripts/vault/resolver.py inbox_processed
python3 scripts/vault/resolver.py system
python3 scripts/vault/resolver.py _private   # should fail with UnknownPathError

# Verify the wrapper
bash scripts/deploy/deploy-f026.sh --help
```

**Gate:** All checks in `contracts/verification-contract.md` § WP01 pass.

### WP02 — Code Migration

**What you're doing:** Converting every hardcoded-path file to a `.tmpl` source with `{{VAULT_*}}` markers. Running `deploy.py --apply` to produce resolved output files.

**Key commands:**
```bash
# Audit hardcoded references BEFORE conversion
grep -rn "00-Inbox\|01-Constitution\|02-Growth\|03-Health\|04-Business\|05-Finance\|06-Journal\|07-Resources" \
  scripts/ ai-agents/ CLAUDE.md \
  | grep -v "_private"   # exclude the CLAUDE.md boundary line

# Convert each file to a .tmpl, add to targets.json, then:
python3 scripts/vault/deploy.py   # dry-run
python3 scripts/vault/deploy.py --apply   # apply

# Verify zero hardcoded residue after conversion
grep -rn "00-Inbox\|01-Constitution\|02-Growth\|03-Health\|04-Business\|05-Finance\|06-Journal\|07-Resources" \
  scripts/ ai-agents/ CLAUDE.md \
  | grep -v "_private" \
  | grep -v "\.tmpl:"
# Expect: zero matches
```

**Gate:** All checks in `contracts/verification-contract.md` § WP02 pass.

### WP03 — Documentation Synchronization

**What you're doing:** Updating every architecture JSON, markdown view, runbook, INDEX, and roadmap to match the new folder state. Creating the new migration runbook.

**Key commands:**
```bash
# Audit doc references
grep -rn "00-Inbox\|01-Constitution\|02-Growth\|03-Health\|04-Business\|05-Finance\|06-Journal\|07-Resources" \
  docs/ \
  | grep -v "docs/archive/" \
  | grep -v "docs/func-spec/"

# Update each file manually, ensuring JSON files get updated_by: #152

# Validate docs
python3 tooling/scripts/validate_docs.py
```

**Gate:** All checks in `contracts/verification-contract.md` § WP03 pass.

### WP04 — Pre-Rename Deploy + Refactor-Fidelity Checkpoint

**What you're doing:** Proving the refactor is transparent. Run the pre-rename deploy, then compare agent behavior before and after. Zero behavior change expected.

**Key commands:**
```bash
# Capture baseline BEFORE deploy
ssh office2-claude 'cd /data/services/openclaw/inbox-agent && ./run-once.sh' > /tmp/026-capture-baseline.log
ssh office2-claude 'cd /data/services/openclaw/tasker-agent && ./run-once.sh' > /tmp/026-tasker-baseline.log
# (Exact commands depend on the one-shot invocation pattern used by your agents — may need adjustment during WP01 audit)

# Run the pre-rename deploy
bash scripts/deploy/deploy-f026.sh --apply --mode pre-rename

# Re-capture after deploy
ssh office2-claude 'cd /data/services/openclaw/inbox-agent && ./run-once.sh' > /tmp/026-capture-postdeploy.log
ssh office2-claude 'cd /data/services/openclaw/tasker-agent && ./run-once.sh' > /tmp/026-tasker-postdeploy.log

# Diff — expect no semantic differences
diff /tmp/026-capture-baseline.log /tmp/026-capture-postdeploy.log
diff /tmp/026-tasker-baseline.log /tmp/026-tasker-postdeploy.log
```

**Gate:** All checks in `contracts/verification-contract.md` § WP04 pass. Diffs contain only timestamp / run-ID differences, nothing semantic. **Explicit operator authorization required before WP05.**

### WP05 — Folder Rename + Post-Rename Deploy + Smoke Tests

**What you're doing:** The risky window. Follow this order carefully. Every step gates on the previous one's verification.

#### Pre-flight

```bash
# Tier 2 backup check
ssh office2-claude 'restic snapshots --last 1'
# Confirm a snapshot ≤24 hours old. If older, trigger a new one:
# ssh office2-claude '/path/to/restic-backup-script.sh'
```

#### Pause cron

```bash
ssh office2-claude 'crontab -l'   # see current state
ssh office2-claude 'crontab -e'   # comment out felix-admin-capture entry
ssh office2-claude 'crontab -l'   # verify commented out
```

#### Create processed-inbox folder

```bash
# Create directly on office2 (or on Mac if sync propagates faster)
ssh office2-claude 'mkdir -p /home/kgale/second-brain/notes/02-Inbox-Processed'
ssh office2-claude 'touch /home/kgale/second-brain/notes/02-Inbox-Processed/.gitkeep'
# Wait for Obsidian Sync to propagate if creating on Mac
```

#### Rename folders via Obsidian UI

**Do this in Obsidian on your Mac.** One folder at a time. After each rename, verify in Obsidian that wikilinks still resolve.

Rename order:
1. `00-Inbox` → `01-Inbox`
2. `01-Constitution` → `03-Constitution`
3. `02-Growth` → `04-Growth`
4. `03-Health` → `05-Health`
5. `04-Business` → `06-Business`
6. `05-Finance` → `07-Finance`
7. `06-Journal` → `08-Journal`
8. `07-Resources` → `09-Resources`

(`00-System` stays as-is. `02-Inbox-Processed` is already in place from the previous step.)

After all renames: wait for Obsidian Sync to propagate to office2. Verify:
```bash
ssh office2-claude 'ls /home/kgale/second-brain/notes/'
# Expect: 00-System, 01-Inbox, 02-Inbox-Processed, 03-Constitution, 04-Growth, 05-Health, 06-Business, 07-Finance, 08-Journal, 09-Resources
```

#### Update registry

Edit `scripts/vault/paths.json` — change every path value to point at the new folder names.

Edit `CLAUDE.md` (or `CLAUDE.md.tmpl`) — update the `_private/` boundary line from `02-Growth/_private/` to `04-Growth/_private/`.

Commit the changes to the mission's branch.

#### Post-rename deploy

```bash
bash scripts/deploy/deploy-f026.sh --apply --mode post-rename
```

The wrapper will:
1. Run `deploy.py --apply`
2. Grep for stale literals (expect zero)
3. Grep for unreplaced markers (expect zero)
4. Smoke-test `felix-admin-capture` (expect clean run)
5. Smoke-test `felix-admin-tasker` (expect clean run)
6. Verify wikilink integrity
7. Re-enable the cron
8. Verify the cron fires correctly

If any step fails, the wrapper halts with a loud failure message and does NOT re-enable the cron. Follow the rollback section of the WP05 work package file.

#### Cron resume verification

```bash
ssh office2-claude 'crontab -l | grep felix-admin-capture'
# Expect: line is NOT commented out
# Wait for the next natural cron tick (or run manually) and verify the agent succeeds
```

**Gate:** All checks in `contracts/verification-contract.md` § WP05 pass. NFR-004: total risky-window duration ≤90 minutes. **Explicit operator authorization required before WP06.**

### WP06 — Cross-Repo FR-6 + Mission Close-Out

**What you're doing:** A single cross-repo operation in the `~/second-brain/` repo, then final mission verification.

#### Cross-repo edit (in `~/second-brain/`, NOT in `kg-automation`)

```bash
# Switch to the second-brain repo
cd ~/second-brain
git status   # confirm clean

# Add the ignore pattern
echo '' >> .gitignore
echo '# Privacy boundary — constitutional hard limit' >> .gitignore
echo '_private/' >> .gitignore

# Verify the pattern matches (test with a hypothetical path)
git check-ignore -v _private/test.md
# Expect: .gitignore:<line>:_private/  _private/test.md

# Idempotent cached removal (no-op today — _private/ is empty)
git rm --cached -r _private/ 2>/dev/null || true

# Commit and push
git add .gitignore
git commit -m "chore: gitignore _private/ privacy boundary (kg-automation mission 026)"
git push

# Verify final state
git status
# Expect: clean, branch in sync with origin
```

#### Return to kg-automation

```bash
cd /Users/kentgale/repos/kg-automation
```

#### Final mission verification

Open `spec.md` and walk through each of the 10 Success Criteria. Check each one off in the WP06 verification contract. Confirm:

- Registry has all 10 logical names
- Zero hardcoded residue (except CLAUDE.md boundary)
- Folders have clean 00–09 ordinal sequence
- `02-Inbox-Processed/` exists and is reachable via registry
- `felix-admin-capture` and `felix-admin-tasker` run cleanly against new paths
- Cron is firing on schedule
- Obsidian wikilinks all resolve
- `_private/` is gitignored in second-brain
- Architecture docs reflect new state
- Mission #149 is unblocked

#### Close the GitHub issue

```bash
gh issue close 152 --repo kentonium3/kg-automation \
  --comment "Closed by mission 026 merge. See kitty-specs/026-vault-path-registry-and-folder-renumber/ for artifacts. #149 is now unblocked."
```

**Gate:** All checks in `contracts/verification-contract.md` § WP06 pass. Ready for `/spec-kitty.merge`.

## Rollback quick reference

| WP | Rollback |
|---|---|
| WP01, WP02, WP03 | `git revert` the WP commits. No runtime state touched. |
| WP04 | Same — `git revert`. Pre-rename deploy is a pure refactor by design. |
| WP05 (pre-redeploy failure) | Obsidian UI rename folders back to original; revert `paths.json`; re-enable cron. |
| WP05 (post-redeploy failure) | Re-run `deploy.py --apply` with reverted `paths.json` to restore old-state agent files; Obsidian UI rename folders back; re-enable cron. |
| WP05 (catastrophic) | Restic restore of the vault to pre-migration snapshot; follow Tier 2 recovery procedure in `docs/runbooks/governance/post-change-verification.md`. |
| WP06 | `git revert` in second-brain repo; trivially reversible. |

## When to stop and ask for help

- Any verification check fails twice in a row
- Obsidian shows unresolved wikilinks after a rename that you cannot immediately diagnose
- Any `deploy-f026.sh` failure you don't understand
- Restic backup verification fails
- Cron re-enable produces errors
- Any step takes longer than expected without clear progress

Default posture: when in doubt, halt and investigate. A paused inbox is an inconvenience; a corrupted vault is an emergency.

## Reference

- `spec.md` — WHAT and WHY
- `plan.md` — HOW at a planning level
- `research.md` — decision records and audit findings
- `data-model.md` — schemas and file contracts
- `contracts/` — interface contracts and acceptance tests
- `docs/runbooks/vault-path-registry-migration.md` — (created in WP03) reusable playbook for future similar migrations
