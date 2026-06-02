# Quickstart: Remove escalation v1 comment-write parity

**Mission**: `remove-escalation-v1-parity-01KT4VTD`

How to verify the cleanup locally and on office2.

## Local (unit + integration)

```bash
cd /Users/kentgale/repos/kg-automation
pytest tests/escalation tests/enrichment -v
```

Expected: every named test case from [`contracts/escalation-side-effects.contract.md`](contracts/escalation-side-effects.contract.md) § "Test obligations" passes green, including:

- `level_sent_no_comment` / `snoozed_no_comment` / `dismissed_no_comment`: one JSONL append, zero Vikunja calls.
- `done_patch_then_jsonl` / `rescheduled_patch_then_jsonl`: one Vikunja PATCH, one JSONL append, zero comment PUTs.
- `patch_failure_blocks_jsonl`: VikunjaError raised, JSONL unchanged.
- `reconcile_no_phantom_path`: no `phantom_subscription` hard-fail filed when unsubscribed Vikunja tasks exist.

Then grep-validate the cleanup:

```bash
grep -rn "Felix-Escalation\|_format_v1_comment\|_COMMENT_PREFIX\|_COMMENT_MARKER\|_count_escalation_comments\|phantom_subscription\|C-001 parity\|comment.*parity" \
  scripts/ docs/runbooks/ docs/design/architecture/data/ tests/escalation/ tests/enrichment/
```

Expected: zero matches.

## office2 (post-deploy verification)

1. After merge, sync the office2 checkout:
   ```bash
   ssh office2-claude 'cd /home/claude/kg-automation && git fetch && git reset --hard origin/main'
   ```
2. Confirm reconcile runs without exception on a dry-run pass:
   ```bash
   ssh office2-claude 'python3 -m scripts.escalation.reconcile_completions --all --dry-run --quiet'
   ```
3. Trigger the escalation-daily cron by hand and inspect:
   ```bash
   ssh office2-claude 'openclaw cron run 5f734842-ca17-44f7-8040-f8e6a15355c4'
   sleep 30
   ssh office2-claude 'openclaw cron runs --id 5f734842-ca17-44f7-8040-f8e6a15355c4 --limit 1'
   ```
4. Inspect the targeted task in the Vikunja UI: verify **no new** `[Felix-Escalation]` comment was added in the post-cleanup tick. Historical comments from pre-cleanup still appear (intentional).
5. Inspect the JSONL log to confirm the event was appended:
   ```bash
   ssh office2-claude 'tail -1 /data/services/openclaw/state/escalation/project-9-escalation-history.jsonl'
   ```

## Architecture data verification

```bash
cd /Users/kentgale/repos/kg-automation
python tooling/scripts/validate_docs.py
jq '[.flows[] | select(.flow_id == "escalation-event-write-vikunja")] | length' docs/design/architecture/data/data-flows.json
```

Expected: `validate_docs.py` exits 0; the flow-id query returns `0`.

## Rollback

If a problem surfaces post-merge, revert the merge commit on `main`. There is no state-migration step to undo — JSONL state and pre-cutover Vikunja comments are untouched. The pre-cleanup behavior reappears on the next merge revert.
