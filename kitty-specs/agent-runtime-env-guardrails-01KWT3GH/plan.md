# Implementation Plan: Agent runtime-env guardrails

**Branch**: `feat/agent-runtime-env-guardrails` | **Date**: 2026-07-05 | **Spec**: [spec.md](./spec.md)
**Input**: Feature specification from `kitty-specs/agent-runtime-env-guardrails-01KWT3GH/spec.md`
**Source issue**: kentonium3/kg-automation#658 (P2-infra, Tier 3)

## Summary

Eliminate the "unstated runtime-environment assumption" bug class from Felix's OpenClaw
agent commands, fleet-wide. Deliver a **deterministic checker** (shared library function)
that detects the assumption in agent prompts; wrap it as a **pytest guard** in the existing
Test CI and **fold it into `validate_workspace.py`** so newly-authored agents inherit it;
**convert every in-scope invocation** across the four felix-admin agents (and the `.tmpl`
sources) to a robust, gateway-independent canonical form; and **redeploy** the hardened
prompts via the manifest pipeline. Entirely Felix-side.

Two decisions fixed during planning (see `research.md`):
- **Scope (D1)** covers BOTH `python3 -m scripts.…` invocations AND
  `python3 /home/claude/kg-automation/scripts/…py` absolute-path invocations — the
  checkout-path axis manifests as both.
- **Canonical anchor form (D2)** reuses the gateway-declared `PYTHONPATH` as the repo root
  with a fail-loud `${PYTHONPATH:?…}` guard — no gateway/systemd change.

## Technical Context

**Language/Version**: Python for the checker/guard — **must be 3.11-compatible** (stdlib
only; the existing Test CI runs Python 3.11 per `.github/workflows/test-ci.yml` and C-001
forbids changing the workflow — so no 3.12-only syntax, Codex LOW-1); Bash for the converted
invocation forms inside agent prompts; deploy manifest YAML.
**Primary Dependencies**: pytest (existing Test CI); `scripts/openclaw/agents/validate_workspace.py`
(#587 validator, extended); the `deploys/queued/` felix-deployer manifest pipeline. No new
third-party packages.
**Storage**: N/A (no persistent state; the checker is pure over file contents).
**Testing**: pytest — the guard IS a test; plus unit fixtures for the checker's detection
of each violation shape and acceptance of the canonical form.
**Target Platform**: kg-automation CI (Linux) for the guard; office2 (Ubuntu 24.04, the
`/home/claude/kg-automation` checkout under `openclaw-gateway.service`) for the deployed
prompts.
**Project Type**: single project (helper + test + agent-prompt edits, no app tiers).
**Performance Goals**: guard completes < 5 s over all agent prompts on a CI runner (NFR-002).
**Constraints**: deterministic, no network/LLM/env-probing (NFR-001); no `.github/workflows/`
change (C-001); no native OpenClaw element altered (C-002); `-m scripts.` module form
retained (C-003); Tier 3 deploy via manifest (C-004).
**Scale/Scope**: 7 agent workspaces audited; 4 converted (capture, habits, escalation,
tasker) + their `.tmpl` sources; 30 `-m scripts.` invocations + the abs-path invocations
on the checkout-path axis.

## Charter Check

*GATE: Must pass before Phase 0 research. Re-check after Phase 1 design.*

Charter directives in scope (from `charter context --action plan`): 001, 003, 010, 024,
031, 033, 034.

- **DIRECTIVE_001 (Architectural Integrity)** — PASS. The checker is a single shared
  function with one responsibility (detect env assumptions); the guard and the validator
  are thin consumers. Clear separation.
- **DIRECTIVE_003 (Decision Documentation)** — PASS. D1/D2 recorded via the decision CLI +
  `research.md`; the canonical form and its trade-offs are documented at the guard.
- **DIRECTIVE_010 (Specification Fidelity)** — PASS with a recorded deviation: scope is
  EXPANDED beyond the #658 body's literal "`-m scripts.`" set to include abs-path
  invocations (D1). Documented; endorsed by the operator.
- **DIRECTIVE_024 (Locality of Change)** — PASS, and load-bearing for D2: reusing
  `PYTHONPATH` keeps the blast radius on the agent-prompt + tooling surface with no
  systemd/gateway change.
- **DIRECTIVE_031 (Context-Aware Design)** — PASS. Work stays within the Felix
  agent-workspace bounded context; the one cross-boundary touch (reading OpenClaw's
  gateway-declared `PYTHONPATH`) is an explicit, documented reliance, not implicit coupling.
- **DIRECTIVE_033 / 034** — PASS (testing + quality gates satisfied by the pytest guard and
  the deterministic checker fixtures).

No violations → Complexity Tracking left empty.

## Project Structure

### Documentation (this mission)

```
kitty-specs/agent-runtime-env-guardrails-01KWT3GH/
├── plan.md              # This file
├── research.md          # Phase 0 output
├── data-model.md        # Phase 1 output (checker detection model)
├── quickstart.md        # Phase 1 output
├── contracts/           # Phase 1 output (checker + guard behavior contract)
└── traces/              # mission tracer files (doctrine)
```

### Source Code (repository root)

```
scripts/openclaw/agents/
├── env_assumptions.py          # NEW — the shared deterministic checker (detect + classify)
├── validate_workspace.py       # EXTENDED — add check_runtime_env_assumptions() consuming the checker
├── tests/
│   └── test_env_assumptions_guard.py   # NEW — the Test-CI pytest guard + checker unit fixtures
├── felix-admin-capture/AGENTS.md, AGENTS.md.tmpl   # CONVERTED invocations
├── felix-admin-habits/AGENTS.md                    # CONVERTED (de-hardcode the cd + abs-path)
├── felix-admin-escalation/AGENTS.md                # CONVERTED (bare → canonical)
├── felix-admin-tasker/AGENTS.md, AGENTS.md.tmpl    # CONVERTED
└── felix-admin-calendar/, felix-doc-auditor/, main/ # AUDITED (0 -m scripts.; abs-path in calendar/tasker)

deploys/queued/
└── 0010-agent-runtime-env-guardrails.yaml          # NEW — redeploy converted prompts
```

**Structure Decision**: the checker lives beside the surface it guards
(`scripts/openclaw/agents/env_assumptions.py`) per the helper/library/skill decision
(domain-co-located helper, not a shared `scripts/lib/` primitive — its only consumers are
the guard test and the workspace validator). The guard test lives in the existing
`scripts/openclaw/agents/tests/` package so it is collected by the existing Test CI.

## Complexity Tracking

*No Charter Check violations — section intentionally empty.*

## Implementation Concern Map

> Implementation concerns are NOT work packages. `/spec-kitty.tasks` translates these into
> executable WPs.

### IC-01 — Shared env-assumption checker
- **Purpose**: One deterministic function that scans an agent-prompt file and classifies
  each invocation as compliant (canonical `${PYTHONPATH:?}` form) or a violation (bare
  `-m scripts.`; hardcoded-checkout `cd`/abs-path; `~`/HOME-relative write), returning
  structured findings — the single source of truth both consumers share.
- **Relevant requirements**: FR-001, FR-002, FR-007.
- **Affected surfaces**: `scripts/openclaw/agents/env_assumptions.py` (new).
- **Sequencing/depends-on**: none (foundational).
- **Risks**: must distinguish **actual command invocations from prose/doc mentions**
  (e.g. capture line 74 "Invoke via `python3 -m scripts.inbox.<helper>` form" is
  documentation, not a command) and from fenced examples — the v323 F4 mis-flag class. Must
  handle single-path `PYTHONPATH` assumption (see research trade-off).

### IC-02 — Test-CI pytest guard
- **Purpose**: A pytest test that runs the checker across all agent prompts and fails on
  any unremediated violation (or a documented waiver), with actionable file/line/pattern
  messages. Rides the existing Test CI — no workflow-file change.
- **Relevant requirements**: FR-003, NFR-001..004, SC-001.
- **Affected surfaces**: `scripts/openclaw/agents/tests/test_env_assumptions_guard.py` (new).
- **Sequencing/depends-on**: IC-01.
- **Risks**: fixture coverage for both violation shapes and the canonical form (NFR-003);
  must be deterministic and fast.

### IC-03 — Workspace-validator fold
- **Purpose**: Add `check_runtime_env_assumptions()` to `validate_workspace.py` as a new
  `CheckResult`, reusing IC-01, so #167-authored workspaces are validated at authoring time.
- **Relevant requirements**: FR-004, SC-002.
- **Affected surfaces**: `scripts/openclaw/agents/validate_workspace.py`.
- **Sequencing/depends-on**: IC-01.
- **Risks**: keep the existing check structure/return contract intact; don't regress the
  privacy/output-discipline checks.

### IC-04 — Invocation conversion
- **Purpose**: Convert every in-scope invocation (both `-m scripts.` and `python`/`python3`
  abs-path) in capture/habits/escalation/tasker **and calendar** AND their `.tmpl` sources
  to the canonical **cd form** `cd "${PYTHONPATH:?…}" && …`; keep each `.tmpl` and its
  rendered `AGENTS.md` in lockstep; ensure helper path args are absolute.
- **Relevant requirements**: FR-005, FR-006.
- **Affected surfaces**: capture/habits/escalation/tasker/calendar `AGENTS.md`
  (+ capture/tasker `.tmpl`).
- **Sequencing/depends-on**: IC-01 (canonical form defined); verified by IC-02.
- **Risks**: `.tmpl`↔rendered drift (v323 lesson); the cd form requires absolute helper args
  (Codex HIGH-3 — audit each helper's args); `~`/HOME writes already clean (confirm);
  `python` (not just `python3`) abs-path lines (Codex MED-1).

### IC-05 — Fleet audit + docs
- **Purpose**: Audit `main` for the class (0 `-m scripts.`; convert any abs-path per D1);
  **disposition `felix-doc-auditor` as retired** (scripts-first driver, no live agent, in
  the validator exclusion set — recorded disposition, not active remediation, Codex MED-5);
  update the #167 authoring standard doc to reference the guardrail; reconcile architecture
  docs per the signal map. (calendar's abs-path CONVERSION moved to IC-04, not audit-only.)
- **Relevant requirements**: FR-008, Architecture Impact.
- **Affected surfaces**: `main` prompt; #167 standard doc; `docs/INDEX.md` /
  `DEVELOPER_PORTAL.md` if a new guard surface warrants it; a disposition note for doc-auditor.
- **Sequencing/depends-on**: IC-01.
- **Risks**: doc-auditor's exclusion from the validator must not read as an unverifiable
  "audit" — disposition it explicitly.

### IC-06 — Deploy + verify
- **Purpose**: Ship the converted prompts to office2 via `deploys/queued/0010-…yaml`
  (invoking `deploy_agent_prompts.py`); felix-deployer auto-rebaselines the audited surface;
  verify per-agent health INCLUDING calendar; run the cwd-independence smoke.
- **Relevant requirements**: FR-009, SC-004, SC-005.
- **Affected surfaces**: `deploys/queued/0010-agent-runtime-env-guardrails.yaml` (new).
- **Sequencing/depends-on**: IC-04, IC-05 (converted prompts must exist).
- **Risks**: agent slug ≠ deploy dir (verify per `reference_office2_agent_deploy_paths`);
  health checks must cover **calendar** (validate_calendar_event via stdin + log_action
  shape, Codex MED-4) in addition to capture prescan self-check + habits/escalation/tasker
  cron green; plus the non-repo-cwd smoke (Codex HIGH-3).
