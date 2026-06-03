# Sweeper tick signal extractor

**Mission**: `sweeper-tick-signal-extractor-01KT6MJP`
**Mission type**: software-dev
**Source issue**: [#510](https://github.com/kentonium3/kg-automation/issues/510)
**Target branch**: `main`
**Created**: 2026-06-03

---

## Intent Summary

Add a `sweeper_tick` signal extractor to the felix-core-digest signal-extraction loop so that `felix-habit-sweeper` failures escalate automatically through the existing Haiku-gate rather than requiring manual `journalctl` or `jq` inspection. The extractor reads the latest record from `/data/services/openclaw/state/habits/sweeper-ledger.jsonl` (the append-only JSONL ledger the sweeper writes alongside each per-date tick artifact) and trips on three conditions, all binary: (1) `exit_status != "success"` in the latest record, (2) latest `started_at_utc` older than 26 hours OR ledger entirely empty (timer didn't fire), (3) `errors[]` non-empty in the latest record. The signal participates in the existing trip-evaluator and dedup machinery with no orchestrator changes beyond a dispatch-table entry and the per-signal config block.

## Background & Motivation

Mission #60 / #408 shipped `felix-habit-sweeper`, a daily 07:30 ET systemd timer that runs the 48-hour auto-skip pass on day-specific habit tasks and writes a structured per-tick artifact at `/data/services/openclaw/state/habits/sweeper-tick-<date>.json` plus a ledger append at `/data/services/openclaw/state/habits/sweeper-ledger.jsonl`. The tick contract (`kitty-specs/habit-day-specific-scheduling-01KT48Y6/contracts/sweeper-tick.contract.md`) enumerates an explicit `exit_status` enum (`success` plus failure cases) and an `errors[]` array.

Today, sweeper failures surface only on manual inspection — `journalctl --user -u felix-habit-sweeper.service` or `jq` against the per-date artifact. No automated alarm exists. The signal-driven monitoring loop introduced by mission #490 (`signal-driven-monitoring-haiku-gate-01KT22PC`) is the right substrate: it already runs every 15 minutes, dedups against open GitHub issues, and routes through the Haiku gate for escalation. Adding the sweeper-tick extractor closes the silent-failure gap surfaced in the #408 mission review.

Three failure modes the extractor must catch:

- **Sweeper aborted mid-tick**: `exit_status` is one of the non-success enum values (e.g., `vikunja_unreachable`, `malformed_schedule_yaml`, `aborted`).
- **Per-habit failures**: `errors[]` is non-empty in an otherwise-successful run (some habits processed, others raised).
- **Timer didn't fire**: the ledger's most recent `started_at_utc` is older than 26 hours, OR the ledger has no entries at all. The 26-hour threshold is the 24-hour cadence plus 2 hours of slack for a late tick.

## User Scenarios & Testing

### Primary scenario: failed sweeper tick triggers an issue within one 15-minute cycle

1. At 07:30 ET, `felix-habit-sweeper.service` runs and `sweeper.py` writes a ledger record with `exit_status="vikunja_unreachable"`.
2. The next signal-extraction tick (≤15 min later) reads the latest ledger record and detects the failed `exit_status`.
3. The trip evaluator returns `tripped_cycle` (binary signal, count_cycle=1, cycle_threshold=1).
4. Dedup check finds no open `sweeper-tick` issue; the deterministic filer creates one with the standard label set and a body excerpt from the ledger record.
5. Operator triages and resolves; on the next cycle after issue close, a successful tick clears the trip (no new issue).

### Secondary scenario: timer didn't fire (sweeper-stale detection)

1. The sweeper systemd timer fails to fire at 07:30 ET (e.g., OpenClaw gateway down, host outage, unit disabled).
2. The next signal-extraction tick after the 26-hour threshold (~32 hours after the missed tick at most, given the 15-min cycle and the 26-hour staleness budget) reads the ledger, computes `now - latest.started_at_utc > 26 hours`, and trips.
3. The filer creates an issue carrying the latest tick timestamp so the operator sees how long the gap has been.

### Edge cases

- **Ledger has zero entries** (fresh install, never run): trip with reason "no ledger entries — sweeper has never produced a tick." The detector treats absence as failure rather than passing silently.
- **Ledger file missing entirely**: same as zero entries (configuration drift; the sweeper is not deployed).
- **Latest entry is a dry-run** (`dry_run: true` from a development invocation): the extractor MUST NOT trip on a dry-run's `exit_status` field alone — dry-runs may legitimately exit with diagnostic status codes that are not production failures. The detector skips records with `dry_run: true` and falls back to the most recent non-dry-run record. If no non-dry-run record exists within the 26-hour window, that itself is a stale trip.
- **Partial ledger corruption** (last line is truncated mid-write): the detector tolerates and reads the most recent complete JSON line. A corruption-only ledger trips with reason "no parseable records."
- **Clock skew**: the extractor uses `now_utc` from the cycle (the same `now_utc` the existing extractors use), so clock skew is uniform across signals. Not a per-extractor concern.

## Requirements

### Functional

| ID | Status | Requirement |
|---|---|---|
| FR-001 | proposed | Add a new signal extractor module at `scripts/openclaw/observation/signals/sweeper_tick.py` that conforms to the existing `extract()` signature used by `creds_restore.py`, `watchdog_reconnect.py`, and `unhandled_error.py` (returns a `SignalExtraction` dataclass). |
| FR-002 | proposed | The extractor MUST read the JSONL ledger at the path declared in the signal's `source_path_pattern` config field (default: `/data/services/openclaw/state/habits/sweeper-ledger.jsonl`) and locate the most recent **non-dry-run** record. |
| FR-003 | proposed | The extractor MUST evaluate three trip conditions against the located record (or against absence): (a) `exit_status != "success"`; (b) `errors` array non-empty; (c) `now_utc - started_at_utc > 26 hours`. The ledger having zero non-dry-run records, the file missing, or the file containing only unparseable lines all map to condition (c) (stale/absent). |
| FR-004 | proposed | When ANY of the three conditions hold, the extractor MUST return `count_cycle = 1` and an excerpt containing the offending record (or a synthetic excerpt for the no-record case naming the failure reason). When NO condition holds, the extractor MUST return `count_cycle = 0`. |
| FR-005 | proposed | Excerpts MUST honor the redaction policy in `_engine.redact_dict` (redact string values >`REDACT_MAX_VALUE_LEN`). No sweeper field is expected to carry secrets, but the policy applies uniformly per spec C-005 from mission #490. |
| FR-006 | proposed | Add a `[signals.sweeper_tick]` section to `scripts/openclaw/observation/signals/config.toml` with `source_kind = "sweeper_ledger_jsonl"`, `cycle_threshold = 1`, `rolling_window_minutes = 60`, `rolling_threshold = 1`, `dedup_strategy = "open_issue_present"`, `priority = "P2"`, `area_label = "felix-core"`, `tier_hypothesis = "3"`, `excerpt_lines = 1`, `enabled = true`. The binary semantic (1 = bad, 0 = good) makes cycle_threshold=1 the natural mapping; the quiet-cycle gate from #512 means a no-fail cycle stays below the threshold without filing. |
| FR-007 | proposed | Extend `_VALID_SOURCE_KINDS` in `scripts/openclaw/observation/signals/config_loader.py` to include `"sweeper_ledger_jsonl"` so the config parser accepts the new section. |
| FR-008 | proposed | Wire the extractor into `build_extractor_dispatch()` in `scripts/openclaw/observation/tick.py` under the key `"sweeper_tick"`. |
| FR-009 | proposed | Add tests at `scripts/openclaw/observation/tests/test_signals_sweeper_tick.py` covering each FR-003 trip condition (failed exit, errors non-empty, stale latest, empty ledger, missing file, dry-run skipping, partial-line tolerance) plus the no-trip happy path. Test scaffolding patterns follow `test_signals_creds_restore.py`. |
| FR-010 | proposed | Add an entry to `docs/design/architecture/data/signal-to-doc-map.json` per the d43b7387 pattern, with `id: "sweeper-tick-stale-or-failed"`, a `match.source = "sweeper-ledger"` block, `doc_targets` including `docs/runbooks/habits-ops.md` (so that future doc-audit picks up runbook drift when sweeper behavior changes), `issue_title_prefix`, and the standard label set. |

### Non-Functional

| ID | Status | Requirement |
|---|---|---|
| NFR-001 | proposed | The extractor MUST complete in <500 ms per cycle on the production ledger size (currently <100 records; expected growth ~365/year). |
| NFR-002 | proposed | No changes to the trip predicate in `tick.py::_threshold_status` (the quiet-cycle gate from #512 is preserved unchanged). The extractor uses the existing `count_cycle ≥ cycle_threshold` path. |
| NFR-003 | proposed | No changes to the persisted `SignalState` schema or the `last-tick.json` field structure. New signals participate via the existing dispatch + per-signal-state pattern. |
| NFR-004 | proposed | Existing tests for the other three signals MUST continue to pass without modification. |

### Constraints

| ID | Status | Constraint |
|---|---|---|
| C-001 | proposed | The change is Tier 3 (Logic/Workflow) per the project change-risk taxonomy. No pre-flight checklist required. |
| C-002 | proposed | All new code lives in the existing `scripts/openclaw/observation/signals/` and `scripts/openclaw/observation/tests/` directories. No new top-level subtrees. |
| C-003 | proposed | The mission MUST land in a single mission with all FRs satisfied, per the Felix Constitution Directive 7 (no orphaned transitional artifacts). Although this is a feature addition rather than a migration, the same completeness principle applies — the signal-to-doc-map registration is part of the surface and ships with the extractor, not as a follow-on. |
| C-004 | proposed | The detector MUST source `now_utc` from the cycle's `now_utc` parameter (already plumbed through `extract()` calls). No `datetime.now()` calls in the extractor body. |

## Success Criteria

| ID | Criterion | Measurement |
|---|---|---|
| SC-001 | A ledger with a successful latest record produces `count_cycle = 0` (no trip). | Automated unit test against `extract()` with a synthetic ledger containing one `exit_status="success"` record. |
| SC-002 | A ledger with `exit_status != "success"` in the latest record produces `count_cycle = 1`. | Unit test covering each non-success enum value. |
| SC-003 | A ledger with a stale latest record (started_at_utc > 26h old) produces `count_cycle = 1`. | Unit test with `now_utc` advanced 27 hours past `started_at_utc`. |
| SC-004 | A ledger with `errors[]` non-empty produces `count_cycle = 1` even when `exit_status == "success"`. | Unit test. |
| SC-005 | An empty ledger file, a missing ledger file, and a ledger of dry-run-only records all produce `count_cycle = 1` (stale). | Three unit tests. |
| SC-006 | Latest record is dry-run; second-latest is fresh non-dry-run success → `count_cycle = 0`. | Unit test. |
| SC-007 | Trailing partial line in ledger → most recent complete record is used; no exception. | Unit test. |
| SC-008 | After merge, the production signal-extraction tick on office2 emits a `sweeper_tick` signal evaluation in `last-tick.json` (count_cycle, count_rolling, threshold_status) on every cycle. | Observational on office2 after deploy. |
| SC-009 | A manually-injected failed ledger entry on a non-production machine causes the integration test path to file a P2 issue with the right labels. | Replay-mode test (`--replay-log`) extended to cover the new source_kind. |
| SC-010 | `validate_docs.py` passes after the signal-to-doc-map.json update. | Automated. |

## Out of Scope

- Changes to `felix-habit-sweeper.service` or the sweeper script itself (`scripts/habits/sweeper.py`). The extractor only consumes the ledger artifact; the producer is unchanged.
- Changes to `_engine.run_extraction()` or the log-walking framework used by the three openclaw-log extractors. The sweeper extractor is a parallel implementation appropriate for the JSONL-latest-record read pattern.
- Changes to the trip evaluator (`_threshold_status`) or the dedup machinery.
- Per-error-category alarms (e.g., a separate signal for `vikunja_unreachable` vs `malformed_schedule_yaml`). One coarse-grained `sweeper_tick` signal is sufficient until operational experience says otherwise.
- A morning-checkin extractor for the morning-checkin-*.json artifacts. Different ledger, different cadence; defer.

## Assumptions

- The sweeper ledger format matches `kitty-specs/habit-day-specific-scheduling-01KT48Y6/contracts/sweeper-tick.contract.md` and is stable. Verified by inspection of the live ledger on office2 on 2026-06-03 — current records include the `errors`, `exit_status`, `started_at_utc`, and `dry_run` fields the extractor depends on.
- The 26-hour staleness threshold is operationally correct (24 h cadence + 2 h slack). A late tick within 2 hours of the expected fire time stays below the threshold; anything later trips.
- `cycle_threshold = 1` is the right binary mapping for a yes/no signal. The quiet-cycle gate from #512 ensures cycles with `count_cycle = 0` never trip, which is exactly the behavior we want for a passing health check.
- The existing test scaffolding under `scripts/openclaw/observation/tests/` is the right surface (not `signals/tests/` as the issue body says). Verified by directory listing.

## Dependencies

- Mission #490 (`signal-driven-monitoring-haiku-gate-01KT22PC`) — the signal-extraction substrate.
- Mission #61 (`signal-trip-cycle-floor-01KT4NHJ`) — the quiet-cycle gate this extractor relies on for clean no-fail behavior.
- Mission #60 (`felix-habit-sweeper`) and #408 — produces the ledger this extractor reads.
- Reference contract: `kitty-specs/habit-day-specific-scheduling-01KT48Y6/contracts/sweeper-tick.contract.md`.
- Commit `d43b7387` (`feat(docs): mission-end doc-impact resolver`) — the `signal-to-doc-map.json` pattern this mission extends.

## Key Entities

- **Sweeper ledger**: `/data/services/openclaw/state/habits/sweeper-ledger.jsonl` — append-only JSONL, one record per tick.
- **Ledger record**: a JSON object with fields per the sweeper-tick contract — `schema_version`, `tick_id`, `started_at_utc`, `duration_ms`, `dry_run`, `expired_checkin_dates_evaluated`, `habits_evaluated`, `habits_auto_skipped`, `errors`, `exit_status`.
- **`sweeper_tick` signal**: the new entry in `config.toml` and `build_extractor_dispatch()`. Binary semantic: count_cycle=1 means "latest non-dry-run tick is failed or stale," count_cycle=0 means "latest non-dry-run tick is recent and successful."
- **Staleness threshold**: 26 hours. 24 h sweeper cadence + 2 h slack.
- **`sweeper_ledger_jsonl` source_kind**: a new value in `_VALID_SOURCE_KINDS` — distinguishes this read path from `openclaw_log` (log-substring matching) and the reserved-but-unused `agent_jsonl` / `systemd_journal` kinds.
