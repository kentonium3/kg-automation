# Data Model: Suppress expected drift alerts during rebaseline

No new persistent data is introduced. The helper is a **read-only consumer** of an
existing entity and produces one ephemeral output.

## Entities consumed

### Pending-rebaseline token (existing — owned by felix-deployer)

- **Location**: `/data/services/felix-deployer/state/rebaseline-pending.json`
- **Written by**: `scripts/deploy/felix-deployer/rebaseline.py` (`write_token`, atomic).
- **Read by (new)**: `expected_drift.py` via `rebaseline.read_token` (never written).
- **Fields consumed by this mission**:

  | Field | Type | Use here |
  |-------|------|----------|
  | `expected_baselines` | `list[str]` | The set of baseline filenames with expected in-flight drift. Membership source for FR-002(b). |
  | `pending_since_utc` | ISO-8601 `str` | Window-open timestamp. Freshness = `now − pending_since_utc ≤ AUDIT_SUPPRESS_WINDOW_SECONDS` (~900 s, a dedicated short bound — NOT felix-deployer's 24 h `MAX_AGE_SECONDS`). See FR-005. |

  Other token fields (`schema_version`, `observed_head_sha`, `surface_ids`,
  `matched_files`, `last_check_utc`, `alerts_emitted`) are ignored.
- **Absent/malformed semantics**: `read_token` returns `None` for an absent or
  unreadable/malformed file → the expected set is empty (FR-004).

### Baseline (existing — owned by security-monitor)

- A named snapshot file in `/data/services/security-monitor/baselines/` (e.g.
  `systemd-user-unit-contents.txt`). `audit.sh`'s `check_baseline(name, current)`
  diffs the live value against the stored snapshot. `name` is the join key against
  `expected_baselines`.

## Value produced (ephemeral)

### Expected-drift set

- **Producer**: `expected_drift.py --list`
- **Shape**: whitespace-separated baseline names on stdout (possibly empty).
- **Consumer**: `audit.sh` shell variable `EXPECTED_DRIFT`, consulted by exact-token
  membership inside `check_baseline()`.
- **Lifetime**: one audit run. Never persisted.

## Decision truth table (the deterministic core, IC-01/IC-02)

**Detection is unconditional.** For every drifted baseline, `check_baseline` always
emits `[ALERT] <name>` + sets `ALERT=1`, and the run exits `1` — so felix-deployer
always detects the drift and rebaselines (FR-008). The table below governs only
whether that baseline's line is included in the **human push**:

| Token state | `name ∈ expected_baselines` | Fresh (age ≤ ~15 min) | Push includes this baseline? |
|-------------|:---------------------------:|:---------------------:|------------------------------|
| present | yes | yes | **No — push suppressed** (line stays in log/stdout + `drift-events.jsonl`) |
| present | yes | no (stale) | Yes — pushed (FR-005) |
| present | no | — | Yes — pushed (FR-002/FR-003 unexpected) |
| absent | — | — | Yes — pushed (FR-004) |
| unreadable / malformed | — | — | Yes — pushed (FR-004) |
| helper/import error | — | — | Yes — pushed (FR-004/NFR-002/NFR-003, fail-safe) |

Non-baseline IOC alert lines never match `changed since baseline:` → always pushed
(R6/FR-003). The push fires iff at least one alert line survives the filter.

## Invariants

- **INV-1** (read-only): the mission never writes to any felix-deployer state (C-001).
- **INV-2** (single source of truth): "expected" and "stale" are defined solely by
  felix-deployer's token fields + `MAX_AGE_SECONDS` (C-002).
- **INV-3** (fail toward alerting): every non-`(present ∧ member ∧ fresh)` case pages
  (NFR-003).
- **INV-4** (record preserved): a suppressed drift still writes the audit log +
  `drift-events.jsonl` identically to an alerted one (FR-006).
- **INV-5** (detection contract preserved): the `[ALERT] <name>` stdout line and the
  exit-`1`-on-drift behavior are unchanged for every drift, so felix-deployer's
  reconcile still detects expected drift and stamps the baseline (FR-008). Only the
  push emit is gated.
