# Quickstart: Felix-Vikunja Sync Reconciliation Driver

**Mission**: `felix-vikunja-sync-reconciliation-driver-01KTA1J3`
**Phase**: Plan / Phase 1
**Date**: 2026-06-04

Operator-facing reference for installing, bootstrapping, observing, and recovering the sync reconciliation driver. Use this after merge and during steady-state operation. Detailed implementation references the other phase-1 artifacts (`plan.md`, `contracts/`, `data-model.md`).

---

## Install (one-time, post-merge)

After the mission merges to `main` and `git pull` reaches office2, deploy the systemd user units:

```bash
ssh office2-claude
cd ~/kg-automation
git pull --ff-only origin main
```

Inspect the systemd unit files (placeholders — actual paths committed by implement phase):

```bash
cat scripts/sync/systemd/felix-vikunja-sync.service
cat scripts/sync/systemd/felix-vikunja-sync.timer
```

Deploy:

```bash
mkdir -p ~/.config/systemd/user
cp scripts/sync/systemd/felix-vikunja-sync.service ~/.config/systemd/user/
cp scripts/sync/systemd/felix-vikunja-sync.timer ~/.config/systemd/user/
systemctl --user daemon-reload
```

**Do NOT start the timer yet.** Bootstrap first.

---

## Bootstrap (first run, manual)

The driver's `--bootstrap` flag pulls all current task state and seeds the cache without emitting any conflict events. Run it ONCE, manually, before enabling the timer:

```bash
cd ~/kg-automation
python3 -m scripts.sync.driver --bootstrap
```

Expected output (success):

```
[bootstrap] Pulled N tasks from Vikunja
[bootstrap] Wrote /data/services/openclaw/state/sync/task-cache.json
[bootstrap] Wrote /data/services/openclaw/state/sync/freshness.json
[bootstrap] Wrote /data/services/openclaw/state/sync/last-tick.json
exit 0
```

Verify:

```bash
ls -l /data/services/openclaw/state/sync/
cat /data/services/openclaw/state/sync/freshness.json | jq
cat /data/services/openclaw/state/sync/last-tick.json | jq
```

Bootstrap should complete in under 5 seconds at current scale. If it fails, the failure record is in `last-tick.errors.jsonl` — read that and fix the underlying issue (most likely: credentials missing, Vikunja unreachable, state directory permissions).

---

## Enable steady-state operation

After successful bootstrap:

```bash
systemctl --user enable --now felix-vikunja-sync.timer
```

Verify the timer is active and the first tick will fire within 5 minutes:

```bash
systemctl --user list-timers felix-vikunja-sync.timer
```

After 5 minutes, the first steady-state tick runs. Verify:

```bash
cat /data/services/openclaw/state/sync/last-tick.json | jq '{started_at_utc, duration_ms, events_emitted, cycle_error}'
```

`cycle_error` should be `null`. `events_emitted` should be `{auto_resolved: 0, unsafe_to_auto_resolve: 0}` if no edits happened during the cycle window.

---

## Daily health check

```bash
# Single command: confirm the driver is alive
cat /data/services/openclaw/state/sync/last-tick.json | jq '.completed_at_utc, .cycle_error'
```

If `completed_at_utc` is older than ~15 minutes (3 cadence intervals), something is wrong. Check the timer:

```bash
systemctl --user status felix-vikunja-sync.timer
journalctl --user -u felix-vikunja-sync.service -n 50
```

And the failure stream:

```bash
tail -n 5 /data/services/openclaw/state/sync/last-tick.errors.jsonl
```

---

## Observe conflict events

The full divergence history is in `conflict-events.jsonl`:

```bash
# Most recent 10 events, in human-readable form
tail -n 10 /data/services/openclaw/state/sync/conflict-events.jsonl | jq

# Count today's events by class
jq -r --arg day "$(date -u +%Y-%m-%d)" \
  'select(.ts_observed_utc | startswith($day)) | .class' \
  /data/services/openclaw/state/sync/conflict-events.jsonl | sort | uniq -c

# Find unsafe events delivered today
jq -c 'select(.delivery_status == "delivered")' \
  /data/services/openclaw/state/sync/conflict-events.jsonl | tail -n 20
```

---

## Recovery scenarios

### "My cache is corrupted / I want a clean slate"

Delete the cache + freshness pointer + run bootstrap again. **Conflict log is preserved.**

```bash
rm /data/services/openclaw/state/sync/task-cache.json
rm /data/services/openclaw/state/sync/freshness.json
rm /data/services/openclaw/state/sync/project-cache.json
python3 -m scripts.sync.driver --bootstrap
```

### "I see too many WhatsApp pings on a noisy day"

The G-3 daily cap (default 5) is in `guard-state.json`. Lower it temporarily:

```bash
jq '.g3_daily_cap.cap = 2' /data/services/openclaw/state/sync/guard-state.json > /tmp/gs.tmp
mv /tmp/gs.tmp /data/services/openclaw/state/sync/guard-state.json
```

Restore later if needed. The next cycle re-reads the file.

### "I want to silence a specific task forever"

Add the label `felix:ignore` to that task in Vikunja's UI. UC-4 fires, classifying any future divergence on that task as `auto_resolved`, suppressing the WhatsApp ping.

### "I want to dry-run the cycle to see what would happen"

```bash
cd ~/kg-automation
python3 -m scripts.sync.driver --dry-run
```

Runs all 6 phases. Skips disk writes. Skips the openclaw CLI call. Logs to stdout. Useful for verifying changes after editing the field whitelist or guard config.

### "I want to disable the driver temporarily"

```bash
systemctl --user stop felix-vikunja-sync.timer
```

State files remain. Re-enable with `systemctl --user start felix-vikunja-sync.timer`; the next tick covers any edits made while disabled.

---

## SC verification (per spec)

Map each success criterion to its verification command:

| SC | Command/test |
|---|---|
| SC-001 (5-min convergence) | Edit a task's `title` in Vikunja UI. After 5 min, `jq '.tasks["<id>"].fields.title' /data/services/openclaw/state/sync/task-cache.json` matches the new value. |
| SC-002 (unsafe → single WhatsApp ping) | Edit a `due_date` (downstream-affecting field). After 5 min, confirm a WhatsApp message arrived AND `delivery_status == "delivered"` in the most recent conflict-event row for that task+field. |
| SC-003 (same-day dedup) | Edit the same field on the same task twice within 24h. Second edit produces a row with `delivery_status == "suppressed_by_g1"`. |
| SC-004 (≤1/day) | Observe `conflict-events.jsonl` over 7 consecutive days. Count daily `delivery_status == "delivered"` rows. |
| SC-005 (Vikunja unreachable recovery) | `sudo tailscale down` for 10 minutes, then up. Verify `last-tick.errors.jsonl` shows the failed ticks, then `last-tick.json` shows recovery, and the events from the unreachable window appear in `conflict-events.jsonl`. |
| SC-006 (crash idempotency) | `kill -9 <driver_pid>` mid-tick. Verify next tick re-processes without duplicate events (search for duplicate `event_id` in `conflict-events.jsonl`). |
| SC-007 (operator health check) | `cat /data/services/openclaw/state/sync/last-tick.json` returns a human-readable JSON record within seconds. |
| SC-008 (forward-compat #516) | Static review of an event row's `schema_version`, `event_id`, `router_route_set` against `conflict-event-schema.md` § Forward compatibility. |
| SC-009 (no new Vikunja write-path bug) | Code review during implement phase: all Vikunja calls in `scripts/sync/` are READS only; no POST/PUT/DELETE to Vikunja. The driver's `update` phase writes only to local files. |

---

## When to escalate

Open a GitHub issue (or comment on #518) if:

- A cycle fails consistently for >30 minutes despite Vikunja being reachable
- WhatsApp pings exceed the daily cap repeatedly across multiple days (signal of UC classification needing tuning)
- A divergence is detected on a field that should NOT be divergent (signal of an existing touchpoint not respecting Felix's `vikunja-api` write path — likely related to #519's touchpoint migration)
- `conflict-events.jsonl` grows past 100MB without rotation tooling being added

---

## Where to read next

- **Architecture intent**: `docs/design/architecture/adr/0003-felix-vikunja-sync-architecture.md`
- **Cycle phase contracts**: `contracts/cycle-pipeline.md`
- **Event schema**: `contracts/conflict-event-schema.md`
- **WhatsApp send shape**: `contracts/whatsapp-send.md`
- **State layout**: `contracts/state-directory.md`
- **Original research**: `docs/research/felix-vikunja-sync-architecture/`
