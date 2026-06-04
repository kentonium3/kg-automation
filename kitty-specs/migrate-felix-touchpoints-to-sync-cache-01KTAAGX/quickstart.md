# Quickstart: Migrate Felix Touchpoints to Sync Cache

**Mission**: `migrate-felix-touchpoints-to-sync-cache-01KTAAGX`
**Phase**: Plan / Phase 1
**Date**: 2026-06-04

Operator-facing post-merge verification commands for the touchpoint migration mission. Most of the system-level operator runbook for the underlying sync driver lives at [`docs/runbooks/sync-driver-ops.md`](<../../docs/runbooks/sync-driver-ops.md>); this quickstart only covers what's new in #519.

---

## Pre-deploy verification (on Mac before merge)

```bash
cd ~/repos/kg-automation
```

Run the full test suite. Per FR-009 + C-008 the entire migrated touchpoint test set runs under fully mocked I/O.

```bash
python3 -m pytest tests/sync/ tests/common/ tests/habits/ tests/escalation/ tests/enrichment/ -q
```

Expected: all pass. No live `/data/...` access. No live HTTP. The fixture in `tests/common/conftest.py` synthesizes everything from `tmp_path`.

```bash
grep -rn 'urlopen\|requests\.get' scripts/habits/reconcile_completions.py scripts/habits/query_active_habits_v2.py scripts/habits/morning_checkin_list.py scripts/escalation/reconcile_completions.py scripts/enrichment/reconcile_completions.py
```

Expected: zero hits matching Vikunja URLs. (TP-04 `set_due_dates.py` retains its PUT-side `_http_request` for write paths; the grep should show ONLY the PUT-side line, not any GET line.) Per SC-009.

---

## Post-merge deploy on office2 (operator step)

The sync driver is already running on office2 (deployed 2026-06-04 21:48 UTC for #518). No new systemd units. No new credentials. The migration just changes how the touchpoints READ the same cache the driver already produces.

```bash
ssh office2-claude
```

```bash
cd ~/kg-automation && git pull --ff-only origin main
```

That's the entire deploy. No services to restart; the touchpoints are invoked on cron and will use the new code on their next firing.

---

## Smoke test — touchpoint reads from cache

Pick one migrated touchpoint and invoke it manually. The simplest is `morning_checkin_list.py` (TP-07):

```bash
cd ~/kg-automation && python3 -m scripts.habits.morning_checkin_list --dry-run 2>&1 | head -20
```

Expected output:
- A list of today's active habits (drawn from cache, not Vikunja)
- Zero direct Vikunja HTTP calls (verify with the next command)

```bash
journalctl --user -u felix-vikunja-sync.service -n 5 --no-pager
```

Expected: recent sync cycles with `cycle_error: null`. (Touchpoints use the cache the driver writes; if the driver is unhealthy, touchpoints fail per their SLA.)

---

## Verification — cache freshness vs touchpoint SLA

```bash
python3 -c "from scripts.common import sync_cache; print(sync_cache.read_freshness_pointer())"
```

Expected: ISO-8601 UTC timestamp within the last ~6 minutes (one cadence interval).

```bash
python3 -c "from scripts.common import sync_cache; print('healthy:', sync_cache.is_cache_healthy(sync_cache.SLA_NORMAL))"
```

Expected: `healthy: True`. (`is_cache_healthy` is the operator-facing non-raising check.)

---

## SC verification commands

Map each Success Criterion to its verification command:

| SC | Command/test |
|----|---|
| SC-001 | Invoke each touchpoint manually with `--dry-run` (where supported) or with synthetic args. Watch `journalctl --user -u felix-vikunja-sync.service` and confirm no new Vikunja HTTP calls from the touchpoint. (Best verified pre-deploy via the pre-deploy grep above; post-deploy verification via Vikunja access logs over 24h.) |
| SC-002 | `systemctl --user stop felix-vikunja-sync.timer`; wait beyond SLA_NORMAL (15 min); invoke any touchpoint; observe stderr message `"sync cache stale beyond SLA_NORMAL (max 900s); pointer age <N>s. Recovery: systemctl --user status felix-vikunja-sync.timer"` and non-zero exit. Restart: `systemctl --user start felix-vikunja-sync.timer`. |
| SC-003 | `mv /data/services/openclaw/state/sync/task-cache.json /tmp/`; invoke any touchpoint; observe stderr message containing "sync cache freshness pointer missing" or "task-cache.json missing" and non-zero exit. Restore: `mv /tmp/task-cache.json /data/services/openclaw/state/sync/`. |
| SC-004 | Pre-migration baseline: capture Vikunja access log GET volume from Felix-bot token over a 24h window. Post-migration: same 24h window. Compare. Expected: ≥95% reduction. |
| SC-005 | 7-day observation window: every morning, capture the WhatsApp habit check-in message; compare to the pre-migration baseline week. Expected: identical content. |
| SC-006 | Create a new task in Vikunja UI; before the next driver tick (≤5 min wait), invoke `python3 -m scripts.habits.morning_checkin_list` (or any touchpoint that touches tasks by ID); observe stderr message containing "task <N> not in sync cache" and non-zero exit. Wait for next driver tick; touchpoint succeeds. |
| SC-007 | Create a private-project task (use the operator's `02-Growth/_private/` Obsidian convention to assign project); invoke a touchpoint that references it by ID; observe stderr message containing "is private-project (data unavailable in cache)" and non-zero exit. Verify no task title appears anywhere in the stderr. |
| SC-008 | `python3 -m pytest tests/habits/test_reconcile_completions.py tests/habits/test_query_active_habits_v2.py tests/habits/test_set_due_dates.py tests/habits/test_morning_checkin_list.py tests/escalation/test_reconcile_completions.py tests/enrichment/test_reconcile_completions.py tests/common/test_sync_cache.py -q`. Expected: all pass. |
| SC-009 | `grep -E 'urlopen\\|requests\\.get' scripts/habits/reconcile_completions.py scripts/habits/query_active_habits_v2.py scripts/habits/morning_checkin_list.py scripts/escalation/reconcile_completions.py scripts/enrichment/reconcile_completions.py` returns zero hits matching Vikunja URLs. (TP-04 `set_due_dates.py` retains write-side `_http_request`; grep should show only write-side lines.) |

---

## Recovery scenarios

### "A migrated touchpoint is throwing 'sync cache stale' errors"

Check the driver:

```bash
systemctl --user status felix-vikunja-sync.timer
```

```bash
tail -n 5 /data/services/openclaw/state/sync/last-tick.errors.jsonl
```

Recover per `docs/runbooks/sync-driver-ops.md`. Once the driver resumes, touchpoints will succeed on their next invocation.

### "A touchpoint is throwing 'task <N> not in sync cache'"

The task was created in Vikunja after the last driver tick. Wait for the next tick (≤5 min); the cache will catch up and the touchpoint will succeed.

If the issue persists across multiple ticks, check the driver's last-tick.errors.jsonl — Vikunja may be unreachable.

### "I want to disable the migration and revert all touchpoints to direct Vikunja reads"

Per Q1's clean-cutover decision, the migration is not flippable at runtime. To revert: `git revert <merge_commit>` and re-deploy. This is a non-trivial operation; only do it as a true emergency.

### "I want to run a touchpoint against direct Vikunja for debugging"

The cache-read path is the production path. For ad-hoc debugging, use `curl` or `jq` against Vikunja directly (the operator-side has the token in `~/.config/gh/...` or wherever). Do NOT add a "force direct" flag to the touchpoint — it would violate Q1.

---

## When to escalate

Open a comment on #519 (the source issue) or file a new issue if:

- A migrated touchpoint produces incorrect output (cache and Vikunja disagree on a field's value and the touchpoint surfaces the cache value with no operator-side reconciliation)
- Cache health degrades persistently (the driver's last-tick.errors.jsonl shows daily errors)
- The `is_cache_healthy` check returns False with no apparent driver health issue
- A new touchpoint is added in a future mission and needs migration

---

## References

- Mission spec: [`spec.md`](./spec.md)
- Implementation plan: [`plan.md`](./plan.md)
- Phase 0 research: [`research.md`](./research.md)
- Helper API contract: [`contracts/helper-api.md`](./contracts/helper-api.md)
- Migration pattern: [`contracts/migration-pattern.md`](./contracts/migration-pattern.md)
- Source issue: [#519](https://github.com/kentonium3/kg-automation/issues/519)
- Sync driver runbook: [`docs/runbooks/sync-driver-ops.md`](../../docs/runbooks/sync-driver-ops.md)
