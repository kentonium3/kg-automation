# Quickstart: Atomic inbox-file finalize helper

## What it does

Finalizes one routed inbox file in a single atomic, idempotent step: marks
frontmatter `status: processed`, moves it to `02-Inbox-Processed/`, and appends a
daily-log line. Replaces the agent's fragile inline edit + move + log calls.

## Run it

```bash
# From repo root (paths resolved from scripts/vault/paths.json):
python3 scripts/inbox/finalize_inbox_file.py "/abs/path/01-Inbox/Inbox 2026-06-24 0915.md" \
  --routed-by felix-admin-capture
```

Success prints a single JSON line and exits 0:

```json
{"finalized": true, "steps_executed": ["status", "move", "log"], "file_final_path": ".../02-Inbox-Processed/Inbox 2026-06-24 0915.md"}
```

Re-running on the same (now finalized) file is safe: exit 0, no duplicate log line.

## Exit codes (for the calling agent)

- `0` — done (or already done) → record complete
- `1` — validation defect (bad path / missing / malformed frontmatter) → do not retry, surface
- `2` — filesystem error (perms / cross-FS) → surface for operator, do not mark complete

## Run the tests

```bash
cd ~/repos/kg-automation
pytest tests/inbox/test_finalize_inbox_file.py -v
```

Tests run against a hermetic tmp vault (registry path overridden), covering all
eight scenarios including atomicity, idempotency, and error surfacing.

## Deploy to office2

Delivered via the manifest pipeline: `deploys/queued/finalize-inbox-file.yaml`
makes the helper present on office2 and records the felix-admin-capture
standing-orders cutover. No rebaseline required (the only audited surface is the
agent `AGENTS.md`, which the security monitor does not hash) — record that
reasoning at merge.
