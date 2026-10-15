# Contract: installed-file report (`FELIX_DEPLOY_INSTALLED_REPORT`)

**Producer**: `scripts/deploy/lib/userunits.install_units`, and in future any deploy-library installer.
**Channel**: the environment variable `FELIX_DEPLOY_INSTALLED_REPORT`, holding the absolute path of a file. It is set only for an entrypoint's `--apply`, by `scripts/deploy/lib/apply.dry_run_then_apply_gate`.
**Consumer**: `apply` (reader) → `felix-deployer/_tick` → `rebaseline.baselines_for_installed_paths` (mapper).

## Format

UTF-8 JSON Lines, append-only. One object per installed file whose bytes changed:

```json
{"path": "/home/claude/kg-automation/scripts/sync/systemd/felix-vikunja-sync.timer"}
```

- `path` is a string: the absolute, resolved path of the **source** (repository) file whose bytes were written to the host.
- Lines are written only after the file has landed (`os.replace` succeeded).
- Unchanged (byte-identical) installs and dry runs write nothing.
- No other keys are required. Readers ignore unknown keys.

## Producer rules

- Variable unset or empty: write nothing, with no other behavior change.
- A report write failure never fails the install; the report is advisory.

## Reader rules (`apply`)

- Reject the file wholesale above 1 MiB, with a warning.
- Parse per line. A line that is not a JSON object, has no `path`, or has a non-string `path` is skipped with a warning.
- Stop after 10,000 accepted entries, with a warning.
- Return `details["installed_paths"]` (deduplicated, order preserved) and `details["installed_report_warnings"]`, on `--apply` success and failure alike.
- Delete the report directory afterwards.

## Mapper rules (`rebaseline.baselines_for_installed_paths`)

- Resolve the path. Reject anything not inside `repo_root`, after resolving symlinks.
- Make the path repo-relative and pass it to `match_surfaces(paths, registry)`, the same function and registry read `observe` uses.
- Union the matched surfaces' `affected_baselines`. A path that matches nothing contributes nothing (C-002).
- An unreadable registry gives no baselines plus a warning; it never raises.
