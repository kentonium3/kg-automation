# Tasks: Felix component-health canary registry

**Mission**: felix-canary-registry-01KX8T7B · **Issue**: kentonium3/kg-automation#327 (Foundation 1 / #516)
**Planning base / merge target**: `feat/felix-canary-registry`
**Source artifacts**: [spec.md](spec.md) · [plan.md](plan.md) · [research.md](research.md) ·
[data-model.md](data-model.md) · [contracts/canary-contracts.md](contracts/canary-contracts.md) ·
[quickstart.md](quickstart.md)

7 work packages translate the plan's IC-01..IC-07 concern map. Every FR-001..010 is covered.
Tests live under `tests/canary/` (repo test root) — **never** co-located under `scripts/canary/tests/`
(the #701-mission stale-co-located-test guard). office2 runs `python3` only; the module form is
`python3 -m scripts.canary.run`.

## Dependency graph

```
WP01 (schema+validator) ──┬─► WP02 (registry) ──► WP03 (probes+health) ──► WP04 (run+dedup) ──┬─► WP06 (deploy) ──► WP07 (docs)
                          └─► WP05 (inventory: restic + runner registration) ──────────────────┘
```

- WP01 → WP02, WP05
- WP02 → WP03
- WP03 → WP04
- WP04, WP05 → WP06
- WP04, WP05, WP06 → WP07

MVP scope = WP01 → WP04 (a runnable `python3 -m scripts.canary.run --dry-run` over the real inventory).
WP05/06/07 make it live on office2.

## Subtask Index (reference table — not a tracking surface)

| ID | Description | WP | Parallel |
|----|-------------|----|----------|
| T001 | Validate `max_age_seconds` is a positive int when present | WP01 | |
| T002 | Warn when an alert-eligible freshness/log-scan `health_check` omits `max_age_seconds` | WP01 | [P] |
| T003 | Validator unit tests (accept, reject non-int, warn-on-omit) | WP01 | |
| T004 | `CanaryTarget` dataclass + `SERVICE_TYPES` reuse | WP02 | |
| T005 | Load `service-inventory.json` → yield a target per service-type entry | WP02 | |
| T006 | Alert-eligibility gate (`status ∈ {active,running}`) per ADR-0006 | WP02 | [P] |
| T007 | Pointer-path resolution: `state_path` else `endpoint` (F4) | WP02 | [P] |
| T008 | Coverage-gap set: active/running with `method: none`/missing/unhandled | WP02 | |
| T009 | Registry unit tests (fixtures, not the live file) | WP02 | |
| T010 | `ProbeResult` + method→probe dispatch over the real vocabulary | WP03 | |
| T011 | `http` / `shell` / `systemd-status` / `command` liveness probes | WP03 | [P] |
| T012 | Freshness-pointer probe (heterogeneous timestamp field — design callout) | WP03 | |
| T013 | Log-scan probe (`log-tail`/`journal`) | WP03 | [P] |
| T014 | `health.py` `evaluate()` — gate-before-probe + ProbeResult→HealthResult (ADR-0006) | WP03 | |
| T015 | Probe + health unit tests (injected effects, offline) | WP03 | |
| T016 | `dedup.py` DedupState — transition/recovery mandatory reset (F7) | WP04 | |
| T017 | `run.py` orchestration: iterate → evaluate → dedup → emit | WP04 | |
| T018 | Emit via `alert_bus` (real `Alert`/`Severity` API, F3) + severity map | WP04 | [P] |
| T019 | Per-component JSONL ledger (F8) + aggregate tick-signal | WP04 | |
| T020 | CLI `--once` / `--dry-run` / `--self-check`; fail-open pass (NFR-004) | WP04 | |
| T021 | Runner unit tests (injected probes, dedup transitions, fail-safe) | WP04 | |
| T022 | Add `max_age_seconds: 100800` to restic `health_check` + reconcile method (design callout) | WP05 | |
| T023 | Register `felix-canary` runner entry in inventory (FR-010) | WP05 | [P] |
| T024 | Confirm restic pointer `snapshot_timestamp_utc` semantics + update narrative/`updated_by` | WP05 | |
| T025 | `felix-canary.service` + `.timer` (15-min) + `OnFailure=` alert shim unit | WP06 | |
| T026 | `deploy-felix-canary.py` entrypoint (install → daemon-reload → verify → enable) | WP06 | |
| T027 | Verify-before-enable: `--self-check` **and** one real unit run asserting tick+ledger (F9) | WP06 | |
| T028 | `deploys/queued/0017-felix-canary-registry.yaml` manifest (tier 3, audited, rebaseline) | WP06 | [P] |
| T029 | Deploy-script unit tests (byte-identical ExecStart guard, #703) | WP06 | |
| T030 | `docs/runbooks/canary-registry-ops.md` runbook | WP07 | |
| T031 | Register in `docs/INDEX.md` + `docs/DEVELOPER_PORTAL.md` | WP07 | [P] |
| T032 | Coherence: INV-003 note + `coherence/decisions.jsonl` entry | WP07 | [P] |
| T033 | Architecture-doc updates per `signal-to-doc-map.json` (service-added) | WP07 | |

---

## WP01 — health_check `max_age_seconds` schema + validator support

**Goal**: Add the one inventory schema change this mission needs — an optional `max_age_seconds`
integer on `health_check` — and teach `validate_architecture_data.py` to validate it. Foundation for
every freshness probe. **Dependencies**: none. **Prompt**: [tasks/WP01-max-age-schema-validator.md](tasks/WP01-max-age-schema-validator.md).
**Est. size**: ~180 lines.

- [x] T001 Validate `max_age_seconds` is a positive int when present (WP01)
- [x] T002 Warn (warn→strict) when an alert-eligible freshness/log-scan `health_check` omits `max_age_seconds` (WP01)
- [x] T003 Validator unit tests: accept valid, reject non-int/≤0, warn-on-omit (WP01)

**Independent test**: `pytest tests/tooling/test_validate_architecture_data*.py` green; `python
tooling/scripts/validate_architecture_data.py` still exits 0 (warn-only) on the current tree.

## WP02 — canary registry loader (`registry.py`)

**Goal**: Read `service-inventory.json` and yield one `CanaryTarget` per service-type entry, classify
alert-eligibility by declared `status`, resolve the freshness pointer path, and produce a coverage-gap
set for live entries with no usable `health_check`. **Dependencies**: WP01. **Prompt**:
[tasks/WP02-registry-loader.md](tasks/WP02-registry-loader.md). **Est. size**: ~300 lines.

- [x] T004 `CanaryTarget` dataclass; reuse the canonical `SERVICE_TYPES`/`NON_SERVICE_TYPES` sets (WP02)
- [x] T005 Load inventory → a target for each service-type entry (WP02)
- [x] T006 Alert-eligibility: `status ∈ {active,running}` (ADR-0006) (WP02)
- [x] T007 Pointer-path resolution: `state_path` else `endpoint` (F4) (WP02)
- [x] T008 Coverage-gap set: active/running with `method: none`/missing/unhandled method (FR-006) (WP02)
- [x] T009 Unit tests against fixtures (not the live inventory) (WP02)

**Independent test**: `pytest tests/canary/test_registry.py` green; a fixture inventory yields the
expected target set + gap set.

## WP03 — probe evaluators + health computation (`probes.py` + `health.py`)

**Goal**: Implement the method→probe dispatch over the **real** inventory vocabulary and map probe
results to a health outcome per ADR-0006, gating before probing. Pure w.r.t. injected effects.
**Dependencies**: WP01, WP02. **Prompt**: [tasks/WP03-probes-and-health.md](tasks/WP03-probes-and-health.md).
**Est. size**: ~420 lines.

- [x] T010 `ProbeResult` dataclass + method→probe dispatch (real vocabulary, F1) (WP03)
- [x] T011 `http`/`shell`/`systemd-status`/`command` liveness probes (WP03)
- [x] T012 Freshness-pointer probe — heterogeneous timestamp field resolution (design callout) (WP03)
- [x] T013 Log-scan probe (`log-tail`/`journal`) (WP03)
- [x] T014 `evaluate()` — gate-before-probe (F6) + ProbeResult→HealthResult mapping (WP03)
- [x] T015 Probe + health unit tests, injected effects, offline (WP03)

**Independent test**: `pytest tests/canary/test_probes.py tests/canary/test_health.py` green; a suppressed
target returns `suppressed` without any probe call.

## WP04 — runner orchestration (`run.py` + `dedup.py`)

**Goal**: The systemd/CLI entrypoint. Iterate targets → evaluate → dedup (transition/recovery reset,
F7) → emit stale/failed/degraded + persistent-unknown + gap → write the aggregate tick-signal and the
per-component JSONL ledger (F8). Fail-open. **Dependencies**: WP02, WP03. **Prompt**:
[tasks/WP04-runner-orchestration.md](tasks/WP04-runner-orchestration.md). **Est. size**: ~450 lines.

- [ ] T016 `dedup.py` DedupState (per-`component_id`, mandatory transition/recovery reset, F7) (WP04)
- [ ] T017 `run.py` orchestration: iterate → evaluate → dedup → emit (WP04)
- [ ] T018 Emit via `alert_bus` real `Alert`/`Severity` API (F3) + severity map (R6) (WP04)
- [ ] T019 Per-component JSONL ledger (F8) + aggregate `last-tick.json` (WP04)
- [ ] T020 CLI `--once`/`--dry-run`/`--self-check`; fail-open pass (NFR-004) (WP04)
- [ ] T021 Runner unit tests: dedup transitions, fail-safe, emission set (WP04)

**Independent test**: `pytest tests/canary/test_run.py tests/canary/test_dedup.py` green;
`python3 -m scripts.canary.run --dry-run` prints a health line for every service-type entry.

## WP05 — inventory: restic normalization + runner registration

**Goal**: The mission's only `service-inventory.json` edits. Normalize the restic backup onto the
uniform freshness path (`max_age_seconds: 100800`) and register the `felix-canary` runner as a Felix
component (FR-010). **Dependencies**: WP01. **Prompt**:
[tasks/WP05-inventory-registration.md](tasks/WP05-inventory-registration.md). **Est. size**: ~160 lines.

- [x] T022 Add `max_age_seconds: 100800` to restic `health_check`; reconcile method (design callout) (WP05)
- [x] T023 Register `felix-canary` runner entry (`systemd_user_timer`, `active`, tick-signal health_check) (WP05)
- [x] T024 Confirm `snapshot_timestamp_utc` semantics; update inventory narrative + `updated_by` (WP05)

**Independent test**: `python tooling/scripts/validate_architecture_data.py` exits 0; the two edited
entries validate; `python3 -m json.tool` parses the file.

## WP06 — deploy: systemd timer + manifest + verify-before-enable

**Goal**: Install `felix-canary.service`+`.timer` (15-min) + an `OnFailure=` alert shim on office2 via
a `deploys/queued/` manifest; verify before enabling by running the **real unit once** and asserting a
tick-signal + ledger line landed (F9, #703). **Dependencies**: WP04, WP05. **Prompt**:
[tasks/WP06-deploy-manifest.md](tasks/WP06-deploy-manifest.md). **Est. size**: ~360 lines.

- [ ] T025 `felix-canary.service` + `.timer` (15-min) + `OnFailure=` alert shim unit (WP06)
- [ ] T026 `deploy-felix-canary.py`: install → daemon-reload → verify → enable (WP06)
- [ ] T027 Verify-before-enable: `--self-check` **and** one real unit run asserting tick+ledger (F9) (WP06)
- [ ] T028 `deploys/queued/0017-felix-canary-registry.yaml` (tier 3, audited_surface, rebaseline) (WP06)
- [ ] T029 Deploy-script unit tests + byte-identical ExecStart guard (#703) (WP06)

**Independent test**: `pytest tests/deploy/test_deploy_felix_canary.py` green; the deploy script's
`ExecStart` string equals the `.service` file's `ExecStart` byte-for-byte.

## WP07 — docs + coherence

**Goal**: Operational runbook, navigation registration, and coherence records so the new service is
discoverable and doctrine-consistent. **Dependencies**: WP04, WP05, WP06. **Prompt**:
[tasks/WP07-docs-and-coherence.md](tasks/WP07-docs-and-coherence.md). **Est. size**: ~200 lines.

- [ ] T030 `docs/runbooks/canary-registry-ops.md` (WP07)
- [ ] T031 Register in `docs/INDEX.md` + `docs/DEVELOPER_PORTAL.md` (WP07)
- [ ] T032 Coherence: INV-003 note + `coherence/decisions.jsonl` entry (WP07)
- [ ] T033 Architecture-doc updates per `signal-to-doc-map.json` (service-added) (WP07)

**Independent test**: Docs CI green; INDEX + DEVELOPER_PORTAL link the runbook; `coherence/decisions.jsonl`
parses.
