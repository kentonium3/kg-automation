# Quickstart: verify the coverage checks

## Offline (any machine with the repo)

```bash
python3 -m pytest scripts/office2/felix_health_check/tests tests/deploy/test_deploy_health_check_coverage.py -q
```

## Read-only against live office2 state (pre-merge integration check, form (a))

Evaluate coverage only, with no script run, no alert and no record write. The branch is shipped from office4 as a tarball into a scratch directory, so the felix-deployer checkout on office2 (which tracks `main`) is never touched:

```bash
git archive fix/canary-deadman-backup-coverage | ssh office2-claude 'd=$(mktemp -d /dev/shm/hcc.XXXXXX) && tar -x -C "$d" && (cd "$d" && python3 scripts/deploy/deploy-health-check-coverage.py --dry-run); rm -r -- "$d"'
```

Expected: a `coverage_checks` JSON line with `felix-canary` and `restic-backup` both `ok`; `would_retire` naming `~/helper-scripts/health-check.sh`.

## Live, post-merge (form (b): the manifest does this)

```bash
ssh office2-claude 'systemctl --user start felix-health-check.service && jq "{status, script_path, coverage_checks}" /data/services/openclaw/felix-health-check/last-run.json'
```

Expected: `status` is `ALL_HEALTHY` (or `FAILURES_DETECTED` for a real fault), `script_path` is under `/home/claude/kg-automation/`, and two `coverage_checks` entries; `test ! -e ~/helper-scripts/health-check.sh`.
