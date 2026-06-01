# Implementation Plan — Signal-Driven Monitoring with Haiku Gate

**Mission**: `signal-driven-monitoring-haiku-gate-01KT22PC`
**Source issue**: [#490](https://github.com/kentonium3/kg-automation/issues/490)
**Spec**: [`spec.md`](./spec.md)
**Research**: [`research.md`](./research.md)
**Data model**: [`data-model.md`](./data-model.md)
**Contracts**: [`contracts/`](./contracts/)
**Quickstart**: [`quickstart.md`](./quickstart.md)

---

## Branch contract

- **Current branch at plan start**: `main`
- **Planning base branch**: `main`
- **Merge target branch**: `main`
- **`branch_matches_target`**: true

(Restated per /spec-kitty.plan §"Branch Strategy Confirmation".)

---

## Summary

Replace Felix's general-purpose Sonnet heartbeat with a two-layer observation pipeline. Loop 1 (signal extraction) extends `felix-core-digest` with deterministic, zero-LLM signal extraction from OpenClaw logs and threshold-driven issue filing via the existing `felix-file-issue.py` body builder. Loop 2 (heartbeat gate) is a new Python driver invoked by its own systemd timer; it inspects the latest signal-extraction output + HEARTBEAT.md, decides routing via a cached Haiku call, and only invokes Sonnet via `openclaw system event --mode now` on novel/ambiguous signal. Architecture mirrors `felix-doc-auditor` post-#343 exactly: stateless Python oneshots, structured health signals, JSONL ledgers, Anthropic SDK direct.

---

## Technical Context

**Language/Version**: Python 3.11+ (matches kg-automation project standard; office2 has 3.12 installed).
**Primary Dependencies**: `anthropic` SDK (already deployed for felix-doc-auditor), `tomli`/`tomllib` (stdlib in 3.11+), `gh` CLI (already deployed), `openclaw` CLI (already deployed).
**Storage**:
- Source data: `/tmp/openclaw/openclaw-*.log` (OpenClaw's existing rotating log path).
- Runtime state: `/data/services/openclaw/felix-core-digest-signals/` and `/data/services/openclaw/felix-heartbeat-gate/` (new directories, parallel to `felix-doc-auditor-driver/`).
- GitHub (issues, labels) as the canonical persistence layer for outcomes.

**Testing**: pytest + pytest-cov. Mirrors `scripts/doc_audit/` conventions. Target ≥85% line / ≥80% branch coverage on new modules. `# pragma: no branch` allowed on defensive checks per existing project pattern.

**Target Platform**: office2 (Ubuntu 24.04 LTS) as the `claude` user. systemd user timers (`--user`).

**Project Type**: Single project — extends existing `scripts/openclaw/observation/` package and adds a new `scripts/openclaw/heartbeat_gate/` package within the same repo.

**Performance Goals**:
- Signal-extraction tick: complete in <5s for a normal day's log size.
- Gate tick: complete in <3s for the Haiku call (cached prompt). <500ms overhead beyond the API call.

**Constraints**:
- Cycle floor: 15 min for signal extraction (existing felix-core-digest cadence).
- Gate cadence: 30 min (matches historical heartbeat cadence).
- No new credentials (reuse `kg-felix-bot` PAT + existing Anthropic API key at `/data/services/openclaw/secrets/anthropic`).
- No OpenClaw upstream changes (C-003).

**Scale/Scope**:
- 3–4 initial signal definitions; expected 5–10 within a few months as patterns emerge.
- ≤5 deterministic issue filings/day expected at steady state (per spec NFR-006 implicit).
- 48 gate ticks/day × ≤5 Sonnet escalations/day expected (per cost model in `research.md`).

---

## Charter Check

*Gate evaluated before Phase 0 research; re-evaluated after Phase 1 design.*

| Check | Result |
|---|---|
| Branch contract matches target | ✅ PASS — current/base/target all `main`. |
| Charter governance loaded | ⚠ WARN — tool-registry mismatch (`pytest`/`python` missing from spec-kitty `DEFAULT_TOOL_REGISTRY`). Known limitation, deferred per `project_charter_tool_registry_mismatch` memory; does not block. |
| No unresolved `[NEEDS CLARIFICATION]` markers in spec | ✅ PASS — OD-1, OD-2, OD-3 all resolved in `research.md`. |
| All FRs and NFRs have measurable acceptance criteria | ✅ PASS — see spec §3, §4, §6 and the per-NFR thresholds. |
| Architecture-impact section identifies affected JSON files | ✅ PASS — `service-inventory.json`, `credential-manifest.json`, `data-flows.json`. |
| Change-risk tier classified before implementation | ✅ PASS — spec §11; planner refined in §"Change-risk tier classification" below. |
| Test strategy committed | ✅ PASS — `research.md` §"Test strategy". |
| Identity for autonomous filings | ✅ PASS — `kg-felix-bot`, no new credential. |
| Bulk-edit check | ✅ PASS — `change_mode: regular` in meta.json. |
| Constitutional Compliance (autonomy / scope / failure / privacy / Directive 6) | ✅ PASS — spec §12. |
| Felix-Constitution Two-Constitutions principle | ✅ PASS — operates under Felix Constitution (project), spec-kitty governs the workflow only. |

No gate failures. Charter Check re-evaluated post-Phase 1: same result.

---

## Project Structure

### Documentation (this mission)

```
kitty-specs/signal-driven-monitoring-haiku-gate-01KT22PC/
├── plan.md                              # This file
├── spec.md                              # Mission specification
├── research.md                          # Phase 0 — OD resolutions and design rationale
├── data-model.md                        # Phase 1 — entities (E1–E4)
├── quickstart.md                        # Phase 1 — operator + extender quickstart
├── contracts/
│   ├── signal-config.contract.md        # TOML schema for signals/config.toml
│   ├── tick-signal.contract.md          # last-tick.json schema
│   ├── gate-decision.contract.md        # last-gate-decision.json schema
│   └── filer-invocation.contract.md     # filer ↔ felix-file-issue.py subprocess contract
├── meta.json
├── checklists/requirements.md
└── tasks/                               # Created by /spec-kitty.tasks (not now)
```

### Source code (kg-automation repo)

```
scripts/openclaw/observation/            # EXISTING package — extended
├── summarize.py                         # UNCHANGED
├── config.py                            # UNCHANGED
├── log_action.py                        # UNCHANGED
├── tick.py                              # NEW — entrypoint orchestrating signal extraction + filing
├── state.py                             # NEW — per-signal counter persistence (E2)
├── filer.py                             # NEW — invokes felix-file-issue.py per contract
├── signals/                             # NEW package
│   ├── __init__.py
│   ├── config.toml                      # NEW — signal definitions (E1, seed values per OD-2)
│   ├── config_loader.py                 # NEW — TOML loader + validation
│   ├── openclaw_log.py                  # NEW — shared log-tail + grep helpers
│   ├── creds_restore.py                 # NEW — FR-006 signal #1
│   ├── watchdog_reconnect.py            # NEW — FR-006 signal #2
│   └── unhandled_error.py               # NEW — FR-006 signal #3
└── tests/                               # EXTENDED
    ├── test_state_persistence.py        # NEW
    ├── test_signals_creds_restore.py    # NEW
    ├── test_signals_watchdog_reconnect.py # NEW
    ├── test_signals_unhandled_error.py  # NEW
    ├── test_filer.py                    # NEW — mocks felix-file-issue.py subprocess
    ├── test_tick_orchestrator.py        # NEW
    ├── test_replay_20260601.py          # NEW — integration test against captured log
    └── fixtures/
        ├── creds_restore.jsonl
        ├── watchdog_reconnect.jsonl
        ├── unhandled_error.jsonl
        └── captured/openclaw-2026-06-01.log  # NEW — checked-in replay artifact

scripts/openclaw/heartbeat_gate/         # NEW package
├── __init__.py
├── gate.py                              # NEW — entrypoint
├── context.py                           # NEW — assembles digest + HEARTBEAT.md + novelty
├── escalator.py                         # NEW — invokes `openclaw system event --mode now`
├── ledger.py                            # NEW — gate-ledger.jsonl writer
├── prompts/
│   └── routing.prompt.md                # NEW — cache-aware prompt for Haiku routing
└── tests/
    ├── test_gate_no_signal.py
    ├── test_gate_with_signal.py
    ├── test_gate_heartbeat_md_tasks.py
    ├── test_gate_fallback_on_api_failure.py
    └── test_escalator.py                # mocks `openclaw system event`

scripts/office2/                         # EXTENDED
├── felix-core-digest.service            # MODIFIED — runs tick.py after summarize.py
├── felix-core-digest.timer              # UNCHANGED (15 min cadence)
├── felix-heartbeat-gate.service         # NEW
└── felix-heartbeat-gate.timer           # NEW (30 min cadence)

docs/design/architecture/data/           # EXTENDED per spec §10
├── service-inventory.json               # MODIFIED — entries for new services
├── credential-manifest.json             # MODIFIED — confirm kg-felix-bot scope
└── data-flows.json                      # MODIFIED — add new flows
+ corresponding *.view.md regeneration

docs/design/architecture/baselines/
└── felix-heartbeat-gate-pre-rollout.json # NEW — token baseline for NFR-001 validation
```

**Structure Decision**: Single-project layout. The mission extends two existing in-repo packages (`scripts/openclaw/observation/`) and adds one new package (`scripts/openclaw/heartbeat_gate/`). Both are pure Python with no separate build system. Deployment uses the existing repo→office2 deploy script (no new infra).

---

## Phase 0 — Research outputs

See [`research.md`](./research.md). Summary:

- **OD-1 resolved**: wrapper-based gate driver (no per-invocation OpenClaw model switch exists). Disable OpenClaw heartbeat; new systemd timer fires our gate; gate invokes `openclaw system event --mode now` on escalation.
- **OD-2 resolved**: seed thresholds 6/18 (creds_restore), 10/25 (watchdog_reconnect), 3/5 (unhandled_error). Calibrated against 2026-06-01 log; would have fired 3–5 times on the actual corruption pattern, never during quiet hours.
- **OD-3 resolved**: live filing from day one (Kent's plan-phase input).
- **Architecture pattern adoption**: full mirror of `felix-doc-auditor` post-#343 — stateless Python driver, Anthropic SDK direct, structured `last-tick.json`, JSONL ledger.
- **Cost estimate**: ~$0.55–1.60/day post-rollout, baseline ~$3–7/day. Achievable ≥80% reduction per NFR-001 if Sonnet escalations stay ≤5/day.
- **Loose periodic checks**: confirmed not active today (`HEARTBEAT.md` is template-only); no migration burden.

---

## Phase 1 — Design outputs

### Data model

See [`data-model.md`](./data-model.md). Four entities:
- **E1** Signal definition (config-time, in repo)
- **E2** Signal state (runtime persistent, per-signal file)
- **E3** Cycle record (runtime transient + ledger)
- **E4** Heartbeat gate decision (runtime transient + ledger)

### Contracts

| Contract | Purpose |
|---|---|
| [`contracts/signal-config.contract.md`](./contracts/signal-config.contract.md) | TOML schema for `signals/config.toml`; validation; seed configuration; hot-reload behavior. |
| [`contracts/tick-signal.contract.md`](./contracts/tick-signal.contract.md) | JSON schema for `last-tick.json`; health-check semantics; atomicity. |
| [`contracts/gate-decision.contract.md`](./contracts/gate-decision.contract.md) | JSON schema for `last-gate-decision.json`; outcome semantics; fallback (FR-011). |
| [`contracts/filer-invocation.contract.md`](./contracts/filer-invocation.contract.md) | Subprocess contract for `felix-file-issue.py` invocation; tempfile lifecycle; output parsing; error handling. |

### Quickstart

See [`quickstart.md`](./quickstart.md). Covers health check, manual ticks, adding/tuning signals, disable/re-enable, issue investigation, gate auditing, cost math.

---

## Architecture overview

```
┌────────────────────────────────────────────────────────────────────────┐
│ office2 (Ubuntu 24.04 LTS, claude user)                                │
│                                                                        │
│  ┌────────────────────────────┐    ┌──────────────────────────────┐    │
│  │ felix-core-digest.timer    │    │ felix-heartbeat-gate.timer   │    │
│  │   (every 15 min)           │    │   (every 30 min)             │    │
│  └────────────┬───────────────┘    └────────────┬─────────────────┘    │
│               │                                 │                      │
│               ▼                                 ▼                      │
│  ┌────────────────────────────┐    ┌──────────────────────────────┐    │
│  │ tick.py (NEW)              │    │ gate.py (NEW)                │    │
│  │  ├─ signals/*.py (NEW)     │    │  ├─ context.py (NEW)         │    │
│  │  │  read /tmp/openclaw/*   │    │  │  read last-tick.json +    │    │
│  │  │  count matches          │    │  │  HEARTBEAT.md             │    │
│  │  ├─ state.py (NEW)         │    │  ├─ Haiku via Anthropic SDK  │    │
│  │  │  per-signal counters    │    │  │  (cache-aware prompt)     │    │
│  │  └─ filer.py (NEW)         │    │  └─ escalator.py (NEW)       │    │
│  │     subprocess →           │    │     openclaw system event    │    │
│  │     felix-file-issue.py    │    │     --mode now --text "..."  │    │
│  └────────────┬───────────────┘    └────────────┬─────────────────┘    │
│               │                                 │                      │
│               ▼                                 ▼                      │
│  ┌────────────────────────────┐    ┌──────────────────────────────┐    │
│  │ last-tick.json             │    │ last-gate-decision.json      │    │
│  │ signals-ledger.jsonl       │    │ gate-ledger.jsonl            │    │
│  │ state/<signal>.json        │    │                              │    │
│  └────────────────────────────┘    └──────────────────────────────┘    │
│                                                                        │
│  ┌──────────────────────────────────────────────────────────────────┐  │
│  │ openclaw gateway (existing; config modified)                     │  │
│  │  - heartbeat scheduler: DISABLED via `openclaw system heartbeat  │  │
│  │    disable` (replaced by felix-heartbeat-gate.timer)             │  │
│  │  - main agent: UNCHANGED, still claude-sonnet-4-6                │  │
│  │  - waked by `openclaw system event --mode now` from gate on      │  │
│  │    escalation                                                    │  │
│  └──────────────────────────────────────────────────────────────────┘  │
│                                                                        │
│  ┌──────────────────────────────────────────────────────────────────┐  │
│  │ felix-file-issue.py (existing, UNCHANGED)                        │  │
│  │  ↑ called by NEW filer.py (deterministic path)                   │  │
│  │  ↑ existing callers: main agent (LLM path)                       │  │
│  │  Verifies kg-felix-bot identity; builds template-compliant body  │  │
│  └──────────────────────────────────────────────────────────────────┘  │
└────────────────────────────────────────────────────────────────────────┘
                              │
                              ▼
                  GitHub issues @ kentonium3/kg-automation
                  (filed by kg-felix-bot)
```

**Key properties**:
- Two independent loops; neither blocks the other.
- Signal extraction is fully deterministic — no LLM in the file-issue path.
- Gate is the only LLM-touching new code (Haiku for routing).
- Sonnet escalation reuses the existing OpenClaw main-agent path verbatim — wake mechanism changes (event-driven), agent code does not.
- `felix-file-issue.py` is unchanged; we add one new caller.

---

## Change-risk tier classification (refined from spec §11)

| Component | Tier | Plan-time confirmation |
|---|---|---|
| Python signal extractor + filer (new code in repo) | Tier 3 | Dry-run / replay validation via `tests/fixtures/captured/openclaw-2026-06-01.log` before deploy. |
| Heartbeat gate driver (new code in repo) | Tier 3 | Mocked unit tests + manual `--dry-run` invocation before enabling timer. |
| New systemd units (`felix-heartbeat-gate.service/.timer`) | Tier 3 (logic) + Tier 2 at first deploy (state dir creation) | Confirm Restic backup currency before first deploy of new state directories. |
| OpenClaw heartbeat disable (`openclaw system heartbeat disable`) | Tier 2 | Snapshot `~/.openclaw/openclaw.json` before; verify `openclaw system heartbeat last` shows the disable took effect. |
| `service-inventory.json` / `credential-manifest.json` / `data-flows.json` updates | Tier 4 (auto-commit) | Standard CLAUDE.md update protocol, `updated_by: #490`. |
| Markdown view regeneration | Tier 4 | Automated by existing scripts. |

No Tier 0 changes expected. If one surfaces (e.g., gh PAT scope change), generate script + present to Kent per CLAUDE.md absolute rule.

---

## Open items for /spec-kitty.tasks (work-package planning hints)

These are NOT unresolved spec ambiguities — they are suggestions for the next phase:

1. **Suggested WP boundaries** (5 WPs, sequential):
   - **WP-01** — Signal-extraction core: `signals/` package, `state.py`, `tick.py` orchestrator, fixtures. No filing yet. Unit tests + state-persistence tests green.
   - **WP-02** — Deterministic filer: `filer.py`, contract integration test against `felix-file-issue.py --dry-run`. Tick orchestrator wires in filer.
   - **WP-03** — Replay integration test: capture `/tmp/openclaw/openclaw-2026-06-01.log` into fixtures, run full pipeline, assert NFR-004/NFR-006 satisfied.
   - **WP-04** — Heartbeat gate: `gate.py`, `context.py`, `escalator.py`, prompt, ledger; full unit + behavioral tests.
   - **WP-05** — Deployment: architecture docs update, systemd units deployed, OpenClaw heartbeat disabled, pre-rollout baseline captured, post-deploy monitoring window opens.

2. **WP dependency chain**:
   - WP-02 needs WP-01's state model and filer signature.
   - WP-03 needs WP-01 + WP-02 deployed *on the mission lane* (not merged to main).
   - WP-04 needs WP-03's `last-tick.json` format pinned (frozen in contract).
   - WP-05 deploys everything; requires all prior WPs on the lane.

3. **Single mission, no split** (per Kent's specify-phase decision). FR-2's gate consumes FR-1's `last-tick.json` format which solidifies during WP-01/WP-03 — that's the spec's load-bearing single-mission assumption (A5).

4. **Implementer prompt guidance** (per `feedback_wp_prompts_grep_codebase`): WP prompts must direct the implementer to grep `scripts/doc_audit/` for the precedent patterns rather than describing them in prose. The implementer should read `scripts/doc_audit/run.py`, `scripts/doc_audit/config.py`, and `scripts/doc_audit/judgment/tier_classification.py` as their style guide.

---

## Branch contract (restated)

- **Current branch**: `main`
- **Planning base**: `main`
- **Merge target**: `main`
- **`branch_matches_target`**: true

Completed changes from this mission merge into `main` via spec-kitty merge commit (not PR).

---

## ⛔ STOP

Per the /spec-kitty.plan mandatory stop, this command ends here. **Do not generate `tasks.md` or work-package files.** Operator runs `/spec-kitty.tasks` when ready.

**Generated artifacts**:
- `plan.md` (this file)
- `research.md`
- `data-model.md`
- `contracts/signal-config.contract.md`
- `contracts/tick-signal.contract.md`
- `contracts/gate-decision.contract.md`
- `contracts/filer-invocation.contract.md`
- `quickstart.md`

**Next suggested command**: `/spec-kitty.tasks`
