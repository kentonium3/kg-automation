---
work_package_id: WP03
title: Probe evaluators + health computation (probes.py + health.py)
dependencies:
- WP01
- WP02
requirement_refs:
- FR-002
- FR-003
- FR-009
tracker_refs:
- kentonium3/kg-automation#327
planning_base_branch: feat/felix-canary-registry
merge_target_branch: feat/felix-canary-registry
branch_strategy: Planning artifacts for this mission were generated on feat/felix-canary-registry. During /spec-kitty.implement this WP may branch from a dependency-specific base, but completed changes must merge back into feat/felix-canary-registry unless the human explicitly redirects the landing branch.
subtasks:
- T010
- T011
- T012
- T013
- T014
- T015
history:
- at: '2026-07-11T15:30:13Z'
  actor: spec-kitty agent mission tasks
  event: WP created from /spec-kitty.tasks
agent_profile: python-pedro
role: implementer
execution_mode: code_change
authoritative_surface: scripts/canary/
owned_files:
- scripts/canary/probes.py
- scripts/canary/health.py
- tests/canary/test_probes.py
- tests/canary/test_health.py
create_intent:
- scripts/canary/probes.py
- scripts/canary/health.py
- tests/canary/test_probes.py
- tests/canary/test_health.py
tags: []
---

## ⚡ Do This First: Load Agent Profile

Before reading anything else, load your assigned profile via `/ad-hoc-profile-load python-pedro`
(or your harness's profile loader). It carries your identity, governance scope, and boundaries.

## Objective

Implement the two evaluation modules:
- `scripts/canary/probes.py` — a **method→probe dispatch** over the REAL inventory vocabulary (F1),
  each probe returning a `ProbeResult`.
- `scripts/canary/health.py` — `evaluate(target, now, *, injected effects) -> HealthResult`, which
  **gates before probing** (F6) and maps the `ProbeResult` to an ADR-0006 health outcome.

Both are **pure with respect to injected effects**: network (`http_get`), subprocess (`run_cmd`), and
filesystem (`read_state`) are passed in as callables so unit tests run fully offline and deterministically.
No LLM anywhere (FR-009 / INV-E).

Read first: `../contracts/canary-contracts.md` §2 (dispatch table) + §3 (evaluation contract),
`../data-model.md` (ProbeResult, HealthResult, state-set diagram), `../research.md` R3/R4/R6, `../plan.md`
IC-03.

## Context

- `CanaryTarget` comes from WP02 (`scripts.canary.registry`). Import it.
- **Real method vocabulary** (dispatch these; anything else was already classified as a gap by WP02, so
  `evaluate` should never see it — but defend anyway → `unknown`):

  | method(s) | probe | healthy iff | stale iff | failed iff | unknown iff |
  |-----------|-------|-------------|-----------|-----------|-------------|
  | `http` | GET `endpoint` | status == `expected` (int) within `timeout_seconds` | — | status ≠ expected | connection inconclusive |
  | `shell` | run `endpoint` | exit 0 | — | non-zero exit | spawn error |
  | `systemd-status` | run `endpoint` | active/running | — | inactive/failed | systemctl error |
  | `tick-signal-file`/`signal-file`/`state-file` | read pointer JSON | good fields AND ts within `max_age_seconds` | ts older than `max_age_seconds` | explicit error field in pointer | unreadable/malformed |
  | `log-tail`/`journal` | run `endpoint` (tail/journalctl[+grep]) | marker present in window | marker older than `max_age_seconds` (if set) | command error w/ output | inconclusive |
  | `self-check-command`/`self-test` | run `endpoint` | exit 0 | — | non-zero | spawn error |

- **Fail-safe**: a probe that raises must be caught and turned into `ProbeResult(evaluable=False)` /
  `HealthResult(outcome="unknown")` — `evaluate()` **never raises** for a component-level failure (INV-D).
  WP04 collects these into `errors[]` and keeps ticking.

## ⚠️ Design callout — heterogeneous freshness timestamp field (resolve in T012)

The freshness-pointer probe reads a JSON pointer and must compare its authoritative timestamp against
`max_age_seconds`. **The timestamp field name differs per component** and there is NO schema field naming it
(`max_age_seconds` is the only inventory schema addition allowed — see data-model.md). Observed today:
- restic `last-backup.json` → `snapshot_timestamp_utc` (plus `restic_exit_code` in {0,3} as the "good" field)
- the canary runner's own `last-tick.json` (WP04) → `completed_at_utc`
- `felix-trust-scan` `seen-findings.json` → a **map** of fingerprints with no single top-level timestamp
- agent-prompt-sync → a JSONL audit log with a `tick_summary` record (not a flat pointer at all)

**Required approach**: implement the freshness probe to resolve the timestamp by trying an ordered list of
**candidate top-level keys** (module constant, e.g. `TIMESTAMP_KEYS = ("completed_at_utc",
"snapshot_timestamp_utc", "timestamp", "last_tick_utc", "script_finished_at_utc", "at", "ts")`), taking the
first present ISO-8601 value. Also honor an explicit error signal when present (e.g. a non-zero
`restic_exit_code` not in {0,3}, or an `errors`/`error` field → `failed`). If the pointer is a shape the
probe cannot interpret (a bare map like seen-findings, or a JSONL file), return
`ProbeResult(evaluable=False)` → `unknown` with evidence naming why (this surfaces as a persistent-unknown
WARN in WP04, which is the correct honest behavior — better than a false "healthy"). **Do NOT special-case
individual component names in the probe** — key-list resolution + explicit-error detection only. Record the
candidate-key list + the "unhandled pointer shape → unknown" rule in a module docstring; note in your review
handoff that agent-prompt-sync (JSONL) and trust-scan (map) will read as persistent-unknown until a future
pass extends the probe — that is expected and honest (INV-002), not a bug to hack around.

## Subtasks

### T010 — `ProbeResult` + dispatch
- `@dataclass(frozen=True)` `ProbeResult(ok: bool, stale: bool, evaluable: bool, evidence: str)`.
- `run_probe(health_check, now, *, http_get, run_cmd, read_state) -> ProbeResult` dispatching on
  `health_check["method"]` via a method→handler map. Unhandled/`none` method (defensive) → `evaluable=False`.
- Each handler wrapped so an exception → `ProbeResult(ok=False, stale=False, evaluable=False,
  evidence=f"{type(e).__name__}: {e}")`.

### T011 — Liveness probes: `http` / `shell` / `systemd-status` / `command`
- `http`: `http_get(endpoint, timeout=timeout_seconds)` returns a status int; healthy iff `== expected`.
  Treat a connection/timeout error (injected as an exception or sentinel) as `evaluable=False`.
- `shell` / `self-check-command` / `self-test`: `run_cmd(endpoint, timeout=...)` returns `(exit_code,
  stdout, stderr)`; healthy iff exit 0; non-zero → `ok=False`; spawn error → `evaluable=False`.
- `systemd-status`: run `endpoint` (a `systemctl [--user] status …`); active/running → healthy; else failed;
  systemctl error → unknown. Parse from exit code / output per the injected `run_cmd` contract.

### T012 — Freshness-pointer probe (`tick-signal-file`/`signal-file`/`state-file`)
- Resolve the pointer via WP02's `pointer_path` (already on the target — the probe receives it). Use
  `read_state(path) -> dict` (injected). Apply the **design-callout** algorithm above: candidate-key
  timestamp resolution, explicit-error detection, and unhandled-shape → `evaluable=False`.
- `stale = (now - ts) > timedelta(seconds=max_age_seconds)` when `max_age_seconds` is present; if it is
  absent, freshness cannot be judged → treat as liveness-only (`ok` from the good-fields check, `stale=False`)
  and rely on WP01's validator warning to have surfaced the omission.

### T013 — Log-scan probe (`log-tail` / `journal`)
- `run_cmd(endpoint, timeout=...)` (the endpoint is a `tail`/`journalctl [| grep]` command). Marker present
  in output → healthy; if `max_age_seconds` is declared and the most-recent matching line is older → stale;
  command error with output → failed; inconclusive → unknown. Keep it deterministic via injected `run_cmd`.

### T014 — `health.py` `evaluate()` — gate-before-probe + mapping
- `evaluate(target, now, *, http_get, run_cmd, read_state) -> HealthResult`.
- **Gate first (F6/INV-A)**: `if not target.alert_eligible: return HealthResult(outcome="suppressed",
  should_emit=False, severity=None, ...)` — **no probe call**.
- Else call `run_probe`, then map:
  - `not evaluable` → `unknown` (severity WARN — but `should_emit` for unknown/gap is decided by the
    dedup/persistence layer in WP04; here set `severity=Severity.WARN` and let WP04 apply persistence).
  - `evaluable and ok and not stale` → `healthy` (severity None).
  - `evaluable and ok and stale` → `stale` (severity ERROR).
  - `evaluable and not ok` → `failed` (severity ERROR).
  - (degraded is a self-reported partial; only produce it if a probe explicitly signals it — otherwise it is
    not reachable this mission. Leave the enum value + WARN mapping in place for WP04.)
- `HealthResult` fields per data-model.md: `component_id, outcome, alert_eligible, should_emit, severity,
  evidence, evaluated_at` (ISO-8601 UTC from `now`). Import `Severity` from `scripts.common.alert_bus`.
- Set `should_emit` for the deterministic-now cases (`stale`/`failed`/`degraded` → True; `healthy`/
  `suppressed` → False). Leave `unknown` `should_emit=False` **here** — WP04's dedup layer flips it to True
  once the unknown persists past the window (F5). Document this split in the docstring.
- `evaluate` **never raises** for a component fault (INV-D); wrap the probe call.

### T015 — Unit tests (offline, injected effects)
- `tests/canary/test_probes.py` + `tests/canary/test_health.py`.
- Probes: each method's healthy/failed/unknown paths via injected `http_get`/`run_cmd`/`read_state`;
  freshness stale vs fresh across the `max_age_seconds` boundary with an injected `now`; candidate-key
  resolution (a pointer using `snapshot_timestamp_utc`, one using `completed_at_utc`); an unhandled pointer
  shape (bare map) → `evaluable=False`; explicit-error field → failed.
- Health: **suppressed target returns without calling any injected effect** (assert the injected callables
  were not invoked — this proves gate-before-probe); each outcome maps to the right severity; a probe that
  raises → `unknown`, no exception escapes `evaluate`.

## Branch Strategy

Planning base and merge target are both `feat/felix-canary-registry`. `/spec-kitty.implement` allocates this
WP's execution worktree per the computed lane in `lanes.json`; commit there. Completed work merges back to
`feat/felix-canary-registry`.

## Definition of Done

- [ ] All six method groups dispatch to a probe; unhandled/`none` (defensive) → `evaluable=False`.
- [ ] Freshness probe resolves the timestamp via the candidate-key list + honors explicit-error fields;
      an uninterpretable pointer shape → `unknown` (not a false healthy).
- [ ] `evaluate()` returns `suppressed` **without probing** for non-alert-eligible targets (tests assert no
      injected effect was called).
- [ ] Every outcome maps to the correct `Severity` (ERROR failed/stale, WARN degraded/unknown, None
      healthy/suppressed); `unknown.should_emit` left False here (WP04 persistence flips it).
- [ ] `evaluate()` never raises for a component-level fault (INV-D).
- [ ] `pytest tests/canary/test_probes.py tests/canary/test_health.py` green; all effects injected, no
      network/subprocess/real files.

## Reviewer guidance

Verify: gate-before-probe is real (suppressed path calls **no** probe — check the tests assert the injected
callables were untouched); the freshness probe does **not** special-case component names (key-list + explicit
error only); an uninterpretable pointer becomes `unknown`, never `healthy`; `stale` maps to **ERROR** (not
WARN — a live scheduled job that didn't run is a real incident, R6); no `datetime.now()` inside the modules
(`now` is injected); no LLM, no un-injected I/O.

## Activity Log
