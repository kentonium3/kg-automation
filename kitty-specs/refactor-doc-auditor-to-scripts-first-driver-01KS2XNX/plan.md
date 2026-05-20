# Implementation Plan: Refactor doc-auditor to scripts-first driver

**Mission**: `refactor-doc-auditor-to-scripts-first-driver-01KS2XNX`
**Mission ID**: `01KS2XNXGQVC18MEF7801JKCYR`
**Branch**: `main` | **Date**: 2026-05-20 | **Spec**: [spec.md](./spec.md)
**Input**: GitHub issue [#343](https://github.com/kentonium3/kg-automation/issues/343)

---

## Summary

Replace the LLM-first procedural agent for `felix-doc-auditor` with a stateless Python driver. The driver owns the deterministic workflow (signal ingestion, lock state, Tier-A auto-commit, debt filing, audit closure, structured tick signal) and calls an LLM only at three narrow, named judgment moments (`tier_classification`, `debt_body_generation`, `cross_file_implication`). The new driver consumes existing well-built helpers (`handle_drift_events.py`, `handle_audit_routing.py`) via a hybrid library+CLI pattern. At cutover, the old openclaw-agent definition is fully retired — fail-forward, no parallel path.

Three discovery decisions (from `/spec-kitty.specify`) and four planning decisions (from `/spec-kitty.plan`) drive the implementation:

- **Spec Q1** = fully retire the openclaw-agent surface at cutover
- **Spec Q2** = reliability as an NFR with a lightweight observation hook for #327
- **Spec Q3** = process the full queue per tick
- **Plan Q1** = `claude-haiku-4-5` via the official `anthropic` SDK with prompt caching on judgment-template boilerplate
- **Plan Q2** = 3 LLM judgment moments (the deterministic missing-artifact and audit-summary moments become templates/glob-intersections)
- **Plan Q3** = `SignalSource` Protocol abstraction with two initial adapters (`GHIssueSignalSource`, `DriftEventSignalSource`)
- **Plan Q4** = pytest with mocked `gh` + mocked Anthropic SDK + one live smoke test

---

## Technical Context

**Language/Version**: Python 3.10+ (the office2 system Python is 3.12; the spec-kitty venv has 3.13). Driver targets 3.10+ for compatibility.

**Primary Dependencies**:
- `anthropic` (official Python SDK) — LLM calls + prompt caching
- `gh` CLI (existing on office2) — invoked as subprocess for GitHub operations
- Standard library: `argparse`, `subprocess`, `json`, `pathlib`, `dataclasses`, `typing.Protocol`, `tomllib` (for config)
- Existing helpers (imported): `handle_drift_events.py`, `handle_audit_routing.py`

**Storage**:
- Tick signal at `/data/services/openclaw/felix-doc-auditor-driver/last-tick.json` (current-state JSON, atomic writes)
- Activity log at `/home/kgale/second-brain/agents/logs/doc-auditor-YYYY-MM-DD.md` (append-only markdown, preserved format)
- Drift-event cursor at `/data/services/security-monitor/.drift-events.cursor` (preserved location)
- No database. All persistent state is file-based.

**Testing**: pytest with three layers: unit (mocked `gh` + mocked Anthropic SDK), integration (mocked surfaces + real internal wiring covering all 5 tick outcomes and 4 edge cases), live smoke (gated by `pytest -m live_smoke`, hits real GH + real Anthropic).

**Target Platform**: Linux (Ubuntu 24.04 LTS on office2). systemd user timer + oneshot service. macOS dev environment for tests.

**Project Type**: Single Python package (`scripts/doc_audit/`). No web/mobile component.

**Performance Goals**:
- Typical tick: ≤30 seconds wall-clock
- Per-tick token consumption: ≥80% below pre-rework baseline (NFR-001)
- 95% successful-tick rate over 7-day post-cutover soak (NFR-002)

**Constraints**:
- 30-min systemd timeout (`TimeoutStartSec=30min`)
- Per-tick state artifacts ≤100 KB (NFR-003)
- Fail-forward (C-007) — no automatic rollback
- Inherits Tier-A vs judgment classification policy unchanged (C-001)

**Scale/Scope**: Hourly tick cadence. Typical queue depth 0-2 audits per tick (normal); occasional backlog up to ~10 audits after outage (Q3=B drains in one tick).

---

## Charter Check

Charter governance is currently unresolved per the pre-existing tool-registry mismatch (see memory `project_charter_tool_registry_mismatch.md`), but the project charter at `.kittify/charter/charter.md` IS present. Spec-kitty's compact-mode charter context loaded successfully for both `--action specify` and `--action plan`. Section anchors confirmed:

| Anchor | Compliance |
|---|---|
| Two Constitutions — Don't Conflate | ✅ Driver operates within Felix Constitution; no charter directive conflicts. |
| Testing Standards | ✅ Plan Q4 = pytest + mocks + live smoke; matches the testing approach used by `tests/inbox/` and `tests/habits/` (existing convention). |
| Quality Gates | ✅ Spec quality checklist passes all 16 items; this plan adds Phase 0 research + Phase 1 design artifacts; no [NEEDS CLARIFICATION] markers. |
| Performance Benchmarks | ✅ NFR-001 (≥80% token reduction) is the explicit performance gate. NFR-002 (95% successful ticks) is the reliability gate. |
| Branch Strategy | ✅ `current_branch=main, base_branch=main, target_branch=main, branch_matches_target=true`. No worktree required for plan; implement-phase will create lane worktrees per spec-kitty 3.1.8 conventions. |
| Deployment Constraints | ✅ Plan honors C-004 (queue-drained at cutover), C-007 (fail-forward), C-006 (kg-felix-bot identity preserved). |
| Change-Risk Taxonomy (Tier Protocol) | ✅ Spec risk-tier 3 (Logic / Workflow). systemd unit edit is the operationally most consequential surface; reversible via re-deploy. |
| Governance Activation | ✅ Constitutional Compliance section of spec maps to Observed Level 2; Tier-A frontmatter applies autonomously; judgment edits remain gated. |

**No gate violations.** Re-check after Phase 1: still none — design artifacts do not introduce new gate considerations.

**Note on charter tool-registry**: the charter resolution emitted `Charter selected unavailable tool(s): pytest, python`. This is non-blocking (charter context loaded in compact mode); flagged in memory for resolution after #343.

---

## Project Structure

### Documentation (this feature)

```
kitty-specs/refactor-doc-auditor-to-scripts-first-driver-01KS2XNX/
├── plan.md                                    # This file (/spec-kitty.plan output)
├── spec.md                                    # /spec-kitty.specify output
├── research.md                                # Phase 0 output (14 decisions + assumption validation)
├── data-model.md                              # Phase 1 output (10 entities + state machine)
├── quickstart.md                              # Phase 1 output (operator quickstart)
├── contracts/                                 # Phase 1 output (4 contracts)
│   ├── driver-invocation.contract.md
│   ├── judgment-prompts.contract.md
│   ├── signal-source.contract.md
│   └── tick-signal.contract.md
├── checklists/
│   └── requirements.md                        # Specify-phase quality checklist (16/16 pass)
├── meta.json
├── status.events.jsonl                        # Spec-kitty workflow state
└── tasks/                                     # Will be populated by /spec-kitty.tasks
```

### Source Code (repository root)

```
scripts/doc_audit/                             # NEW Python package — the driver
├── __init__.py
├── run.py                                     # CLI entry point (driver-invocation.contract.md)
├── config.py                                  # Config dataclass + load_config()
├── config.toml                                # Default config
├── data_model.py                              # E-001..E-010 dataclasses (data-model.md)
├── signals/
│   ├── __init__.py
│   ├── base.py                                # SignalSource Protocol + Signal dataclass
│   ├── gh_issue.py                            # GHIssueSignalSource
│   └── drift_event.py                         # DriftEventSignalSource (wraps handle_drift_events.py)
├── judgment/
│   ├── __init__.py
│   ├── client.py                              # Anthropic SDK wrapper + prompt-cache helpers
│   ├── tier_classification.py
│   ├── debt_body_generation.py
│   └── cross_file_implication.py
├── prompts/
│   ├── tier_classification.prompt.md          # Cache-aware template (judgment-prompts.contract.md)
│   ├── debt_body_generation.prompt.md
│   └── cross_file_implication.prompt.md
├── routing/
│   ├── __init__.py
│   └── apply_decisions.py                     # Wraps handle_audit_routing.py imports
├── output/
│   ├── __init__.py
│   ├── tick_signal.py                         # Writes last-tick.json atomically
│   └── activity_log.py                        # Appends to /home/kgale/second-brain/agents/logs/
└── README.md                                  # In-tree dev/test guide

scripts/openclaw/agents/felix-doc-auditor/     # MODIFIED — refactor for import surface
├── handle_drift_events.py                     # Add importable functions; CLI entry point preserved
└── handle_audit_routing.py                    # Add importable functions; CLI entry point preserved

scripts/office2/                               # MODIFIED — systemd unit + deploy script
├── felix-doc-auditor.service                  # ExecStart change (openclaw agent → python run.py)
└── deploy/
    └── felix-doc-auditor-driver.sh            # NEW deploy script (D10 cutover steps)

tests/doc_audit/                               # NEW test package
├── __init__.py
├── conftest.py                                # Shared fixtures (mocked gh, mocked anthropic)
├── test_signals_gh_issue.py
├── test_signals_drift_event.py
├── test_judgment_tier_classification.py
├── test_judgment_debt_body_generation.py
├── test_judgment_cross_file_implication.py
├── test_routing_apply_decisions.py
├── test_output_tick_signal.py
├── test_output_activity_log.py
├── test_integration_tick_outcomes.py          # 5 outcomes + 4 edge cases
└── test_smoke_live.py                         # Gated by pytest -m live_smoke

docs/design/architecture/baselines/            # NEW — NFR-001 measurement artifacts
├── felix-doc-auditor-pre-rework.json
└── felix-doc-auditor-post-rework.json

docs/runbooks/
└── doc-auditor-driver-ops.md                  # NEW operator runbook (FR-013)

docs/design/architecture/data/                 # MODIFIED — service-inventory + data-flows + credential-manifest updates
├── service-inventory.json                     # felix-doc-auditor entry: invocation, dependencies updated
├── data-flows.json                            # Remove openclaw-session-state edges; add direct-API edges
└── credential-manifest.json                   # Anthropic key path noted as used by driver process
```

**Structure Decision**: Single Python package layout. The driver is a self-contained module under `scripts/doc_audit/` because:
- The repo's existing convention puts automation scripts under `scripts/` (matches `scripts/inbox/`, `scripts/habits/`, etc.)
- The driver consumes existing helpers from `scripts/openclaw/agents/felix-doc-auditor/` via import — no cross-tree dependency
- Tests under `tests/doc_audit/` mirror the package layout for clean discovery

The old openclaw agent workspace at `scripts/openclaw/agents/felix-doc-auditor/AGENTS.md` etc. is **deleted at cutover** (per FR-010). The two reusable helpers (handle_drift_events.py, handle_audit_routing.py) remain at their current paths — they're not openclaw-agent-specific; the agent just happened to be the caller.

---

## Phase 0 Output

[`research.md`](./research.md) — 14 decisions (D1–D14), 7-assumption validation table, 3 open questions flagged for Phase 1.

Key research findings:
- All 7 spec assumptions validated against live office2 state (✅ Anthropic key readable, ✅ gh auth as kg-felix-bot, ✅ activity log writable, ✅ helpers exist and are reusable).
- **Bonus discovery**: the signal-driven pipeline is more built-out than the spec implied — `signal-to-doc-map.json` (12 mappings) and `handle_drift_events.py` (323 lines) already deliver the deterministic-WHAT layer of the signal-driven architecture. The driver consumes these as-is; no signal-source expansion is in scope for #343.

---

## Phase 1 Output

- [`data-model.md`](./data-model.md) — 10 entities (E-001..E-010) + audit issue lifecycle state machine
- [`contracts/tick-signal.contract.md`](./contracts/tick-signal.contract.md) — JSON schema + write semantics + consumer expectations
- [`contracts/signal-source.contract.md`](./contracts/signal-source.contract.md) — Protocol definition + adapter expectations
- [`contracts/judgment-prompts.contract.md`](./contracts/judgment-prompts.contract.md) — template structure + I/O schemas per moment
- [`contracts/driver-invocation.contract.md`](./contracts/driver-invocation.contract.md) — CLI surface + exit codes + systemd unit shape
- [`quickstart.md`](./quickstart.md) — operator quickstart for the post-cutover ops model

---

## Complexity Tracking

No charter check violations. No complexity justification required.

The driver is intentionally a single Python package (not split across packages); the only deliberate "complexity" choice is the hybrid library+CLI refactor of `handle_drift_events.py` and `handle_audit_routing.py`, which research D3 justifies (test surface + overhead) over either pure-subprocess (rejected for testability) or pure-library (rejected for breaking the existing bash-invocable contract).

---

## Branch Strategy (restated)

- **Current branch**: `main`
- **Planning/base branch**: `main`
- **Final merge target**: `main`
- **Worktree creation**: deferred to `/spec-kitty.tasks` / `/spec-kitty.implement`. Lane worktrees per spec-kitty 3.1.8 convention will land at `.worktrees/refactor-doc-auditor-to-scripts-first-driver-01KS2XNX-lane-<a-z>/`.

---

## Next Step

User invokes `/spec-kitty.tasks` to break the plan into work packages. This plan is the input.
