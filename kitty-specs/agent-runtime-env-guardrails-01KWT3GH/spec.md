# Feature Specification: Agent runtime-env guardrails

**Mission**: agent-runtime-env-guardrails-01KWT3GH
**Source issue**: kentonium3/kg-automation#658 (P2-infra, Tier 3)
**Status**: Draft — pending plan
**Created**: 2026-07-05

## Overview

Felix's OpenClaw agents emit shell commands and invoke helpers that silently depend
on runtime-environment facts the invocation does not control: the current working
directory, `~`/`HOME` expansion, and which of office2's two repository checkouts is
active. When any of these drift, the agent either fails (`ModuleNotFoundError`, the
#656 case) or writes to the wrong, unsynced location (the #656 stray-directory case).
This is a recurring silent-failure/wrong-location bug class, not a one-off.

This mission eliminates the class fleet-wide: it adds a **deterministic guard** that
detects the assumption in agent prompts, **folds the same check into the workspace
validator** so newly-authored agents inherit it, **converts every existing in-scope
invocation** to a robust, launch-context-independent form, and **redeploys** the
hardened prompts. The already-shipped concrete fixes (#656 gateway `PYTHONPATH`, #659
observation-log repoint) are the seed instances and are explicitly out of scope.

The work is **entirely Felix-side**: it touches Felix agent prompts, Felix tooling,
and Felix CI. It alters **no** native OpenClaw element (core/package, the
`~/.openclaw/skills/` layout, `openclaw.json`, or `openclaw-gateway.service`).

## User Scenarios & Testing

**Primary actor**: an agent author (human or an #167 workspace-authoring agent) adding
or editing an OpenClaw agent prompt; secondarily, CI acting as the always-on enforcer.

### Scenario 1 — the class cannot re-enter (primary)
1. An author writes an agent prompt containing `python3 -m scripts.foo` with no explicit
   resolution of its runtime environment.
2. On push, the Test CI guard flags the invocation with a specific, actionable message
   naming the file and line.
3. CI is red until the author converts the invocation to the guardrail-explicit form (or
   records an explicit, documented waiver at the guard).

### Scenario 2 — authoring-time enforcement
1. An #167 workspace-authoring agent generates a new agent workspace.
2. `validate_workspace.py` runs the same env-assumption check and rejects the workspace
   if it contains an unguarded invocation or a `~`/`HOME`-relative write — before it is
   ever deployed.

### Scenario 3 — existing fleet is cleared
1. The four felix-admin agents (capture, habits, escalation, tasker) currently emit 30
   `python3 -m scripts.` invocations across their `AGENTS.md` (and the capture
   `AGENTS.md.tmpl`).
2. Each is converted to a form that resolves its runtime environment explicitly and works
   whether or not it is launched under `openclaw-gateway.service`, without hardcoding a
   checkout path.
3. The hardened prompts are redeployed to office2; each agent passes its health check on
   the next run (capture routes real inbox content with no "helpers not deployed"
   hallucination; habits/escalation/tasker cron runs are green).

### Edge cases
- **`-m scripts.` outside the gateway.** Invocations must not assume the gateway-provided
  `PYTHONPATH`; a manually-run or helper-chained invocation must still resolve correctly.
- **Checkout-path trap.** A remediation that hardcodes `/home/claude/kg-automation`
  re-introduces the very checkout-path assumption the mission exists to kill; such a
  remediation is itself a violation.
- **Template drift.** Fixing a rendered `AGENTS.md` without fixing its `AGENTS.md.tmpl`
  leaves a latent regression that the next render reintroduces.
- **Reads vs writes.** A read of `~/.openclaw/...` (OpenClaw's own home) is a legitimate,
  stable contract and must NOT be flagged; only `~`/`HOME`-relative **writes** are the
  stray-dir class.

## Requirements

### Functional Requirements

| ID | Requirement | Status |
|----|-------------|--------|
| FR-001 | The system provides a deterministic guard that detects, in every agent prompt under `scripts/openclaw/agents/`, `python3 -m scripts.` invocations that do not explicitly resolve their runtime environment (cwd/`PYTHONPATH`) and are therefore not robust to launch context. | Proposed |
| FR-002 | The guard detects `~`/`HOME`-relative **write** operations in agent prompts, while **permitting** reads of `~/.openclaw/...` (OpenClaw-home) paths. | Proposed |
| FR-003 | The guard executes as a pytest-based check inside the **existing** kg-automation Test CI, requiring **no** change to any `.github/workflows/` file. | Proposed |
| FR-004 | The same env-assumption check is integrated into `scripts/openclaw/agents/validate_workspace.py` (the #587 validator) so newly authored agent workspaces are validated for the class at authoring time. | Proposed |
| FR-005 | Every in-scope `python3 -m scripts.` invocation in the four felix-admin agents (capture, habits, escalation, tasker) **and** the capture `AGENTS.md.tmpl` is converted to a guardrail-explicit form that (a) resolves its runtime environment explicitly, (b) works with or without `openclaw-gateway.service`, and (c) does **not** hardcode a checkout path. | Proposed |
| FR-006 | Any `~`/`HOME`-relative **write** in the in-scope prompts is converted to a canonical absolute anchor, or explicitly dispositioned with a documented reason. | Proposed |
| FR-007 | The canonical guardrail-explicit form and any permitted reliance (e.g. on a declared root env var) are documented **at the guard**, not in scattered prose. | Proposed |
| FR-008 | `felix-admin-calendar`, `felix-doc-auditor`, and `main` are audited for the same class and remediated or dispositioned (each currently has zero `-m scripts.` invocations). | Proposed |
| FR-009 | The hardened prompts are redeployed to office2 through a `deploys/queued/<name>.yaml` manifest consumed by felix-deployer. | Proposed |

### Non-Functional Requirements

| ID | Requirement | Threshold | Status |
|----|-------------|-----------|--------|
| NFR-001 | The guard is deterministic: no network, no LLM, no environment probing; identical inputs yield identical results. | 100% reproducible across runs | Proposed |
| NFR-002 | The guard completes fast enough to sit in the existing Test CI without materially slowing it. | < 5 s over all agent prompts on a CI runner | Proposed |
| NFR-003 | The guard has zero false negatives for the two known seed patterns. | Detects both the #656 cwd-drift `-m scripts.` shape and the #656 `~`/`HOME`-relative-write shape in a fixture | Proposed |
| NFR-004 | The guard's flag messages are actionable. | Each flag names the file, the line, the offending pattern, and the remediation class | Proposed |

### Constraints

| ID | Constraint | Status |
|----|------------|--------|
| C-001 | No modification to any `.github/workflows/` file; the guard rides the existing Test CI via pytest. | Proposed |
| C-002 | No modification to any native OpenClaw element: core/package, the `~/.openclaw/skills/` install layout, `openclaw.json`, or `openclaw-gateway.service`. | Proposed |
| C-003 | The `python3 -m scripts.X.Y` module invocation form is **retained** (it is required for helpers importing `scripts.common.*`); only its unstated env dependency is made explicit. | Proposed |
| C-004 | Tier 3 change; deploy flows through the `deploys/queued/` manifest pipeline; felix-deployer auto-rebaselines the audited surface (agent prompts). | Proposed |
| C-005 | The #656 (gateway `PYTHONPATH`) and #659 (observation-log repoint) seed fixes are out of scope — they are already shipped. | Proposed |

## Success Criteria

| ID | Criterion |
|----|-----------|
| SC-001 | The env-assumption guard exists and runs green in Test CI, with zero unremediated flags across all agent prompts (or every remaining flag explicitly waived with a documented reason at the guard). |
| SC-002 | `validate_workspace.py` enforces the check: a newly-authored workspace containing an unguarded env-assuming invocation or a `~`/`HOME`-relative write is rejected at validation. |
| SC-003 | A re-scan of the four felix-admin agents (+ capture `.tmpl`) shows zero unanchored `python3 -m scripts.` invocations; all 30 known occurrences are converted or dispositioned. |
| SC-004 | Post-redeploy, the four affected agents pass their health checks: capture `prescan --self-check` → `ok` and the next cron run routes real inbox content with no "helpers not deployed" hallucination; habits/escalation/tasker next cron runs are green. |
| SC-005 | No native OpenClaw element is changed — verifiable from the mission diff scope (no edits under `~/.openclaw`, `openclaw.json`, or `openclaw-gateway.service`). |

## Key Entities

- **Agent prompt** (`scripts/openclaw/agents/<agent>/AGENTS.md`, and its `.tmpl` where
  present) — the deployed command surface that carries the invocations.
- **Env-assumption guard** — the deterministic detector (pytest + a shared checker).
- **Workspace validator** (`validate_workspace.py`, #587) — the authoring-time enforcer
  that reuses the guard's checker.
- **Deploy manifest** (`deploys/queued/<name>.yaml`) — the redeploy vehicle.

## Domain Language

- **Runtime-environment assumption** — a command's reliance on cwd, `~`/`HOME` expansion,
  or checkout path that the command itself does not guarantee.
- **Guardrail-explicit form** — an invocation that resolves its runtime environment
  explicitly and robustly (absolute anchor, thin wrapper, or an explicitly-consumed
  declared-root env), documented at the guard.
- **Gateway-independent** — behaves correctly whether or not launched under
  `openclaw-gateway.service` (which provides `PYTHONPATH` per #656). The design must not
  depend on that env.
- **Seed instance** — a concrete prior fix (#656, #659) that motivated the class; out of
  scope here.

## Assumptions

- The `openclaw-gateway.service` `PYTHONPATH` from #656 remains in place, but the design
  deliberately does **not** rely on it (per the anchor-for-portability decision).
- The felix-deployer manifest pipeline is operational for the redeploy step.
- The exact canonical anchor mechanism (thin wrapper vs declared-root env vs resolved
  repo-root) is a plan-phase design decision, constrained by C-003 and the
  no-hardcoded-checkout rule; it is a designated post-plan Codex-review target.

## Architecture Impact

Per `docs/design/architecture/data/signal-to-doc-map.json`, the material change class is
**agent-prompt-changed** (and, if the guard ships any deploy/systemd artifact,
`systemd-unit-added-or-modified`). Doc targets to review at merge:

- `data/service-inventory.json` + markdown view — **no change expected** (no new/removed
  service, port, or credential).
- `data/network-topology.json` — **no change**.
- `data/audited-surfaces.json` — agent prompts are already an audited surface; confirm the
  guard/validator additions are reflected if they become a deploy artifact.
- The #167 workspace-authoring standard doc — **updated** to reference the new guardrail
  (so authored agents inherit the expectation).
- `docs/INDEX.md` / `docs/DEVELOPER_PORTAL.md` — review for any new guard/runbook surface.

Rebaseline: **Yes** (audited surface = agent prompts); delivered via `deploys/queued/`, so
felix-deployer auto-rebaselines on the happy path; the merge records
`Rebaseline: completed at <ts>` (automated) per `docs/runbooks/security-baseline-ops.md`.
