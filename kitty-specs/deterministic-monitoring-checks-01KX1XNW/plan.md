# Implementation Plan: Deterministic Monitoring Checks

**Branch**: `feat/deterministic-monitoring-checks` | **Date**: 2026-07-08 | **Spec**: [spec.md](./spec.md)
**Input**: Feature specification from `kitty-specs/deterministic-monitoring-checks-01KX1XNW/spec.md`

## Summary

Replace Felix's two LLM-mediated self-monitoring paths with deterministic execution:
(1) the 30-min heartbeat-gate's Haiku `gate.decide` call becomes a pure stdlib
function `decide_deterministic(context)` over the already-computed `GateContext`
fields, and (2) the twice-daily health-check moves off the Sonnet `main` agent onto a
new `felix-health-check` systemd user timer that execs the existing bash check and
alerts (on failure) via ntfy. Cadence, escalation-to-Sonnet, the ledger, and the
fail-safe are preserved. The escalation rule is **already validated at design time**
against the full 1748-tick historical ledger: 0 missed escalations, 0 over-escalations
(research R0). Deploy via a `deploys/queued/` manifest; rebaseline required.

## Technical Context

**Language/Version**: Python 3.12 (office2, python3-only); the heartbeat tick decision
path becomes **standard-library only** (removes `anthropic` from the hot path).
**Primary Dependencies**: no new packages. Removes `anthropic` from the tick path.
Runtime touchpoints: systemd user units, `openclaw cron` CLI (removal only), ntfy
(`curl` to ntfy.sh) for health-check failure alerts. **Reuse existing precedents**:
`scripts/office2/credential-health-check.{service,timer}` + `scripts/office2/deploy/
credential-health-check.sh` (systemd-timer deterministic-check pattern) and
`scripts/office2/security-monitor/audit.sh:243-255` (canonical ntfy-send: curl POST
with Title/Priority/Tags, non-fatal-on-failure with a log line).
**Storage**: files only — `gate-ledger.jsonl`, `last-gate-decision.json` (heartbeat),
a health-check signal/state file; no database. `/home/claude/helper-scripts/health-check.sh`
reused in place.
**Testing**: `pytest` under `scripts/openclaw/heartbeat_gate/tests/` (existing suite
adapts to the deterministic decide); new ledger-replay validation
(`validate_ledger.py`) with a committed fixture; health-check wrapper unit tests.
**Target Platform**: Linux (office2, Ubuntu 24.04 LTS), systemd user units.
**Project Type**: single (scripts/ tree).
**Performance Goals**: gate decision completes < 1 s (no network round-trip vs. the
prior Haiku call, NFR-004); cadences unchanged (heartbeat 30 min; health-check 2×/day).
**Constraints**: no LLM in the monitoring hot path (NFR-001/002); Tier 3; deploy via
`deploys/queued/` manifest (DIR-004); openclaw cron via CLI only (DIR-007); rebaseline
required (#557); `python3 -m` invocation form (C-006).
**Scale/Scope**: 48 gate ticks/day + 2 health-checks/day. Changed surfaces: the
`heartbeat_gate` module (decide path), one new systemd timer+service+wrapper, one
deploy manifest, arch-doc JSON/md + AGENT-REGISTRY review, one validation harness.

## Charter Check

*GATE: Must pass before Phase 0 research. Re-check after Phase 1 design.*

| Charter item | Status |
|---|---|
| DIR-001/002 (office2 Linux production) | ✅ targets office2 systemd + python3 only |
| DIR-004 (manifest deploy discipline) | ✅ `deploys/queued/<name>.yaml` planned (IC-04) |
| DIR-007 (openclaw cron via CLI only) | ✅ crons removed via `openclaw cron`, never crontab |
| DIR-005/006 (safe-deploy order, no pause needed) | ✅ artifacts-then-config; worst-case mid-deploy fire is harmless (legacy cron runs once more) |
| DIRECTIVE_034 / DIR-010 (test-first, c4-incremental) | ✅ ledger-replay + unit tests precede/accompany code; spec→plan→research→data-model→tasks layering |
| DIR-014 (doc-sync requirement) | ✅ FR-012 / IC-04 update service-inventory + AGENT-REGISTRY |
| #557 rebaseline | ✅ systemd units + openclaw config → rebaseline recorded in merge commit |
| Design-time discipline (Directive 6) | ✅ the whole mission is a deterministic-vs-stochastic correction; validated R0 |

No charter violations. Complexity Tracking not required.

## Project Structure

### Documentation (this mission)

```
kitty-specs/deterministic-monitoring-checks-01KX1XNW/
├── plan.md              # this file
├── spec.md
├── research.md          # Phase 0 (incl. design-time INV-006 validation)
├── data-model.md        # Phase 1
├── quickstart.md        # Phase 1 (deploy + verify)
├── contracts/           # Phase 1 (escalation-rule + health-check-runner contracts)
└── checklists/requirements.md
```

### Source Code (repository root)

```
scripts/openclaw/heartbeat_gate/
├── gate.py                     # CHANGED: Haiku call → decide_deterministic(context)
├── run.py                      # CHANGED: step 2 calls deterministic decide; drop --api-key/--prompt from tick path
├── context.py                  # UNCHANGED (already deterministic; sole input)
├── escalator.py                # UNCHANGED (step 3 preserved)
├── ledger.py                   # UNCHANGED (step 4 preserved; tokens zeroed)
├── validate_ledger.py          # NEW: INV-006 ledger-replay harness
└── tests/                      # adapt gate tests; add validate_ledger + wrapper tests

scripts/openclaw/health_check/  # NEW (or scripts/office2/): thin non-agent wrapper
└── run.py                      # NEW: exec health-check.sh, classify output, ntfy on failure

deploy/systemd/                 # NEW unit files staged for deploy (repo-side source)
├── felix-health-check.service
└── felix-health-check.timer

deploys/queued/<NNNN>-deterministic-monitoring-checks.yaml   # NEW deploy manifest

docs/design/architecture/data/service-inventory.json (+ .md view)  # CHANGED (FR-012)
docs/constitution/AGENT-REGISTRY.md                                # REVIEWED (FR-012)
```

**Structure Decision**: Single-project layout. The heartbeat-gate change is
co-located in the existing `scripts/openclaw/heartbeat_gate/` module (Locality of
Change, DIR-024). The health-check wrapper + units live under **`scripts/office2/`**
(with `scripts/office2/deploy/`), mirroring the `credential-health-check` precedent
rather than inventing a new layout — decided post-Codex-review.

## Complexity Tracking

*No Charter Check violations — section intentionally empty.*

## Implementation Concern Map

> Concerns, not work packages. `/spec-kitty.tasks` maps these to WPs.

### IC-01 — Determinize the heartbeat-gate decision

- **Purpose**: Replace the Haiku `gate.decide` call with a pure, stdlib-only
  `decide_deterministic(context)` that reproduces the routing prompt's boolean
  escalation contract and emits a deterministic reason + zeroed token fields.
- **Relevant requirements**: FR-001, FR-002, FR-003, FR-004, FR-006, FR-007, FR-008, NFR-001, NFR-004, NFR-005
- **Affected surfaces**: `scripts/openclaw/heartbeat_gate/gate.py`, `run.py` (step 2
  call site + CLI parser), `tests/test_gate_routing.py`, `tests/test_run.py`
- **Sequencing/depends-on**: none
- **Risks**: keep `run.py` steps 1/3/4 and the fail-safe byte-for-byte behavioral;
  the deterministic path never imports `anthropic`. **Codex #2**: `decide_deterministic`
  must be **total** over any `GateContext` `load_context` can produce, and/or broaden
  `run.py` step-2 `except` to `Exception` → fallback (else an impl error hits the
  exit-1 emergency path, violating FR-007) — ship a malformed-context fail-safe test.
  **Codex #7**: fully remove `--api-key`/`--prompt` (no vestigial no-op flags), update
  ALL affected tests, and smoke the installed `ExecStart`. **Codex #8**: escalation
  `reason` must cite triggers with no action/recommendation framing.

### IC-02 — Validate the rule against history (INV-006)

- **Purpose**: Ship the ledger-replay harness that asserts 0 missed escalations and
  reports over-escalation, run against the live ledger and a committed fixture.
- **Relevant requirements**: FR-011, NFR-006, SC-005
- **Affected surfaces**: `scripts/openclaw/heartbeat_gate/validate_ledger.py`, a
  committed fixture ledger, synthetic `GateContext` fixtures, `tests/`
- **Sequencing/depends-on**: IC-01 (needs `decide_deterministic`)
- **Risks (Codex #3/#4)**: the **live ledger replay validates the escalate-vs-not
  boolean ONLY** (ledger lacks `issues_filed`/per-signal counts) — do not claim it
  proves the 3-label split. Validate `LOG_AND_SKIP`↔`HEARTBEAT_OK` via **synthetic
  `GateContext` fixtures** (issues_filed non-empty; below-but-nonzero activity; fully
  quiet). Keep the live replay result (0 missed / 0 over) reproducible.

### IC-03 — Move the health-check off the Sonnet agent

- **Purpose**: New `felix-health-check` systemd user timer+service+wrapper that execs
  the existing bash check and alerts on failure via ntfy; remove the two openclaw
  `health-check-*` crons.
- **Relevant requirements**: FR-009, FR-010, NFR-002
- **Affected surfaces**: `scripts/office2/felix-health-check.{service,timer}` +
  `scripts/office2/deploy/`, new wrapper script, `openclaw cron` removal (2 crons),
  wrapper tests
- **Sequencing/depends-on**: none (parallel to IC-01)
- **Risks**: delivery channel change WhatsApp → ntfy (flagged for Kent). **Codex #1**:
  run the check via `subprocess` (NOT `exec`); a missing script AND an ntfy-send
  failure must each alert/log (not rely on systemd-failed alone). **Codex #9**:
  classification precedence = `FAILURES_DETECTED` wins over `ALL_HEALTHY`; handle
  both-token / stderr-only / non-zero+ALL_HEALTHY / oversized-output (truncation).
  **Codex #5**: acceptance must operator-visibly verify the ntfy push is received with
  full output. Timer `OnCalendar` matches 11:00/23:00.

### IC-04 — Deploy, docs, rebaseline

- **Purpose**: One deploy manifest for the systemd unit + wrapper and the cron
  removal; update architecture docs; record rebaseline.
- **Relevant requirements**: FR-012, FR-013, C-002, C-003
- **Affected surfaces**: `deploys/queued/<NNNN>-deterministic-monitoring-checks.yaml`,
  `docs/design/architecture/data/service-inventory.json` (+ md), `AGENT-REGISTRY.md`,
  merge-commit rebaseline line
- **Sequencing/depends-on**: IC-01, IC-03 (deploys their outputs)
- **Risks**: resolve whether `openclaw cron remove` rides the felix-deployer happy
  path or is out-of-band manual (research R7 open sub-question); rebaseline covers both
  systemd units and openclaw config. **Codex #6 (deploy order)**: to avoid double-alert
  or missed-check windows around 11:00/23:00 — install wrapper+unit → manual smoke →
  enable timer → `systemctl --user list-timers` verify → remove the 2 crons via CLI →
  confirm no health-check cron remains. Rollback re-adds the crons.

---

**Branch contract (restated)**: current branch `feat/deterministic-monitoring-checks`;
planning/base branch `feat/deterministic-monitoring-checks`; final merge target
`feat/deterministic-monitoring-checks` (then `feat → main` as a separate post-merge
step gated by the mandatory post-merge Codex review). `branch_matches_target = true`.

**Next suggested command**: `/spec-kitty.tasks` (after the mandatory post-plan Codex review).
