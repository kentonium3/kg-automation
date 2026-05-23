# Contract: enrichment CLI surfaces

**Mission**: `tasker-jsonl-migration-01KSB5XV`

## record_completion

Mirrors `scripts/escalation/record_completion.py` API. Adapted state vocabulary.

```bash
python3 -m scripts.enrichment.record_completion \
  --task-id <int> \
  --state {proposed,confirmed,skipped,declined} \
  --source {agent,reconcile,backfill,operator_repair} \
  [--note "free text"] \
  [--idempotent] \
  [--no-vikunja] \
  [--base-url URL] \
  [--token-path PATH]
```

Exit codes: 0 success / 1 Vikunja error (atomic-contract failure) / 2 JSONL append error (soft-fail per Q10) / 3 invalid args.

## reconcile_completions

Mirrors escalation's reconcile pattern.

```bash
python3 -m scripts.enrichment.reconcile_completions \
  [--since YYYY-MM-DD]    # default: 2026-04-11
  [--dry-run]
  [--ledger-path PATH]
  [--base-url URL]
  [--token-path PATH]
```

Idempotent (key on task_id + state + comment_timestamp; duplicates skipped).
Exit codes: 0 success / 1 Vikunja error / 3 invalid args.

## cutover_tasker

One-shot operator script per `cutover_362.py` pattern.

```bash
python3 scripts/openclaw/helpers/cutover_tasker.py [--dry-run] [--force]
```

Steps:
1. Deploy SKILL.md (cp from repo to /home/claude/.openclaw/skills/task-intelligence/)
2. Deploy AGENTS.md (cp from repo to /data/services/openclaw/tasker-agent/)
3. Run reconcile_completions (backfill JSONL)
4. Write marker at ~/.config/openclaw/cutover-310.done

Idempotent (marker check, --force override).
Exit codes: 0 success/no-op / 1 filesystem error / 2 reconcile failed / 3 invalid args.
