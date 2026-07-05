# Contract: `migrate-observation-logs.py` CLI + deploy manifest

No REST/GraphQL surface. The mission's contracts are (1) the migrator CLI and (2) the deploy
manifest that invokes it. Both follow the kg-automation helper-script conventions and the #656
migrator precedent.

## Migrator CLI

`scripts/deploy/migrate-observation-logs.py`

### Invocation

- Module form (preferred for tests): `python3 -m scripts.deploy.migrate_observation_logs [flags]`
- Entrypoint form (felix-deployer, via shebang): `/usr/bin/env python3 scripts/deploy/migrate-observation-logs.py [flags]`
  - MUST have the `+x` bit (git mode 100755) and a `sys.path` shim resolving the repo root
    (`_REPO_ROOT = Path(__file__).resolve().parents[2]; sys.path.insert(0, str(_REPO_ROOT))`).

### Flags

| Flag | Default | Meaning |
|---|---|---|
| `--dry-run` | **on** (default) | Report planned actions; no mutation; exit 0. |
| `--apply` | — | Perform migration; then, if preconditions pass, decommission. |
| `--source-root` | `/home/claude/second-brain` | Stray-tree root (the clone to migrate-from + remove). |
| `--vault-logs-dir` | `/home/kgale/second-brain/agents/logs` | Migration target. |
| `--skip-snapshot-gate` | off | Test-only escape hatch; NEVER set in the manifest. |
| `--no-decommission` | off | Migrate logs only; skip the destructive removal (staged rollout). |

### Behavior contract

1. `--dry-run` (default) prints a JSON plan (`{migrate: [...], remove: "<root>", preconditions: {...}}`)
   to stdout and exits **0** with **zero** filesystem side effects (NFR-004).
2. `--apply`:
   - Union-merges `agents/logs/{agent}/*.jsonl` into `--vault-logs-dir` (copy-before-cutover,
     atomic per file). Idempotent.
   - Evaluates preconditions (snapshot ≤24h, recoverability, no-writer). On any failure: emit a
     structured error to stderr and exit **non-zero** WITHOUT removing anything.
   - On all-pass: `rm -rf` the `--source-root` tree. MUST NOT traverse/read/log any `_private`
     path (C-008).
   - Post-checks: source absent; vault dir ownership `claude` / mode `0640` files as applicable.
3. Idempotent re-run after success: no-op, exit 0 (FR-005).

### Exit codes

| Code | Meaning |
|---|---|
| 0 | Success (dry-run, applied, or convergent no-op) |
| non-zero | Precondition failed / migration error / abort-before-delete (nothing destructive ran) |

### stdout / stderr

- stdout: single JSON object (plan in dry-run; result summary in apply). No `_private` paths ever.
- stderr: structured `_emit`-style progress + errors.

## Deploy manifest

`deploys/queued/NNNN-migrate-observation-logs-and-decommission.yaml`

- `tier: 2`
- `pre`: Restic snapshot gate (`verify_restic_recent`, ≤24h).
- `apply`: run `scripts/deploy/migrate-observation-logs.py --apply`.
- `post`:
  - `test ! -e /home/claude/second-brain` (decommission verified)
  - vault log dir present with expected ownership/mode
- `audited_surface: true` (deploy-pipeline) → felix-deployer auto-rebaseline; record on deploy.

## Regression test contract (NFR-004)

A test MUST assert, for the entrypoint:
- file mode has the executable bit,
- the `sys.path` shim is present,
- invoking the script path with `--dry-run` via subprocess exits 0 and mutates nothing,
- the JSON plan never contains a `_private` substring.
