---
title: Felix-Vikunja sync driver operations
doc_type: runbook
audience: agents_and_humans
status: approved
created: 2026-06-04
last_validated: 2026-06-04
last_updated: '2026-06-04'
updated_by: '#518'
owners: ['kgale']
version: v1.0
---

# Felix-Vikunja Sync Driver Operations

Operator runbook for the Felix-Vikunja sync reconciliation driver — the centralized
deterministic poller introduced in #518. Read this before installing, after a
failure incident, and any time you want to confirm the driver is healthy.

## What this driver does

The driver runs every 5 minutes on office2 as the `claude` user. Each tick:

1. Pulls Vikunja's task delta since the last successful tick (`GET /tasks/all?updated_since=…`).
2. Compares the fetched state against Felix's local cache.
3. Classifies each divergence (UC-1/UC-2 collapsed cache-divergence + UC-3 downstream-affecting + UC-4 operator-override).
4. Appends a 15-field row to `conflict-events.jsonl` for every divergence.
5. For unsafe-class divergences that pass the three guards (G-1 24h dedup, G-2 30-min post-write suppression, G-3 daily cap), sends a 3-line WhatsApp message.
6. Updates the local cache to mirror Vikunja's state (Vikunja wins, always).
7. Advances the freshness pointer ONLY if every prior step succeeded.

Architectural source of truth: [`docs/design/architecture/adr/0003-felix-vikunja-sync-architecture.md`](<../design/architecture/adr/0003-felix-vikunja-sync-architecture.md>). Implementation: `scripts/sync/`. Tests: `tests/sync/`.

---

## Install (one-time, post-merge)

After the mission merges and `git pull` reaches office2:

```bash
ssh office2-claude
```

```bash
cd ~/kg-automation && git pull --ff-only origin main
```

```bash
mkdir -p ~/.config/systemd/user
```

```bash
cp scripts/sync/systemd/felix-vikunja-sync.{service,timer} ~/.config/systemd/user/
```

```bash
systemctl --user daemon-reload
```

**Do NOT start the timer yet.** Bootstrap first.

---

## Bootstrap (first run, manual)

The `--bootstrap` flag pulls all current Vikunja task state, seeds the cache,
and writes the initial freshness pointer. It does NOT classify or emit any
conflict events. Run it ONCE, manually:

```bash
cd ~/kg-automation && python3 -m scripts.sync.driver --bootstrap
```

Expected: exit 0, state files populated, no `conflict-events.jsonl` created.

Verify:

```bash
ls -l /data/services/openclaw/state/sync/
```

```bash
cat /data/services/openclaw/state/sync/last-tick.json | jq
```

If bootstrap fails, the failure record is in `last-tick.errors.jsonl`. Fix the
underlying issue (most likely: token missing, Vikunja unreachable, permissions)
and re-run.

---

## Enable steady-state operation

After successful bootstrap:

```bash
systemctl --user enable --now felix-vikunja-sync.timer
```

Verify the timer is scheduled and the first tick will fire within 5 minutes:

```bash
systemctl --user list-timers felix-vikunja-sync.timer
```

After the first tick:

```bash
cat /data/services/openclaw/state/sync/last-tick.json | jq '{started_at_utc, duration_ms, events_emitted, cycle_error}'
```

`cycle_error` should be `null`.

---

## Daily health check

The single canonical command:

```bash
cat /data/services/openclaw/state/sync/last-tick.json | jq '.completed_at_utc, .cycle_error'
```

Expected: a recent (within ~6 minutes) `completed_at_utc` and `null` cycle error.

If the timestamp is older than ~15 minutes (3 cadence intervals), check the timer:

```bash
systemctl --user status felix-vikunja-sync.timer
```

And the failure stream:

```bash
tail -n 5 /data/services/openclaw/state/sync/last-tick.errors.jsonl
```

And the service journal:

```bash
journalctl --user -u felix-vikunja-sync.service -n 50
```

---

## Observe conflict events

The full divergence history:

```bash
tail -n 10 /data/services/openclaw/state/sync/conflict-events.jsonl | jq
```

Count today's events by class:

```bash
jq -r --arg day "$(date -u +%Y-%m-%d)" 'select(.ts_observed_utc | startswith($day)) | .class' /data/services/openclaw/state/sync/conflict-events.jsonl | sort | uniq -c
```

All unsafe events delivered today:

```bash
jq -c 'select(.delivery_status == "delivered")' /data/services/openclaw/state/sync/conflict-events.jsonl | tail -n 20
```

---

## Recovery scenarios

### "I see too many WhatsApp pings"

Lower the daily cap in `guard-state.json`:

```bash
jq '.g3_daily_cap.cap = 2' /data/services/openclaw/state/sync/guard-state.json > /tmp/gs.tmp && mv /tmp/gs.tmp /data/services/openclaw/state/sync/guard-state.json
```

The next tick re-reads the file.

### "I want to silence a specific task forever"

Add the label `felix:ignore` to that task in Vikunja's UI. UC-4 fires; future
divergences on that task classify as `auto_resolved` and are logged without
producing a WhatsApp ping.

### "My cache feels stale — I want a clean slate"

```bash
rm /data/services/openclaw/state/sync/task-cache.json /data/services/openclaw/state/sync/freshness.json /data/services/openclaw/state/sync/project-cache.json
```

```bash
cd ~/kg-automation && python3 -m scripts.sync.driver --bootstrap
```

The conflict-events.jsonl history is preserved.

### "I want to dry-run a tick without writes"

```bash
cd ~/kg-automation && python3 -m scripts.sync.driver --dry-run
```

Runs all 6 phases in memory. Skips state writes. Skips the openclaw CLI call.
Logs a summary to stderr.

### "I want to temporarily disable the driver"

```bash
systemctl --user stop felix-vikunja-sync.timer
```

State files remain. Re-enable with `systemctl --user start felix-vikunja-sync.timer`.

### Vikunja unreachable

The driver tolerates this — each tick that fails on fetch records the failure
to `last-tick.errors.jsonl` and does NOT advance the freshness pointer. The next
successful tick covers the gap via the `updated_since` delta poll.

---

## Known soft edge (Vikunja server-side auto-advance)

When Felix completes a recurring habit via WhatsApp reply, Vikunja's server-side
auto-advance flips `done` back to `false` and advances `due_date`. The driver's
diff phase observes this as a divergence — and the driver cannot distinguish
"Vikunja auto-fired" from "Kent edited" because Vikunja v0.24.6 returns
`updated_by: null` on every task (see [`research.md` § Unknown 3](<../research/felix-vikunja-sync-architecture/research.md>) — actually this is documented in the mission research; the absence is unchanged).

Mitigations:

- **G-2 (30-min post-write suppression)** suppresses the immediate auto-advance case (because Felix just wrote `done=true` and the auto-advance fired within seconds).
- **UC-4 (`felix:ignore` label)** lets the operator silence known recurring habits.

If you see WhatsApp noise from recurring habits during the first few weeks of
operation, apply the `felix:ignore` label to the affected tasks.

---

## Success-criteria verification commands (from spec)

| SC | Verification |
|----|--------------|
| SC-001 | Edit a `title` in Vikunja UI; after 5 min `jq '.tasks["<id>"].fields.title' /data/services/openclaw/state/sync/task-cache.json` matches the new value. |
| SC-002 | Edit a `due_date` (downstream-affecting); after 5 min confirm a WhatsApp message arrived AND `delivery_status == "delivered"` in the most recent conflict-events.jsonl row for that task+field. |
| SC-003 | Edit the same field twice within 24h; second edit row has `delivery_status == "suppressed_by_g1"`. |
| SC-004 | Observe `conflict-events.jsonl` over 7 days; count daily `delivery_status == "delivered"` rows; expect ≤ 1 per calendar day. |
| SC-005 | `sudo tailscale down` for 10 min then up; verify `last-tick.errors.jsonl` shows the failed ticks, then `last-tick.json` shows recovery, and the events from the unreachable window appear in `conflict-events.jsonl`. |
| SC-006 | `kill -9 <driver_pid>` mid-tick; verify next tick re-processes without duplicate events (search for duplicate `event_id` in `conflict-events.jsonl`). |
| SC-007 | `cat /data/services/openclaw/state/sync/last-tick.json` returns a human-readable JSON record within seconds. |
| SC-008 | Static review of an event row's `schema_version`, `event_id`, `router_route_set` against `contracts/conflict-event-schema.md` § Forward compatibility. |
| SC-009 | Code review: confirm `scripts/sync/` has no POST/PUT/DELETE to Vikunja. Driver is read-only against Vikunja. |

---

## When to escalate

Open a GitHub issue (or comment on #518) if:

- A cycle fails consistently for >30 minutes despite Vikunja being reachable
- WhatsApp pings exceed the daily cap repeatedly across multiple days (signal of UC classification needing tuning)
- A divergence is detected on a field that should NOT be divergent (signal of an existing touchpoint not respecting Felix's vikunja-api write path — likely #519 territory)
- `conflict-events.jsonl` grows past 100MB without rotation tooling being added

---

## References

- Spec: [`kitty-specs/felix-vikunja-sync-reconciliation-driver-01KTA1J3/spec.md`](<../../kitty-specs/felix-vikunja-sync-reconciliation-driver-01KTA1J3/spec.md>)
- ADR: [`ADR-0003 — Felix-Vikunja sync architecture`](<../design/architecture/adr/0003-felix-vikunja-sync-architecture.md>)
- Cycle pipeline contract: [`contracts/cycle-pipeline.md`](<../../kitty-specs/felix-vikunja-sync-reconciliation-driver-01KTA1J3/contracts/cycle-pipeline.md>)
- Conflict-event schema: [`contracts/conflict-event-schema.md`](<../../kitty-specs/felix-vikunja-sync-reconciliation-driver-01KTA1J3/contracts/conflict-event-schema.md>)
- WhatsApp send contract: [`contracts/whatsapp-send.md`](<../../kitty-specs/felix-vikunja-sync-reconciliation-driver-01KTA1J3/contracts/whatsapp-send.md>)
- State directory layout: [`contracts/state-directory.md`](<../../kitty-specs/felix-vikunja-sync-reconciliation-driver-01KTA1J3/contracts/state-directory.md>)
- Research: [`docs/research/felix-vikunja-sync-architecture/`](<../research/felix-vikunja-sync-architecture/>)
- Source issue: [#518](https://github.com/kentonium3/kg-automation/issues/518)
- Parent epic: [#507](https://github.com/kentonium3/kg-automation/issues/507)
