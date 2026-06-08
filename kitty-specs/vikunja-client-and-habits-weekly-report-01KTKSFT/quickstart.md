# Quickstart: Operator smoke test for vikunja-client + habits-weekly-report

**Mission**: `vikunja-client-and-habits-weekly-report-01KTKSFT`
**Spec**: [spec.md](./spec.md) | **Plan**: [plan.md](./plan.md)

Post-deploy smoke test. Run after the mission merges to main AND is deployed to office2 (existing post-merge sync). Verifies (a) client works end-to-end, (b) weekly helper produces accurate JSON, (c) cron-fired WhatsApp report content is correct, (d) failure modes surface deterministically.

Estimated runtime: ~10 minutes including cron-tick wait if you want full end-to-end.

## Preconditions

- Mission merged to main.
- Office2 has pulled the latest main (post-merge sync ran).
- Weekly cron is enabled (`habits-weekly-report` at `0 22 * * 0`).
- Vikunja API reachable from office2.

## Test 1 — Client smoke test (direct invocation)

**Setup**: SSH to office2 and run the client directly.

```bash
ssh office2-claude
python3 -c "
from scripts.common.vikunja_client import VikunjaClient
client = VikunjaClient()
tasks = client.get('/projects/13/tasks', params={'per_page': '5'})
print(f'Got {len(tasks)} tasks; first: {tasks[0][\"title\"]}')
"
```

**Verify**: prints `Got N tasks; first: <some habit title>`. No errors. Exit 0.

**Tear down**: nothing.

## Test 2 — Weekly helper happy path

**Setup**: SSH to office2 and run the new weekly helper manually.

```bash
ssh office2-claude
python3 /home/claude/kg-automation/scripts/habits/query_active_habits_weekly.py
```

**Verify**:
- Helper exits 0.
- stdout is valid JSON matching the schema in `contracts/weekly_report_payload.md`.
- The `habits` array contains daily habits from project 13 AND any "X — Monday/Wednesday/Friday" Strength training habits.
- "Upload cardiac lab history" or similar one-off task is NOT in the array.
- Per-habit `percent_current` values look reasonable (not all 100%, not all 0%).
- `overall_percent_current` is a float in `[0, 100]`.
- The log_action stream gained a `weekly_report_generated` entry.

**Tear down**: nothing (helper has no side effects beyond log_action).

## Test 3 — Weekly helper with baseline window

**Setup**: same as Test 2 but with `--window-end` set to last Sunday.

```bash
ssh office2-claude
LAST_SUN=$(date -d "last Sunday" +%Y-%m-%d)
python3 /home/claude/kg-automation/scripts/habits/query_active_habits_weekly.py --window-end "$LAST_SUN"
```

**Verify**:
- `window_end_iso` matches `$LAST_SUN`.
- `prior_window_*` populated with the week before that.
- Habit rows have `percent_prior` populated (some non-zero, presumably).

## Test 4 — Vikunja unreachable failure mode

**Setup**: SSH to office2 and run the helper with a deliberately broken token.

```bash
ssh office2-claude
VIKUNJA_TOKEN=invalid python3 -c "
from scripts.common.vikunja_client import VikunjaClient
from scripts.common.vikunja_client import VikunjaAuthError
client = VikunjaClient(token='invalid-token-deliberately')
try:
    client.get('/projects/13/tasks')
except VikunjaAuthError as exc:
    print(f'Got expected auth error: {exc}')
"
```

**Verify**:
- Prints `Got expected auth error: VikunjaAuthError: /projects/13/tasks` (no body content).
- Exit 0 (we caught the exception).

## Test 5 — Output discipline at the next weekly cron tick

**Setup**: wait for the next Sunday 10pm America/New_York cron tick (or trigger manually if `openclaw cron trigger` supports it). Observe the WhatsApp message.

**Verify**:
- WhatsApp message body first character is `S` (`Sent by felix-admin-habits:sonnet`).
- No preamble before the identity line.
- No internal agent reasoning ("Perfect. Now I need to format...", "According to AGENTS.md...", etc.).
- Habit rows in the body match the JSON output from Test 2 (if Test 2 was run around the same time).
- Percentages reflect actual completions, not all-100%.

## Test 6 — Sibling agents audit (no regression)

**Setup**: trigger `escalation-daily` (next noon, or manually) and observe its WhatsApp message.

**Verify**:
- felix-admin-escalation's WhatsApp message ALSO begins with `Sent by felix-admin-escalation:<model>`. No preamble.
- (Optionally) check felix-admin-tasker per the FR-010 audit conclusion — either it has the Hard Rules in its AGENTS.md OR has an explicit no-user-facing-WhatsApp annotation.

## Test 7 — Morning check-in unchanged

**Setup**: wait for the next morning cron tick (`habits-morning-checkin` at 11:05 UTC).

**Verify**:
- Morning check-in WhatsApp message is functionally identical to pre-mission behavior (per C-004 / NFR-006).
- No new errors or anomalies in the morning-check-in log_action stream.

## Failure modes to watch

- `weekly_report_failed` log_action entry without a corresponding WhatsApp surface: indicates the agent caught the error but didn't render. Bug.
- Hallucinated WhatsApp content (percentages that don't match `done_at` data): regression to the original bug. Bug.
- Internal monologue in WhatsApp: regression to the original Bug A. Bug.
- Cardiac task or one-off appearing in the report: regression to the original Bug B. Bug.

## Rollback

If the smoke test reveals a regression:

```bash
ssh office2-kgale
cd /home/claude/kg-automation  # or wherever the deploy lives
git revert <merge-commit-hash>
git push origin main
# Wait for next office2 sync tick OR manually pull
```

No data destruction concerns: client + helper are read-only; no Vikunja state modified. Pending log_action entries persist as the audit trail. The morning check-in path is untouched and continues to work regardless.
