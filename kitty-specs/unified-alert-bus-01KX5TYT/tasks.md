# Tasks: Unified Alert Bus

**Mission**: unified-alert-bus-01KX5TYT · **Issue**: kentonium3/kg-automation#701
**Planning base**: `feat/unified-alert-bus` · **Merge target**: `feat/unified-alert-bus`

Builds the `felix-alert` bus (library + CLI + bash shim) and migrates the 3 real ntfy emitters
(felix-deployer subsystem, felix-health-check, security-monitor) onto it, adds an enforcement co-emit,
provisions a new dedicated topic + runtime env wiring, and updates architecture docs. Deploys to
office2 via the manifest pipeline. Tier 3; rebaseline on audited surfaces.

## Subtask Index

| ID | Description | WP | Parallel |
|----|-------------|----|----------|
| T001 | `model.py` — Alert, Severity, SEVERITY_MAP, AlertResult | WP01 | | [D] |
| T002 | `render.py` — title/body rendering, field-safe, redact-before-truncate | WP01 | | [D] |
| T003 | `delivery.py` — topic resolution + curl POST + fail-safe AlertResult | WP01 | | [D] |
| T004 | `__init__.py` — public API `emit/Alert/Severity/AlertResult` | WP01 | | [D] |
| T005 | `__main__.py` — CLI `emit`/`self-test` (+`--strict`) | WP01 | | [D] |
| T006 | `alert_bus.sh` — shim: source env-file, checkout-cd, best-effort exit 0 | WP01 | | [D] |
| T007 | Unit tests (model/render/delivery/cli) ≥90% coverage | WP01 | | [D] |
| T008 | Migrate `notify.py` (failure/rebaseline/health) → `emit()` | WP02 | [D] |
| T009 | Thread real stderr (`result.details`) through `_tick.py` → Alert.details (SC-002) | WP02 | | [D] |
| T010 | Migrate `health.py` `dispatch_health_notification` → `emit()`, preserve bool | WP02 | | [D] |
| T011 | Update `deploy_agent_prompts.py` consumer; preserve `last_alert_ts` stamp | WP02 | | [D] |
| T012 | Update felix-deployer + agent-prompt-sync notifier tests (+#699 regression) | WP02 | | [D] |
| T013 | Migrate `felix_health_check/run.py` → `emit()` | WP03 | [D] |
| T014 | `AlertResult → {attempted,sent,detail}` adapter; preserve `last-run.json` | WP03 | | [D] |
| T015 | felix-health-check unit tests (missing-topic/failure/success) | WP03 | | [D] |
| T016 | Migrate `audit.sh` → `alert_bus.sh` (drop hardcoded topic + raw curl) | WP04 | [D] |
| T017 | Add `felix-alert` co-emit to enforcement `notification.py` (keep WhatsApp+GitHub) | WP04 | | [D] |
| T018 | Enforcement + audit behavior-preservation tests | WP04 | | [D] |
| T019 | `deploys/queued/unified-alert-bus.yaml` manifest | WP05 | |
| T020 | New `FELIX_ALERT_NTFY_TOPIC` credential + `credential-manifest.json` + env.sample | WP05 | |
| T021 | Wire `EnvironmentFile` into 3 systemd units + `felix-health-check.sh` provisioning | WP05 | |
| T022 | Deploy preflight (missing-env report) + per-runtime self-test | WP05 | |
| T023 | `service-inventory.json` — bus library + unified topic; retire old topic notes | WP06 | |
| T024 | `docs/runbooks/alerting.md` — bus, schema, how to emit (Python/CLI/bash) | WP06 | |

## Work Packages

### WP01 — Alert bus library (schema · render · delivery · CLI · shim)
- **Goal**: the whole `felix-alert` bus in `scripts/common/alert_bus/` + `alert_bus.sh`, with ≥90% test coverage.
- **Priority**: P1 (foundation / MVP). **Independent test**: `pytest tests/common/alert_bus` green; `self-test` delivers with a topic set.
- **Subtasks**: T001–T007. **Dependencies**: none. **Est. size**: ~450 lines.
- **Requirements**: FR-001, FR-002, FR-003, FR-004, FR-005, FR-008. **Risks**: severity map correctness; fail-safe semantics; redaction ordering.

### WP02 — felix-deployer subsystem migration (+ real stderr)
- **Goal**: migrate `notify.py` + `deploy/lib/health.py` + `_tick.py` + the `agent-prompt-sync` consumer onto `emit()`; thread real stderr into failure alerts.
- **Priority**: P1 (fixes the #699 opacity symptom). **Independent test**: forced deployer failure → alert body names the failing cause; `pytest tests/deploy tests/openclaw/test_deploy_agent_prompts.py` green.
- **Subtasks**: T008–T012. **Dependencies**: WP01. **Est. size**: ~420 lines.
- **Requirements**: FR-003, FR-006. **Risks**: 3 notify call sites; health.py bool contract used by two consumers.

### WP03 — felix-health-check migration + adapter
- **Goal**: migrate `felix_health_check/run.py` onto `emit()` with an `AlertResult → {attempted,sent,detail}` adapter preserving `last-run.json`.
- **Priority**: P2. **Independent test**: `pytest tests/office2/felix_health_check` green; signal-file shape unchanged across missing-topic/failure/success.
- **Subtasks**: T013–T015. **Dependencies**: WP01. **Est. size**: ~260 lines.
- **Requirements**: FR-006. **Risks**: `{attempted,sent,detail}` byte-compatibility.

### WP04 — audit.sh migration + enforcement co-emit
- **Goal**: point `audit.sh` at the shim; add a `felix-alert` co-emit to enforcement `notification.py` (keep WhatsApp+GitHub).
- **Priority**: P2. **Independent test**: audit run posts via the bus and stays non-fatal on failure; enforcement drift → both a `felix-alert` and its GitHub record.
- **Subtasks**: T016–T018. **Dependencies**: WP01 (Python emit for enforcement), WP01/shim for audit. **Est. size**: ~280 lines.
- **Requirements**: FR-006, FR-009. **Risks**: audit cron fail-safe; enforcement co-emit must not disturb existing channels.

### WP05 — provisioning, runtime env wiring, deploy manifest
- **Goal**: mint/record the new topic credential, wire `FELIX_ALERT_NTFY_TOPIC` into every runtime, ship the manifest, add preflight + per-runtime self-test.
- **Priority**: P1 (without this the bus is built but not delivering). **Independent test**: preflight flags a missing env-file; self-test delivers from systemd + cron contexts on office2.
- **Subtasks**: T019–T022. **Dependencies**: WP02, WP03, WP04. **Est. size**: ~360 lines.
- **Requirements**: FR-001, FR-007, FR-008. **Risks**: topic secrecy (out-of-band, never committed); an unwired runtime silently gets `NTFY_MISSING_TOPIC`.

### WP06 — architecture docs + alerting runbook
- **Goal**: record the bus library + unified topic in `service-inventory.json`; write `docs/runbooks/alerting.md`; note retired per-component topics.
- **Priority**: P3 (polish). **Independent test**: architecture-data validator green; runbook documents Python/CLI/bash emit.
- **Subtasks**: T023–T024. **Dependencies**: WP05. **Est. size**: ~200 lines.
- **Requirements**: (documentation of FR-001/FR-005/FR-007). **Risks**: JSON authoritative / markdown sync.

## Dependencies & parallelization

```
WP01 ──┬── WP02 ─┐
       ├── WP03 ─┤
       └── WP04 ─┴── WP05 ── WP06
```
WP02/WP03/WP04 run in parallel after WP01. **MVP = WP01 + WP02** (the bus + the #699 symptom fix).
