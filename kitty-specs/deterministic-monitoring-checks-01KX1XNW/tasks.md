# Tasks: Deterministic Monitoring Checks

**Mission**: deterministic-monitoring-checks-01KX1XNW · **Branch**: `feat/deterministic-monitoring-checks`
**Spec**: [spec.md](./spec.md) · **Plan**: [plan.md](./plan.md) · **Contracts**: [escalation-rule](./contracts/escalation-rule.contract.md), [health-check-runner](./contracts/health-check-runner.contract.md)

Tests ARE in scope (the spec explicitly demands INV-006 validation, the fail-safe test,
synthetic label fixtures, and the health-check test matrix).

## Subtask Index

| ID | Description | WP | Parallel |
|---|---|---|---|
| T001 | Implement `decide_deterministic(context)` (boolean rule + label split, stdlib-only, total) | WP01 | | [D] |
| T002 | Deterministic `build_reason(context)` (cite triggers, ≤500, no action framing) | WP01 | | [D] |
| T003 | Rewire `run.py` step 2 → deterministic decide; broaden step-2 `except`→fallback | WP01 | | [D] |
| T004 | Remove `--api-key`/`--prompt` + `anthropic` from the tick path (no vestiges) | WP01 | | [D] |
| T005 | Update `test_gate_routing.py` + `test_run.py` (deterministic + malformed→fallback) | WP01 | | [D] |
| T006 | Retire/neutralize the routing prompt + measure-tokens LLM baseline if now dead | WP01 | | [D] |
| T007 | Implement `validate_ledger.py` (replay; assert 0 missed; report over-escalation %) | WP02 | | [D] |
| T008 | Commit a fixture `gate-ledger.jsonl` (escalate + both non-escalate labels) | WP02 | [D] |
| T009 | Synthetic `GateContext` fixtures + tests for the 3-label split | WP02 | | [D] |
| T010 | Test `validate_ledger` against the fixture; wire into pytest | WP02 | | [D] |
| T011 | Health-check wrapper (subprocess, precedence, signal file, ntfy, truncation) | WP03 | | [D] |
| T012 | `felix-health-check.service` (mirrors credential-health-check.service) | WP03 | [D] |
| T013 | `felix-health-check.timer` (OnCalendar 11:00 + 23:00) | WP03 | [D] |
| T014 | Deploy script `scripts/office2/deploy/felix-health-check.sh` (+ preflight) | WP03 | | [D] |
| T015 | Wrapper test matrix (both-token / stderr / non-zero+healthy / missing / truncation / ntfy-fail) | WP03 | | [D] |
| T016 | Author `deploys/queued/deterministic-monitoring-checks.yaml` manifest | WP04 | | [D] |
| T017 | Resolve cron-removal path (felix-deployer happy-path vs out-of-band) + encode | WP04 | | [D] |
| T018 | Update `service-inventory.json` (+ md view); `updated_by=676` | WP04 | [D] |
| T019 | Review/update `AGENT-REGISTRY.md` for main's reduced scheduled workload | WP04 | [D] |
| T020 | Record rebaseline obligation (systemd units + openclaw config) in deploy notes | WP04 | | [D] |

## Work Packages

### WP01 — Determinize the heartbeat-gate decision  → [tasks/WP01-determinize-gate.md](./tasks/WP01-determinize-gate.md)
- **Goal / priority**: Replace the Haiku `gate.decide` call with a pure, stdlib-only
  `decide_deterministic` that reproduces the routing prompt's boolean escalation
  contract and emits a deterministic reason + zeroed tokens. **MVP core.**
- **Independent test**: `pytest scripts/openclaw/heartbeat_gate/tests/` green; a
  `--dry-run` tick prints `tokens=in:0(cache:0)/out:0`; malformed-context tick →
  `fallback_invoked=true`, exit 0.
- **Subtasks**: T001–T006 · **Dependencies**: none · **Est.**: ~380 lines

### WP02 — Ledger-replay + synthetic-fixture validation (INV-006)  → [tasks/WP02-validate-ledger.md](./tasks/WP02-validate-ledger.md)
- **Goal / priority**: Ship the INV-006 forcing function: replay the escalation rule
  over a gate-ledger and assert 0 missed; validate the label split via synthetic
  fixtures.
- **Independent test**: `python3 -m scripts.openclaw.heartbeat_gate.validate_ledger
  --ledger <fixture>` → `MISSED escalations: 0`; label fixtures pass.
- **Subtasks**: T007–T010 · **Dependencies**: WP01 · **Est.**: ~260 lines

### WP03 — Health-check off the Sonnet agent  → [tasks/WP03-health-check-off-agent.md](./tasks/WP03-health-check-off-agent.md)
- **Goal / priority**: New `felix-health-check` systemd user timer + wrapper that execs
  the existing bash check via subprocess and ntfy-alerts on failure; parity with the
  `credential-health-check` precedent.
- **Independent test**: `systemctl --user start felix-health-check.service` runs the
  check with no main session; forced `FAILURES_DETECTED` produces an ntfy push; wrapper
  test matrix green.
- **Subtasks**: T011–T015 · **Dependencies**: none (parallel to WP01) · **Est.**: ~420 lines

### WP04 — Deploy manifest + architecture docs + rebaseline  → [tasks/WP04-deploy-docs-rebaseline.md](./tasks/WP04-deploy-docs-rebaseline.md)
- **Goal / priority**: One deploy manifest (systemd units + wrapper + cron removal),
  architecture-doc sync, and the rebaseline record.
- **Independent test**: manifest passes `deploys/schema/manifest-v1.schema.json`;
  `validate_architecture_data.py` green; AGENT-REGISTRY reflects the workload change.
- **Subtasks**: T016–T020 · **Dependencies**: WP01, WP03 · **Est.**: ~300 lines

## Dependencies (summary)

```
WP01 ─┐
      ├─► WP04 (deploy + docs)
WP03 ─┘
WP01 ─► WP02 (needs decide_deterministic)
```

- **MVP**: WP01 (the deterministic gate) + WP02 (proves it). WP03 is independent and
  parallelizable. WP04 lands last (deploys WP01+WP03 outputs).
- Parallel opportunity: WP01 and WP03 have no shared files and can run concurrently.
