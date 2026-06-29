# Quickstart — Atomic in-place inbox finalize

## Run the finalize helper

```bash
cd /Users/kentgale/repos/kg-automation           # repo root (module import form)
python3 -m scripts.inbox.mark_processed --path "$VAULT/notes/01-Inbox/Inbox 2026-06-28 0915.md"
echo "exit=$?"
```

Expected on a fresh note:
```
{"finalized": true, "already_processed": false, "status": "processed", "file_final_path": ".../01-Inbox/Inbox 2026-06-28 0915.md"}
exit=0
```
Re-run → `"already_processed": true`, `exit=0`. The note stays in `01-Inbox/`.

## Verify the failure surfaces (the incident class)

```bash
chmod 0444 "$NOTE"                                 # make the note unwritable
python3 -m scripts.inbox.mark_processed --path "$NOTE"; echo "exit=$?"
# stderr: {"error": "fs_error", "detail": "<OSError ...>"}   exit=2
# the note is unchanged (still status: unprocessed)
```

## Run the tests

```bash
cd /Users/kentgale/repos/kg-automation
python3 -m pytest tests/inbox/ -v                  # full inbox suite
python3 -m pytest tests/inbox/ -k mark_processed -v
```

Covered outcomes: happy-path write, idempotent no-op, validation failures (missing
file / outside inbox root / bad frontmatter), filesystem error (exit 2, original
uncorrupted), privacy refusal (exit 3). The perm-denied test skips when the runner
is root.

## Deploy (informational — handled by the pipeline, not run here)

- `scripts/inbox/mark_processed.py` reaches office2 via the clone's `git pull`.
- The `felix-admin-capture/AGENTS.md` Step 5c edit deploys via the **pull-based
  agent-prompt-sync** service (slug `felix-admin-capture` → dir `inbox-agent`),
  NOT a `deploys/queued/` felix-deployer manifest.
- Rebaseline: **not required** — the agent-prompt surface is not hashed by
  `audit.sh` (gap #621).
