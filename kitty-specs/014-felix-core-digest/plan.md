# Implementation Plan: Felix Core Digest

**Branch**: `main` | **Date**: 2026-04-04 | **Spec**: [spec.md](spec.md)
**Input**: Feature specification from `kitty-specs/014-felix-core-digest/spec.md`

## Summary

Replace the fragile Markdown-regex log parsing architecture with a
deterministic JSONL pipeline: `log_action.py` (CLI log writer) →
per-agent JSONL files → rewritten `summarize.py` (JSONL parser) →
per-agent Markdown digests in Obsidian. Deploy on a 15-minute systemd
timer on office2 under the `claude` account.

**Critical research finding**: OpenClaw agents CAN call external Python
scripts via the `exec` tool (see [research.md](research.md) R1). The
primary path — agents calling `python log_action.py` as a subprocess —
is confirmed viable. No fallback path needed.

## Technical Context

**Language/Version**: Python 3 (office2 system Python)
**Primary Dependencies**: Python standard library only (json, argparse, pathlib, datetime)
**Storage**: JSONL files (append-only); Markdown files (generated digests)
**Testing**: pytest (existing test framework in `scripts/openclaw/observation/tests/`)
**Target Platform**: Linux (Ubuntu 24.04 on office2)
**Project Type**: Single project — extends existing observation module
**Performance Goals**: < 100ms per log write; < 10s for full daily digest
**Constraints**: No sudo on `claude` account; stdlib-only for log_action.py
**Scale/Scope**: 3 agents, ~50-100 log entries/day, 5-day digest retention

## Constitution Check

*GATE: Must pass before Phase 0 research. Re-check after Phase 1 design.*

- **Paradigm: test-first** — PASS. All new code (log_action.py, JSONL
  parsing, retention logic) requires tests before implementation. Existing
  test fixtures are mapped to JSONL equivalents before Markdown fixtures
  are deleted.
- **Directive: TEST_FIRST** — PASS. Test coverage is FR-14, FR-15, NFR-05.
- **Tools: git, python, spec-kitty** — PASS. All tools in use.
- **Deterministic boundary** — PASS. log_action.py owns schema enforcement;
  agents own only judgment of what to log.

**Post-Phase 1 re-check**: No new violations. The design adds no external
dependencies, no new abstraction layers, and no complexity beyond what the
spec requires.

## Project Structure

### Documentation (this feature)

```
kitty-specs/014-felix-core-digest/
├── spec.md
├── plan.md              # This file
├── research.md          # Phase 0 output
├── data-model.md        # Phase 1 output
├── checklists/
│   └── requirements.md
└── tasks/
    └── README.md
```

### Source Code (repository root)

```
scripts/openclaw/observation/
├── log_action.py                    ← NEW: deterministic log writer CLI
├── summarize.py                     ← MODIFIED: JSONL parsing, new output paths, retention
├── config.py                        ← MODIFIED: add log_verbosity() method
└── tests/
    ├── test_summarize.py            ← MODIFIED: tests against JSONL fixtures
    ├── test_log_action.py           ← NEW: log_action.py unit tests
    └── fixtures/
        ├── capture-routine.jsonl    ← NEW (replaces .md)
        ├── capture-flagged.jsonl    ← NEW (replaces .md)
        ├── capture-error.jsonl      ← NEW (replaces .md)
        ├── capture-security.jsonl   ← NEW (replaces .md)
        ├── habits-routine.jsonl     ← NEW (replaces .md)
        ├── habits-mixed.jsonl       ← NEW (replaces .md)
        ├── multi-run.jsonl          ← NEW: multi-run day coverage
        ├── verbose-trace.jsonl      ← NEW: verbose verbosity coverage
        ├── malformed.jsonl          ← NEW: malformed line handling
        └── truncated-refs.jsonl     ← NEW: generative output cross-refs

scripts/openclaw/agents/
├── felix-admin-capture/AGENTS.md    ← MODIFIED: new Action Logging section
├── felix-admin-habits/AGENTS.md     ← MODIFIED: new Action Logging section
└── felix-admin-tasker/AGENTS.md     ← MODIFIED: new Action Logging section

scripts/office2/
├── felix-core-digest.timer          ← NEW: systemd timer (15-min interval)
└── felix-core-digest.service        ← NEW: systemd service (oneshot)

scripts/deploy/
└── deploy-f014.sh                   ← NEW: deployment script

docs/
├── constitution/
│   └── agent-registry.json          ← MODIFIED: add log_verbosity + tasker entry
├── handbooks/
│   └── observation-ops.md           ← NEW: operations runbook
└── design/architecture/
    ├── data/
    │   ├── service-inventory.json   ← MODIFIED: add felix-core-digest
    │   └── data-flows.json          ← MODIFIED: add observation flow
    ├── service-inventory.md         ← MODIFIED: add felix-core-digest
    └── data-flows.md                ← MODIFIED: add observation flow
```

**Structure Decision**: Extends the existing `scripts/openclaw/observation/`
module. No new top-level directories. `log_action.py` lives alongside
`summarize.py` in the observation module — both are part of the same
subsystem.

## Implementation Sequence

The sequence is ordered to minimize risk and ensure each step is testable
before the next depends on it.

### Phase 1: Foundation (no office2 dependency)

1. **log_action.py + tests** (FR-01 through FR-07, NFR-01, NFR-04)
   - Write test_log_action.py first (test-first)
   - Implement log_action.py: CLI interface, schema validation, JSONL
     serialization, verbosity filtering, truncation enforcement
   - Tests run locally; no office2 deployment needed

2. **Registry + config updates** (FR-18, FR-19)
   - Add `felix-admin-tasker` to agent-registry.json
   - Add `log_verbosity: "standard"` to all three agents
   - Add `log_verbosity()` method to config.py following autonomy_level() pattern
   - Add tests for verbosity lookup

3. **JSONL fixture creation** (FR-14, FR-15)
   - Map all 6 Markdown fixtures to JSONL equivalents
   - Create 4 new fixtures (multi-run, verbose, malformed, truncated)
   - Do NOT delete Markdown fixtures yet — both exist temporarily

### Phase 2: Rewrite (summarize.py changes)

4. **summarize.py JSONL parsing** (FR-08, FR-09, FR-13)
   - Replace parse_log_file() with parse_jsonl_log()
   - Replace find_log_files() to walk per-agent subdirectories
   - Malformed line handling (stderr + skip)
   - Update tests to use JSONL fixtures
   - Delete Markdown fixtures only after all tests pass

5. **Output structure + retention** (FR-10, FR-11, FR-12)
   - Change output paths to `Agent-Logs/{agent-name}/YYYY-MM-DD-log.md`
   - Implement 5-day retention (filename-based age)
   - Implement idempotency check (skip write when no new content)
   - Update generate_digest() and generate_agent_detail() for new paths
   - Tests for retention and idempotency

### Phase 3: Agent Updates

6. **AGENTS.md updates** (FR-16, FR-17)
   - Diff each agent's current Action Logging section
   - Replace with log_action.py instructions and per-agent action/category lists
   - Verify no fields silently dropped (see research.md R4 mapping)

7. **Gitignore** (FR-20)
   - Add `agents/logs/` to `~/second-brain/.gitignore`

### Phase 4: Infrastructure + Deployment

8. **Systemd timer/service** (FR-21)
   - Create `felix-core-digest.timer` (15-min interval, persistent)
   - Create `felix-core-digest.service` (oneshot, runs summarize.py)
   - Follow second-brain-sync.timer pattern

9. **Deploy script** (FR-23)
   - Create `deploy-f014.sh` following F013 pattern
   - Stages: copy log_action.py, copy AGENTS.md files, copy systemd units,
     enable timer, validate

10. **Deploy to office2** — manual step via `bash scripts/deploy/deploy-f014.sh`

### Phase 5: Documentation

11. **Operations runbook** (FR-22)
    - `docs/handbooks/observation-ops.md`

12. **Architecture docs** (FR-24)
    - `service-inventory.json`: add felix-core-digest as type "cron"
    - `data-flows.json`: add observation flow
    - Update markdown counterparts

### Phase 6: End-to-End Validation

13. **E2E verification** on office2:
    - Agent run produces JSONL entry
    - Timer fires, summarize.py generates digest
    - Digest appears in Obsidian on Mac
    - Idle run produces no file writes
    - Retention deletes old files

## Key Design Decisions

### 1. log_action.py CLI Interface

```
python log_action.py \
  --agent felix-admin-capture \
  --category routine \
  --action file_processed \
  --target "Inbox 2026-04-04 0715.md" \
  --outcome completed \
  --context '{"project": "Personal", "vikunja_task_id": null}'
```

- `--agent`, `--category`, `--action`, `--target`, `--outcome` are required
- `--context` accepts a JSON string (optional, stripped at brief verbosity)
- `--trace` accepts a JSON string (optional, stripped at brief/standard)
- `--registry` optional override for registry path (default: auto-detect)
- `--log-dir` optional override for log directory (default: `~/second-brain/agents/logs/`)

`ts` and `run_id` are never accepted as arguments — always generated.

### 2. Idempotency Mechanism

summarize.py tracks last-processed state via file mtime comparison:
- Before processing, stat each agent's JSONL file for mtime
- Compare against the digest file's mtime
- If JSONL mtime <= digest mtime, skip that agent
- This is simple, requires no state file, and handles the common case

### 3. Digest Internal Format Compatibility

The existing `filter_actions_by_autonomy()`, `detect_critical_alerts()`, and
`summarize_routine_actions()` functions operate on dicts with
`{"category": str, "text": str}` structure. The new `parse_jsonl_log()`
returns the same shape by mapping JSONL `action` + `target` fields to
`text`. Processing layer changes are minimal.

### 4. felix-admin-tasker Registry Addition

Research found tasker is deployed (F013) but not in agent-registry.json.
It must be added with the same structure as capture/habits: team, scope,
autonomy_level, deployed_feature, registered date, transition_history.
This is a prerequisite for FR-18 (log_verbosity for all agents).

## Risk Mitigations

| Risk | Mitigation | Implemented In |
|---|---|---|
| Fixture mapping gaps | Research R3 maps all 6 fixtures; JSONL created before MD deleted | Phase 1 step 3, Phase 2 step 4 |
| AGENTS.md deployment gap | Deploy AGENTS.md before activating JSONL summarize.py | Phase 4 deploy sequence |
| Idle cron writes | Idempotency check (mtime comparison) | Phase 2 step 5 |
| Tasker not in registry | Add during registry update | Phase 1 step 2 |

## Complexity Tracking

No constitution violations. No complexity beyond what the spec requires.
