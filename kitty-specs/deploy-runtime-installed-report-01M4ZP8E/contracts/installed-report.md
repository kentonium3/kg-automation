# Contract: installed-file report (`FELIX_DEPLOY_INSTALLED_REPORT`)

*(Revised 2026-10-15 after the post-plan review.)*

**Owner**: `scripts/deploy/lib/installed_report.py`, the only module that names the variable, writes the format or reads it.
**Producer**: `installed_report.record_installed(source, dest)`, called by deploy-library installers (`userunits.install_units`).
**Channel**: the environment variable `FELIX_DEPLOY_INSTALLED_REPORT`, holding the absolute path of a file. `scripts/deploy/lib/apply.py` sets it for an entrypoint's `--apply` only and **removes** it from every other command's environment.
**Consumers**: `apply` (reads it with `installed_report.read_report`) → `_tick` → `rebaseline.baselines_for_installed_report`.

**Trust model**: the entrypoint runs as the same user as the deployer and is PR-reviewed. The report defends against bugs and mistakes, not against a malicious entrypoint, which could already write anything that user can write.

## Format

UTF-8 JSON Lines, append-only. One object per installed file whose bytes changed:

```json
{"source": "/home/claude/kg-automation/scripts/sync/systemd/felix-vikunja-sync.timer",
 "dest": "/home/claude/.config/systemd/user/felix-vikunja-sync.timer"}
```

- `source` is the absolute, resolved path of the repository file whose bytes were written.
- `dest` is the absolute, resolved path where they landed on the host.
- A line is written only after the file has landed (`os.replace` succeeded).
- Unchanged installs and dry runs write nothing.

## Producer rules

- Variable unset or empty: write nothing.
- A write failure never fails the install. The producer prints exactly one line, `FELIX_DEPLOY_INSTALLED_REPORT_WRITE_FAILED: <reason>`, to stderr. This is the only output the library ever produces, and it is a protocol marker, not a log.

## Reader rules (`read_report`): fail closed, wholesale

The reader opens the file with `O_RDONLY | O_NOFOLLOW | O_NONBLOCK`, and `fstat` must report a regular file. It reads at most 1 MiB + 1 byte and decodes strictly as UTF-8. Every line must be a JSON object with string `source` and `dest`. Blank lines are allowed, and there may be at most 10,000 entries.

**Any** violation rejects the entire report: `{"entries": [], "rejected": true, "warnings": [<why>]}`. A missing file counts as a valid empty report.

`apply` adds a warning when `--apply`'s stderr carries the write-failure marker.

## Mapper rules (`baselines_for_installed_report`): fail closed, wholesale

- A rejected report contributes nothing.
- For **every** entry:
  - the resolved `source` must lie inside `repo_root`;
  - its repo-relative path must match a surface through `match_surfaces`, the same function and registry read `observe` uses;
  - the resolved `dest` must lie inside one of that surface's `host_paths`, with `~` expanded against the deployer's home.
- If any entry fails a check, the whole report contributes nothing, and a warning names the entry.
- A source that matches no surface is not an error. It contributes nothing (C-002).
- A surface with no `host_paths` contributes nothing.
- An unreadable registry gives nothing plus a warning, and never raises.

## Result keys (documented API)

- `apply` `LibResult.details["installed_report"]` = `{"entries", "rejected", "warnings"}`, on every return after `--apply` ran.
- Tick log event `rebaseline_reported` = `{manifest_name, apply_ok, entries, baselines, rejected, warnings, absorbed}`.
