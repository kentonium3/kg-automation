# Implementation Plan: Unified Alert Bus

**Branch**: `feat/unified-alert-bus` | **Date**: 2026-07-10 | **Spec**: [spec.md](./spec.md)
**Input**: Feature specification from `kitty-specs/unified-alert-bus-01KX5TYT/spec.md`
**Source issue**: kentonium3/kg-automation#701

## Summary

Build the **`felix-alert` bus** — a shared Python library (`scripts/common/alert_bus/`) plus a thin CLI
(`python3 -m scripts.common.alert_bus`) and a bash-callable shim (`scripts/common/alert_bus.sh`) — that
constructs a uniform, self-explanatory alert (timestamp, source, severity, title, description,
action-required, details incl. real stderr), maps severity to ntfy priority/tags, and delivers to a
single canonical ntfy topic. It is the only code that talks to ntfy. Migrate the three components that
emit ntfy today onto it (felix-deployer subsystem, security-monitor `audit.sh`, felix-health-check), add
a co-emit for enforcement drift, retire the per-script curl code, and provision a new dedicated topic
out-of-band. Deploys to office2 via the manifest pipeline.

The name `felix-alert` is already the design term for this primitive in
`docs/design/felix-bedrock-stabilization.md`, `docs/design/coherence/doctrine.md`, and RFC #327.

## Technical Context

**Language/Version**: Python 3.11+ (office2 `python3`); Bash for the shell shim
**Primary Dependencies**: Python standard library + `curl` invoked via `subprocess` (matches every
existing emitter — no new pip package). `pytest` for tests. No new external package source (C-003).
**Storage**: Stateless. The canonical topic id is read from a single environment variable
(`FELIX_ALERT_NTFY_TOPIC`) provisioned out-of-band via an env-file credential; no DB/state files.
**Testing**: `pytest` unit tests with `subprocess` mocked (no live ntfy in CI); direct tests for schema
construction, severity→priority/tag mapping, topic resolution, missing-optional-field rendering, and
delivery-failure (fail-safe) handling. Line+branch coverage ≥ 90% for the module (NFR-002); no
reduction to the repo's enforced coverage gate.
**Target Platform**: office2 (Ubuntu 24.04). All three emitters run **natively** (systemd timers +
cron as the `claude` user) — **no docker container isolation** — so a bash caller can invoke the Python
CLI directly. Confirmed from `service-inventory.json` + the systemd/cron units.
**Project Type**: single (Python library + CLI + bash shim under `scripts/common/`, plus edits to the
existing emitter modules and deploy/doc artifacts).
**Performance Goals**: An `emit()` call is best-effort and non-blocking — it never blocks the host
beyond the curl `--max-time` ceiling (10 s, matching existing emitters). Alert volume is low (a few per
day); no throughput concern.
**Constraints**: ntfy transport only (C-001); deploy exclusively via `deploys/queued/` manifest (C-002);
no new deps (C-003); Tier 3 with rebaseline on audited surfaces `scripts/deploy/**` + security-monitor
(C-004); bash-callable (C-005); fail-safe delivery — a delivery failure never crashes/hangs an emitter
(NFR-001).
**Scale/Scope**: 3 emitter subsystems migrated + 1 enforcement co-emit + new library/CLI/shim +
provisioning + docs. Estimated a few hundred LOC.

## Charter Check

*GATE: Must pass before Phase 0 research. Re-check after Phase 1 design.*

- **DIRECTIVE_001 (Architectural Integrity) / DIRECTIVE_031 (Context-Aware Design)**: PASS — the bus is
  a single-responsibility shared component with a narrow public API (`emit(Alert) -> AlertResult`);
  schema, rendering, and delivery are separated modules; emitters depend only on the public API.
- **DIRECTIVE_024 (Locality of Change)**: PASS — each emitter migration is a localized swap of its curl
  block for one `emit()` call; blast radius is contained per emitter (migrated one at a time, NFR-004).
- **DIRECTIVE_003 / DIRECTIVE_010 (Decision Docs / Spec Fidelity)**: PASS — the plan-phase scope
  correction (5→3 real ntfy emitters + enforcement co-emit) is recorded in spec.md and research.md.
- **Felix Constitution Directive 6 (deterministic-vs-stochastic) + helper/library/skill decision**:
  PASS — all work is deterministic; the invocation-surface test → **shared library** in
  `scripts/common/` (used across the deploy, office2, and openclaw domains), with a CLI + bash shim.
- **Change-Risk Tier**: Tier 3 (Standard). **Rebaseline obligation (#557)**: YES for audited surfaces
  (`scripts/deploy/**`, security-monitor `audit.sh`, any systemd unit edited); the manifest-pipeline
  deploy auto-rebaselines and the merge/applied record stamps the outcome.
- **Architecture-doc standing requirement**: the mission updates `service-inventory.json` +
  `credential-manifest.json` and adds an alerting runbook (IC-08).

No violations → Complexity Tracking not required.

## Project Structure

### Documentation (this mission)

```
kitty-specs/unified-alert-bus-01KX5TYT/
├── plan.md              # This file
├── research.md          # Phase 0 output (decisions + rationale)
├── data-model.md        # Phase 1 output (Alert schema + severity map)
├── quickstart.md        # Phase 1 output (emit / deploy / verify)
├── contracts/           # Phase 1 output (Python API, CLI, ntfy message contracts)
└── tasks/               # Phase 2 output (/spec-kitty.tasks — NOT created here)
```

### Source Code (repository root)

```
scripts/common/
├── alert_bus/                    # NEW package — the felix-alert bus
│   ├── __init__.py               #   public API: emit(), Alert, Severity, AlertResult
│   ├── model.py                  #   Alert dataclass + Severity enum + SEVERITY_MAP (→ priority/tags)
│   ├── render.py                 #   title/body rendering from Alert (missing-field-safe, redacted)
│   ├── delivery.py               #   topic resolution (env) + curl POST + fail-safe AlertResult
│   └── __main__.py               #   CLI: `python3 -m scripts.common.alert_bus emit|self-test ...`
└── alert_bus.sh                  # NEW bash shim: env-anchored `cd <checkout> && python3 -m ...`

# Migrated emitters (curl code removed, now call the bus):
scripts/deploy/felix-deployer/notify.py          # → emit()
scripts/deploy/lib/health.py                     # dispatch_health_notification → emit()
scripts/office2/felix_health_check/run.py        # → emit()
scripts/office2/security-monitor/audit.sh        # → alert_bus.sh
scripts/openclaw/enforcement/notification.py     # ADD felix-alert co-emit (keeps WhatsApp+GitHub)

# Tests (per repo convention):
tests/common/alert_bus/test_model.py test_render.py test_delivery.py test_cli.py

# Deploy + provisioning + docs:
deploys/queued/unified-alert-bus.yaml            # manifest (unnumbered; deployer assigns applied #)
docs/design/architecture/data/credential-manifest.json   # new FELIX_ALERT_NTFY_TOPIC env-file entry
docs/design/architecture/data/service-inventory.json     # bus library + unified topic
docs/runbooks/alerting.md (or observability/)            # how the bus works + how to emit
scripts/common/alert_bus.env.sample                      # env-file template (topic id placeholder)
```

**Structure Decision**: A small **package** (`scripts/common/alert_bus/`) rather than one flat module —
separating model / render / delivery / CLI keeps each unit directly unit-testable to the ≥90% coverage
bar (NFR-002) and honors DIRECTIVE_001 separation of concerns. `scripts/common/` (not a non-existent
`scripts/lib/` nor deploy-specific `scripts/deploy/lib/`) is the repo's home for truly cross-domain
shared code (it already holds `state_log`, `vikunja_client`). Invoked as `from scripts.common.alert_bus
import emit, Alert, Severity` and `python3 -m scripts.common.alert_bus`.

## Complexity Tracking

Not required — no Charter Check violations.

## Implementation Concern Map

> Concerns are architectural areas, not work packages. `/spec-kitty.tasks` translates these into WPs.

### IC-01 — Alert schema & severity mapping

- **Purpose**: Define the uniform alert data shape and the deterministic severity→ntfy mapping so every
  alert carries the same fields and criticality is visually distinguishable on one thread.
- **Relevant requirements**: FR-002, FR-004.
- **Affected surfaces**: `scripts/common/alert_bus/model.py`; `tests/common/alert_bus/test_model.py`.
- **Sequencing/depends-on**: none (foundation).
- **Risks**: getting the severity vocabulary and priority/tag map right so `error`/`critical` stand out
  from `info`/`warn` on a single thread.

### IC-02 — Message rendering (self-explanatory, field-safe, redacted)

- **Purpose**: Render a human-readable title + body from an Alert that shows all present schema fields,
  degrades gracefully when optional fields (e.g. action-required) are absent, and redacts secrets
  before truncation.
- **Relevant requirements**: FR-002, FR-003, NFR-003.
- **Affected surfaces**: `scripts/common/alert_bus/render.py`; reuse the existing secret-redaction
  helper (`scripts/deploy/felix-deployer/_verify.redact_secrets` — evaluate promoting it to shared);
  `tests/common/alert_bus/test_render.py`.
- **Sequencing/depends-on**: IC-01.
- **Risks**: redaction-before-truncation ordering (existing emitters do this — must preserve); ensuring
  the felix-deployer body carries **real stderr**, not just phase+summary (SC-002).

### IC-03 — ntfy delivery, topic resolution, fail-safe

- **Purpose**: Resolve the single canonical topic from `FELIX_ALERT_NTFY_TOPIC`, POST to ntfy via curl
  with the mapped priority/tags headers, and guarantee best-effort delivery — never raise, never hang
  beyond the timeout, return a structured `AlertResult`.
- **Relevant requirements**: FR-001, FR-005, FR-007, NFR-001.
- **Affected surfaces**: `scripts/common/alert_bus/delivery.py`; `tests/common/alert_bus/test_delivery.py`.
- **Sequencing/depends-on**: IC-01.
- **Risks**: fail-safe semantics (unreachable endpoint, missing topic → non-fatal `AlertResult`, no
  exception); preserving the proven curl flag set (`--silent --show-error --fail --max-time 10`,
  `--data-binary @-`).

### IC-04 — CLI + bash shim

- **Purpose**: Expose the bus to shell callers. A `python3 -m scripts.common.alert_bus` CLI (`emit` +
  `self-test` subcommands) and a `scripts/common/alert_bus.sh` shim that env-anchors the call
  (`cd /home/claude/kg-automation && python3 -m …`, the proven checkout-cd form from #658) so cron/bash
  callers don't depend on inherited `PYTHONPATH`.
- **Relevant requirements**: FR-005, FR-008.
- **Affected surfaces**: `scripts/common/alert_bus/__main__.py`, `scripts/common/alert_bus.sh`;
  `tests/common/alert_bus/test_cli.py`.
- **Sequencing/depends-on**: IC-01, IC-02, IC-03.
- **Risks**: the shell-env class from #658/#662 (bare `python3`, stripped PYTHONPATH) — the shim must
  use the canonical checkout-cd form and office2's `python3` (no bare `python`, per env fact).

### IC-05 — Python emitter migrations

- **Purpose**: Rewire the Python ntfy emitters to build an Alert and call `emit()`, deleting their own
  curl code, with no change to their core behavior or health signals.
- **Relevant requirements**: FR-006, FR-003, NFR-004, SC-002.
- **Affected surfaces**: `scripts/deploy/felix-deployer/notify.py`, `scripts/deploy/lib/health.py`
  (+ its caller `_tick.py`), `scripts/office2/felix_health_check/run.py`, **and the indirect consumer
  `scripts/openclaw/deploy/deploy_agent_prompts.py`** (rides on `health.py`'s notifier); their tests.
- **Sequencing/depends-on**: IC-01, IC-02, IC-03 (public API stable).
- **Hard requirements (from post-plan review)**:
  - **SC-002 stderr threading**: `_tick.py:622` currently passes only `result.summary`; the migration
    must thread `result.details` (`stderr_excerpt`, `stdout_excerpt`, `argv`/`failed_command`,
    `returncode`, `phase`, `manifest_path`) into `Alert.details`, with a #699-regression test asserting
    the alert body names the failing cause.
  - **felix-health-check adapter**: define + test an adapter from `AlertResult` → the existing
    `{attempted, sent, detail}` signal-file shape so `run.py`'s `last-run.json` behavior is preserved
    (missing-topic / curl-failure / success cases).
  - **agent-prompt-sync**: preserve `health.record()`'s bool-return contract (used to stamp
    `last_alert_ts`); update its notifier tests.
- **Risks**: felix-deployer's three call sites (failure/rebaseline/health) + health.py's bool return
  contract used by both felix-deployer and agent-prompt-sync — the migration must preserve those
  return semantics.

### IC-06 — Bash emitter migration + enforcement co-emit

- **Purpose**: Point security-monitor `audit.sh` at the shim, and add a `felix-alert` co-emit to the
  enforcement notifier (keeping its WhatsApp + GitHub records).
- **Relevant requirements**: FR-006 (audit.sh), FR-009 (enforcement).
- **Affected surfaces**: `scripts/office2/security-monitor/audit.sh`,
  `scripts/openclaw/enforcement/notification.py`; enforcement tests.
- **Sequencing/depends-on**: IC-04 (shim + CLI). audit.sh is an audited surface → rebaseline.
- **Risks**: audit.sh currently hardcodes its topic + posts once with a summary; the migration must keep
  its cron fail-safe (notification failure never fails the audit).

### IC-07 — Topic provisioning, runtime env wiring, registry, deploy manifest

- **Purpose**: Mint + provision the new dedicated topic out-of-band, record it as a credential + in the
  topic registry, **wire every emitting runtime to load `FELIX_ALERT_NTFY_TOPIC`**, and ship via manifest.
- **Relevant requirements**: FR-007, C-002, C-004.
- **Env wiring (post-plan CRITICAL — the difference between "built" and "delivering")**:
  - Add `EnvironmentFile=/home/claude/.config/felix/alert-bus/env` to `felix-deployer.service`,
    `felix-health-check.service`, and `agent-prompt-sync.service`.
  - **`scripts/common/alert_bus.sh` sources that env-file itself** before invoking Python, so the
    cron-launched `audit.sh` (no systemd EnvironmentFile) still resolves the topic.
  - Update `scripts/office2/deploy/felix-health-check.sh` (and any deploy scripts) to provision the file.
  - Add a **deploy preflight** that reports a missing env-file, and a **per-runtime self-test**
    (systemd context + cron context) proving delivery.
- **Affected surfaces**: `deploys/queued/unified-alert-bus.yaml`,
  `docs/design/architecture/data/credential-manifest.json`, `scripts/common/alert_bus.env.sample`, the
  three systemd units above, `scripts/office2/security-monitor/audit.sh` (drop hardcoded topic),
  `scripts/office2/deploy/felix-health-check.sh`; rebaseline audited surfaces.
- **Sequencing/depends-on**: IC-03 (topic env-var contract), IC-04 (shim sources env). **Operator step**
  (Kent mints the high-entropy topic + provisions the env-file; topic value never committed — the
  deliberate C-002 exception).
- **Risks**: the topic id is a secret (ntfy security = topic secrecy) — must not land in the repo or
  logs; a runtime that isn't wired silently gets `NTFY_MISSING_TOPIC` (the failure the preflight +
  self-test exist to catch).

### IC-08 — Architecture docs + alerting runbook

- **Purpose**: Document the bus (schema, severity map, how to emit from Python/CLI/bash), record the
  library + unified topic in `service-inventory.json`, and note the retired per-component topics.
- **Relevant requirements**: Directive 5 + the architecture-doc standing requirement.
- **Affected surfaces**: `docs/design/architecture/data/service-inventory.json`,
  `docs/runbooks/alerting.md` (new), related markdown views.
- **Sequencing/depends-on**: conceptually last (documents IC-01..07).
- **Risks**: keeping JSON authoritative and markdown views in sync (validator gate).
