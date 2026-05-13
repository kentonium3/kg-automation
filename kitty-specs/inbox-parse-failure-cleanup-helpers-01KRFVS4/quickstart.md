# Quickstart: Inbox parse-failure and cleanup helpers

**Mission**: `inbox-parse-failure-cleanup-helpers-01KRFVS4`

End-to-end verification recipe for the implementer and the post-merge operator.

---

## 1. Local verification (Mac)

```bash
cd /Users/kentgale/repos/kg-automation
python3 -m pytest tests/inbox/ -v
```

**Expect**: 99 existing tests pass + new `test_handle_parse_failures.py` and `test_handle_marker_cleanup.py` tests pass (5+3 = 8+ new tests minimum).

## 2. Deploy to office2

```bash
bash scripts/deploy/deploy-149.sh --apply --backup-confirmed
```

**Expect**: scripts in `/home/claude/kg-automation/scripts/inbox/` and AGENTS.md in `/data/services/openclaw/inbox-agent/` updated on office2.

## 3. Smoke test — `handle_parse_failures.py`

On office2 as claude, construct a synthetic prescan JSON and run the orchestrator against it:

```bash
ssh office2-claude '
set -e
cat > /tmp/smoke-prescan.json <<EOF
{
  "parse_failures": [
    {"path": "/tmp/smoke-canary.md", "reason": "YAML parse error: unterminated string"}
  ],
  "marker_cleanup_needed": [],
  "unprocessed_paths": []
}
EOF
printf -- "---\ntitle: smoke\nstatus: \"unterminated string\ncreated: 2026-05-13\n---\n\nBody.\n" > /tmp/smoke-canary.md
chmod 0664 /tmp/smoke-canary.md
python3 /home/claude/kg-automation/scripts/inbox/handle_parse_failures.py @/tmp/smoke-prescan.json --date 2026-05-13 2>&1
echo "exit=$?"
echo "=== Marker landed? ==="
tail -5 /tmp/smoke-canary.md
rm /tmp/smoke-canary.md /tmp/smoke-prescan.json
'
```

**Expect**:
- stdout: a single integer (the GitHub issue number).
- stderr: structured log lines via `log_action.py` indicating `inbox_quality_issue_filed` (or `_deduped`) AND `parse_error_marker_injected`.
- The canary file's tail shows the injected `> [!error] felix-capture:` callout.
- exit 0.

## 4. Smoke test — `handle_marker_cleanup.py`

```bash
ssh office2-claude '
set -e
printf -- "---\ntitle: cleanup smoke\nstatus: unprocessed\n---\n\n> [!error] felix-capture: see #999 (2026-05-13)\n\nBody.\n" > /tmp/cleanup-smoke.md
chmod 0664 /tmp/cleanup-smoke.md
cat > /tmp/cleanup-prescan.json <<EOF
{
  "parse_failures": [],
  "marker_cleanup_needed": [
    {"path": "/tmp/cleanup-smoke.md", "issue_number": 999}
  ],
  "unprocessed_paths": []
}
EOF
python3 /home/claude/kg-automation/scripts/inbox/handle_marker_cleanup.py @/tmp/cleanup-prescan.json 2>&1
echo "exit=$?"
echo "=== Marker gone? ==="
cat /tmp/cleanup-smoke.md
rm /tmp/cleanup-smoke.md /tmp/cleanup-prescan.json
'
```

**Expect**:
- stderr: structured `marker_stripped` log entry via `log_action.py`.
- The file's body no longer contains the `> [!error] felix-capture:` callout.
- exit 0.

## 5. End-to-end canary (SC-003)

This is the load-bearing verification for the mission — replaces the failed mission #185 canary leg.

1. **Drop fresh canary on Mac**:
   ```bash
   cat > "/Users/kentgale/second-brain/notes/01-Inbox/Inbox 2026-05-13 sc003-canary.md" <<'EOF'
   ---
   title: SC-003 canary
   status: "unterminated string
   created: 2026-05-13
   ---

   Body.
   EOF
   ```

2. **Wait ≤2 min for sync to office2**:
   ```bash
   ssh office2-claude 'head -5 "/home/kgale/second-brain/notes/01-Inbox/Inbox 2026-05-13 sc003-canary.md"'
   ```

3. **Trigger inbox-noon cron**:
   ```bash
   ssh office2-claude 'openclaw cron run 7fa9b299-f8fc-44c2-b37d-de4163c80cdf'
   ```

4. **Verify cron run reports OK**:
   ```bash
   ssh office2-claude 'openclaw cron runs --id 7fa9b299-f8fc-44c2-b37d-de4163c80cdf --limit 1'
   ```

5. **Verify both legs of Step 6 fired**:
   ```bash
   ssh office2-claude 'grep -E "inbox_quality_issue_filed|inbox_quality_issue_deduped|parse_error_marker_injected" ~/second-brain/agents/state/*.jsonl | tail -10'
   ```
   **Expect**: at least one entry of each action type referencing the canary file or its filed issue.

6. **Verify marker landed on the canary file**:
   ```bash
   ssh office2-claude 'tail -5 "/home/kgale/second-brain/notes/01-Inbox/Inbox 2026-05-13 sc003-canary.md"'
   ```
   **Expect**: a `> [!error] felix-capture:` callout block.

7. **Cleanup**: delete the canary from Mac inbox; close the test-artifact GitHub issue if one was created.

## 6. Rollback (if needed)

```bash
git revert <merge-commit-hash>
bash scripts/deploy/deploy-149.sh --apply --backup-confirmed
```

This restores both the helper scripts AND the AGENTS.md prompt to the pre-merge state.
