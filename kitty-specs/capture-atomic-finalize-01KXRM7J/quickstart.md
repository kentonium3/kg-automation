# Quickstart: Atomic Capture Finalize

## What this delivers

One command — `python3 -m scripts.inbox.route_and_finalize --kind <k> --source-path <p>` —
that routes a captured note and marks it processed as a single, fail-loud unit. A note can
no longer be marked `processed` without a verified route + routing-log entry. A health rail
surfaces any violation.

## Verify locally (tests)

```
cd /Users/kentgale/repos/kg-automation
python3 -m pytest tests/inbox -q
```

Expected: per-kind finalize tests (success / route-failure / verify-failure / idempotent),
health-rail tests, and the existing #737 calendar regression tests all pass.

## Verify the atomic guarantee (behavioral)

1. **Happy path** — run finalize for each kind against a fixture note; assert the artifact
   exists, the routing-log has an entry, and the note is `status: processed`.
2. **Failure path (the bug this closes)** — force the route to fail (mock a Vikunja error /
   missing task id); assert the note is left `unprocessed`, no `processed_at`, and the error
   is on stdout with a non-zero exit.
3. **Delegated task** — supply a `--task-id` that does not resolve; assert finalize errors and
   leaves the note unprocessed.
4. **Empty note** — `--kind empty`; assert a routing-log entry (kind=empty) is written and the
   note is processed.
5. **Health rail** — inject a note marked `processed` with no routing-log entry; assert
   `prescan` reports a `processed-without-routing-log` anomaly. Confirm empty/needs-review notes
   do NOT trip it.

## Dry-run on office2 (credential-free wiring)

```
ssh office2-claude 'cd /home/claude/kg-automation && python3 -m scripts.inbox.route_and_finalize --kind someday --source-path <abs> --dry-run'
```

## Deploy

- Helpers (`scripts/inbox/*`, `prescan.py`): office2 checkout self-pull (felix-deployer).
- Capture `AGENTS.md`/`TOOLS.md`: `agent-prompt-sync` → `/data/services/openclaw/inbox-agent/`
  (verify md5 parity across the 5 workspace files).
- Live smoke: next inbox tick routes a real note through finalize; confirm the routing log
  gains an entry and the note is processed. Confirm the health rail reports zero anomalies.

## Rollback

Revert the merge commit; helpers self-pull the prior version; re-run `agent-prompt-sync` on the
previous AGENTS.md. mark_processed / route helpers are unchanged in behavior, so partial rollback
is safe.
