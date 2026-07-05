# Quickstart: Observation-Digest Log Repoint & Decommission

How to build, test, deploy, and verify this mission. All office2 access is `ssh office2-claude`.

## Local development / tests

```bash
cd /Users/kentgale/repos/kg-automation
# Config default unit test (FR-001): resolved log_dir is the vault path under any HOME
pytest scripts/openclaw/observation/tests -k log_dir -q
# Migrator + shebang regression tests (NFR-003, NFR-004)
pytest scripts/deploy -k observation -q
```

## Dry-run both entrypoints (safe; no mutation)

```bash
# Phase 1 (migrate-only): JSON plan of jsonl to union-merge; no delete
ssh office2-claude 'cd /home/claude/kg-automation && python3 scripts/deploy/migrate-observation-logs.py --dry-run'
# Phase 2 (decommission): JSON plan + precondition results; no delete
ssh office2-claude 'cd /home/claude/kg-automation && python3 scripts/deploy/decommission-observation-stray-tree.py --dry-run'
```

Expect: JSON plans, no filesystem change, and NO `_private` or any descendant path in output
(only `source_root` appears).

## Deploy — two staged phases (do NOT run destructive steps by hand)

1. Merge the mission to `main` (spec-kitty), land `feat → main` after post-merge Codex review.
2. **Phase 1** — felix-deployer picks up `deploys/queued/NNNN-migrate-observation-logs.yaml`:
   - Tier-2 Restic snapshot gate (`pre`); `migrate-observation-logs.py --apply` (migrate only);
     `post` vault writability; auto-rebaseline. **No deletion.**
   - Verify ≥1 clean digest cycle: new logs under `/home/kgale`, none new under `/home/claude`.
3. **Phase 2** — only after Phase 1 is verified, stage
   `deploys/queued/MMMM-decommission-observation-stray-tree.yaml`:
   - `pre` snapshot gate; `decommission-observation-stray-tree.py --apply`
     (gate → quiesce → final merge → root-only delete → restart timer);
     `post` `test ! -e /home/claude/second-brain`.

## Post-change verification (maps to Success Criteria)

```bash
# SC-001: new raw logs on the vault account, none new on the stray tree
ssh office2-claude 'find /home/kgale/second-brain/agents/logs -name "*.jsonl" -newermt "-20min" | head'
ssh office2-claude 'test ! -e /home/claude/second-brain && echo "SC-003 OK: stray tree absent" || echo "still present"'

# SC-002: spot-check union-merge preserved entries for a migrated agent/date
# (compare pre-migration line counts captured in the deploy record vs post)

# NFR-002: digest timer still active, no missed cycle
ssh office2-claude 'systemctl --user status felix-core-digest.timer | head'
ssh office2-claude 'journalctl --user -u felix-core-digest.service --since "-20min" | grep -i error || echo "no errors"'
```

## Rollback

- Code: revert the `config.py` commit; felix-deployer re-pulls; `log_dir` reverts.
- Data: pre-delete Restic snapshot restores runtime cruft; tracked vault content restores from
  `kentonium3/second-brain` origin. If `--no-decommission` was used, nothing destructive ran.

## Arch-doc check (SC-005)

```bash
cd /Users/kentgale/repos/kg-automation
python3 tooling/scripts/validate_docs.py   # architecture-data validator must pass
grep -c "path_retention_note" docs/design/architecture/data/service-inventory.json docs/design/architecture/data/data-flows.json  # #659 notes removed
```
