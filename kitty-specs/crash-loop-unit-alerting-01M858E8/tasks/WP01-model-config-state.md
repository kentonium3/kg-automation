---
work_package_id: WP01
title: Crash-loop model, config and state persistence
dependencies: []
requirement_refs:
- FR-002
- FR-004
- FR-010
- NFR-006
planning_base_branch: fix/crash-loop-unit-alerting
merge_target_branch: fix/crash-loop-unit-alerting
branch_strategy: Planning artifacts for this mission were generated on fix/crash-loop-unit-alerting. During /spec-kitty.implement this WP may branch from a dependency-specific base, but completed changes must merge back into fix/crash-loop-unit-alerting unless the human explicitly redirects the landing branch.
base_branch: kitty/mission-crash-loop-unit-alerting-01M858E8
base_commit: a657274a4e10bf85931083f1aef1cf5467536ac6
created_at: '2026-11-23T23:17:26.981830+00:00'
subtasks:
- T001
- T002
- T003
- T004
- T005
history:
- at: '2026-11-23T23:40:00Z'
  actor: tasks
  action: Prompt generated via /spec-kitty.tasks
agent_profile: python-pedro
authoritative_surface: scripts/canary/
create_intent:
- scripts/canary/crash_loop_model.py
- scripts/canary/crash_loop_state.py
- scripts/canary/crash_loop_config.json
- tests/canary/test_crash_loop_model.py
- tests/canary/test_crash_loop_state.py
execution_mode: code_change
model: claude-opus-5-5
owned_files:
- scripts/canary/crash_loop_model.py
- scripts/canary/crash_loop_state.py
- scripts/canary/crash_loop_config.json
- tests/canary/test_crash_loop_model.py
- tests/canary/test_crash_loop_state.py
role: implementer
tags: []
task_type: implement
tracker_refs: []
---

# Work Package Prompt: WP01 – Crash-loop model, config and state persistence

## ⚡ Do This First: Load Agent Profile

Use the `/spk-charter-profile-load` skill to load the agent profile specified in the frontmatter, and behave according to its guidance before parsing the rest of this prompt.

- **Profile**: `python-pedro`
- **Role**: `implementer`
- **Agent/tool**: `claude`

---

## ⚠️ IMPORTANT: Review Feedback

Check `review_ref` via `spec-kitty agent tasks status`; address every item; record progress with `spec-kitty agent tasks add-history <WP> --note "..."`.

---

## Objective

Create the foundation the decision core (WP02), the readers (WP03) and the canary integration (WP04) build on:

1. the value types, frozen dataclasses with no behaviour beyond trivial properties;
2. a **strict** configuration loader and the repo config file;
3. a **fail-safe** state store with semantic validation, a single clock rule, atomic writes and a non-blocking lock.

The code is standard library only, has no clock reads in pure functions and makes no model call (NFR-006).

## Context to read first

- `kitty-specs/crash-loop-unit-alerting-01M858E8/data-model.md` (authoritative for every field name).
- `kitty-specs/crash-loop-unit-alerting-01M858E8/research.md` R-07, R-10 and R-13.
- `kitty-specs/crash-loop-unit-alerting-01M858E8/contracts/crash-loop-config.schema.json` and `contracts/crash-loop-state.schema.json`.
- `scripts/canary/dedup.py`. Copy its atomic-write pattern (`tempfile.mkstemp` in the same directory, `fsync`, `os.replace`, unlink the temp file on failure) and its fail-safe load style.

## Branch Strategy

Planning happened on `kitty/mission-crash-loop-unit-alerting-01M858E8`. The merge target is `fix/crash-loop-unit-alerting`, which reaches `main` only through a PR Kent approves. Your execution worktree comes from `lanes.json` through `spec-kitty agent action implement WP01 --agent claude --mission crash-loop-unit-alerting-01M858E8`. Never edit `kitty-specs/` from the lane.

## Subtasks

### T001 — Value types (`scripts/canary/crash_loop_model.py`)

Define frozen dataclasses (`@dataclass(frozen=True)`) exactly as data-model.md names them:

- `RestartObservation(scope, name, restart_policy, restart_count, state, generation)` with a `key` property returning `f"{scope}:{name}"`.
- `ScopeReading(scope, complete, observations: tuple[RestartObservation, ...], excluded: int, error: str | None, elapsed_ms: int)`. Add classmethods `ScopeReading.ok(scope, observations, excluded, elapsed_ms)` and `ScopeReading.failed(scope, error, elapsed_ms)` so readers cannot build inconsistent objects. A failed reading has no observations and a non-empty error.
- `Proof(baseline_at, baseline_count, current_count, observed_at, delta, period_seconds, m, bound)`, with a `holds` property returning `delta >= bound` (research R-05).
- `CrashLoopEvent(kind, key, scope, name, state, episode_started_utc, proof: Proof)`, where `kind` is one of `alert`, `reremind`, `cleared`. Validate `kind` in `__post_init__` and raise `ValueError` otherwise, since that is a programming error.
- `UnverifiedRise(key, scope, name, state, proof: Proof)`.
- The module constants `SCOPES = ("system", "user", "container")` and `UNIT_KEY_RE = re.compile(r"^(system|user|container):.+$")`.

Keep times as aware `datetime` objects in these types. Serialisation belongs to the state module.

### T002 — `CrashLoopConfig` and the config file

In `crash_loop_model.py`:

- `@dataclass(frozen=True) class CrashLoopConfig` with the fields `threshold, window_seconds, quiet_ticks_to_clear, max_alerts_per_tick, read_budget_seconds, ignore: frozenset[str]`. Also keep `ignore_reasons: Mapping[str, str]` for documentation. Module constants `HISTORY_RETENTION = timedelta(hours=24)` and `HISTORY_MAX = 64` (research R-07).
- `class CrashLoopConfigError(ValueError)`.
- `load_config(path: Path) -> CrashLoopConfig`. It reads the JSON and validates **every** rule in data-model.md and the config schema:
  - integer types (reject `bool`, which is an `int` subclass, and reject floats);
  - `2 ≤ threshold ≤ 50`, `60 ≤ window_seconds ≤ 3600`, `quiet_ticks_to_clear ≥ 1`, `max_alerts_per_tick ≥ 1`, `1 ≤ read_budget_seconds ≤ 10`;
  - no unknown top-level keys;
  - `ignore` is a list of objects with exactly the keys `unit` and `reason`, where `unit` matches `UNIT_KEY_RE`, `reason` is a non-empty, non-whitespace string, and there are no duplicates.

  Any violation, an unreadable file or invalid JSON raises `CrashLoopConfigError` with a message naming the field. **Never fall back to defaults** (R-10).
- `DEFAULT_CONFIG_PATH = Path(__file__).with_name("crash_loop_config.json")`.

Create `scripts/canary/crash_loop_config.json`:

```json
{
  "threshold": 3,
  "window_seconds": 900,
  "quiet_ticks_to_clear": 2,
  "max_alerts_per_tick": 3,
  "read_budget_seconds": 6,
  "ignore": []
}
```

### T003 — State load (`scripts/canary/crash_loop_state.py`)

- `DEFAULT_STATE_PATH = Path("/data/services/felix-canary/state/crash-loop.json")` and `DEFAULT_LOCK_PATH = DEFAULT_STATE_PATH.with_name("crash-loop.lock")`.
- In-memory types (mutable dataclasses are fine here):
  - `Episode(started_utc, last_alert_utc, quiet_ticks: int, peak_delta: int)`. There is **no** pending flag: research R-08 says there is no retry.
  - `UnitState(generation: str, boot_id: str, history: list[tuple[datetime, int]], episode: Episode | None)`. `history[-1]` is always the latest observation.
  - `CrashLoopState(updated_at_utc: datetime | None, boot_id: str | None, units: dict[str, UnitState])`, with `CrashLoopState.empty()`.
- `load_state(path, *, now: datetime) -> tuple[CrashLoopState, list[str]]`. The second element is a list of diagnostics, one string per dropped entry, which WP04 writes into the scope evidence. Rules (R-07):
  - A missing file returns an empty state and no diagnostic. An unreadable file, invalid JSON, a non-object document, or `schema_version != 1` returns an empty state and one diagnostic. Never raise.
  - For each unit entry, drop it with a diagnostic if any of these hold:
    - its key does not match `UNIT_KEY_RE`;
    - `generation` is not a non-empty string;
    - `boot_id` is not a non-empty string;
    - `history` is not a non-empty list of `[iso8601, int ≥ 0]` pairs (no fixed maximum; WP02 prunes);
    - any time is unparseable or naive;
    - history times are not strictly ascending, or its counts are not **strictly** increasing (dominance compaction);
    - **any time in the entry is later than `now + 60 s`**. This is the single clock rule: the entry is malformed and the unit becomes first-seen;
    - `episode` is not `null` and not a well-formed `Episode` (`quiet_ticks ≥ 0`, `peak_delta ≥ 0`, both times iso).
  - Top-level `boot_id` is a string or null. Anything else resets it to null with a diagnostic.
- Parse times with `datetime.fromisoformat`, and **reject naive datetimes** rather than assume UTC.

### T004 — Atomic save and lock

- `save_state(state, path, *, now)` writes `{"schema_version": 1, "updated_at_utc": now_iso, "boot_id": ..., "units": {...}}`. Sort the keys and use a 2-space indent with a trailing newline. Use the dedup.py atomic pattern, creating the parent directory with `mkdir(parents=True, exist_ok=True)`. Raise on failure; WP04 catches the error into `errors[]`.
- `class StateLock`, a context manager that opens `lock_path` (creating it), calls `fcntl.flock(fd, LOCK_EX | LOCK_NB)`, and raises `StateLockBusy` on `BlockingIOError`. It releases on exit. It never blocks.
- Serialisation round-trips exactly: `load_state(save_state(x))` returns `x`.

### T005 — Tests

`tests/canary/test_crash_loop_model.py`:

- Config: the shipped file loads, and its values equal the defaults above.
- Config: each rule has one negative test (parametrize), covering bool-as-int, float, zero or negative values, an unknown key (including a stale `slack_seconds`), a duplicate ignore entry, an empty reason, a bad scope prefix, a missing key, bad JSON and a missing file.
- Event `kind` validation; the `ScopeReading.ok/failed` invariants; the `key` property.

`tests/canary/test_crash_loop_state.py` (use `tmp_path` and an injected `now`):

- Round trip.
- A missing file is empty with no diagnostics. Corrupt JSON, a list document and `schema_version: 2` each load empty with one diagnostic.
- **Per-entry drop**: one bad entry among two good ones keeps the good ones. Cover each rejection rule.
- **Clock rule**: an entry with any time later than `now + 60 s` is dropped; one within `+60 s` is kept. Equal consecutive history counts are rejected.
- Atomic write: monkeypatch `os.replace` to raise, then assert the original file is unchanged and no temp file remains.
- Lock: a second `StateLock` on the same path while the first is held raises `StateLockBusy`, and it succeeds after release.

## Definition of Done

- [ ] All subtasks are implemented. The new tests pass, and `.venv/bin/python -m pytest tests/canary -q` passes.
- [ ] `ruff`/lint clean if the repo configures it. The code is typed, uses the standard library only, and contains no `datetime.now()` calls outside `CrashLoopState` construction helpers that take `now`.
- [ ] No other file is touched. If an out-of-map edit is unavoidable, record a one-line rationale in the commit.
- [ ] Commits use conventional messages and these trailers:
  `Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>` and `Claude-Session: https://claude.ai/code/session_01AFaUqc3Puxhf5oxUb9LLP6`.

## Reviewer guidance

- Every validation rule in data-model.md, R-07 and R-10 has a test, and none falls back silently.
- Naive datetimes are rejected and not coerced.
- The lock is non-blocking.
- There is no dead code: each public name is used by WP02, WP03 or WP04 as specified. Note for the reviewer: callers land in later WPs; check the names against data-model.md.
