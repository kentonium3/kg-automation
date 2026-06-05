---
title: Felix-Vikunja sync driver operations
doc_type: runbook
audience: agents_and_humans
status: approved
created: 2026-06-04
last_validated: 2026-06-05
last_updated: '2026-06-05'
updated_by: '#520'
owners: ['kgale']
version: v2.0
---

# Felix-Vikunja Sync Driver Operations

Operator runbook for the Felix-Vikunja sync reconciliation driver — the centralized
deterministic poller introduced in #518 and extended in #519/#520. Read this before
installing, after a failure incident, and any time you want to confirm the driver
is healthy.

## What this driver does

The driver runs every 5 minutes on office2 as the `claude` user. Each tick executes
a 7-phase pipeline:

| Phase | Name | What happens |
|-------|------|-------------|
| 0 | Preamble | Read Vikunja token, previous caches, freshness timestamp, and base URL (via `vikunja_config.py`) |
| 1 | Fetch | `GET /tasks/all` + `GET /projects` — **full poll every tick** |
| 2 | Diff | 3-way set-diff: `in_vikunja_only` / `in_both` / `in_cache_only` |
| 3 | Classify | UC-1..UC-4 task classification (unchanged, downstream-affecting logic) |
| 4 | Emit | Append to `conflict-events.jsonl` + WhatsApp for **task** events only; project events go to `layer_summary` in `last-tick.json` (no WhatsApp, no JSONL row) |
| 5 | Update | Build `new_task_cache` and `new_project_cache` in memory |
| 5b | Deletion cleanup | For each `in_cache_only` task: cross-reference `habits-history.jsonl` and `schedule.yaml`, then remove from new cache; see *Deletion cleanup* below |
| 6 | Complete | Atomic write of all state files — all-or-nothing |

**Full-poll model**: the driver fetches the complete Vikunja task and project sets on
every tick. There is no `updated_since` delta, no incremental cursor, and no
freshness-pointer advancement gate. Divergences are detected by comparing the
fetched state against the in-memory cache loaded in Phase 0.

**Project layer** (added by #520): `GET /projects` is called alongside the task fetch.
New, changed, or deleted projects are recorded in `project-cache.json` and summarised
in `last-tick.json`'s `layer_summary` field. Project events do not trigger WhatsApp
messages or `conflict-events.jsonl` rows — the project layer is an audit/discovery
surface only.

**Read-only against Vikunja** (SC-009): the driver never issues a POST, PUT, or DELETE
to the Vikunja API.

Architectural source of truth: [`docs/design/architecture/adr/0003-felix-vikunja-sync-architecture.md`](<../design/architecture/adr/0003-felix-vikunja-sync-architecture.md>). Implementation: `scripts/sync/`. Tests: `tests/sync/`.

---

## URL config prerequisite

The driver resolves the Vikunja base URL from `scripts/common/vikunja_config.py`
(`get_vikunja_base_url()`). Resolution order:

1. `VIKUNJA_BASE_URL` environment variable (preferred)
2. `/data/services/openclaw/config/vikunja-base-url.txt` (file fallback, mode 0644)

If neither is present the driver raises `VikunjaConfigError` at Phase 0 and the
tick fails cleanly. **Create the config file before bootstrapping** (see below).

See [`url-config.md`](<../../kitty-specs/felix-vikunja-sync-project-layer-and-url-config-01KTCDZ7/contracts/url-config.md>) for the full resolution contract.

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

**Do NOT start the timer yet.** Configure the URL and bootstrap first.

---

## URL config file (create once, pre-bootstrap)

Create the config directory and the URL file:

```bash
mkdir -p /data/services/openclaw/config
```

```bash
printf 'https://office2.tail0f5f56.ts.net/api/v1/' > /data/services/openclaw/config/vikunja-base-url.txt
```

```bash
chmod 0644 /data/services/openclaw/config/vikunja-base-url.txt
```

Also export the env var for interactive use:

```bash
echo 'export VIKUNJA_BASE_URL=https://office2.tail0f5f56.ts.net/api/v1/' >> ~/.bashrc && source ~/.bashrc
```

And add it to the systemd EnvironmentFile so service-launched processes see it:

```bash
echo 'VIKUNJA_BASE_URL=https://office2.tail0f5f56.ts.net/api/v1/' >> /data/services/openclaw/secrets/openclaw-gateway.env
```

Verify:

```bash
python3 -c "from scripts.common.vikunja_config import get_vikunja_base_url; print(get_vikunja_base_url())"
```

Expected: `https://office2.tail0f5f56.ts.net/api/v1/`

---

## Bootstrap (first run, manual)

The `--bootstrap` flag fetches all current Vikunja task and project state, seeds the
cache files, and records the initial freshness timestamp. It does NOT classify or emit
any conflict events. Run it ONCE, manually:

```bash
cd ~/kg-automation && python3 -m scripts.sync.driver --bootstrap
```

Expected: exit 0, state files populated (`task-cache.json`, `project-cache.json`,
`freshness.json`, `last-tick.json`), no `conflict-events.jsonl` created.

Verify:

```bash
ls -l /data/services/openclaw/state/sync/
```

```bash
cat /data/services/openclaw/state/sync/last-tick.json | jq
```

If bootstrap fails, the failure record is in `last-tick.errors.jsonl`. Fix the
underlying issue (most likely: token missing, Vikunja unreachable, URL config absent,
permissions) and re-run.

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
cat /data/services/openclaw/state/sync/last-tick.json | jq '{started_at_utc, duration_ms, events_emitted, cycle_error, layer_summary}'
```

`cycle_error` should be `null`. `layer_summary` shows the project-layer audit result.

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

## Project layer audit

The driver records a `layer_summary` block in `last-tick.json` each tick. To inspect it:

```bash
cat /data/services/openclaw/state/sync/last-tick.json | jq '.layer_summary'
```

Fields: `projects_total`, `projects_new`, `projects_changed`, `projects_deleted`,
`project_cache_path`. `projects_new` and `projects_deleted` are the most operationally
significant: a non-zero `projects_new` means the Vikunja project list has expanded since
the last tick; `projects_deleted` means a project was removed.

To inspect the raw project cache:

```bash
cat /data/services/openclaw/state/sync/project-cache.json | jq 'keys'
```

Project events do **not** produce WhatsApp alerts or `conflict-events.jsonl` rows.
If a new project appears that you did not expect, check Vikunja's UI directly.

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

## Deletion cleanup (Phase 5b)

When a task is present in the cache but absent from the Vikunja full-poll response
(`in_cache_only`), the driver enters Phase 5b before removing it from the new cache.
Phase 5b cross-references:

1. `habits-history.jsonl` — if the task has a completion history, a deletion note is
   written to `conflict-events.jsonl` with class `cache_only_with_history`.
2. `schedule.yaml` — if the task is referenced in the active schedule, the schedule
   entry is flagged for cleanup.

Only after these cross-reference checks does the task leave the cache. The conflict-event
row documents what was removed and why. To review recent deletions:

```bash
jq -c 'select(.class == "cache_only_with_history" or .class == "cache_only_deleted")' /data/services/openclaw/state/sync/conflict-events.jsonl | tail -n 10
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

Runs all 7 phases in memory. Skips state writes. Skips the openclaw CLI call.
Logs a summary to stderr.

### "I want to temporarily disable the driver"

```bash
systemctl --user stop felix-vikunja-sync.timer
```

State files remain. Re-enable with `systemctl --user start felix-vikunja-sync.timer`.

### "The URL config is missing or wrong"

Check the resolution path:

```bash
python3 -c "from scripts.common.vikunja_config import get_vikunja_base_url; print(get_vikunja_base_url())"
```

If it raises `VikunjaConfigError`, either the env var `VIKUNJA_BASE_URL` is unset or
`/data/services/openclaw/config/vikunja-base-url.txt` is missing. Re-create the file
per the *URL config file* section above.

### Vikunja unreachable

The driver tolerates this — each tick that fails on the Phase 1 fetch records the
failure to `last-tick.errors.jsonl` and does NOT write any new state files (Phase 6
is skipped). Because the driver uses **full-poll** (not incremental), no events are
missed: the next successful tick fetches the complete current state and diffs against
the last successful cache.

---

## Known soft edge (Vikunja server-side auto-advance)

When Felix completes a recurring habit via WhatsApp reply, Vikunja's server-side
auto-advance flips `done` back to `false` and advances `due_date`. The driver's
diff phase observes this as a divergence — and the driver cannot distinguish
"Vikunja auto-fired" from "Kent edited" because Vikunja v0.24.6 returns
`updated_by: null` on every task.

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
- `layer_summary.projects_deleted` is non-zero and you did not intentionally delete a project

---

## References

- Spec (Mission A — driver): [`kitty-specs/felix-vikunja-sync-reconciliation-driver-01KTA1J3/spec.md`](<../../kitty-specs/felix-vikunja-sync-reconciliation-driver-01KTA1J3/spec.md>)
- Spec (Mission C — project layer + URL config): [`kitty-specs/felix-vikunja-sync-project-layer-and-url-config-01KTCDZ7/spec.md`](<../../kitty-specs/felix-vikunja-sync-project-layer-and-url-config-01KTCDZ7/spec.md>)
- ADR: [`ADR-0003 — Felix-Vikunja sync architecture`](<../design/architecture/adr/0003-felix-vikunja-sync-architecture.md>)
- Cycle pipeline contract: [`contracts/cycle-pipeline.md`](<../../kitty-specs/felix-vikunja-sync-project-layer-and-url-config-01KTCDZ7/contracts/cycle-pipeline.md>)
- URL config contract: [`contracts/url-config.md`](<../../kitty-specs/felix-vikunja-sync-project-layer-and-url-config-01KTCDZ7/contracts/url-config.md>)
- Conflict-event schema: [`contracts/conflict-event-schema.md`](<../../kitty-specs/felix-vikunja-sync-reconciliation-driver-01KTA1J3/contracts/conflict-event-schema.md>)
- WhatsApp send contract: [`contracts/whatsapp-send.md`](<../../kitty-specs/felix-vikunja-sync-reconciliation-driver-01KTA1J3/contracts/whatsapp-send.md>)
- State directory layout: [`contracts/state-directory.md`](<../../kitty-specs/felix-vikunja-sync-reconciliation-driver-01KTA1J3/contracts/state-directory.md>)
- Research: [`docs/research/felix-vikunja-sync-architecture/`](<../research/felix-vikunja-sync-architecture/>)
- Source issues: [#518](https://github.com/kentonium3/kg-automation/issues/518), [#519](https://github.com/kentonium3/kg-automation/issues/519), [#520](https://github.com/kentonium3/kg-automation/issues/520)
- Parent epic: [#507](https://github.com/kentonium3/kg-automation/issues/507)
