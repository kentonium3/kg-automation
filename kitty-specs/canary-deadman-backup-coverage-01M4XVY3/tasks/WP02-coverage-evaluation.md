---
work_package_id: WP02
title: Coverage evaluation through the canary's own path
dependencies:
- WP01
requirement_refs:
- FR-001
- FR-002
- FR-003
- FR-004
- FR-012
- NFR-002
- NFR-004
- C-001
- C-002
- SC-001
- SC-003
planning_base_branch: fix/canary-deadman-backup-coverage
merge_target_branch: fix/canary-deadman-backup-coverage
branch_strategy: Planning artifacts for this mission were generated on fix/canary-deadman-backup-coverage. During /spec-kitty.implement this WP may branch from a dependency-specific base, but completed changes must merge back into fix/canary-deadman-backup-coverage unless the human explicitly redirects the landing branch.
base_branch: kitty/mission-canary-deadman-backup-coverage-01M4XVY3
base_commit: 0f7009f6a384fbaeded6c183df657abb84b2e1aa
created_at: '2026-10-14T19:23:23.533540+00:00'
subtasks:
- T006
- T007
- T008
- T009
- T010
phase: Phase 2 - Core behavior
history:
- at: '2026-10-14T19:40:00Z'
  actor: tasks
  action: Prompt generated via /spec-kitty.tasks (plan IC-01; research R1–R5, R12)
agent_profile: python-pedro
authoritative_surface: scripts/office2/felix_health_check/
create_intent:
- scripts/office2/felix_health_check/coverage.py
- scripts/office2/felix_health_check/tests/test_coverage.py
- scripts/office2/felix_health_check/tests/test_agreement.py
- scripts/office2/felix_health_check/tests/fixtures/last-tick.2026-10-14.json
- scripts/office2/felix_health_check/tests/fixtures/last-backup.2026-10-14.json
execution_mode: code_change
lane: planned
model: claude-opus-5-5
owned_files:
- scripts/office2/felix_health_check/coverage.py
- scripts/office2/felix_health_check/tests/test_coverage.py
- scripts/office2/felix_health_check/tests/test_agreement.py
- scripts/office2/felix_health_check/tests/fixtures/**
role: implementer
tags: []
task_type: implement
tracker_refs: []
---

# Work Package Prompt: WP02 – Coverage evaluation through the canary's own path

## ⚡ Do This First: Load Agent Profile

Use the `/spk-charter-profile-load` skill to load the agent profile specified in the frontmatter (or any user-defined profile), and behave according to its guidance before parsing the rest of this prompt.

- **Profile**: `python-pedro`
- **Role**: `implementer`
- **Agent/tool**: `claude`

---

## ⚠️ IMPORTANT: Review Feedback

Check `review_ref` via `spec-kitty agent tasks status`; address every item; record progress with `spec-kitty agent tasks add-history WP02 --note "..."`.

---

## Objectives & Success Criteria

A new module, `scripts/office2/felix_health_check/coverage.py`, exposes one function:

```python
def evaluate_coverage(now: datetime, *, inventory_path: Path = INVENTORY_PATH,
                      read_state: Callable[[str], Any] = _read_json,
                      uptime_seconds: Callable[[], float | None] = _host_uptime) -> list[CoverageFinding]
```

It returns **exactly two** `CoverageFinding`s, in the order `("felix-canary", "restic-backup")`. Each is decided by `scripts.canary.health.evaluate` on that component's inventory target, and it **never raises**.

Done when:
- the incident replay (SC-001 half) yields `felix-canary` → `stale`/failure and `restic-backup` → `failed`/failure;
- the real 2026-10-14 documents yield `healthy`/ok twice;
- every inability yields `unknown`;
- the CI precondition test passes on the real inventory and fails on a doctored one.

## Context & Constraints

- Spec FR-001–FR-004, FR-012, NFR-002–NFR-004, C-001, C-002. Plan IC-01. Research R1–R5 and R12, plus the review dispositions (paula-1/3/4, debbie-2/3). Data model: `CoverageFinding`.
- **C-001**: no bound, good-set or freshness literal in this module. The values come from the inventory, the logic from `scripts/canary/`. Validation of declaration **shape** (R12) is allowed.
- **C-002**: read only the two declared pointer files plus the inventory. The `http_get` and `run_cmd` passed to `health.evaluate` **raise** (R4), so a repointed declaration fails closed as `unknown` rather than executing a command.
- `scripts.canary.registry.load_targets(inventory)` returns **`(targets, gaps)`**.
- Inventory path: resolve from `__file__` (`Path(__file__).resolve().parents[3] / "docs/design/architecture/data/service-inventory.json"`), never the CWD (debbie-3).

## Branch Strategy

- **Planning base branch**: `fix/canary-deadman-backup-coverage` · **Merge target branch**: `fix/canary-deadman-backup-coverage`. Worktrees come from `lanes.json`.

## Subtasks & Detailed Guidance

### Subtask T006 – Findings and outcome mapping

- `COVERAGE_COMPONENTS: tuple[str, ...] = ("felix-canary", "restic-backup")`.
- `@dataclass(frozen=True) class CoverageFinding: component: str; outcome: str; finding: Literal["ok","failure","unknown"]; evidence: str` plus `to_record() -> dict` (keys exactly `component`, `outcome`, `finding`, `evidence`, per the contract).
- Mapping (research R2), with an **allow-list** default:
  - `healthy` → ok;
  - `stale` / `failed` / `degraded` → failure;
  - `unknown` → unknown;
  - `suppressed` → unknown, with evidence `"status '<s>' not alert-eligible: coverage withheld"` (R3, paula-3);
  - **anything else** → unknown.
- Imports of `scripts.canary.*` happen **inside** `evaluate_coverage`'s guarded body, never at module import time, so an import failure is a finding and not a crash. WP03's caller adds a second guard around importing `coverage` itself.

### Subtask T007 – Declaration preconditions (R12) + CI test

- `declaration_problems(health_check: dict) -> list[str]`. Return problems when:
  - `max_age_seconds` is missing, not a finite non-boolean number, or ≤ 0;
  - `key_ledger` is missing or not a dict;
  - there is not exactly one `adjudicated` key with `freshness` and `anchor: true`;
  - any `adjudicated` freshness key carries `max_age_seconds` that is not finite, non-boolean and > 0 (overrides take precedence: `probes.py:598–603`).
- At runtime, a non-empty problem list → `unknown`, `outcome="unavailable"`, evidence `"declaration invalid: …"`. The target is not evaluated.
- Also unknown at runtime: the component is absent from the targets.
- CI test (`test_coverage.py::test_real_inventory_satisfies_preconditions`): for each coverage component, the real inventory has the target, it is alert-eligible (`status in {active, running}`), and `declaration_problems(...) == []` (paula-4). Paired negative: a deep copy with `max_age_seconds` removed → problems non-empty, and `evaluate_coverage` on it → unknown (FR-012 no-op control).

### Subtask T008 – Fail-closed paths (NFR-003)

Each case is one test that asserts both components are unknown (or the affected one is) and that nothing raises:
- inventory file missing; inventory not JSON; inventory JSON but `services` missing;
- one target absent;
- pointer file missing (`read_state` raises `FileNotFoundError`), which flows through `health.evaluate` → `unknown`;
- declaration repointed to `method: "http"`, so the refused effect → unknown;
- `scripts.canary.health` import raising (monkeypatch `sys.modules["scripts.canary.health"] = None`) → both unknown, evidence naming the import.

### Subtask T009 – Sentinel fixtures and agreement corpus

- Fixtures (`tests/fixtures/`):
  - `last-tick.2026-10-14.json` (verbatim, see WP01);
  - `last-backup.2026-10-14.json`, verbatim:

```json
{"schema_version": 2, "snapshot_timestamp_utc": "2026-10-14T15:30:30Z", "snapshot_id": "b1c0d27ca3275c8472e4624d0274597db1a61fac6a0ef9656e869d87269c5de2", "restic_exit_code": 0, "prune_exit_code": 0, "script_finished_at_utc": "2026-10-14T15:30:54Z", "repo_size_bytes": 3940475921, "snapshot_count": 13, "integrity_check_run": false, "integrity_check_passed": null, "last_integrity_check_utc": "2026-09-27T04:00:11Z", "files_processed": 50463, "source_roots_present": true, "repo_fs_free_bytes": 928029237248}
```

  - **Incident pointer, derived from `scripts/office2/restic-backup.sh`'s not-mounted path** (EXIT trap; research F5): `restic_exit_code: 127`, `prune_exit_code: 127`, snapshot ts/id/count `null`, `repo_size_bytes`/`files_processed`/`repo_fs_free_bytes` `null`, `source_roots_present: null`, `last_integrity_check_utc` carried forward `"2026-09-20T04:00:11Z"`, `script_finished_at_utc` that day, `schema_version: 2`, `integrity_check_run: false`, `integrity_check_passed: null`. Add a comment file or a docstring citing the derivation.
  - **Dead-canary tick**: the real tick with `completed_at_utc` = `2026-09-27T15:52:00+00:00`, evaluated at `now = 2026-09-28T11:00:03Z` (debbie's replay values).
- Note: the backup `last_integrity_check_utc` bound is 777600 s (9 days). Pick `now` per case so the *intended* key decides. Document which key each case exercises.
- `test_agreement.py` (SC-003, ≥ 10 documents): for each document, compute the canary's verdict, `health.evaluate(target, …).outcome` with the same injected document, and the health check's `evaluate_coverage(...)` finding for that component. Assert they map consistently (healthy ↔ ok, …).
  - Corpus: healthy real backup; 127 incident; prune 3; snapshot stale; anchor null; future anchor; `snapshot_count` null (`unmeasured_is_unknown` → unknown); `files_processed` 0; key absent; `repo_fs_free_bytes` below minimum; real tick healthy; dead tick; tick missing status; tick zero components.
  - Name the two sentinels explicitly (`test_sentinel_incident_backup_is_failure`, `test_sentinel_dead_canary_is_failure`); paula-1(b).

### Subtask T010 – Post-boot evidence suffix; different CWD

- When the `felix-canary` finding is `failure` with outcome `stale`, and `uptime_seconds()` returns a value below the canary's declared `max_age_seconds`, append ` (host up <N> min: may be a post-boot catch-up)` to the evidence (debbie-4, R9). It is informative only; the finding stays a failure. `_host_uptime` reads `/proc/uptime` and returns `None` on any error.
- Test: the uptime stub below or above the bound → suffix present or absent; finding unchanged.
- Different CWD: `monkeypatch.chdir(tmp_path)`, then `evaluate_coverage(now, read_state=…)` with the default inventory path still finds both targets.

## Test Strategy

```bash
python3 -m pytest scripts/office2/felix_health_check/tests -q
python3 -m pytest -q -x
```

NFR-004: every mapping branch, every precondition branch and every inability case has a test that fails when the branch is removed. Check this by deleting each branch locally, once.

## Risks & Mitigations

- **A hand-written expected verdict drifting from the canary.** Agreement tests compute the canary side live, never hard-code it.
- **Timestamp-boundary flakiness.** Inject `now`; never call `datetime.now()` in tests.

## Review Guidance

- Grep `coverage.py` for numeric literals: none should be health bounds.
- Confirm that the effects passed to `health.evaluate` other than `read_state` raise.
- Confirm `evaluate_coverage` returns exactly two findings in every test, including the inability cases.

## Progress & Status

`spec-kitty agent tasks add-history WP02 --note "…"` · implement: `spec-kitty agent action implement WP02 --agent claude --mission canary-deadman-backup-coverage-01M4XVY3`
