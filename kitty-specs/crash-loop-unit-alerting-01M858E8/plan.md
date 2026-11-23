# Implementation Plan: Crash-loop unit alerting

**Branch**: `kitty/mission-crash-loop-unit-alerting-01M858E8` (planning) → merge target `fix/crash-loop-unit-alerting` → PR to `main` | **Date**: 2026-11-23 | **Spec**: [spec.md](spec.md)
**Input**: Mission specification from `kitty-specs/crash-loop-unit-alerting-01M858E8/spec.md` (kentonium3/kg-automation#1133)

## Planning basis (how the planning questions were answered)

The five discovery Decision Moments in the spec (watched set, threshold, owning monitor, latency, lifecycle) settle every product-level question. The spec delegates exactly one value to this plan: **K**, the number of quiet ticks before a "cleared" entry. Every other open point is an implementation fork.

Kent's standing instruction for this mission (2026-11-23) is to continue through plan, tasks and implementation and stop only for required stops. The autonomous-run protocol (`.agents/autonomous-run-guard/docs/runbooks/autonomous-run-protocol.md`, §1b and D-1) says: at an ordinary implementation fork, take the durable and safe option and log the decision with its rationale. Do not halt on a question. So the planning interrogation was answered from the spec, the resolved Decision Moments, the existing canary code and live read-only probes of office2. Each fork is logged in [research.md](research.md) (R-01 to R-13). No planning Decision Moment was opened, because no question needs Kent's judgment. The judgment calls that Kent may still want to revisit are listed under "Surfaced judgment calls" at the end of this plan.

**Engineering alignment (summary).** felix-canary gains a crash-loop stage that runs once per pass, after the inventory components and coverage gaps. The stage reads the persistent restart counters of three scopes: system units, `claude` user units, and docker containers. It compares each counter with its stored history and runs a per-unit episode state machine with these rules: alert on the first over-threshold tick, re-remind on the canary's 6-hour cadence, and clear after K = 2 quiet ticks. It emits through the existing alert bus. A scope that cannot be read is routed as an `unknown` canary component, so it is visible and never reads as healthy. Any fault in the stage is caught and recorded in the pass's `errors[]`. Every other component is still evaluated.

## Summary

Add restart-loop detection to felix-canary. Today a `Restart=always` unit that loops never reaches `failed`, and the canary's "is it active" probes miss it. The new stage uses the persistent restart counters: systemd `NRestarts` and docker `RestartCount`. These survive the loop, so a loop that starts and ends between two 15-minute ticks is still caught. Detection is deterministic code with injected readers and clock. It is offline-testable and makes no model call. State lives in a new atomically written JSON file next to the canary's dedup state. Configuration (threshold, window, K, ignore list) lives in a version-controlled JSON file in the repo. The change deploys through a `deploys/queued/` manifest. Its entrypoint proves the stage is live on office2 by running the real unit once and checking the fresh state file and ledger.

## Technical Context

**Language/Version**: Python 3.12 on office2 (`/usr/bin/python3`, Ubuntu 24.04), the interpreter the `felix-canary.service` user unit runs. Repo tests run under `.venv/bin/python` (3.11+ compatible; the code uses no 3.12-only syntax).
**Primary Dependencies**: Python standard library only (`subprocess`, `json`, `dataclasses`, `datetime`, `tempfile`, `os`). It reuses `scripts.common.alert_bus` (`emit`, `Alert`, `Severity`) and `scripts.canary.dedup` (the state-file write pattern, the `DEFAULT_WINDOW` 6 h re-remind cadence, and the `unknown` routing for scopes). It adds no third-party dependency, so DIRECTIVE_051 supply-chain checks do not apply (recorded in research.md R-12).
**Storage**: New JSON state file `/data/services/felix-canary/state/crash-loop.json`. It holds per-unit observation history and episode state, written atomically with a temp file and `os.replace`. A missing or corrupt file loads as empty. New repo config file `scripts/canary/crash_loop_config.json`. Crash-loop ledger lines are appended to the existing canary ledger `/data/services/felix-canary/ledger/<date>.jsonl`.
**Testing**: pytest under `.venv/bin/python -m pytest`, offline. Restart readers are injected callables, and `now` is injected. Fixtures are taken verbatim from real office2 `systemctl show`, `systemctl list-units` and `docker inspect --format` output captured on 2026-11-23 (research.md R-03). The existing `tests/canary/` suite is the FR-013/SC-005 ratchet and must pass unmodified.
**Target Platform**: office2 (Ubuntu 24.04, systemd 255, Docker), `claude` account, systemd user unit `felix-canary.service` on its existing 15-minute timer.
**Project Type**: single (existing `scripts/` + `tests/` layout).
**Performance Goals**: The stage adds at most 10 s per pass for up to 50 watched units (NFR-002). Measured on office2: about 0.34 s for `systemctl show` over 192 system services, and about 0.04 s for `docker inspect` over 3 containers.
**Constraints**: No sudo, no journal read, no credential-file read (NFR-003). `docker inspect` is called with a `--format` template that selects four fields only, so container environment variables (which may hold secrets) are never read. Commands run as argv lists, never with `shell=True`. Each subprocess has a timeout. The stage detects only and never restarts or reconfigures anything (C-005).
**Scale/Scope**: On 2026-11-23 office2 had 24 system services with `Restart` other than `no` (11 `always`, 12 `on-failure`, 1 `on-abort`), 1 `claude` user service (`openclaw-gateway`, `always`), and 2 containers with a restart policy (`vikunja`, `transcribe-api`, both `unless-stopped`). That is 27 watched units.

## Charter Check

*GATE: Must pass before Phase 0 research. Re-checked after Phase 1 design: still PASS.*

| Charter rule | Status | How this plan meets it |
|---|---|---|
| Testing Standards: pytest for non-trivial helpers | PASS | The pure decision module and the readers each get unit tests. run_pass gets integration tests, and FR-013 gets a fault-injection control. |
| Fixtures mirror real inputs | PASS | Fixtures are copied from real office2 output (research.md R-03). |
| No dead code | PASS | The stage is wired into `run_pass` and `main()`. A test asserts that `main()` wires the real check (research.md R-09). |
| Integration verification (no staging) | PASS | A pre-merge live exercise would need the new code on office2, and nothing reaches office2 before merge. The defined live verification is therefore the deploy entrypoint's post-merge check. It runs the real unit once and asserts a fresh crash-loop state file, a ledger line and no `crash_loop` errors. It is recorded as the mission's post-merge acceptance. |
| Deployment: manifest discipline (C-004) | PASS | `deploys/queued/<NNNN>-crash-loop-unit-alerting.yaml` plus `scripts/deploy/deploy-crash-loop-unit-alerting.py`. Authored in the branch and **not merged without Kent**. |
| Change-risk tier | Tier 3 | Python logic plus a JSON config read by the canary. No unit-file content changes, and no Tier 0, 1 or 2 action. |
| Rebaseline obligation | Recorded | No audited-surface file changes. `scripts/canary/*.py`, `*.json` and the deploy entrypoint `scripts/deploy/*.py` match no pattern in `audited-surfaces.json`. The manifest under `deploys/queued/*.yaml` matches the `deploy-pipeline` surface, whose `affected_baselines` is empty. Merge record: `Rebaseline: not required — only audited surface touched is deploy-pipeline (deploys/queued manifest), which has no affected_baselines; no unit content changes`. To be confirmed with `tooling/scripts/check_audited_surface_drift.py` before merge (research.md R-11). |
| Documentation sync (Directives 3–5, C-007) | PASS | service-inventory.json and .md, data-flows.json and .md (new state file), service-dependencies.view.md, felix-capability-roadmap.md (review), canary-registry-ops.md, observability-and-alerting.md, and docs/INDEX.md if the runbook's title or scope changes. |
| Probe the real environment (Directive 6) | PASS | Live read-only probes on 2026-11-23 (research.md R-03). |
| Privacy/security boundaries | PASS | No credential reads. The docker `--format` template excludes `Config.Env`. No journal reads and no sudo. |
| Deterministic vs stochastic (Constitution Directive 6) | PASS | Fully deterministic, with no LLM call (NFR-006). |

## Project Structure

### Documentation (this mission)

```
kitty-specs/crash-loop-unit-alerting-01M858E8/
├── spec.md
├── plan.md              # this file
├── research.md          # decisions R-01..R-13, live probe evidence, §0 upstream sweep
├── data-model.md        # entities, state file schema, episode state machine
├── quickstart.md        # how to run/verify offline and on office2
├── contracts/
│   ├── crash-loop-config.schema.json   # repo config file contract
│   ├── crash-loop-state.schema.json    # persisted state contract
│   └── crash-loop-alert.md             # alert / cleared / scope-unknown payloads + ledger lines
├── checklists/requirements.md
└── decisions/            # specify-phase Decision Moments
```

### Source Code (repository root)

```
scripts/canary/
├── crash_loop.py              # NEW: config load, pure decision (observe → episode → events), state load/save
├── crash_loop_readers.py      # NEW: systemd system / systemd --user / docker restart-count readers + parsers
├── crash_loop_config.json     # NEW: threshold, window, K, ignore list (version-controlled)
└── run.py                     # MODIFIED: crash-loop stage in run_pass (opt-in param), wired in main()

tests/canary/
├── fixtures/crash_loop/       # NEW: real office2 output samples
├── test_crash_loop.py         # NEW: decision/state-machine tests (US1–US3, edge cases)
├── test_crash_loop_readers.py # NEW: parser + could-not-check tests (US4)
└── test_run_crash_loop.py     # NEW: run_pass integration, fault isolation, main() wiring

scripts/deploy/deploy-crash-loop-unit-alerting.py   # NEW: deploy entrypoint (--dry-run / --apply)
tests/deploy/test_deploy_crash_loop_unit_alerting.py # NEW
deploys/queued/<NNNN>-crash-loop-unit-alerting.yaml  # NEW manifest (merge gated on Kent)

docs/design/architecture/data/service-inventory.json   # felix-canary entry: purpose/state paths/config
docs/design/architecture/service-inventory.md
docs/design/architecture/service-dependencies.view.md  # felix-canary → systemd / docker read edges
docs/design/architecture/observability-and-alerting.md
docs/design/architecture/data/data-flows.json + data-flows.md        # new crash-loop.json state + counter reads (data-flow-added-or-modified)
docs/design/felix-capability-roadmap.md                # review; note capability
docs/runbooks/canary-registry-ops.md                   # crash-loop section: tuning, ignore list, state reset
docs/INDEX.md                                          # only if the runbook's title/scope line changes
```

**Structure Decision**: Single project. The detection lives inside the existing `scripts/canary/` package (C-001: owner is felix-canary). It is split into a pure decision module and an effects module, mirroring the existing `health.py`/`probes.py` split.

## Complexity Tracking

No charter violations.

## Implementation Concern Map

### IC-01 — Crash-loop decision core

- **Purpose**: Turn per-unit restart-count observations into crash-loop alert, re-remind and cleared events with the episode lifecycle, deterministically.
- **Relevant requirements**: FR-002, FR-003, FR-004, FR-005, FR-007, FR-008, FR-009, FR-010, NFR-001, NFR-004, NFR-006; SC-001, SC-002.
- **Affected surfaces**: `scripts/canary/crash_loop.py`, `scripts/canary/crash_loop_config.json`, `tests/canary/test_crash_loop.py`.
- **Sequencing/depends-on**: none.
- **Risks**: Window-baseline selection with tick jitter (R-05). Counter resets within an episode (R-06). State migration and corruption (R-07).

### IC-02 — Restart-count readers

- **Purpose**: Read `(scope, name, restart_policy, restart_count, state)` for system units, `claude` user units and docker containers without privilege. Report a scope that cannot be read as could-not-check.
- **Relevant requirements**: FR-001, FR-011, FR-012, NFR-002, NFR-003, C-002, C-008; SC-004.
- **Affected surfaces**: `scripts/canary/crash_loop_readers.py`, `tests/canary/test_crash_loop_readers.py`, `tests/canary/fixtures/crash_loop/`.
- **Sequencing/depends-on**: none. It shares only the `RestartObservation` type with IC-01, which defines it. The type is fixed in data-model.md, so either can start first.
- **Risks**: `systemctl show` output ordering. Not-found units have no `NRestarts`. Docker fields must never include `Config.Env`. Subprocess timeouts must stay inside the NFR-002 budget.

### IC-03 — Canary integration and fault isolation

- **Purpose**: Run the crash-loop stage inside `run_pass` after the existing components. Route alerts and could-not-check through the existing emit, dedup and ledger paths. Isolate faults. Wire the stage into `main()`.
- **Relevant requirements**: FR-006, FR-011, FR-013, NFR-005, C-001, C-003; SC-005.
- **Affected surfaces**: `scripts/canary/run.py`, `tests/canary/test_run_crash_loop.py`.
- **Sequencing/depends-on**: IC-01, IC-02.
- **Risks**: Changing an existing component's outcome. The tick-signal schema must stay unchanged. Existing tests must never reach real `systemctl` or `docker`, so the stage is opt-in in `run_pass` and enabled by `main()`.

### IC-04 — Deploy and living documentation

- **Purpose**: Deliver the change through the manifest pipeline with a verifying entrypoint, and update the architecture docs and runbook.
- **Relevant requirements**: FR-014, C-004, C-007; NFR-002 (measured at apply).
- **Affected surfaces**: `scripts/deploy/deploy-crash-loop-unit-alerting.py`, `tests/deploy/test_deploy_crash_loop_unit_alerting.py`, `deploys/queued/*.yaml`, and the docs listed above.
- **Sequencing/depends-on**: IC-03.
- **Risks**: Merging to `main` deploys to office2, because the canary runs from the checkout. **Merging needs Kent's approval.** The manifest number must be the next free one at merge time. The entrypoint must never wrap commands in `ssh` (it runs on office2).

## Surfaced judgment calls (logged, not blocking)

These forks were decided under D-1/§5. Kent may want to revisit them:

1. **K = 2 quiet ticks (30 minutes)** before "cleared" (R-04). The spec delegates K to the plan.
2. **A long gap between ticks still alerts.** If the canary misses ticks (it was down or the host was suspended), a rise of at least the threshold since the previous observation alerts. The evidence states the real, longer period (R-05). This favours never missing a loop over strict window accounting.
3. **An unexpected fault in the crash-loop stage is recorded in the pass's `errors[]`.** That makes the canary's own tick status `error`, so felix-canary's self-check reports it (R-08). The other path was silent logging, and it was rejected under engineering principle 14 (could-not-check must be visible).
4. **A scope that cannot be read pages on the canary's existing `unknown` cadence.** It is recorded at once and paged once it has persisted past the 6-hour window (R-08). It is not paged immediately.
