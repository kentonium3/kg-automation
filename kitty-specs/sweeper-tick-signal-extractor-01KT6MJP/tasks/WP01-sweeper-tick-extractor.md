---
work_package_id: WP01
title: Sweeper tick extractor
dependencies: []
requirement_refs:
- FR-001
- FR-002
- FR-003
- FR-004
- FR-005
- FR-006
- FR-007
- FR-008
- FR-009
- FR-010
- NFR-001
- NFR-002
- NFR-003
- NFR-004
- C-001
- C-002
- C-003
- C-004
planning_base_branch: main
merge_target_branch: main
branch_strategy: Planning artifacts for this feature were generated on main. During /spec-kitty.implement this WP may branch from a dependency-specific base, but completed changes must merge back into main unless the human explicitly redirects the landing branch.
base_branch: kitty/mission-sweeper-tick-signal-extractor-01KT6MJP
base_commit: d2cff0d98c988a65d4edd6c8b95f9e7f25f03f2a
created_at: '2026-06-03T11:48:59.128600+00:00'
subtasks:
- T001
- T002
- T003
- T004
- T005
- T006
- T007
shell_pid: "51028"
agent: "claude"
assignee: "claude"
history:
- timestamp: '2026-06-03T11:50:00Z'
  actor: claude:opus-4-7:planner
  action: created
authoritative_surface: scripts/openclaw/observation/
execution_mode: code_change
owned_files:
- scripts/openclaw/observation/signals/sweeper_tick.py
- scripts/openclaw/observation/signals/config_loader.py
- scripts/openclaw/observation/signals/config.toml
- scripts/openclaw/observation/tick.py
- scripts/openclaw/observation/tests/test_signals_sweeper_tick.py
- scripts/openclaw/observation/tests/test_config_loader.py
- docs/design/architecture/data/signal-to-doc-map.json
tags: []
---

# WP01 — Sweeper tick extractor

**Mission**: `sweeper-tick-signal-extractor-01KT6MJP` — [spec.md](../spec.md), [plan.md](../plan.md), [data-model.md](../data-model.md), [contracts/sweeper-tick-extractor.contract.md](../contracts/sweeper-tick-extractor.contract.md)
**Source issue**: [#510](https://github.com/kentonium3/kg-automation/issues/510)

## Objective

Land the `sweeper_tick` signal extractor so felix-habit-sweeper failures escalate automatically through the existing Haiku-gate. Six source surfaces ship together (extractor, config_loader update, config.toml entry, dispatch wiring, tests, signal-to-doc-map entry); the seventh subtask is the broader regression run.

## Context

Mission #490 built the signal-extraction substrate. Three log-scanning extractors already exist (`creds_restore`, `watchdog_reconnect`, `openclaw_unhandled_error`) — all in `scripts/openclaw/observation/signals/`. Mission #60 / #408 added the `felix-habit-sweeper` systemd timer plus its JSONL ledger at `/data/services/openclaw/state/habits/sweeper-ledger.jsonl`. This WP adds a fourth extractor that reads that ledger and trips on three conditions per the data-model truth table.

Design decisions resolved during specify/plan:
- Binary semantic: `count_cycle = 1` for "bad", `0` for "good"; `cycle_threshold = 1` trips when bad. The quiet-cycle gate from #512 keeps good cycles below threshold automatically.
- Skip `dry_run: true` records when locating "latest". Diagnostic invocations don't trigger production alarms.
- Staleness threshold: 26 hours (24 h cadence + 2 h slack), named constant in the extractor module.
- New `source_kind = "sweeper_ledger_jsonl"`.

## Branch Strategy

- Planning base branch: `main`
- Final merge target: `main`
- Execution worktree: allocated automatically by `spec-kitty next` per `lanes.json`.

---

## Subtask T001 — Implement the extractor module

**Purpose**: Write `scripts/openclaw/observation/signals/sweeper_tick.py` implementing the `extract()` function with the same signature the other three extractors use and the predicate from `contracts/sweeper-tick-extractor.contract.md`.

**Steps**:

1. Read the three existing extractors to internalize the patterns:
   - `scripts/openclaw/observation/signals/creds_restore.py` — the simplest of the three; thin wrapper around `_engine.run_extraction`.
   - `scripts/openclaw/observation/signals/types.py` — contains `SignalExtraction` dataclass.
   - `scripts/openclaw/observation/signals/config_loader.py` — contains `SignalDefinition` dataclass.
2. Note that the existing extractors all delegate to `_engine.run_extraction` because they share a log-scanning pattern. The sweeper extractor does NOT delegate — it has a different read pattern (latest-record JSONL parse). Implement directly.
3. Create the new module. Structure:

   ```python
   """Signal extractor for felix-habit-sweeper tick failures (#510).

   Reads the latest non-dry-run record from the sweeper ledger and trips on
   three conditions: (a) exit_status != "success", (b) errors[] non-empty,
   (c) latest started_at_utc older than STALE_THRESHOLD_HOURS. See
   contracts/sweeper-tick-extractor.contract.md for the full predicate.
   """
   from __future__ import annotations

   import json
   from datetime import datetime, timedelta, timezone
   from pathlib import Path
   from typing import Optional

   from scripts.openclaw.observation.signals._engine import redact_dict
   from scripts.openclaw.observation.signals.config_loader import SignalDefinition
   from scripts.openclaw.observation.signals.openclaw_log import LogCursor
   from scripts.openclaw.observation.signals.types import SignalExtraction

   STALE_THRESHOLD_HOURS = 26
   ```

4. Implement the public `extract` function with the signature mirroring the other extractors:

   ```python
   def extract(
       state_dir: Path,
       signal_def: SignalDefinition,
       now_utc: datetime,
       prior_cursor: Optional[LogCursor],
       prior_rolling_count: int,
   ) -> SignalExtraction:
       """Walk the sweeper ledger; return a SignalExtraction.

       Args mirror the other extractors so build_extractor_dispatch() can
       hand off uniformly. state_dir and prior_cursor are accepted for
       signature compatibility but not used — this extractor is cursorless
       and stateless.
       """
       ledger_path = Path(signal_def.source_path_pattern)
       count_cycle, excerpts, last_event_at = _evaluate(ledger_path, now_utc, signal_def)
       return SignalExtraction(
           signal_id=signal_def.signal_id,
           count_cycle=count_cycle,
           count_rolling=prior_rolling_count + count_cycle,
           excerpts=excerpts,
           last_event_at_utc=last_event_at,
           new_cursor=None,
       )
   ```

5. Implement the private `_evaluate` helper. It should:
   - Return `(1, [excerpt], None)` and short-circuit if the ledger file doesn't exist, is empty, or contains no parseable records.
   - Read the ledger from the tail. A simple `Path.read_text().splitlines()` is adequate at current scale (<1 MB for years); the NFR-001 budget is 500 ms.
   - Walk the parsed records in REVERSE order (newest first). Tolerate `json.JSONDecodeError` and skip the line (captures the trailing-partial-line case).
   - Skip records where `record.get("dry_run") is True`.
   - On the first non-dry-run record found, evaluate the three conditions in order:
     - Stale: `now_utc - parse_iso(record["started_at_utc"]) >= timedelta(hours=STALE_THRESHOLD_HOURS)` → trip with synthetic stale excerpt.
     - Failed: `record.get("exit_status") != "success"` → trip with redacted record JSON.
     - Errors: `record.get("errors")` is a non-empty list → trip with redacted record JSON.
     - All pass → return `(0, [], record["started_at_utc"] parsed)`.
   - If the loop exits without finding a non-dry-run record, return the synthetic "no production record" excerpt with `count_cycle=1`.

6. Implement small private helpers:
   - `_parse_iso(s: str) -> Optional[datetime]` — return `datetime` parsed from ISO-8601 with `Z` suffix, or `None` on parse failure. Normalize to tz-aware UTC.
   - `_synthetic_stale_excerpt(record, now_utc)` — builds the synthetic JSON per data-model § "Excerpt content" row 4. Returns a JSON string.
   - `_synthetic_no_record_excerpt(ledger_path, ledger_exists, total_records, dry_run_only_count)` — builds the synthetic JSON per data-model rows 5-7. Returns a JSON string.
   - `_record_excerpt(record, signal_def)` — `json.dumps(redact_dict(record, ()), sort_keys=True)`. The redact_keys arg is empty per #512 spec (redaction is value-length-driven, not key-name-driven, per mission #490 spec C-005).

7. Verify the module imports without errors:
   ```
   python3 -c "from scripts.openclaw.observation.signals import sweeper_tick"
   ```

**Files**:
- `scripts/openclaw/observation/signals/sweeper_tick.py` (NEW; ~120 lines)

**Validation**:
- [ ] Module imports cleanly.
- [ ] `extract()` signature matches the three existing extractors exactly.
- [ ] No `datetime.now()` calls in the module (per Invariant I-2).
- [ ] No filesystem writes (per Invariant I-1).

---

## Subtask T002 — Add new source_kind to config_loader

**Purpose**: Make the config parser accept `source_kind = "sweeper_ledger_jsonl"`.

**Steps**:

1. Open `scripts/openclaw/observation/signals/config_loader.py`.
2. Locate `_VALID_SOURCE_KINDS` (around line 46). It's a set currently containing `{"openclaw_log", "agent_jsonl", "systemd_journal"}`.
3. Add `"sweeper_ledger_jsonl"` to the set.
4. No other changes needed in this file — the loader's other logic is source-kind-agnostic.

**Files**:
- `scripts/openclaw/observation/signals/config_loader.py` (1-line edit + comment)

**Validation**:
- [ ] `grep -nE "_VALID_SOURCE_KINDS|sweeper_ledger_jsonl" scripts/openclaw/observation/signals/config_loader.py` shows the new value.
- [ ] Existing tests for the config loader still pass.

---

## Subtask T003 — Add config.toml block

**Purpose**: Register the new signal in the production config so the orchestrator picks it up.

**Steps**:

1. Open `scripts/openclaw/observation/signals/config.toml`.
2. Append a new section at the bottom (after `[signals.openclaw_unhandled_error]`):

   ```toml
   [signals.sweeper_tick]
   source_kind             = "sweeper_ledger_jsonl"
   source_path_pattern     = "/data/services/openclaw/state/habits/sweeper-ledger.jsonl"
   match_pattern           = ""
   match_kind              = "substring"
   cycle_threshold         = 1
   rolling_window_minutes  = 60
   rolling_threshold       = 1
   dedup_strategy          = "open_issue_present"
   priority                = "P2"
   area_label              = "felix-core"
   tier_hypothesis         = "3"
   excerpt_lines           = 1
   enabled                 = true
   ```

   `match_pattern = ""` and `match_kind = "substring"` are present for schema-shape compatibility with the loader; the sweeper extractor does not use them. Document this with an inline comment.

3. Add a short comment block above the new section explaining the binary semantic and the staleness threshold reference, in the same style as the existing inline comments.

**Files**:
- `scripts/openclaw/observation/signals/config.toml` (adds ~20 lines)

**Validation**:
- [ ] `grep -nE "\[signals\.sweeper_tick\]" scripts/openclaw/observation/signals/config.toml` returns one match.
- [ ] `python3 -c "from scripts.openclaw.observation.signals.config_loader import load_config; print(load_config('scripts/openclaw/observation/signals/config.toml'))"` parses without raising.

---

## Subtask T004 — Wire into the dispatch table

**Purpose**: Make `build_extractor_dispatch()` aware of the new extractor.

**Steps**:

1. Open `scripts/openclaw/observation/tick.py`.
2. Locate the existing per-signal imports near the top — three lines like:

   ```python
   from scripts.openclaw.observation.signals import creds_restore as _creds_restore
   ```

   Add an equivalent line for `sweeper_tick`:

   ```python
   from scripts.openclaw.observation.signals import sweeper_tick as _sweeper_tick
   ```

3. Locate `build_extractor_dispatch()` (around line 296). Its return statement maps signal_ids to extractor functions. Add an entry:

   ```python
   return {
       "whatsapp_creds_restore": _creds_restore.extract,
       "web_watchdog_reconnect": _watchdog_reconnect.extract,
       "openclaw_unhandled_error": _unhandled_error.extract,
       "sweeper_tick": _sweeper_tick.extract,        # NEW (#510)
   }
   ```

**Files**:
- `scripts/openclaw/observation/tick.py` (2 line additions; no other changes)

**Validation**:
- [ ] `grep -nE "_sweeper_tick|sweeper_tick.*extract" scripts/openclaw/observation/tick.py` returns at least two matches (import + dispatch entry).
- [ ] `python3 -c "from scripts.openclaw.observation.tick import build_extractor_dispatch; print(build_extractor_dispatch())"` shows the new key.

---

## Subtask T005 — Implement the test suite

**Purpose**: Cover all eight named cases from `contracts/sweeper-tick-extractor.contract.md` § "Test obligations".

**Steps**:

1. Open `scripts/openclaw/observation/tests/` and read `test_signals_creds_restore.py` end-to-end to understand the existing test style — fixtures, helper builders, assertions.
2. Create `scripts/openclaw/observation/tests/test_signals_sweeper_tick.py`. Imports:

   ```python
   from __future__ import annotations

   import json
   import sys
   from datetime import datetime, timedelta, timezone
   from pathlib import Path

   import pytest

   _REPO_ROOT = Path(__file__).resolve().parents[4]
   if str(_REPO_ROOT) not in sys.path:
       sys.path.insert(0, str(_REPO_ROOT))

   from scripts.openclaw.observation.signals.config_loader import SignalDefinition
   from scripts.openclaw.observation.signals.sweeper_tick import extract, STALE_THRESHOLD_HOURS
   ```

3. Write a `_signal_def` factory that produces a SignalDefinition with `source_path_pattern` pointing at a tmp_path-relative ledger:

   ```python
   def _signal_def(ledger_path: Path) -> SignalDefinition:
       return SignalDefinition(
           signal_id="sweeper_tick",
           source_kind="sweeper_ledger_jsonl",
           source_path_pattern=str(ledger_path),
           match_pattern="",
           match_kind="substring",
           cycle_threshold=1,
           rolling_window_minutes=60,
           rolling_threshold=1,
           dedup_strategy="open_issue_present",
           dedup_window_hours=24,
           priority="P2",
           area_label="felix-core",
           tier_hypothesis="3",
           excerpt_lines=1,
           enabled=True,
       )
   ```

   (Verify the exact field set by reading `SignalDefinition` in `config_loader.py` first — the example above is illustrative and may need adjustment.)

4. Write a `_write_ledger` helper that takes a list of dicts and writes them to the ledger path as JSONL:

   ```python
   def _write_ledger(path: Path, records: list[dict]) -> None:
       path.parent.mkdir(parents=True, exist_ok=True)
       path.write_text("\n".join(json.dumps(r) for r in records) + "\n", encoding="utf-8")
   ```

5. Define a fixed `_NOW` constant (e.g., `2026-06-03T12:00:00Z`) for deterministic tests.

6. Implement the eight named test functions per the contract. For each, name the test after the case name (e.g., `test_success_recent`). Each test:
   - Builds the ledger (via `_write_ledger`).
   - Builds the signal_def.
   - Calls `extract(state_dir=tmp_path, signal_def=..., now_utc=_NOW, prior_cursor=None, prior_rolling_count=0)`.
   - Asserts `result.count_cycle`, the shape of `result.excerpts`, and `result.last_event_at_utc` per the contract's table.

7. Add two additional regression tests:
   - `test_rolling_accumulates`: when `prior_rolling_count=2` and `count_cycle=1`, `count_rolling` must be 3.
   - `test_signal_id_is_passed_through`: the returned `SignalExtraction.signal_id` equals `signal_def.signal_id`.

8. Run the new test file alone first:
   ```
   pytest scripts/openclaw/observation/tests/test_signals_sweeper_tick.py -v
   ```
   Expect all 10 tests to pass.

**Files**:
- `scripts/openclaw/observation/tests/test_signals_sweeper_tick.py` (NEW; ~250 lines)

**Validation**:
- [ ] All eight named cases from the contract's "Test obligations" table are covered.
- [ ] Tests pass: `pytest scripts/openclaw/observation/tests/test_signals_sweeper_tick.py -v`.

---

## Subtask T006 — Add signal-to-doc-map entry

**Purpose**: Register the new signal in the doc-impact resolver so future doc-audit ticks pick up runbook drift when sweeper behavior changes.

**Steps**:

1. Open `docs/design/architecture/data/signal-to-doc-map.json`.
2. Append a new mapping to the `mappings` array. Use the existing entry shape:

   ```json
   {
     "id": "sweeper-tick-stale-or-failed",
     "match": {
       "source": "sweeper-ledger",
       "signal_id": "sweeper_tick"
     },
     "doc_targets": [
       "docs/runbooks/habits-ops.md",
       "scripts/openclaw/agents/felix-admin-habits/AGENTS.md"
     ],
     "rationale": "A sweeper tick failure or staleness implies the habits operations runbook and the felix-admin-habits agent prompt may need updating when the failure pattern is understood. Same pattern as openclaw-cron-drift (#510).",
     "issue_title_prefix": "[doc-audit] sweeper-tick stale or failed",
     "issue_labels": [
       "P3-candidate",
       "spec: brief",
       "area/felix-core"
     ]
   }
   ```

3. Increment `last_updated` to today's date and append `#510` to `updated_by` field at the top of the JSON (follow the pattern of other recent entries — comma-separated or `+`-separated as the file uses).
4. Validate the JSON parses:
   ```
   jq empty docs/design/architecture/data/signal-to-doc-map.json
   ```
5. Run the docs validator:
   ```
   python tooling/scripts/validate_docs.py
   ```

**Files**:
- `docs/design/architecture/data/signal-to-doc-map.json` (~15 line addition)

**Validation**:
- [ ] `jq '.mappings[] | select(.id == "sweeper-tick-stale-or-failed")' docs/design/architecture/data/signal-to-doc-map.json` returns the new entry.
- [ ] `validate_docs.py` exits 0.

---

## Subtask T007 — Full observation test suite

**Purpose**: Confirm no regression in the existing extractors or the tick orchestrator.

**Steps**:

1. Run the full observation suite:
   ```
   pytest scripts/openclaw/observation/tests/ -v
   ```
2. Verify all tests pass — both the new sweeper_tick tests and the existing mission #490 / #61 tests.
3. Run a broader sweep as a sanity check:
   ```
   pytest tests/ -v
   ```

**Validation**:
- [ ] `pytest scripts/openclaw/observation/tests/ -v` exits 0 with all tests passing.
- [ ] `pytest tests/ -v` matches the pre-WP baseline (no new failures introduced by this WP).

---

## Definition of Done

- [ ] All seven subtasks marked done.
- [ ] `pytest scripts/openclaw/observation/tests/ -v` is green end-to-end.
- [ ] The new extractor module, test file, config block, dispatch entry, source_kind enum value, and signal-to-doc-map entry are all present.
- [ ] No edits to files outside the owned_files set.
- [ ] No changes to `SignalState` schema or `last-tick.json` field structure (NFR-003).
- [ ] No changes to `_threshold_status` predicate (NFR-002).

## Reviewer guidance

A reviewer should verify, in order:

1. **The extractor's `extract()` signature matches the three existing extractors exactly** — same arg order, same types, same return type. Any deviation breaks the dispatch hand-off.
2. **The extractor is pure** — no `datetime.now()`, no filesystem writes, no environment reads beyond what's plumbed via arguments. Per Invariant I-2.
3. **The dry-run skip is correct**: a ledger of only-dry-runs trips with the no-record reason, not silently passes.
4. **The stale-detection arithmetic uses `now_utc` from the cycle**, not a `datetime.now()` call. Per Invariant I-2.
5. **All eight named test cases from the contract's "Test obligations" table are present** in `test_signals_sweeper_tick.py`, with assertions matching the truth table.
6. **The signal-to-doc-map entry follows the d43b7387 pattern** for newly-added entries — id, match block, doc_targets, rationale, issue_title_prefix, issue_labels.
7. **No edits to files outside owned_files**. Reviewer can grep the diff for any unexpected paths.

## Risks

- **JSONL ledger size growth**: at current scale (<100 records) the read-and-parse-all approach is trivially fast. If the ledger grows to 100K+ records this becomes a concern; defer until observed.
- **Off-by-one on stale threshold**: 26 h vs 25 h vs 27 h. The constant is named in the module and clearly documented; tune in a follow-on if production shows it's wrong.
- **Test fixture drift if the sweeper contract changes**: tests pin the field set the extractor depends on. A contract change requires both the producer (sweeper) and consumer (this extractor) to update; the tests will fail loudly, which is the desired behavior.

## Activity Log

- 2026-06-03T11:49:01Z – claude – shell_pid=96494 – Assigned agent via action command
- 2026-06-03T11:57:57Z – claude – shell_pid=96494 – Moved to for_review
- 2026-06-03T11:58:07Z – codex – shell_pid=99009 – Started review via action command
- 2026-06-03T14:49:25Z – codex – shell_pid=99009 – Moved to planned
- 2026-06-03T15:33:52Z – claude – shell_pid=50360 – Started implementation via action command
- 2026-06-03T15:35:06Z – claude – shell_pid=50360 – Moved to for_review
- 2026-06-03T15:35:14Z – codex – shell_pid=51028 – Started review via action command
- 2026-06-03T15:39:17Z – codex – shell_pid=51028 – Moved to planned
- 2026-06-03T16:17:54Z – claude – shell_pid=51028 – Moved to in_progress
