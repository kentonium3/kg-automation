# Contract: State Directory Layout

**Mission**: `felix-vikunja-sync-reconciliation-driver-01KTA1J3`
**Phase**: Plan / Phase 1 / contracts
**Date**: 2026-06-04

The driver's on-disk state lives under `/data/services/openclaw/state/sync/` on office2. This document fixes the layout and the file-by-file ownership semantics. Implementation owns the I/O in `scripts/sync/state.py`; tests verify the layout via the `tmp_path` fixture mirroring `tests/habits/conftest.py` patterns.

---

## Directory layout

```
/data/services/openclaw/state/sync/
├── freshness.json              # FreshnessPointer (entity 2)
├── task-cache.json             # TaskCacheRecord (entity 3)
├── project-cache.json          # ProjectCacheRecord (entity 8)
├── guard-state.json            # Guard state (G-3 daily cap)
├── conflict-events.jsonl       # ConflictEvent log (entity 4) — append-only
├── last-tick.json              # PerTickHealthRecord — success path; overwrite
└── last-tick.errors.jsonl      # PerTickHealthRecord — failure path; append-only
```

Owner: `claude:secondbrain` (matches sibling state-dirs `habits/`, `escalation/`, `enrichment/`).
Mode: 0750 on the directory; 0640 on the files (consistent with the rest of `/data/services/openclaw/state/`).

---

## File-by-file semantics

### `freshness.json` (overwrite)

Single JSON file holding the per-layer pointer values. Written atomically (write to `.tmp`, fsync, rename) during the cycle's `complete` phase. Never appended to.

```json
{
  "schema_version": 1,
  "last_updated_utc": "2026-06-04T19:25:32Z",
  "layers": {
    "status_and_task": {
      "last_polled_utc": "2026-06-04T19:25:30Z"
    }
  }
}
```

**Bootstrap state**: on first install, this file does NOT exist. The `--bootstrap` invocation creates it with `last_polled_utc` set to the bootstrap cycle's `started_at_utc`.

**Recovery**: if this file is corrupted (parse error), the driver exits with code 1 and writes the failure to `last-tick.errors.jsonl`. Operator recovery: invoke `--bootstrap` to regenerate from scratch (will produce a stream of "first observation" cache writes but NO conflict events — this is the safe recovery path).

### `task-cache.json` (overwrite)

The full TaskCacheRecord schema (entity 3). One JSON object containing all tracked tasks. Written atomically during `complete`. Read at cycle start by the `diff` phase.

Estimated steady-state size at current Felix scale (15 active habit tasks + future capability tasks): single-digit KB. At ~100 tasks: tens of KB.

**Why one file, not one-file-per-task**: single-file simplifies atomic-write semantics. The 100-task upper bound keeps file size manageable. If the cache grows past 1MB, consider sharding (out of scope for this mission).

### `project-cache.json` (overwrite)

ProjectCacheRecord schema (entity 8). Single JSON object containing all projects the driver has touched. Updated just-in-time when a task references an unknown project_id. Written atomically.

### `guard-state.json` (overwrite)

The G-3 daily cap state plus any future guard state. Single JSON object. Written atomically by the `emit` phase whenever guard state changes (i.e., when an unsafe event is delivered or the daily counter rolls).

```json
{
  "schema_version": 1,
  "g3_daily_cap": {
    "calendar_day_et": "2026-06-04",
    "unsafe_pings_sent_today": 0,
    "cap": 5
  }
}
```

**Day rollover**: on cycle start, if `calendar_day_et` is not the current ET calendar day, reset `unsafe_pings_sent_today` to 0 and update `calendar_day_et`. Operators can adjust the `cap` value by editing this file directly between cycles; the driver re-reads on every cycle.

### `conflict-events.jsonl` (append-only)

The conflict-event log. Each line is one ConflictEvent row per the schema in `conflict-event-schema.md`. **Append-only** — never rewritten in place, never has rows removed. Per-line write is atomic (single `write` of `{json}\n`); no inter-row corruption is possible under normal POSIX semantics.

Estimated steady-state size: at ≤1 unsafe ping/day plus a handful of auto_resolved events per day, the log grows on the order of 1KB/day. A year is single-digit MB. No rotation built in (per research.md Unknown 2).

**Read access**: G-1 dedup reads the file via a tail-scan looking back at most 24h. Implementation reads the file in reverse line order (or chunks) and stops at the first event older than now-24h. For a year-old log this is hundreds of bytes scanned per cycle (assuming events average ~600 bytes), negligible cost.

### `last-tick.json` (overwrite — success path)

PerTickHealthRecord schema (entity 5). Written atomically at the END of every successful cycle (the very last step of phase `complete`). Operator reads this file to confirm the driver is alive and healthy.

### `last-tick.errors.jsonl` (append-only — failure path)

When a cycle FAILS (exit code 1 or 2), the failure record is appended here instead of overwriting `last-tick.json`. This preserves the most recent SUCCESS record (so the operator can see what was working) while the failure stream accumulates.

Operator-side semantics:
- "Is the driver alive?" → tail `last-tick.errors.jsonl` for entries newer than the current `last-tick.json`'s `completed_at_utc`.
- "Has anything failed recently?" → count entries in `last-tick.errors.jsonl` with `failed_at_utc` > 24h ago.

---

## Atomic-write pattern

Every overwrite uses:

```python
def atomic_write_json(path: Path, data: dict) -> None:
    tmp = path.with_suffix(path.suffix + ".tmp")
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(data, f, sort_keys=True, indent=2)
        f.flush()
        os.fsync(f.fileno())
    os.replace(tmp, path)
```

This is the same pattern used by `scripts/habits/sweeper.py:_atomic_write_json` and is referenced from there in implementation. Append-only files use a single `f.write(line + "\n")` followed by `f.flush()` — no temp file, no rename.

---

## State directory lifecycle

| Phase | Action |
|---|---|
| **Install** | Directory created with `mkdir -p`; mode 0750; ownership `claude:secondbrain` set by the installer. |
| **First bootstrap** | `--bootstrap` invocation populates `freshness.json`, `task-cache.json`, `project-cache.json`, writes empty `guard-state.json`, creates empty `conflict-events.jsonl`, writes the bootstrap-cycle `last-tick.json`. No `last-tick.errors.jsonl` yet (only created on first failure). |
| **Steady state** | Each tick reads + writes per the cycle pipeline. |
| **Operator recovery** | Delete `task-cache.json` + `freshness.json` and re-run `--bootstrap`. Cache + pointer regenerate from scratch. Conflict log is preserved. |
| **Disable** | Operator stops the systemd timer. Files persist (no cleanup). Driver can be re-enabled by restarting the timer; the next tick picks up from the persisted state. |

---

## Backup integration

`/data/services/openclaw/state/sync/` is part of `/data/` and is captured by the existing Restic backup. No special configuration needed. The most recent state (last 24h) is recoverable from a Restic snapshot.

**Disaster recovery scenario**: if office2's disk fails and Restic is the only surviving copy, the operator restores `/data/services/openclaw/state/sync/` from the most recent snapshot and the driver resumes from the restored freshness pointer. Any divergences that occurred between the snapshot and the disaster are re-detected on the next cycle (the freshness pointer was older, so the delta poll covers the gap). No events are lost.

---

## File-system permissions

Permissions are inherited from the existing `/data/services/openclaw/state/` parent directory. Specifically:

- All files writable by `claude` (the user the systemd unit runs as)
- All files readable by `secondbrain` group (allows operator reads via the existing `kgale` user → secondbrain group membership pattern, matching habits/escalation precedent)
- World: no access

No special ACLs needed. No sudo needed for any operation.

---

## Testing the layout

`tests/sync/test_state.py` covers:

- `atomic_write_json` roundtrip (write → read → equal)
- `atomic_write_json` mid-write crash: file is either the old version or the new version, never partial
- `freshness.json` schema validation
- `task-cache.json` field-set whitelist enforcement
- `guard-state.json` day-rollover behavior
- `last-tick.json` overwrite vs `last-tick.errors.jsonl` append semantics
- Bootstrap path: empty directory → all files populated after `--bootstrap`

Tests use `tmp_path` fixture; no live `/data/services/openclaw/state/sync/` interaction.
