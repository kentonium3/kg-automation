# Implementation Plan: Vikunja client + habits weekly report

**Branch**: `kitty/mission-vikunja-client-and-habits-weekly-report-01KTKSFT` | **Date**: 2026-06-08 | **Spec**: [spec.md](./spec.md)

## Summary

Three bundled issues (#562 umbrella, #542 foundation, #561 co-shipped) ship in one mission as the canonical Directive-6 fix for felix-admin-habits' weekly-report path. Shared Vikunja client lands first (FR-001/002), then morning-check-in migrates onto it (FR-007 — proves zero regression), then the new deterministic weekly helper builds on top (FR-003/004/005/006), then habits + sibling agents' standing orders gain output-discipline Hard Rules + weekly-procedure documentation (FR-008/009/010), and architecture inventories sync to match (FR-013 + doc-sync requirement). The mission preserves the existing project-13 + daily-habit filter pattern from `363685ea` (#556 fix), extends it to recurring-on-weekday via Vikunja's native `repeat_after` + `repeat_mode` encoding, and replaces LLM improvisation with deterministic data — the agent's job becomes pure rendering.

## Technical Context

**Language/Version**: Python 3.10+ (matches existing `scripts/inbox/`, `scripts/habits/`, `scripts/common/` helpers; office2 Ubuntu 24.04 ships Python 3.12).

**Primary Dependencies**: Standard library only for new code (`urllib.request`, `urllib.parse`, `urllib.error`, `json`, `os`, `dataclasses`, `datetime`, `zoneinfo`). Existing surfaces consumed (not new dependencies): `scripts/common/vikunja_config.py::get_vikunja_base_url()` (base URL resolution), `scripts/openclaw/observation/log_action.py` (audit trail), token file at `/data/services/openclaw/secrets/vikunja-api` (read directly; no helper exists for token).

**Storage**: No new state files. Reads Vikunja via API; writes nothing to disk except via `log_action.py` (existing JSONL stream). Token cached in-memory per client instance (FR-002 — no global state).

**Testing**: pytest with branch coverage (`pytest --cov=scripts/common --cov=scripts/habits --cov-branch --cov-fail-under=90`) following the pattern from mission #558's calendar helper. New test directories: `tests/common/` (for vikunja_client) and `tests/habits/` (extend existing for the new weekly helper). Coverage targets: ≥90% line, ≥85% branch on `scripts/common/vikunja_client.py` AND `scripts/habits/query_active_habits_weekly.py`. Tests use `urlopen` mocking via the global guard in `tests/conftest.py` plus per-test response mocks.

**Target Platform**: Ubuntu 24.04 LTS on office2 (production); macOS Darwin 25.5.0 for dev/test on Kent's Mac.

**Project Type**: single — additions to existing repo (`scripts/`, `tests/`, agent AGENTS.md files across `scripts/openclaw/agents/felix-admin-{habits,escalation,tasker}/`).

**Performance Goals**: ≤5s wall-clock for the weekly helper at the 95th percentile under normal Vikunja load (NFR-001). Single invocation per weekly cron tick; no parallelism.

**Constraints**: Tier 3 (logic/workflow). No host configuration, network, credentials, ports, or sudo-protected resources modified (C-006). Privacy boundary at `~/second-brain/notes/04-Growth/_private/` is absolute (C-005). Idempotency required (NFR-004). No third-party HTTP libraries (C-001 — `requests` not used; matches the `validate_calendar_event.py` precedent from #558).

**Scale/Scope**: New client ~200 LoC + ~50 unit tests. New weekly helper ~250 LoC + ~30 tests + fixtures. AGENTS.md edits ~80 lines across felix-admin-habits, plus smaller edits to escalation + tasker per the audit. Migration of `query_active_habits_v2.py` is a ~10-line import + class instantiation swap. Architecture JSON updates touch ~3 files.

## Charter Check

*GATE: Must pass before Phase 0 research. Re-check after Phase 1 design.*

| Directive | Applies? | How this plan satisfies |
|---|---|---|
| DIRECTIVE_001 — Architectural Integrity | Yes | Client is independently testable; helper is pure-function; agent prompt edits are localized to one AGENTS.md per agent; no cross-component leakage. |
| DIRECTIVE_003 — Decision Documentation | Yes | Spec captures the Directive-6 split decision; this plan documents the recurrence-model choice (Vikunja native `repeat_after`); research.md will record the cron-cadence and sibling-audit outcomes. |
| DIRECTIVE_010 — Specification Fidelity | Yes | Plan derives strictly from spec FRs/NFRs/Cs; out-of-scope items (second migration, voice/UX changes, etc.) carried verbatim from spec. |
| DIRECTIVE_024 — Locality of Change | Yes | Client localized to `scripts/common/`; helper localized to `scripts/habits/`; agent edits localized to each agent's AGENTS.md. No cross-cutting refactors. |
| DIRECTIVE_031 — Context-Aware Design | Yes | Domain language section in spec defines the bounded context. Plan respects those boundaries. |
| DIRECTIVE_033 — Targeted Staging | Yes | Implementation will stage only the expected deliverables per WP. No blanket `git add .` in WP prompts. |
| DIRECTIVE_034 — Test-First Development | Yes | Client unit tests authored before client implementation. Helper unit tests authored before helper implementation. Regression tests for FR-012 explicit failure modes added before fix. |
| DIR-001 — c4-incremental-detail-modeling | Yes | This plan is Layer 2 of the C4 progression; research.md and data-model.md follow. |
| DIR-002 — Privacy/security boundaries | Yes | C-005 affirms the `04-Growth/_private/` absolute rule. No new privacy surface. |
| DIR-003 — Docs synchronized | Yes | See Documentation Sync section in spec. |
| DIR-004 — Documentation standards | Yes | Plan + spec follow YAML-frontmatter and structural conventions. |
| DIR-005 — Doc-sync requirement in mission | Yes | Spec's "Documentation Synchronization Requirement" section enumerates the JSON + Markdown files that must update in the merge PR. |
| DIR-006 — Probe real environment | Yes | Live probing of office2 done during this plan phase. Surfaces in research.md: actual habit data shape, weekly cron cadence and configuration, sibling-agent AGENTS.md content for audit outcomes. |

**Gate verdict**: PASS. Proceed to Phase 0.

## Project Structure

### Documentation (this feature)

```
kitty-specs/vikunja-client-and-habits-weekly-report-01KTKSFT/
├── plan.md              # This file
├── spec.md              # Feature spec (committed)
├── research.md          # Phase 0 output (live-probe research per DIR-006)
├── data-model.md        # Phase 1 output
├── quickstart.md        # Phase 1 output
└── contracts/           # Phase 1 output
    ├── vikunja_client.md
    ├── query_active_habits_weekly.md
    └── weekly_report_payload.md
```

### Source code (repository root)

```
scripts/
├── common/
│   ├── vikunja_config.py                  # EXISTING (consumed)
│   └── vikunja_client.py                  # NEW
├── habits/
│   ├── query_active_habits_v2.py          # MODIFIED (migrated to use client)
│   └── query_active_habits_weekly.py      # NEW
└── openclaw/
    └── agents/
        ├── felix-admin-habits/AGENTS.md    # MODIFIED (Hard Rules + weekly-report procedure)
        ├── felix-admin-escalation/AGENTS.md  # MODIFIED IF AUDIT REQUIRES
        └── felix-admin-tasker/AGENTS.md      # MODIFIED IF AUDIT REQUIRES

tests/
├── common/
│   ├── __init__.py                         # NEW (if not present)
│   ├── test_vikunja_client.py              # NEW (~50 tests)
│   └── fixtures/
│       └── vikunja_client_responses.json   # NEW
└── habits/
    ├── test_query_active_habits_v2.py      # EXISTING (must still pass)
    ├── test_query_active_habits_weekly.py  # NEW (~30 tests)
    └── fixtures/
        └── weekly_report_responses.json    # NEW

docs/
└── design/
    └── architecture/
        ├── data/
        │   ├── service-inventory.json     # MODIFIED
        │   ├── data-flows.json            # MODIFIED
        │   └── signal-to-doc-map.json     # MODIFIED
        └── data-flows.md                  # MODIFIED
```

**Structure Decision**: Single-project layout. Mission delivers (a) a new infrastructure module + tests, (b) a new helper script + tests, (c) one migrated helper (zero-regression target), (d) AGENTS.md edits across three agents, (e) architecture JSON + narrative updates.

## Phase 0: Research

Live-probe research (per DIR-006) is the primary phase-0 work. Findings recorded in [research.md](./research.md). Headlines to verify:

- **Vikunja recurrence model verification**: read at least three of Kent's actual habits via the Vikunja API on office2; confirm `repeat_after`, `repeat_mode`, and `due_date` carry the values the spec assumes. Specifically verify the "Strength training — Wed" habit's `repeat_after == 604800` and its `due_date` is a Wednesday.
- **Vikunja check-in history queryability**: confirm the API exposes per-task per-day completion records over a 14-day window.
- **Weekly cron cadence + configuration**: `openclaw cron list --json` on office2; find the felix-admin-habits weekly entry. Document day/time, delivery mode (presumed `announce`), and trigger phrasing.
- **Sibling-agent AGENTS.md content**: read `scripts/openclaw/agents/felix-admin-{escalation,tasker}/AGENTS.md` end-to-end. Classify each as (a) already has Hard Rules — no edit needed, (b) doesn't have Hard Rules but emits user-facing WhatsApp — add them, (c) doesn't emit user-facing WhatsApp — add explicit annotation.
- **felix-admin-habits' model identity**: confirm sonnet per the 2026-06-08 leaked message header.
- **"WP04 T015" citation resolution**: search prior missions for a WP04 T015 referencing weekly habit reports. If real, the prior spec informs design. If confabulated, document as agent-hallucination evidence.
- **Architecture-docs-first probe** (per memory `feedback_architecture_docs_first.md`): consult arch JSONs FIRST before any office2 SSH for things like the openclaw plugin set or other deployed surfaces.

## Phase 1: Design & Contracts

Design artifacts:

- [data-model.md](./data-model.md) — entities (VikunjaClient, exception hierarchy, WeeklyHabitReport JSON shape, HabitClassification) with field tables, validation rules, and lifecycle.
- [contracts/vikunja_client.md](./contracts/vikunja_client.md) — public surface of the new client: method signatures, exception classes, redaction policy, timeout behavior, base URL normalization.
- [contracts/query_active_habits_weekly.md](./contracts/query_active_habits_weekly.md) — stdin/stdout JSON contract for the weekly helper. Mirrors the validate_calendar_event contract pattern from #558.
- [contracts/weekly_report_payload.md](./contracts/weekly_report_payload.md) — WeeklyHabitReport JSON schema the agent consumes for rendering.
- [quickstart.md](./quickstart.md) — operator-runnable smoke test for office2 verification.

## Re-evaluation of Charter Check (post-Phase 1)

All gates remain PASS. If research surfaces a gate violation (e.g., the recurrence model differs from spec assumptions), plan phase records the deviation and either revises the spec or files a separate issue.

## Work-package strategy (advisory for /spec-kitty.tasks)

Anticipated WPs (5 WPs target; finalize-tasks may collapse or split):

- **WP01 — Shared Vikunja client + tests** (no deps): new `scripts/common/vikunja_client.py` (~200 LoC), exception hierarchy, full unit test suite covering FR-001/002. Owned files: `scripts/common/vikunja_client.py`, `tests/common/**`.
- **WP02 — Migrate query_active_habits_v2.py to client** (depends WP01): zero-regression target (NFR-006). Owned files: `scripts/habits/query_active_habits_v2.py`.
- **WP03 — New weekly helper + tests** (depends WP01): new `scripts/habits/query_active_habits_weekly.py` (~250 LoC), WeeklyHabitReport JSON contract, full test suite covering FR-003/004/005/006/012. Owned files: `scripts/habits/query_active_habits_weekly.py`, `tests/habits/test_query_active_habits_weekly.py`, `tests/habits/fixtures/weekly_report_responses.json`.
- **WP04 — AGENTS.md edits (habits + sibling audit)** (depends WP03): rewrite `felix-admin-habits/AGENTS.md` with Hard Rules + weekly-report procedure (FR-008/009); audit + edit `felix-admin-escalation/AGENTS.md` and `felix-admin-tasker/AGENTS.md` per FR-010. Owned files: those three AGENTS.md files.
- **WP05 — Architecture doc-sync** (no deps): update `docs/design/architecture/data/service-inventory.json`, `data-flows.json`, `data-flows.md`, `signal-to-doc-map.json`. Owned files: those four.

## Branch contract (final reaffirmation)

- **Current branch**: `kitty/mission-vikunja-client-and-habits-weekly-report-01KTKSFT` (the mission coord branch — necessary per the 11-symptom workaround chain in kg-automation#559)
- **Planning/base branch**: `kitty/mission-vikunja-client-and-habits-weekly-report-01KTKSFT` (legacy mode in effect per `meta.json` `coordination_branch: ""`)
- **Final merge target**: `main` (per `meta.json` `target_branch: main`)
- **Branch matches target**: false (expected per the workaround; spec-kitty merge sources target from `meta.json` regardless)

## Workflow-class workaround posture for this mission

Per memory `project_speckitty_upgrade_pending.md` and `kentonium3/kg-automation#559`, this mission runs on spec-kitty 3.2.0rc37 using the documented 11-symptom workaround chain. Subsequent missions should upgrade first. Key postures active for this mission:

- `meta.json` has `coordination_branch: ""` (permanent legacy mode)
- `.kittify/config.yaml` has `auto_commit: false`
- All operations from the coord branch, NOT main
- `safe-commit --to-branch <coord>` for all spec/plan/tasks commits
- `--force` on `move-task --to approved` (review-lock guard)
- `--target-branch <coord>` on `finalize-tasks` if needed
- Manual `git merge --no-ff -X theirs <coord>` for the eventual mission-end merge
- WPs to `done` from coord branch posture

## Next phase

After plan.md commits, `/spec-kitty.tasks` decomposes into the 5 WPs above. This command STOPS here per the spec-kitty.plan runbook's mandatory stop point.
