# Quickstart: verify the cause shows up

## Locally

```bash
.venv/bin/python3 -m pytest tests/office2/restic_backup tests/canary tests/office2/felix_health_check tests/architecture/test_key_ledger_rules.py -q
.venv/bin/python3 tooling/scripts/validate_architecture_data.py
```

## On office2 after felix-deployer pulls the merge (read-only, as claude)

1. Next canary tick: `restic-backup` outcome unchanged, no `tick_error`.
2. In-memory evaluation of a synthetic not-mounted pointer against the live inventory (no files written):

   ```bash
   ssh office2-claude 'cd /home/claude/kg-automation && python3 -c "…evaluate synthetic pointer…"'
   ```

   Expect evidence ending `; cause: backup drive /mnt/backups is not mounted`.
3. Felix health-check coverage line for today's real pointer: unchanged text, because the live producer has no `failure_reason` yet.

## Operator handoff (Kent)

Install the new `backup.sh` per `docs/runbooks/restic-backup-ops.md` § Operator handoff. Then confirm that `backup-script-drift` reports `converged`, and that the next 04:00 pointer carries `"failure_reason": null`.
