# Implementation Plan: Felix Truthful Reporting Guardrails

**Branch**: `fix/felix-truthful-reporting` | **Date**: 2026-07-10 | **Spec**: [spec.md](./spec.md)
**Input**: Feature specification from `kitty-specs/felix-truthful-reporting-01KX6MN5/spec.md`

## Summary

Make Felix's status reports trustworthy and stop it creating unrequested
infrastructure, via two complementary layers: (1) **doctrine** — a truthful-
reporting + mechanism-fidelity block applied fleet-wide to agent prompts, plus a
no-unrequested-infrastructure block for `main`; and (2) **bounded detection** —
a **load-bearing** deterministic cron-drift detector (live crons vs an approved
baseline — agent-independent) and a completion-assertion **action ledger**
auto-emitted by artifact-creation helpers plus a verifier that grounds asserted
artifacts against existence, both alerting through the shipped #701 unified alert
bus. Enforcement is doctrine + prompt only (no hard capability change); the
cron-drift detector is the reliable backstop for the infrastructure class. A
pure verbal completion lie with no artifact/assertion is an acknowledged blind
spot (doctrine-only in v1). See [research.md](./research.md) for the D1–D4
decisions (revised after the post-plan Codex review — findings 1–10 folded).

## Technical Context

**Language/Version**: Python 3.12 (office2 is `python3`-only; invoke helpers as `python3 -m scripts.<pkg>.<mod>`)
**Primary Dependencies**: `scripts/common/alert_bus/` (#701 emit library), OpenClaw CLI (`openclaw cron list/get --json`, 2026.6.11), Vikunja API client (`scripts/vikunja/` / `VikunjaClient`), existing `log_action.py` JSONL substrate
**Storage**: Committed approved-cron baseline (JSON/YAML in repo); append-only completion-assertion JSONL on office2 (under the second-brain agents/logs substrate or `/data/services/`); no database
**Testing**: pytest with `--cov-branch`; mock OpenClaw/Vikunja/alert-bus at the subprocess/client boundary; fleet-guard agent-prompt tests for AGENTS.md budget/format; deterministic fixtures for drift + assertion scenarios
**Target Platform**: office2 (Ubuntu 24.04 LTS); detector runs as a systemd **user** timer under the `claude` account
**Project Type**: single (Python helpers/libraries + agent-prompt doctrine + deploy manifest)
**Performance Goals**: detection cycle ≤ 15 min (NFR-002); scan cost negligible (a few CLI/API calls per tick)
**Constraints**: fail-safe — detector failure never breaks agents (NFR-001); doctrine additions within AGENTS.md ~12k rawChars budget (NFR-003); alerts reuse #701 topic only (C-002); no `openclaw.json` tool-grant changes (C-003)
**Scale/Scope**: 7 fleet agents; ~7 legitimate crons today; single operator (Kent)

## Charter Check

*GATE: Must pass before Phase 0 research. Re-check after Phase 1 design.*

- **DIRECTIVE_034 Test-First**: acceptance + unit tests precede implementation; drift/assertion detectors are TDD-friendly (deterministic given mocked CLI/API). **PASS (planned).**
- **DIRECTIVE_010 Specification Fidelity**: bounded-detection scope is explicitly recorded (spec "Scope decisions" + research D2 limitation); no silent scope expansion. **PASS.**
- **DIRECTIVE_024 Locality of Change**: doctrine edits localized to `AGENTS.md`; detector localized to new `scripts/` modules; no cross-cutting refactor. **PASS.**
- **DIRECTIVE_003 Decision Documentation**: D1–D4 recorded in research.md with rationale + alternatives. **PASS.**
- **DIRECTIVE_033 Targeted Staging**: WPs stage only their own deliverables. **PASS (process).**
- **Project — Helper/Library/Skill conventions** (`docs/design/helper-script-conventions.md`): detector is a helper+library with a CLI interface, stdout/exit-code contract, atomic state, idempotency, fail-safe. **PASS (planned).**
- **Project — Engineering principles** (deterministic work into scripts; LLM for judgment only): detection is fully deterministic; the LLM's only role is doctrine adherence. **PASS.**
- **Project — Change-risk taxonomy**: agent prompts = Tier 3 logic. They are a *listed but unmonitored* audited surface — per gap #621 (verified in `audited-surfaces.json` 2026-07-10) `audit.sh` does not hash `AGENTS.md`, so **rebaseline is NOT required or possible** for the prompt edits; the detector code (`scripts/trust/`, `scripts/deploy/`) is not a hashed baseline either. Detector + manifest = Tier 3. No Tier 0/1/2 actions. **PASS — mission is `Rebaseline: not required` (Codex finding 9).**
- **Project — Deploy discipline**: office2 deploy flows through `deploys/queued/<name>.yaml` + felix-deployer; entrypoint installs the systemd timer. **PASS (planned).**

No charter violations requiring Complexity Tracking.

## Project Structure

### Documentation (this mission)

```
kitty-specs/felix-truthful-reporting-01KX6MN5/
├── plan.md              # This file
├── research.md          # Phase 0 (D1–D4)
├── data-model.md        # Phase 1
├── quickstart.md        # Phase 1
├── contracts/           # Phase 1 (detector CLI + assertion record contracts)
└── tasks.md             # Phase 2 (/spec-kitty.tasks — NOT created here)
```

### Source Code (repository root)

```
scripts/
├── openclaw/agents/
│   ├── _shared/                     # (new or existing) canonical doctrine snippet source, if factored
│   ├── main/AGENTS.md               # + truthful-reporting + mechanism-fidelity + no-unrequested-infra
│   ├── felix-admin-capture/AGENTS.md    # + truthful-reporting + mechanism-fidelity
│   ├── felix-admin-habits/AGENTS.md     #   (same)
│   ├── felix-admin-tasker/AGENTS.md     #   (same)
│   ├── felix-admin-escalation/AGENTS.md #   (same)
│   ├── felix-admin-calendar/AGENTS.md   #   (same)
│   └── felix-doc-auditor/AGENTS.md      #   (same)
├── trust/                           # NEW — the detection subsystem
│   ├── cron_baseline.py             #   load/compare approved-cron baseline
│   ├── cron_drift_detector.py       #   enumerate live crons, diff, emit alerts
│   ├── completion_assertion.py      #   record + schema for completion-assertions
│   ├── assertion_verifier.py        #   verify asserted artifacts exist, emit alerts
│   └── run_trust_scan.py            #   single entrypoint driving both scans (timer target)
├── deploy/
│   └── deploy-truthful-reporting.py # NEW — installs timer + preflight + self-test
data/ or committed baseline:
└── docs/design/architecture/data/approved-crons.json  # NEW — the approved-cron baseline (candidate home)

deploys/queued/
└── NNNN-truthful-reporting-detector.yaml   # NEW — deploy manifest

systemd (installed on office2 by the entrypoint):
└── felix-trust-scan.timer + .service       # NEW — ≤15-min cadence

tests/
└── trust/                                   # NEW — unit + acceptance tests
```

**Structure Decision**: Single-project Python. Detection code is a new
self-contained `scripts/trust/` package (locality); doctrine changes are
in-place `AGENTS.md` edits; deploy follows the established manifest + entrypoint
+ systemd-timer pattern. The approved-cron baseline's exact committed home
(`docs/design/architecture/data/` vs `scripts/trust/`) is finalized in
data-model.md.

## Complexity Tracking

*No Charter Check violations — table intentionally empty.*

## Implementation Concern Map

> Concerns are architectural areas, not work packages. `/spec-kitty.tasks`
> translates these into WPs.

### IC-01 — Truthful-reporting & mechanism-fidelity doctrine (fleet-wide)

- **Purpose**: Encode "report only verified performed actions" and "fulfil the
  requested mechanism or report inability — never silently substitute" in every
  fleet agent prompt, extending the existing Output-discipline pattern.
- **Relevant requirements**: FR-001, FR-002.
- **Affected surfaces**: all `scripts/openclaw/agents/<agent>/AGENTS.md`
  (7 agents); optional shared canonical snippet source to prevent drift.
- **Sequencing/depends-on**: none (pure prompt edits).
- **Risks**: AGENTS.md prompt budget (NFR-003) — keep terse, run fleet-guard
  tests. Audited surface → rebaseline on deploy.

### IC-02 — No-unrequested-infrastructure guardrail (main)

- **Purpose**: Instruct `main` never to create/modify scheduled or standing
  infrastructure (crons) unless explicitly requested; fulfil a reminder request
  with the requested mechanism (Vikunja task), not a substituted cron.
- **Relevant requirements**: FR-003, FR-002.
- **Affected surfaces**: `scripts/openclaw/agents/main/AGENTS.md`.
- **Sequencing/depends-on**: none.
- **Risks**: overlaps IC-01 placement in the same file — coordinate edits to one
  AGENTS.md to avoid churn.

### IC-03 — Unrequested-infrastructure drift detector (deterministic backstop)

- **Purpose**: Enumerate live OpenClaw crons and diff against a committed
  approved-cron baseline; alert via #701 on any unapproved/missing cron. The
  reliable, agent-independent half of detection.
- **Relevant requirements**: FR-004, FR-005, FR-006(b); NFR-001, NFR-002.
- **Affected surfaces**: `scripts/trust/cron_baseline.py`,
  `cron_drift_detector.py`, the approved-cron baseline artifact.
- **Sequencing/depends-on**: none for logic; shares the runner (IC-05) with
  IC-04.
- **Risks**: baseline maintenance false-positives; OpenClaw CLI output shape
  drift — mock at the subprocess boundary, verify `--json` shape in a contract.

### IC-04 — Completion-assertion action ledger & verifier (grounding claims)

- **Purpose**: Define a structured completion-assertion (artifact kind + id
  **list** + optional request/conversation ref) and **auto-emit it from the
  artifact-creation helpers on success** (starting with the Vikunja task helper
  `scripts/vikunja/create_task.py`, #686) — not from free-form agent compliance.
  A deterministic verifier confirms each asserted artifact exists and alerts via
  #701 on a missing artifact. Doctrine (IC-01) additionally asks for a manual
  assertion only when an agent bypasses a wrapped helper.
- **Relevant requirements**: FR-004, FR-005, FR-006(a); NFR-001, NFR-002.
- **Affected surfaces**: `scripts/trust/completion_assertion.py`,
  `assertion_verifier.py`; a small auto-emit hook in
  `scripts/vikunja/create_task.py`; a doctrine line in IC-01; Vikunja existence
  checks (calendar/vault → `unverifiable_kind` warn, deferred).
- **Sequencing/depends-on**: the assertion record schema/helper settles first,
  then the create-helper auto-emit hook and the verifier.
- **Risks**: this ledger is **not** a verbal-lie detector (Codex findings 1–2) —
  the cron-drift detector (IC-03) is the load-bearing guard. Keep verification
  deterministic; **no LLM judge**. Model **multi-artifact** completions as an id
  list with per-artifact results (Codex finding 7 — the 7-task case). Be careful
  the auto-emit hook is fail-safe (a ledger-write failure must not break task
  creation).

### IC-05 — Runner, deploy, rebaseline & regression verification

- **Purpose**: A single scan entrypoint driving IC-03+IC-04, a systemd user
  timer (≤15 min), a `deploys/queued/` manifest + entrypoint that installs the
  timer and runs a preflight self-test, and the SC-001..005 regression
  verification. **Rebaseline is NOT required** (gap #621 — prompts unmonitored;
  detector code not a hashed baseline); the merge commit records
  `Rebaseline: not required — <reason>`.
- **Relevant requirements**: NFR-001, NFR-002, C-002, C-004; SC-001..005.
- **Affected surfaces**: `scripts/trust/run_trust_scan.py`,
  `scripts/deploy/deploy-truthful-reporting.py`, `deploys/queued/…yaml`,
  systemd unit files, architecture docs (`service-inventory.json` + narrative)
  per the standing architecture-update requirement.
- **Sequencing/depends-on**: after IC-03 + IC-04 logic exists.
- **Risks**: deploy gotchas (entrypoint must be `chmod +x`; must install +
  daemon-reload units; failing queued manifest fail-loops felix-deployer). The
  entrypoint must **trigger `agent-prompt-sync.service` and verify deployed
  prompt content before the regression DM test** (Codex finding 10 — do not wait
  for the 5-min timer). Timer mode always exits 0; preflight/self-test mode may
  exit 2 (Codex finding 8). Fold in the #701/#699 deploy lessons.
