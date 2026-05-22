# Implementation Plan: Drift event auto-resolution via LLM judgment

**Branch**: `main` | **Date**: 2026-05-22 | **Spec**: [spec.md](spec.md)
**Input**: Feature specification from `kitty-specs/drift-event-auto-resolution-01KS8J32/spec.md`
**Mission ID**: `01KS8J321F8KE7369R3DA02329`

## Summary

Extend the post-#343 doc-audit driver with a new "drift interpretation" LLM judgment moment (Moment 0) that runs before issue filing for every mapped drift event. The judgment classifies each drift event as `PROPOSED_EDIT`, `JUDGMENT_REQUIRED`, or `NO_CHANGE_NEEDED` with explicit confidence. PROPOSED_EDIT verdicts at confidence ≥0.80 are translated into the existing `ProposedEdit` dataclass and routed through the existing `tier_classification` (Moment 1) — preserving all SKILL.md §4.3 safety guardrails.

The architecture mirrors the existing `tier_classification` surface: cache-aware prompt, `JudgmentClient` reuse, defense-in-depth schema validation. Two LLM calls per PROPOSED_EDIT path (Moment 0 + Moment 1); negligible cost at Haiku 4.5 rates given current drift volume (~3-10 events/day).

## Technical Context

**Language/Version**: Python 3.13
**Primary Dependencies**: existing `anthropic` SDK (already in use by `scripts/doc_audit/judgment/client.py`); stdlib `json`, `dataclasses`, `pathlib`, `logging`
**Storage**: append-only JSONL ledger at `/data/services/security-monitor/logs/drift-events-ledger.jsonl`; existing markdown activity log at `~/second-brain/agents/logs/doc-auditor-YYYY-MM-DD.md` preserved unchanged
**Testing**: pytest, mocked `JudgmentClient`, fixture-driven (synthetic drift events derived from real piling-up baselines)
**Target Platform**: office2 (Ubuntu 24.04 LTS Linux) via systemd user timer; CLI also runnable on Mac for dev
**Project Type**: single project (scripts/ module addition)
**Performance Goals**: LLM call P95 ≤15s single-attempt; end-to-end P95 ≤90s with retries; ≥98% successful event processing rate
**Constraints**: ≤30% operator-triage rate (success criterion); no new third-party deps; tier_classification surface unchanged (C-003)
**Scale/Scope**: ~3-10 drift events/day across 3 baselines today; pipeline must handle bursts during cron sweeps

## Charter Check

**Status**: Skipped (no `.kittify/charter/charter.md` present at planning time; `spec-kitty charter context --action plan --json` returned compact mode with unresolved governance per pre-existing tool-registry issue — not a blocker per memory `project_charter_tool_registry_mismatch.md`).

When the charter governance is re-resolved (separate work), this plan section should be revisited.

## Project Structure

### Documentation (this feature)

```
kitty-specs/drift-event-auto-resolution-01KS8J32/
├── plan.md              # This file
├── research.md          # Phase 0 — D1..D10 decisions
├── data-model.md        # Phase 1 — entities E1..E6
├── quickstart.md        # Phase 1 — operator cutover guide
├── contracts/
│   ├── cli.md           # CLI surface contract
│   ├── api.md           # Python API surface contract
│   ├── llm-json.md      # Strict LLM output JSON schema
│   └── ledger-schema.md # JSONL ledger schema contract
└── spec.md              # (already exists)
```

### Source Code (repository root)

```
scripts/doc_audit/
├── judgment/
│   ├── drift_interpretation.py        # NEW — Moment 0 LLM judgment
│   └── (existing modules unchanged)
├── prompts/
│   ├── drift_interpretation.prompt.md # NEW — cache-aware prompt
│   └── (existing prompts unchanged)
├── helpers/
│   ├── handle_drift_events.py         # MODIFIED — invokes Moment 0
│   ├── cutover_362.py                 # NEW — one-shot backlog cutover
│   └── (existing helpers unchanged)
├── output/
│   ├── drift_ledger.py                # NEW — JSONL append writer
│   └── activity_log.py                # (unchanged)
├── routing/
│   └── drift_to_proposed_edit.py      # NEW — verdict → ProposedEdit translator
├── data_model.py                      # MODIFIED — extend change_type set
└── config.toml                        # MODIFIED — drift_interpretation block

tests/doc_audit/
├── judgment/
│   └── test_drift_interpretation.py   # NEW
├── helpers/
│   ├── test_handle_drift_events.py    # MODIFIED — new test cases
│   └── test_cutover_362.py            # NEW
├── output/
│   └── test_drift_ledger.py           # NEW
├── routing/
│   └── test_drift_to_proposed_edit.py # NEW
└── fixtures/
    ├── drift_event_openclaw_cron.json   # NEW
    ├── drift_event_openclaw_json.json   # NEW
    └── drift_event_systemd_dropins.json # NEW
```

**Structure Decision**: Single-project layout extension. New code lives under `scripts/doc_audit/` mirroring the existing post-#343 package structure. Tests parallel under `tests/doc_audit/`. No new top-level directories.

## Phase 0 — Outline & Research

Detailed in [research.md](research.md). Ten decisions resolved:

- **D1**: Drift interpretation prompt structure (cache-aware split, examples, output schema)
- **D2**: Doc state truncation strategy for large files (>8KB)
- **D3**: `change_type` enum extension — add `drift_derived` value
- **D4**: Audit ledger schema (JSONL alongside existing markdown log)
- **D5**: Backlog cutover script design (idempotent, marker-guarded)
- **D6**: Retry/backoff implementation (30s/60s/120s, mirrors tasker pattern)
- **D7**: Cost budget per drift event (~1.5K tokens avg at Haiku 4.5; $0.01/day worst case)
- **D8**: Test fixture strategy (synthetic from real baselines + mocked SDK)
- **D9**: config.toml flag mechanism (read per-tick; no watcher)
- **D10**: CLI surface for drift_interpretation (mirrors existing tier_classification CLI)

## Phase 1 — Design & Contracts

Detailed in [data-model.md](data-model.md) and [contracts/](contracts/).

### Entities (6)

- **E1 — DriftVerdict** (LLM output): `{verdict, confidence, proposed_edit?, question?, rationale}`
- **E2 — DriftInterpretationContext** (LLM input): drift event metadata + diff + mapping + target doc states
- **E3 — AuditLedgerEntry** (JSONL row): event_id, timestamp, baseline, mapping_id, verdict, confidence, outcome, doc_paths, retry_count, latency_ms
- **E4 — ProposedEdit** (existing E-004, extended): adds `drift_derived` to `change_type` set
- **E5 — DriftInterpretationError** (exception): carries diagnostic context for escalation issue bodies
- **E6 — CutoverState** (one-shot marker): `~/.config/doc-audit/cutover-362.done` sentinel file

### Contracts

- **[cli.md](contracts/cli.md)**: standalone CLI surface for `drift_interpretation.py` — flags, exit codes, stdin/stdout JSON
- **[api.md](contracts/api.md)**: Python API surface — `interpret(client, context) -> DriftVerdict` + helpers
- **[llm-json.md](contracts/llm-json.md)**: strict LLM output JSON schema for the three verdict shapes
- **[ledger-schema.md](contracts/ledger-schema.md)**: JSONL ledger row schema + append semantics

### Quickstart

[quickstart.md](quickstart.md) provides operator-facing cutover steps: pre-flight checks, deploy sequence, cutover-362 script invocation, post-deploy smoke tests, 7-day observation, and rollback procedure.

## Charter Re-Check (post-Phase 1)

Same status as initial: charter is absent or governance-unresolved. No new gate violations introduced by Phase 0/Phase 1 design.

## Branch Strategy

- **Planning base branch**: `main`
- **Merge target branch**: `main`
- **branch_matches_target**: true
- Execution worktrees are allocated per lane at task-finalization time; not relevant during plan phase.

## Complexity Tracking

No charter violations to track (charter absent).

## Open Decisions

All planning questions resolved during the alignment step (Q1: ProposedEdit bridge via translator; defaults confirmed for audit ledger shape, prompt context, CLI surface, test strategy, cutover mechanism, config.toml flag).

No `[NEEDS CLARIFICATION: …]` markers remain.
