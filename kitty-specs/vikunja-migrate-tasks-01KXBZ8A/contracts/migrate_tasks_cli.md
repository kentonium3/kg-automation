# Contract: `migrate_tasks.py` CLI

Invocation (office2, as kent):

```
python3 -m scripts.vikunja.migrate_tasks [options]
```

## Options

| Flag | Default | Meaning |
|------|---------|---------|
| `--manifest PATH` | `scripts/vikunja/task_migration_manifest.yaml` | routing manifest |
| `--token-file PATH` | `/data/services/openclaw/secrets/vikunja-api-kent` | kent token ONLY; the felix-bot path is refused |
| `--apply` | off (dry-run) | execute the plan; without it, print the plan and exit 0 |
| `--backup-confirmed` | off | required for any deletion (task or project); absent → deletions raise |
| `--json` | off | emit the plan/summary as JSON instead of human text |

## Behavior

- **Dry-run (default)**: fetch live state, compute + print the plan (moves,
  labels, deletes, skips, blocks), exit 0. No mutations.
- **`--apply`**: run the plan (moves → labels → task-deletes → project-deletes,
  children first). Print applied summary.
- Refuses up front if `--token-file` resolves to the felix-bot token path.
- Refuses (non-zero) if any doomed project is non-empty (FR-006).
- Refuses (non-zero) if the plan contains a delete and `--backup-confirmed` is
  absent (NFR-002).

## Exit codes

| code | meaning |
|------|---------|
| 0 | dry-run printed, or apply succeeded, or nothing to do (idempotent) |
| 1 | fail-loud: non-empty doomed project, wrong identity, missing backup flag, owner mismatch, or Vikunja error |

## stdout (human)

```
PLAN (dry-run)
  moves:    30   labels: 11   task-deletes: 2   project-deletes: 6   skipped: 0
  move   #42  Everyday(2) -> Personal(20)   'Return lawn service contract...'
  label  #14  t:habit                        'Wake at 5:00 AM'
  delete task #89                            'TEST-679C verification event'
  delete project 4 'Someday'  (empty: ok)
  ...
```

## stdout (`--json`)

```json
{
  "mode": "apply",
  "moved": 30, "labeled": 11, "tasks_deleted": 2, "projects_deleted": 6,
  "skipped": 0, "blocked": [],
  "actions": [ {"kind":"move","task":42,"from":2,"to":20}, ... ]
}
```
