# Inbox Pre-Scan Helper

Pure-Python helper that classifies files in the Obsidian vault inbox and
archives stale `processed` notes. Invoked by the OpenClaw inbox-processing
agent before it reads the inbox, and by the deploy wrapper during preflight.

## Files

- `prescan.py` — the helper itself (CLI, no LLM, PyYAML + stdlib only)

## Invocation

```bash
python3 scripts/inbox/prescan.py              # full run
python3 scripts/inbox/prescan.py --self-check # preflight: verify paths only
```

## Contract

- **stdin**: not read
- **stdout**: single-line JSON `PrescanResult` (exit 0) or `{"self_check": "ok", ...}` in `--self-check` mode
- **stderr**: human-readable log lines
- **exit 0**: success (helper may still report non-fatal warnings)
- **exit 1**: fatal error (registry missing, inbox paths unresolvable, etc.)

## Behavior

1. Resolve `{{VAULT_INBOX}}` and `{{VAULT_INBOX_PROCESSED}}` from
   `scripts/vault/paths.json`.
2. Walk `{{VAULT_INBOX}}` non-recursively, reading `.md` files.
3. For each file, parse the YAML frontmatter and classify by `status` + mtime:
   - `unprocessed` → hand to agent
   - `processed` and mtime ≤ 7 days → leave in place silently
   - `processed` and mtime > 7 days → move to `{{VAULT_INBOX_PROCESSED}}`
   - missing/unknown/malformed → treat as unprocessed (safety default)
4. Emit a `PrescanResult` JSON blob on stdout.
5. Append a run entry to `inbox-prescan-YYYY-MM-DD.md` under the agent log dir.

## Environment overrides (tests only)

- `PRESCAN_REGISTRY_PATH` — alternate path to `paths.json`
- `PRESCAN_LOG_DIR` — alternate directory for the daily log file

## Troubleshooting

- `Vault registry not found` — `scripts/vault/paths.json` is missing; run the
  vault deploy or check the deploy wrapper.
- `Inbox path does not exist` — registry resolves to a directory that isn't
  present on this host. Usually a sync/mount issue.
- `destination already exists` warning — a previous run left a file in
  `{{VAULT_INBOX_PROCESSED}}` with the same name; inspect manually.
- Daily log written to `/tmp` — the primary log dir
  (`/home/claude/second-brain/agents/logs`) isn't writable; run on office2
  or set `PRESCAN_LOG_DIR` to a writable path.

## Guardrails

- Never reads or writes inside any `_private/` subdirectory (C-001).
- Never modifies file contents including frontmatter (C-002).
- Never imports from `anthropic`, `openclaw`, or any LLM SDK (NFR-002).
- Uses `yaml.safe_load` exclusively; never `yaml.load` (NFR-004).
