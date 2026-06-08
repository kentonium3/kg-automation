# Contract: Helper CLI Surface

**Module**: `scripts/openclaw/deploy/deploy_agent_prompts.py`
**Invocation form**: `python3 -m scripts.openclaw.deploy.deploy_agent_prompts` (MANDATORY per NFR-005 and `[[feedback_helper_m_invocation_form]]`)
**Working directory**: `/home/claude/kg-automation` (set by systemd `WorkingDirectory`; also the assumed cwd for manual invocation)

## Command-line interface

```
python3 -m scripts.openclaw.deploy.deploy_agent_prompts [--dry-run] [--agent SLUG]
```

### Flags

| Flag | Type | Default | Behavior |
|---|---|---|---|
| `--dry-run` | bool flag | false | Compute drift; print one line per drift-candidate to stdout; emit NO audit log entries; do NOT modify any deployed file; do NOT run `git pull`. Exit 0 regardless of drift count. |
| `--agent SLUG` | str | (all in-scope agents) | Restrict iteration to one agent. SLUG must match a key under `services[openclaw].agents.*`. If SLUG is unknown, exit code 3 (validation error) with stderr message. |

### Exit codes

| Code | Meaning | Conditions |
|---|---|---|
| 0 | Success | `git pull --ff-only` succeeded (or `--dry-run` skipped it), all per-file copies succeeded (or no drift was present). |
| 1 | Partial failure | `git pull` succeeded but one or more per-file copies failed. Audit log contains `error` entries; deployed files are in a partially-updated state (atomically per file, not per agent). |
| 2 | Git pull failed | `git fetch` or `git pull --ff-only origin main` returned non-zero. NO file copies attempted. Audit log contains exactly one `git_pull_failed` entry plus the tick summary. |
| 3 | Validation error | `--agent SLUG` references an unknown slug, OR `service-inventory.json` missing/unreadable, OR `/home/claude/kg-automation` missing/not a git clone. NO audit log entries. NO file modifications. Stderr message describes the error. |

## stdout / stderr discipline

- **stdout**: Only used in `--dry-run` mode. One line per drift-candidate file in the format:
  ```
  DRIFT <agent_slug> <filename> src_md5=<hex> dst_md5=<hex|absent>
  ```
  In non-dry-run mode, stdout is silent.
- **stderr**: Used for validation errors (exit code 3) and unexpected exceptions. Format is unconstrained (human-readable). Normal operation writes nothing to stderr.
- **journal**: When invoked by the systemd service unit, stdout and stderr both route to the journal (`StandardOutput=journal`, `StandardError=journal`). Operators read with `journalctl --user -u agent-prompt-sync.service`.

## State mutations

| Path | Action | Conditions |
|---|---|---|
| `/home/claude/kg-automation/.git/` | git fetch / git pull --ff-only | Every non-dry-run tick |
| `/data/services/openclaw/<deploy-dir>/<filename>` | atomic write (temp + os.replace) | When src_md5 != dst_md5; never in `--dry-run` |
| `/data/services/openclaw/deploy/agent-prompt-sync.jsonl` | append one or more lines | Every non-dry-run tick; never in `--dry-run` |
| `/data/services/openclaw/deploy/` | mkdir -p | Only on first run when missing; harmless if already present |

No other paths are written. No paths are deleted. No paths are renamed.

## Invariants checked at process start

1. CWD must contain `.git/` (we're in a git checkout). On failure, exit 3.
2. `docs/design/architecture/data/service-inventory.json` exists and parses as JSON. On failure, exit 3.
3. The parsed JSON contains a `services` array with an entry named `openclaw` containing an `agents` map. On failure, exit 3.
4. If `--agent SLUG` was passed, SLUG is a key in the agents map. On failure, exit 3.

## Test contract

| Test | Asserts |
|---|---|
| `test_parse_args_defaults` | Empty argv → dry_run=False, agent=None |
| `test_parse_args_dry_run` | `["--dry-run"]` → dry_run=True |
| `test_parse_args_agent` | `["--agent", "felix-admin-capture"]` → agent="felix-admin-capture" |
| `test_parse_args_both` | `["--dry-run", "--agent", "felix-admin-capture"]` → dry_run=True, agent="felix-admin-capture" |
| `test_main_validation_no_git_dir` | tmp_path with no `.git/` → exit 3, no audit log written |
| `test_main_validation_no_service_inventory` | tmp_path with `.git/` but no service-inventory.json → exit 3 |
| `test_main_validation_unknown_agent` | `--agent does-not-exist` → exit 3 |
| `test_main_git_pull_failed_exit_2` | git_pull mocked to return non-zero → exit 2, audit log contains `git_pull_failed` entry, no `copy` entries |
| `test_main_no_drift_exit_0` | All MD5s match → exit 0, audit log contains only `skip` entries plus tick_summary |
| `test_main_drift_copied_exit_0` | Source modified → exit 0, audit log contains one `copy` entry for the modified file plus skips for others |
| `test_main_per_file_failure_exit_1` | Atomic copy mocked to raise OSError on one file → exit 1, audit log contains the `error` entry plus successful actions for the rest |
| `test_main_dry_run_no_mutations` | `--dry-run` with drift present → exit 0, stdout has DRIFT line, no audit log lines, no deployed file changes |

## Backwards-compatibility commitment

This contract is the externally observable surface of the helper. Changes to flag names, exit codes, or audit-log shape are breaking changes and must ship as a separate mission with a migration note in the runbook.
