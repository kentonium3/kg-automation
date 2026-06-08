# Implementation Plan: Vikunja client + habits weekly report

**Branch**: `kitty/mission-vikunja-client-and-habits-weekly-report-01KTKSFT` | **Date**: 2026-06-08 | **Spec**: [spec.md](./spec.md)
**Revision**: 2 (post phase-0 live-probe findings; FR-007 dropped, data source changed, recurrence math revised; 4 WPs not 5)

## Summary

Mission ships the bundled #562/#542/#561 slice as a Directive-6 fix for felix-admin-habits' weekly-report path. Phase-0 live probes (recorded in research.md) revealed three load-bearing surprises that re-shaped the spec: (1) `query_active_habits_v2.py` reads a local sync cache (not Vikunja API), so the planned "v2 migration to shared client" is impossible — v2 has nothing to migrate; (2) Vikunja's `done_at` field IS queryable via `?filter=done=true`, so the new weekly helper can query completion history directly via the shared client; (3) Kent's "Strength training — Mon/Wed/Fri" habits are NOT recurring in Vikunja's data model (`repeat_after=0`) — they're per-occurrence tasks with weekday encoded in the title, mirroring the day-of-week filter pattern from mission #408. Net effect: scope tightens to 4 WPs (was 5) — shared Vikunja client, new weekly helper as the first client consumer, AGENTS.md edits + sibling audit, architecture doc-sync.

## Technical Context

**Language/Version**: Python 3.10+ (matches existing `scripts/inbox/`, `scripts/habits/`, `scripts/common/` helpers; office2 Ubuntu 24.04 ships Python 3.12).

**Primary Dependencies**: Standard library only for new code (`urllib.request`, `urllib.parse`, `urllib.error`, `json`, `os`, `dataclasses`, `datetime`, `zoneinfo`, `re` for weekday-in-title parsing). Existing surfaces consumed (not new dependencies): `scripts/common/vikunja_config.py::get_vikunja_base_url()` (base URL resolution), `scripts/openclaw/observation/log_action.py` (audit trail), token file at `/data/services/openclaw/secrets/vikunja-api` (read directly).

**Storage**: No new state files. Reads Vikunja via API (the new weekly helper); writes nothing to disk except via `log_action.py`. Token cached in-memory per client instance.

**Testing**: pytest with branch coverage (`pytest --cov=scripts/common --cov=scripts/habits --cov-branch --cov-fail-under=90`) following the pattern from mission #558's calendar helper. New test directories: `tests/common/` (for vikunja_client) and `tests/habits/test_query_active_habits_weekly.py` (for the new helper). The existing `tests/habits/test_query_active_habits_v2.py` is NOT modified — v2 is untouched per C-004. Tests use `urlopen` mocking via the global guard in `tests/conftest.py` plus per-test response mocks.

**Target Platform**: Ubuntu 24.04 LTS on office2 (production); macOS Darwin 25.5.0 for dev/test on Kent's Mac.

**Project Type**: single — additions to existing repo (`scripts/`, `tests/`, agent AGENTS.md files across `scripts/openclaw/agents/felix-admin-{habits,escalation,tasker}/`).

**Performance Goals**: ≤5s wall-clock for the weekly helper at the 95th percentile under normal Vikunja load (NFR-001). Single invocation per weekly cron tick; ≤4 API calls per invocation.

**Constraints**: Tier 3 (logic/workflow). No host configuration, network, credentials, ports, or sudo-protected resources modified (C-006). Morning check-in path is NOT modified (C-004). Privacy boundary at `~/second-brain/notes/04-Growth/_private/` is absolute (C-005). Idempotency required (NFR-004). No third-party HTTP libraries (C-001).

**Scale/Scope**: New client ~200 LoC + ~50 unit tests. New weekly helper ~250 LoC + ~30 tests + fixtures. AGENTS.md edits ~80 lines across felix-admin-habits + smaller edits for escalation + tasker per the audit. Architecture JSON updates touch ~3 files.

## Charter Check

*GATE: Must pass before Phase 0 research. Re-check after Phase 1 design.*

| Directive | Applies? | How this plan satisfies |
|---|---|---|
| DIRECTIVE_001 — Architectural Integrity | Yes | Client is independently testable; helper is pure-function; agent prompt edits are localized to one AGENTS.md per agent; no cross-component leakage. |
| DIRECTIVE_003 — Decision Documentation | Yes | Spec revision 2 documents the data-source decision (Vikunja API via done_at filter, NOT cache); research.md records phase-0 findings that drove the decision. |
| DIRECTIVE_010 — Specification Fidelity | Yes | Plan derives strictly from spec (revised) FRs; FR-007 explicitly carries the "dropped" audit trail. |
| DIRECTIVE_024 — Locality of Change | Yes | Client → `scripts/common/`; helper → `scripts/habits/`; agent edits → each agent's AGENTS.md. Morning check-in path explicitly untouched. |
| DIRECTIVE_031 — Context-Aware Design | Yes | Domain language section in spec defines the bounded context including the daily-vs-weekday-in-title habit kinds. |
| DIRECTIVE_033 — Targeted Staging | Yes | Implementation will stage only the expected deliverables per WP. |
| DIRECTIVE_034 — Test-First Development | Yes | Client unit tests authored before client implementation. Helper unit tests authored before helper implementation. Regression tests for FR-012 explicit failure modes added before fix. |
| DIR-001 — c4-incremental-detail-modeling | Yes | This plan is Layer 2; research.md and data-model.md follow. |
| DIR-002 — Privacy/security boundaries | Yes | C-005 affirms the absolute rule. |
| DIR-003 — Docs synchronized | Yes | See spec's Documentation Sync section. |
| DIR-004 — Documentation standards | Yes | Plan + spec follow YAML-frontmatter conventions. |
| DIR-005 — Doc-sync requirement | Yes | Spec's "Documentation Synchronization Requirement" enumerates affected docs. |
| DIR-006 — Probe real environment | Yes | Live probing of office2 done during phase-0; findings recorded in research.md drove the revision-2 scope correction. |

**Gate verdict**: PASS. Proceed to Phase 0.

## Project Structure

### Documentation (this feature)

```
kitty-specs/vikunja-client-and-habits-weekly-report-01KTKSFT/
├── plan.md              # This file (revision 2)
├── spec.md              # Feature spec (revision 2; committed)
├── research.md          # Phase 0 output (live-probe findings drove revision 2)
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
│   ├── vikunja_config.py                  # EXISTING (consumed; UNCHANGED)
│   ├── sync_cache.py                      # EXISTING (consumed by v2; UNCHANGED in this mission)
│   └── vikunja_client.py                  # NEW
├── habits/
│   ├── query_active_habits_v2.py          # EXISTING (UNCHANGED in this mission; C-004)
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
    ├── test_query_active_habits_v2.py      # EXISTING (UNCHANGED in this mission)
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

**Structure Decision**: Single-project layout. 4-WP roster (revision 2).

## Phase 0: Research (substantially complete)

Live-probe research per DIR-006 was the primary phase-0 work, done before this plan revision. Findings recorded in [research.md](./research.md). Headlines (drove revision 2 of spec.md):

- **R-001 — Vikunja recurrence model**: of Kent's 11 habits in project 13, 7 are daily (`repeat_after=86400`) and 3 are weekday-in-title (`repeat_after=0`, title contains weekday name). The "Strength training — Mon/Wed/Fri" pattern is per-occurrence, not Vikunja-recurring. The weekly helper mirrors the day-of-week filter from mission #408 (`query_active_habits_v2.py`'s `_weekday_name_for_date`).
- **R-002 — Vikunja done_at is queryable**: `GET /projects/13/tasks?filter=done=true` returns historical completed tasks with `done_at` populated. Confirmed via live probe. The exact date-range filter syntax (`&filter=done_at>=<iso>`) is verified during plan-phase contract work.
- **R-003 — Morning check-in uses sync cache, not Vikunja API**: `query_active_habits_v2.py` reads `/data/services/openclaw/state/sync/task-cache.json` via `scripts.common.sync_cache`. The cache holds current state only, no completion history. v2 has nothing to migrate to the new client; FR-007 is DROPPED.
- **R-004 — Weekly cron confirmed**: `habits-weekly-report` at `0 22 * * 0` (Sunday 10pm America/New_York), `announce` delivery to WhatsApp. FR-014 verified.
- **R-005 — Sibling-agent paths different than assumed**: deployed AGENTS.md aren't at `/home/claude/.openclaw/agents/felix-admin-{escalation,tasker}/AGENTS.md` (only felix-admin-capture and Felix main are there). The repo paths `scripts/openclaw/agents/felix-admin-*/AGENTS.md` exist but deployed paths differ per memory `reference_office2_agent_deploy_paths.md`. Plan phase locates the actual deployed paths.
- **R-006 — escalation-daily cron exists**: `escalation-daily` at `0 12 * * *`, announce → WhatsApp. felix-admin-escalation IS a user-facing-WhatsApp agent; Hard Rules ARE in scope per FR-010.

Items remaining for plan phase:
- Verify date-range filter syntax for `done_at` (`>=`, `<`, etc.) against Vikunja's actual filter expression language.
- Locate sibling-agent AGENTS.md deployed paths on office2.
- Audit all 11 habits' titles against the weekday-in-title regex pattern (`(Mon|Tue|Wed|Thu|Fri|Sat|Sun)(day)?`); confirm no false positives or false negatives.
- Verify `felix-admin-tasker` has a cron or not.

## Phase 1: Design & Contracts

Design artifacts (Phase-1 work, produced after this plan commits):

- [data-model.md](./data-model.md) — entities (VikunjaClient, exception hierarchy, WeeklyHabitReport JSON shape, HabitClassifier) with field tables, validation rules, and lifecycle.
- [contracts/vikunja_client.md](./contracts/vikunja_client.md) — public surface of the new client: method signatures, exception classes, redaction policy, timeout behavior, base URL normalization.
- [contracts/query_active_habits_weekly.md](./contracts/query_active_habits_weekly.md) — CLI contract for the weekly helper: args, stdin (none), stdout JSON shape, exit codes.
- [contracts/weekly_report_payload.md](./contracts/weekly_report_payload.md) — WeeklyHabitReport JSON schema the agent consumes for rendering.
- [quickstart.md](./quickstart.md) — operator-runnable smoke test for office2 verification.

## Re-evaluation of Charter Check (post-Phase 1)

All gates remain PASS.

## Work-package strategy (advisory for /spec-kitty.tasks)

Revised to 4 WPs in revision 2:

- **WP01 — Shared Vikunja client + tests** (no deps): new `scripts/common/vikunja_client.py` (~200 LoC), exception hierarchy, full unit test suite covering FR-001/002. Owned files: `scripts/common/vikunja_client.py`, `tests/common/**`.
- **WP02 — New weekly helper + tests** (depends WP01): new `scripts/habits/query_active_habits_weekly.py` (~250 LoC) using the shared client to query `done_at` history, with the weekday-in-title classifier (FR-004) and per-habit percentage math (FR-003/004/005/006/012). Full test suite. Owned files: `scripts/habits/query_active_habits_weekly.py`, `tests/habits/test_query_active_habits_weekly.py`, `tests/habits/fixtures/weekly_report_responses.json`.
- **WP03 — AGENTS.md edits (habits + sibling audit)** (depends WP02): rewrite `felix-admin-habits/AGENTS.md` with Hard Rules + weekly-report procedure (FR-008/009); audit + edit `felix-admin-escalation/AGENTS.md` and `felix-admin-tasker/AGENTS.md` per FR-010. Owned files: those three AGENTS.md files.
- **WP04 — Architecture doc-sync** (no deps): update `docs/design/architecture/data/service-inventory.json`, `data-flows.json`, `data-flows.md`, `signal-to-doc-map.json`. Owned files: those four.

Dependency graph: WP01 → WP02 → WP03; WP04 independent (parallelizable with WP01).

## Branch contract

- **Current branch**: `kitty/mission-vikunja-client-and-habits-weekly-report-01KTKSFT` (the mission coord branch)
- **Planning/base branch**: same (legacy mode)
- **Final merge target**: `main`
- **Branch matches target**: false (expected per the 11-symptom workaround chain)

## Workflow-class workaround posture for this mission

Per memory `project_speckitty_upgrade_pending.md` and `kentonium3/kg-automation#559`, this mission runs on spec-kitty 3.2.0rc37 using the documented 11-symptom workaround chain. Next mission upgrades first.

Key postures active for this mission:
- `meta.json` has `coordination_branch: ""` (permanent legacy mode)
- `.kittify/config.yaml` has `auto_commit: false`
- All operations from the coord branch, NOT main
- `safe-commit --to-branch <coord>` for all spec/plan/tasks commits
- `--force` on `move-task --to approved` (review-lock guard)
- `--target-branch <coord>` on `finalize-tasks` if needed
- Manual `git merge --no-ff -X theirs <coord>` for the eventual mission-end merge
- WPs to `done` from coord branch posture

## Next phase

After plan.md commits, `/spec-kitty.tasks` decomposes into the 4 WPs above. This command STOPS here per the spec-kitty.plan runbook's mandatory stop point.
