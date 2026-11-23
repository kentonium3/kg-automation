# Implementation Plan: Crash-loop unit alerting

**Branch**: `kitty/mission-crash-loop-unit-alerting-01M858E8` (planning) → merge target `fix/crash-loop-unit-alerting` → PR to `main` | **Date**: 2026-11-23 | **Spec**: [spec.md](spec.md)
**Input**: Mission specification from `kitty-specs/crash-loop-unit-alerting-01M858E8/spec.md` (kentonium3/kg-automation#1133)

## Planning basis (how the planning questions were answered)

The five discovery Decision Moments in the spec (watched set, threshold, owning monitor, latency, lifecycle) settle every product-level question. The spec delegates exactly one value to this plan: **K**, the number of quiet ticks before a "cleared" entry. Every other open point is an implementation fork.

Kent's standing instruction for this mission (2026-11-23) is to continue through plan, tasks and implementation and stop only for required stops. The autonomous-run protocol (`.agents/autonomous-run-guard/docs/runbooks/autonomous-run-protocol.md`, §1b and D-1) says: at an ordinary implementation fork, take the durable and safe option and log the decision with its rationale. Do not halt on a question. So the planning interrogation was answered from the spec, the resolved Decision Moments, the existing canary code and live read-only probes of office2. Each fork is logged in [research.md](research.md) (R-01 to R-15). No planning Decision Moment was opened, because no question needs Kent's judgment. The judgment calls that Kent may still want to revisit are listed under "Surfaced judgment calls" at the end of this plan.

**Engineering alignment (summary).** felix-canary gains a crash-loop stage that runs once per pass, after the inventory components and coverage gaps. The stage reads the persistent restart counters of three scopes: system units, `claude` user units, and docker containers. It compares each counter with its stored history and runs a per-unit episode state machine with these rules: alert only on a **proven** crossing. Over an interval spanning `m` windows, a rise of at least `m·(N−1)+1` proves at least N restarts within one 15-minute window. It re-reminds on the canary's 6-hour cadence and clears after K = 2 quiet ticks. Clearing rebases the history, so a later episode needs fresh restarts. It emits through the existing alert bus. A scope that cannot be read is routed as an `unknown` canary component, so it is visible and never reads as healthy. Any fault in the stage is caught and recorded in the pass's `errors[]`. Every other component is still evaluated.

## Summary

Add restart-loop detection to felix-canary. Today a `Restart=always` unit that loops never reaches `failed`, and the canary's "is it active" probes miss it. The new stage uses the persistent restart counters: systemd `NRestarts` and docker `RestartCount`. These survive the loop, so a loop that starts and ends between two 15-minute ticks is still caught. Detection is deterministic code with injected readers and clock. It is offline-testable and makes no model call. State lives in a new atomically written JSON file next to the canary's dedup state. Configuration (threshold, window, K, ignore list) lives in a version-controlled JSON file in the repo. The change deploys through a `deploys/queued/` manifest. Its entrypoint proves the stage is live on office2 by running the real unit once and checking the fresh state file and ledger.

## Technical Context

**Language/Version**: Python 3.12 on office2 (`/usr/bin/python3`, Ubuntu 24.04), the interpreter the `felix-canary.service` user unit runs. Repo tests run under `.venv/bin/python` (3.11+ compatible; the code uses no 3.12-only syntax).
**Primary Dependencies**: Python standard library only (`subprocess`, `json`, `dataclasses`, `datetime`, `tempfile`, `os`). It reuses `scripts.common.alert_bus` (`emit`, `Alert`, `Severity`) and `scripts.canary.dedup` (the state-file write pattern, the `DEFAULT_WINDOW` 6 h re-remind cadence, and the `unknown` routing for scopes). It adds no third-party dependency, so DIRECTIVE_051 supply-chain checks do not apply (recorded in research.md R-12).
**Storage**: New JSON state file `/data/services/felix-canary/state/crash-loop.json`. It holds per-unit generation, observation history and episode state, written atomically under a non-blocking `flock` (`crash-loop.lock`). History is compacted by dominance and kept for up to 24 h / 64 entries, with no thinning (R-07). A missing or corrupt file loads as empty, and each entry is validated semantically (R-07). New repo config file `scripts/canary/crash_loop_config.json`. Crash-loop ledger lines are appended to the existing canary ledger `/data/services/felix-canary/ledger/<date>.jsonl`.
**Testing**: pytest under `.venv/bin/python -m pytest`, offline. The pre-mission full-suite baseline is 10907 passed, 51 skipped, 1 xfailed (`.venv/bin/python -m pytest -q -p no:cacheprovider`, 2026-11-23, 517 s). Restart readers are injected callables, and `now` is injected. Fixtures are taken verbatim from real office2 `systemctl show`, `systemctl list-units` and `docker inspect --format` output captured on 2026-11-23 (research.md R-03). The existing `tests/canary/` suite is the FR-013/SC-005 ratchet. Its assertions stay unchanged. Three test fakes of `run_pass` gain `**_ignored` in their signatures only (R-09). Paired stage-disabled and stage-enabled runs prove every existing component's outcome is identical.
**Target Platform**: office2 (Ubuntu 24.04, systemd 255, Docker), `claude` account, systemd user unit `felix-canary.service` on its existing 15-minute timer.
**Project Type**: single (existing `scripts/` + `tests/` layout).
**Performance Goals**: The stage adds at most 10 s per pass for up to 50 watched units (NFR-002). Measured on office2: about 0.34 s for `systemctl show` over 192 system services, and about 0.04 s for `docker inspect` over 3 containers.
**Constraints**: No sudo, no journal read, no credential-file read (NFR-003). Docker commands run with `DOCKER_CONFIG` pointed at an empty temporary directory, so no registry credentials are loaded, and with `DOCKER_HOST` pinned to the local socket. The `--format` template means our process receives only five fields. The docker CLI itself still retrieves the full inspect object from the local daemon (research R-02, correcting the first draft). Commands run as argv lists, never with `shell=True`, inside one 6-second read deadline (R-15). Crash-loop pages are capped at 3 individual notifications per tick plus one bounded aggregate, so at most 4 alert-bus calls. The stage detects only and never restarts or reconfigures anything (C-005).
**Scale/Scope**: On 2026-11-23 office2 had 24 system services with `Restart` other than `no` (11 `always`, 12 `on-failure`, 1 `on-abort`), 1 `claude` user service (`openclaw-gateway`, `always`), and 2 containers with a restart policy (`vikunja`, `transcribe-api`, both `unless-stopped`). That is 27 watched units.

## Charter Check

*GATE: Must pass before Phase 0 research. Re-checked after Phase 1 design: still PASS.*

| Charter rule | Status | How this plan meets it |
|---|---|---|
| Testing Standards: pytest for non-trivial helpers | PASS | The pure decision module and the readers each get unit tests. run_pass gets integration tests, and FR-013 gets a fault-injection control. |
| Fixtures mirror real inputs | PASS | Fixtures are copied from real office2 output (research.md R-03). |
| No dead code | PASS | The stage is wired into `run_pass` and `main()`. A test asserts that `main()` wires the real check (research.md R-09). |
| Integration verification (no staging) | PASS | A pre-merge live exercise would need the new code on office2, and nothing reaches office2 before merge. The defined live verification is therefore the deploy entrypoint's post-merge check. It runs the real unit once and asserts a fresh crash-loop state file, a ledger line and no `crash_loop` errors. It is recorded as the mission's post-merge acceptance. |
| Deployment: manifest discipline (C-004) | PASS | `deploys/queued/<NNNN>-crash-loop-unit-alerting.yaml` plus `scripts/deploy/deploy-crash-loop-unit-alerting.py`. Authored in the branch and **not merged without Kent**. The entrypoint requires all three scopes to read `healthy` (R-11). |
| Change-risk tier | Tier 3 | Python logic plus a JSON config read by the canary. No unit-file content changes, and no Tier 0, 1 or 2 action. |
| Rebaseline obligation | Recorded | The planned Python and config files match no hashed audited-surface pattern. The manifest (`deploys/queued/*.yaml`) matches the `deploy-pipeline` surface (`rebaseline_required: true`, `affected_baselines: []`), and felix-deployer opens a pending observation for it. So the manifest declares `audited_surface: true` and expects a clean reconciliation. Merge record: `Rebaseline: automated — felix-deployer (deferred-confirm) on the post-merge deploy` (R-11, corrected after review). `tooling/scripts/check_audited_surface_drift.py` output is recorded before merge. |
| Documentation sync (Directives 3–5, C-007) | PASS | service-inventory.json and .md, data-flows.json and .md (new state file), service-dependencies.view.md, felix-capability-roadmap.md (review), canary-registry-ops.md (including the 7-day acceptance procedure, R-14), observability-and-alerting.md, and docs/INDEX.md (reviewed and updated for the runbook change, unconditionally). |
| Probe the real environment (Directive 6) | PASS | Live read-only probes on 2026-11-23 (research.md R-03). |
| Privacy/security boundaries | PASS | No credential reads. The docker `--format` template excludes `Config.Env`. No journal reads and no sudo. |
| Deterministic vs stochastic (Constitution Directive 6) | PASS | Fully deterministic, with no LLM call (NFR-006). |

## Project Structure

### Documentation (this mission)

```
kitty-specs/crash-loop-unit-alerting-01M858E8/
├── spec.md
├── plan.md              # this file
├── research.md          # decisions R-01..R-15, live probe evidence, §0 upstream sweep
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
├── crash_loop_model.py        # NEW: value types + strict config loader
├── crash_loop_state.py        # NEW: fail-safe state load/validate, atomic save, non-blocking flock
├── crash_loop.py              # NEW: pure decision (proof → episode → events), emission plan, rendering
├── crash_loop_readers.py      # NEW: systemd system / systemd --user / docker restart-count readers + parsers
├── crash_loop_config.json     # NEW: threshold, window, K, ignore list (version-controlled)
└── run.py                     # MODIFIED: crash-loop stage in run_pass (opt-in param), wired in main()

tests/canary/
├── test_run.py, test_run_deadman.py  # MODIFIED: run_pass fakes accept **_ignored (signature only)
├── fixtures/crash_loop/       # NEW: real office2 output samples
├── test_crash_loop_model.py   # NEW: config + types
├── test_crash_loop_state.py   # NEW: persistence, validation, lock
├── test_crash_loop.py         # NEW: decision/state-machine tests (US1–US3, edge cases, property test)
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
docs/INDEX.md                                          # runbook-modified: review + update the canary-registry-ops entry
```

**Structure Decision**: Single project. The detection lives inside the existing `scripts/canary/` package (C-001: owner is felix-canary). It is split into a pure decision module and an effects module, mirroring the existing `health.py`/`probes.py` split.

## Complexity Tracking

No charter violations.

## Implementation Concern Map

### IC-01 — Crash-loop decision core

- **Purpose**: Turn per-unit restart-count observations into crash-loop alert, re-remind and cleared events with the episode lifecycle, deterministically.
- **Relevant requirements**: FR-002, FR-003, FR-004, FR-005, FR-007, FR-008, FR-009, FR-010, NFR-001, NFR-004, NFR-006; SC-001, SC-002.
- **Affected surfaces**: `scripts/canary/crash_loop_model.py`, `crash_loop_state.py`, `crash_loop.py`, `crash_loop_config.json` and their tests.
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

## Surfaced judgment calls (logged, not blocking; for Kent)

These were decided under D-1/§5. The first two are the operational meaning of Kent's own decisions under 15-minute sampling, and he may want to confirm them:

1. **Only proven crossings page (R-05).** Counters sampled every 15 to 16 minutes cannot show *when* inside an interval the restarts happened. The plan pages only when the rise **proves** ≥ N restarts within some 15-minute window (pigeonhole: `Δ ≥ m·(N−1)+1` over `m` windows). Between ordinary ticks `m = 2`, so a page needs **≥ 5 restarts per tick interval**. A slow loop of 3 or 4 restarts per tick is recorded as `crash-loop-unverified` in the canary ledger and does not page. The 2026-11-23 loop (39 in 7 minutes) is far above the bound. The alternative, paging on "Δ ≥ 3 within one tick interval (about 16 min)", catches slower loops but pages on intervals where no 15-minute window held 3. Codex round 2 judged that a change to Kent's window. **If Kent prefers sensitivity over strictness, the change is small and contained to `evaluate_tick`'s proof predicate.**
2. **A short burst straddling a tick boundary can be missed.** Example: 4 restarts in 2 minutes split 2 + 2 across ticks. This is inherent to the tick cadence Kent chose over a 5-minute or event-driven one. A sustained loop is always caught.
3. **NFR-002 during an alert storm (R-15).** A pass with no crash-loop events adds about 0.4 s of reads, under a 6 s hard cap. A pass that pages adds the alert bus's delivery time for at most 4 calls: typically under 1 s each, with a ceiling of 15 s per call in the bus itself. Making that stricter needs asynchronous delivery or a bus change, both outside this mission (C-003).
4. **A failed delivery is not retried (R-08).** This matches the existing canary: the failure is counted, and the off-host dead-man then pings `fail`.
5. **K = 2 quiet ticks (30 minutes)** before "cleared" (R-04). The spec delegates K to the plan.
6. **An unexpected fault in the crash-loop stage is recorded in `errors[]`.** The canary's own self-check then reports it (R-08). A scope that cannot be read pages on the canary's existing `unknown` cadence (R-08).
7. **At most 3 individual crash-loop notifications per tick**, plus one aggregate bounded to the bus's 1000-character description (R-15).

## Post-plan Codex review dispositions (2026-11-23)

Reviewer: Codex CLI, model `gpt-6.1-sol` (`codex exec --sandbox read-only`, prompt on stdin, personal tree `~/.codex` via `$DOTFILES/bin/codex`). The implementer is Claude Opus 5.5, so the reviewer is a different vendor. The verdict was request changes: 6 HIGH and 8 MEDIUM findings. All are accepted. None changes the spec's scope or a decision Kent made. CX-1 shows that the first draft's long-gap rule departed from NFR-004, so the fix moves the plan back to the spec.

| ID | Sev | Finding (short) | Disposition |
|---|---|---|---|
| CX-1 | HIGH | The baseline rule invents crossings across long gaps and misses dense ones. Sampling cannot prove every rolling window. | The interval rule is rewritten: the baseline is the oldest observation within `horizon = window + slack`. A long gap produces `crash-loop-unverified` with no page. The sampling limit is stated and surfaced (R-05; judgment calls 2 and 3). |
| CX-2 | HIGH | Clearing can replay the same burst as a new episode. | Clearing rebases the history, so a new episode needs N fresh restarts (R-06, INV-CL-5). Codex's sequence becomes a test. |
| CX-3 | HIGH | Docker `--format` does not stop retrieval, and CLI config may hold registry credentials. | The claim is corrected. `DOCKER_CONFIG` is an empty temporary directory and `DOCKER_HOST` is pinned. Our process still receives only the formatted fields (R-02). |
| CX-4 | HIGH | Per-command timeouts exceed the 10 s budget, and alert bursts are unbounded. | One 8 s read deadline, plus a per-tick emission cap of 5 with an aggregate alert (R-15). |
| CX-5 | HIGH | A malformed or partial read can erase coverage and episode state. | Policy exclusion is separated from observation failure. Requested identities are reconciled with what came back. An incomplete scope becomes `unknown` and keeps its state. No argument-free `show` or `inspect` (R-13). |
| CX-6 | HIGH | Crash-loop emission skipped `alerts_undelivered`. | Delivery is accounted for on every emission. An undelivered alert or re-remind stays `alert_pending` and is re-sent. The ledger gains `delivered` (R-08). |
| CX-7 | MED | Counter lifecycle assumptions included a wrong one: daemon-reexec does not reset `NRestarts`. | A lifecycle matrix is added and corrected. Every reset path under-counts and never over-counts (R-06). |
| CX-8 | MED | Name-only identity misses container re-creation and reboots. | A generation is added: the boot ID for units, the container ID for containers. A generation change is a reset, preserving Kent's reboot-is-baseline rule (R-06). |
| CX-9 | MED | No concurrency or emit/save ordering. | A non-blocking `flock`. Emit-then-save, which fails loud (R-07). |
| CX-10 | MED | Backward time and dense histories. | Future entries are clamped. A tick whose `now` is not after the last observation is skipped for that unit. History is capped at 64 and thinned in the middle, keeping the baseline (R-07, INV-CL-9). |
| CX-11 | MED | Deploy verification did not prove all three scopes. | All three scopes must read `healthy`. The unit is started a second time if the first start joined a running pass. A delivered-event check is added (R-11). |
| CX-12 | MED | The "unchanged" test claim was incompatible with the wiring. | Signature-only adaptation of the fakes. Paired disabled and enabled runs. Key-ledger reconciliation with the stage enabled. A dry-run no-write test (R-09). |
| CX-13 | MED | The rebaseline conclusion contradicted `audited-surfaces.json` and `rebaseline.py`. | `audited_surface: true`, expecting a clean deferred-confirm reconciliation (R-11). |
| CX-14 | MED | 7-day criteria were not covered, and INDEX.md was conditional. | A retained-evidence fields list and a dated 7-day procedure (R-14). INDEX.md is updated unconditionally. |

### Round 2 (same reviewer and model, 2026-11-23)

Codex re-checked the revision. Its verdict was still request changes. Round 1 status: CX-2, CX-3, CX-5, CX-7, CX-9, CX-11, CX-12 and CX-13 RESOLVED; CX-1, CX-4, CX-6, CX-8, CX-10 and CX-14 PARTIAL. It also raised new defects, all from machinery that round 1's fixes had added. Following the standing lesson to stop edge-case loops and simplify, the design was **simplified** rather than patched again:

| ID | Sev | Finding (short) | Disposition |
|---|---|---|---|
| R2-C1 | HIGH | The 17-minute `window + slack` rule changes Kent's 15-minute window. | **Replaced** with the proven-crossing rule (pigeonhole): no slack, the literal window, and long gaps under the same rule (R-05). The sensitivity consequence is surfaced as judgment call 1. |
| R2-B1/B2, C2 | HIGH | Pending-retry semantics had no evidence payload, conflicted with clearing, and resent on reset ticks (an FR-009 conflict). | **Removed retry**. This matches the existing canary: there is no `alert_pending`, and the failure is counted for the dead-man (R-08, INV-CL-10). |
| R2-B3 | HIGH | The aggregate could exceed the bus's truncation limits and omitted state. | The aggregate lists `key kind +Δ/period state` entries within 900 characters, then "and k more - see canary ledger". Every event has its own ledger line (R-15). |
| R2-B4 | HIGH | Delivery time is outside NFR-002 and NFR-001. | The cap is cut to 3 + 1 and reads to 6 s. The remaining bus-delivery dependency is surfaced as judgment call 3, because it cannot be fixed within C-003. |
| R2-B5 | MED | Middle-thinning can destroy a future baseline. | **Removed thinning**. Entries are at least 60 s apart, retention is 4 × window, and `last_seen` is tracked separately (R-07). |
| R2-B6 | MED | Two clock rules, and empty-history ambiguity. | **One rule**: a time later than `now + 60 s` on load means a malformed entry, and the unit is first-seen. `now ≤ last_seen_at` skips the unit, and this check runs first (R-07, INV-CL-9). |
| R2-B7 | MED | A reboot did not rebase containers. | A boot-ID change rebases every unit, containers included (R-06, INV-CL-2). |
| R2-CX14 | MED | The 7-day selector missed the aggregate kind. | The selector includes `aggregate`, and each check uses the proof bound (R-14). |

### Round 3 (same reviewer and model, 2026-11-23)

Codex confirmed the pigeonhole bound is correct for half-open intervals, including exact multiples of the window: "Checking additional valid baselines cannot create a false proof." The tightest-proof selection reports valid evidence. Clear-then-unchanged does not replay, and first sight emits nothing. "No additional HIGH defect found" beyond these three:

| ID | Sev | Finding (short) | Disposition |
|---|---|---|---|
| R3-H1 | HIGH | A reboot rebase is lost when the unit's scope is unreadable on the first post-reboot tick. | Each unit stores its own `boot_id`. A mismatch at any later complete read rebases it (R-06, INV-CL-2). |
| R3-M1 | MED | A reset inside an episode could emit `cleared`, contradicting "a reset emits nothing", and the boot path was implicit. | Settled explicitly: a boot change closes the episode silently. A decrease or container-ID change counts as quiet and may emit the INFO `cleared`, but never an alert or re-remind (R-06, INV-CL-2). |
| R3-M2 | MED | 60 s spacing and 4 × window retention can discard a uniquely proving baseline. | **Dominance compaction**: an observation at the same count replaces the newest entry (it dominates), and a higher count is appended. Retention is 24 h / 64 entries, and the residual bound on completeness is stated (R-07). |

### Round 4 (same reviewer and model, 2026-11-23)

R3-H1, R3-M1 and R3-M2 are confirmed resolved. Dominance compaction "preserves proofs … Neither creates false alerts", and no HIGH was introduced. One MEDIUM remained:

| ID | Sev | Finding | Disposition |
|---|---|---|---|
| R4-M1 | MED | The 64-entry cap can drop a single-window proof under an extreme valid config (N = 100, 65 observations in 65 s). | Entries within the last window are never pruned, so m = 1 proofs are always found. The 24 h / 64 bounds apply only to older entries. The config is bounded to `threshold ≤ 50` and `window ≤ 3600` (R-07, R-10). This fix was applied without a fifth round, because it is narrow and deterministic and the WP02 test encodes Codex's exact sequence. Per-WP review re-checks it. |

**Checkpoint outcome:** the post-plan Codex review ran 4 rounds (gpt-6.1-sol). Every finding is folded in. None changes the spec's scope or a Kent decision. Two sampling consequences of his decisions are surfaced for confirmation (judgment calls 1 and 2).
