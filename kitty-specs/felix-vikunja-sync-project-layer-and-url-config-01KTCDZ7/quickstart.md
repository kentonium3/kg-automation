# Quickstart: 5-Minute Validation Flow

**Audience**: reviewers + operators verifying the mission's deliverables end-to-end after merge and deploy.

This is the smoke test for #520. It exercises one task change of each kind (add, delete, update), one project change, the URL config flow, and confirms the cache-read contract from #519 still works.

---

## Pre-conditions

Before running this validation:
- [ ] Mission #520 merged to main
- [ ] Deploy step completed on office2 (git pull + create URL config file)
- [ ] `felix-vikunja-sync.timer` is active
- [ ] Vikunja UI accessible at `https://office2.tail0f5f56.ts.net/`

## Step 1 — Verify URL config in place

```bash
ssh office2-claude 'stat -c "%a %U:%G %n" /data/services/openclaw/config/vikunja-base-url.txt && cat /data/services/openclaw/config/vikunja-base-url.txt'
```

Expected: `644 claude:claude /data/services/openclaw/config/vikunja-base-url.txt` followed by the canonical URL.

```bash
ssh office2-claude 'cd /home/claude/kg-automation && python3 -c "from scripts.common.vikunja_config import get_vikunja_base_url; print(get_vikunja_base_url())"'
```

Expected: prints the URL with trailing slash.

## Step 2 — Verify driver post-rewrite cycle

Wait for the next cron cycle (≤ 5 min), then:

```bash
ssh office2-claude 'cat /data/services/openclaw/state/sync/last-tick.json | python3 -m json.tool'
```

Expected:
- `layer_summary.task_layer.polled_at_utc` present (not `layer_pointers`)
- `layer_summary.project_layer.polled_at_utc` present
- `layer_summary.task_layer.errors` is an empty array (`[]`)
- `layer_summary.project_layer.errors` is an empty array
- `cycle_error: null`
- `duration_ms < 5000`

## Step 3 — Touchpoint cache read still works (NFR-004 regression)

```bash
ssh office2-claude 'cd /home/claude/kg-automation && python3 -m scripts.habits.morning_checkin_list --date $(TZ=America/New_York date +%Y-%m-%d) 2>&1 | tail -25'
```

Expected: exit code 0; output identical in shape to the pre-#520 morning check-in.

## Step 4 — Task addition

Operator creates a temporary test task in Vikunja UI:
- Project: Inbox
- Title: "TEST #520 — task addition validation"

Wait ≤ 5 min. Then:

```bash
ssh office2-claude 'cat /data/services/openclaw/state/sync/task-cache.json | python3 -c "import sys, json; d = json.load(sys.stdin); titles = [e[\"title\"] for e in d[\"tasks\"].values()]; print(\"TEST #520\" in str(titles))"'
```

Expected: `True`.

```bash
ssh office2-claude 'cat /data/services/openclaw/state/sync/last-tick.json | python3 -c "import sys, json; d = json.load(sys.stdin); print(d[\"layer_summary\"][\"task_layer\"][\"added\"])"'
```

Expected: ≥ 1 (covers this addition).

## Step 5 — Task deletion (three-action cleanup verification)

Operator deletes the test task created in Step 4 via Vikunja UI.

Wait ≤ 5 min. Then:

```bash
# Verify cache removal
ssh office2-claude 'cat /data/services/openclaw/state/sync/task-cache.json | python3 -c "import sys, json; d = json.load(sys.stdin); titles = [e[\"title\"] for e in d[\"tasks\"].values()]; print(\"TEST #520\" not in str(titles))"'
```

Expected: `True` (task removed from cache).

```bash
# Verify history-log entry
ssh office2-claude 'tail -1 /home/claude/kg-automation/scripts/habits/state/habits-history.jsonl | python3 -m json.tool'
```

Expected: a JSON line with `event_type: "task_deleted"`, `title` containing "TEST #520".

Note: schedule.yaml pruning is verified only if the test task was a habit (in the Habits project). For an Inbox task, this step doesn't apply — the cleanup runs but finds no schedule.yaml entry to prune. Verify with:

```bash
ssh office2-claude 'grep "TEST #520" /home/claude/kg-automation/scripts/habits/migrations/phase3-schedule.yaml'
```

Expected: no output (entry not present).

## Step 6 — Project rename

Operator renames the Inbox project to "Inbox (test rename)" in Vikunja UI.

Wait ≤ 5 min. Then:

```bash
ssh office2-claude 'cat /data/services/openclaw/state/sync/project-cache.json | python3 -c "import sys, json; d = json.load(sys.stdin); print(d[\"projects\"][\"1\"][\"title\"])"'
```

Expected: `Inbox (test rename)`.

```bash
ssh office2-claude 'cat /data/services/openclaw/state/sync/last-tick.json | python3 -c "import sys, json; d = json.load(sys.stdin); print(d[\"layer_summary\"][\"project_layer\"][\"updated\"])"'
```

Expected: ≥ 1.

**Cleanup**: revert the project name back to "Inbox" in Vikunja UI; next cycle picks up another `project_renamed` event.

## Step 7 — URL config update

Operator edits `/data/services/openclaw/config/vikunja-base-url.txt` to a test value (e.g., `http://100.92.197.90:3456/api/v1/` — the direct-IP variant, which should still work over Tailscale).

```bash
ssh office2-claude 'cd /home/claude/kg-automation && python3 -c "from scripts.common.vikunja_config import get_vikunja_base_url; print(get_vikunja_base_url())"'
```

Expected: prints the new test URL.

Wait ≤ 5 min for the next cron cycle:

```bash
ssh office2-claude 'cat /data/services/openclaw/state/sync/last-tick.json | python3 -c "import sys, json; d = json.load(sys.stdin); print(d[\"cycle_error\"])"'
```

Expected: `null` (cycle succeeded against the new URL).

**Cleanup**: revert the config file to the canonical Tailscale HTTPS value.

## Step 8 — NFR-006 grep success criterion

```bash
cd /Users/kentgale/repos/kg-automation && grep -rn "office2.tail0f5f56.ts.net\|100.92.197.90:3456" scripts/ --include="*.py" | grep -v test_ | grep -v __pycache__
```

Expected: hits only in:
- `scripts/common/vikunja_config.py` (the path/value constant)
- The 6 FR-010 exclusions (provision_felix_bot.py, validate_felix_bot.py, swap_vikunja_secrets.py, revoke_kent_tokens.py, setup_goals.py, migrate_schedule.py, query_active_habits.py, credential_health_check/vikunja_writer.py)

Any other hit is a regression.

---

## Pass criteria

All 8 steps pass with the expected outputs. If any step fails, do not consider the mission delivered until the gap is investigated.

## Rollback path

If validation reveals a critical issue, roll back:

```bash
ssh office2-claude 'cd /home/claude/kg-automation && git log --oneline -5'
# Identify the merge commit hash (before #520 merge)

ssh office2-claude 'cd /home/claude/kg-automation && git reset --hard <pre-520-merge-hash>'
ssh office2-claude 'systemctl --user restart felix-vikunja-sync.timer'
```

Rollback restores #518's incremental-poll driver. The deployed `task-cache.json` and `project-cache.json` from #520 are compatible with #518's read paths (schema unchanged for tasks; project-cache.json's content is a strict subset of what #518 would have written under its own logic).
