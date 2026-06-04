# Implementation Plan: Felix-Vikunja Sync Reconciliation Driver

**Branch**: `main` (planning + final merge target) | **Date**: 2026-06-04 | **Spec**: [spec.md](./spec.md)
**Input**: Feature specification from `kitty-specs/felix-vikunja-sync-reconciliation-driver-01KTA1J3/spec.md`

## Summary

Build the foundational reconciliation driver of the Felix↔Vikunja sync architecture (ADR-0003). A deterministic, one-shot Python script invoked by a systemd user timer at 5-minute cadence executes the 6-phase reconciliation cycle (fetch → diff → classify → emit → update → complete) against the status and task layers. Detected divergences flow through the four unsafe-class criteria (UC-1 through UC-4 per RQ-3), with unsafe events emitted to a 15-field append-only conflict log and delivered to the operator's WhatsApp via the established deterministic OpenClaw send pattern. Project-layer reconciliation, touchpoint migration, and existing-callsite cutover are out of scope (tracked as #519, #520).

Engineering approach (operator-confirmed during planning interrogation, 2026-06-04):

- **Process model**: one-shot timer-fired script. Mirror the established `felix-doc-auditor-driver` and `felix-heartbeat-gate` precedent. Process dies between ticks. Restartable without state coordination. Operator priority is operational reliability; refactor to daemon later if cadence or state requirements push that way.
- **WhatsApp delivery**: deterministic-script invocation of `openclaw agent --agent main --deliver --channel whatsapp --to <num>` (same pattern as `scripts/obsidian/sync-heartbeat.py`). No new helper or agent needed. Phase 0 research probe confirmed the path exists — assumption A-3 holds.
- **Vikunja authorship signal**: Vikunja v0.24.6 returns `updated_by: null` on `GET /tasks/{id}`. UC-1 and UC-2 cannot rely on a direct Vikunja author field; both collapse to "divergence from the driver's expected value" detected via the driver's own value cache. See `research.md` § Authorship Inference for details.

## Technical Context

**Language/Version**: Python 3.12 (Ubuntu 24.04 LTS on office2; matches existing Felix Python driver runtime)

**Primary Dependencies**: Standard library only — `urllib.request` (Vikunja HTTP), `subprocess` (openclaw CLI), `json`, `pathlib`, `argparse`. No third-party packages introduced. Matches `felix-doc-auditor-driver` and `record_completion.py` precedent.

**Storage**:
- Append-only JSONL conflict-event log at `/data/services/openclaw/state/sync/conflict-events.jsonl`
- Per-tick health record (overwrite-on-success) at `/data/services/openclaw/state/sync/last-tick.json`
- Per-layer freshness pointers + Felix-side value cache at `/data/services/openclaw/state/sync/freshness.json` and `/data/services/openclaw/state/sync/task-cache.json`
- Reads credential from `/data/services/openclaw/secrets/vikunja-api` (mode 0600, `claude:felix`)

**Testing**: Mock-based unit tests under `tests/sync/` mirroring the `tests/habits/test_record_completion.py` pattern. Mocked Vikunja HTTP via `urllib.request.urlopen` patching; mocked `subprocess.run` for the openclaw send call. No live integration tests (per memory `feedback_no_live_integration_tests`). Operational SC verification (SC-001 through SC-009) runs manually on office2 post-merge.

**Target Platform**: office2 (Ubuntu 24.04 LTS, Tailscale-gated). Driver runs as `claude` user, invoked by systemd user timer. No sudo required.

**Project Type**: single project (Python scripts + tests; no frontend or mobile).

**Performance Goals**: Single cycle completes in ≤5 seconds at current Felix scale (≤20 active tasks, ≤20 projects). Driver startup overhead amortizes to ~10% of cycle time at 5-min cadence — acceptable per the operator's "operational reliability over efficiency" planning decision.

**Constraints**:
- Polling-only (C-001); no webhooks
- Vikunja wins all conflicts (C-002); driver never writes to Vikunja
- WhatsApp ping volume ≤1/day under steady state (NFR-002) after G-1/G-2/G-3 guards
- ≤5 min convergence latency (NFR-001)
- Driver privacy boundary: tasks routed through `02-Growth/_private/` are logged only by integer `task.id`, never by title or field content

**Scale/Scope**:
- Source files: ~6 new Python modules under `scripts/sync/`
- Test files: ~3 new test modules under `tests/sync/`
- New systemd unit + timer in `~/.config/systemd/user/` (deployed manually post-merge)
- Approximate LOC: 800-1200 (driver) + 600-1000 (tests)

## Charter Check

The project charter at `.kittify/charter/` carries a known "governance unresolved" diagnostic about `pytest`/`python` not being in spec-kitty's built-in tool registry (memory `project_charter_tool_registry_mismatch`). This mission inherits that condition and does not resolve it. No new charter conflicts introduced by this mission's planning artifacts.

**Status**: charter check passes for this mission's scope.

## Project Structure

### Documentation (this feature)

```
kitty-specs/felix-vikunja-sync-reconciliation-driver-01KTA1J3/
├── plan.md                       # This file
├── spec.md                       # Feature specification
├── research.md                   # Phase 0 — research findings (3 unknowns resolved + Authorship Inference)
├── data-model.md                 # Phase 1 — entities + their relationships
├── quickstart.md                 # Phase 1 — operator quickstart commands
├── contracts/
│   ├── cycle-pipeline.md         # The 6-phase contract (fetch → ... → complete)
│   ├── conflict-event-schema.md  # The 15-field event record schema
│   ├── whatsapp-send.md          # Deterministic-callable WhatsApp send contract
│   └── state-directory.md        # On-disk layout under /data/services/openclaw/state/sync/
├── meta.json                     # Mission identity + branch contract
├── checklists/requirements.md    # Spec quality checklist (all pass)
├── status.events.jsonl           # Spec-kitty workflow event log
└── tasks/                        # Populated by /spec-kitty.tasks (NOT this command)
```

### Source Code (repository root)

```
scripts/
├── sync/                                # NEW — this mission's primary deliverable
│   ├── __init__.py
│   ├── driver.py                        # One-shot tick entry point (CLI + cycle orchestration)
│   ├── cycle.py                         # 6-phase pipeline implementation
│   ├── fetch.py                         # Vikunja delta poll (updated_since + per-task/per-project GETs)
│   ├── diff.py                          # Value-comparison between Vikunja and Felix's cache
│   ├── classify.py                      # UC-1..UC-4 classification (collapses UC-1/UC-2 per research finding)
│   ├── emit.py                          # Conflict-event log append + WhatsApp delivery dispatch
│   ├── guards.py                        # G-1 (24h dedup), G-2 (post-write suppression), G-3 (daily cap)
│   ├── state.py                         # Freshness pointers, task cache, per-tick health record I/O
│   ├── http.py                          # urllib wrapper (timeout + retry policy + structured errors)
│   └── send_whatsapp.py                 # subprocess wrapper for the openclaw deterministic send
├── habits/                              # Existing; unchanged
├── security/credential_health_check/    # Existing precedent for driver shape
└── obsidian/sync-heartbeat.py           # Existing precedent for openclaw CLI WhatsApp send

tests/
└── sync/                                # NEW — mock-based unit tests
    ├── __init__.py
    ├── test_driver.py                   # End-to-end tick invocations with mocked I/O
    ├── test_cycle.py                    # Per-phase contract tests
    ├── test_classify.py                 # UC-1..UC-4 classification matrix
    ├── test_guards.py                   # G-1/G-2/G-3 boundary cases
    └── test_send_whatsapp.py            # subprocess mock + error-path verification

# Deployment artifacts (NOT committed; manually deployed to office2 post-merge per project_deployment_strategy)
~/.config/systemd/user/
├── felix-vikunja-sync.service
└── felix-vikunja-sync.timer
```

**Structure Decision**: Single project (Option 1 in the template). All new code lives under `scripts/sync/` and `tests/sync/`. Matches the precedent established by `scripts/habits/`, `scripts/security/credential_health_check/`, and `scripts/openclaw/heartbeat_gate/`. No source-code restructuring of existing directories.

## Complexity Tracking

*No charter violations to justify.*

The mission stays within the established Felix Python-driver shape (timer-fired script, JSONL state log, openclaw CLI for WhatsApp). The one notable design choice — collapsing UC-1 and UC-2 into a single "divergence from driver cache" check — is a research-grounded simplification, not a complexity addition.

| Complexity | Why Needed | Simpler Alternative Rejected Because |
|------------|------------|--------------------------------------|
| None | — | — |
