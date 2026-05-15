# Implementation Plan: Habits morning check-in — extract Steps 1-4 to helper scripts (D6)

**Mission**: `habits-checkin-d6-extract-01KRNV46` | **Date**: 2026-05-15 | **Spec**: [`spec.md`](./spec.md)
**Input**: [`spec.md`](./spec.md) — feature specification with FR/NFR/Constraints
**Tracks**: [#282](https://github.com/kentonium3/issues/282) | **Parent epic**: [#281](https://github.com/kentonium3/kg-automation/issues/281)
**Branch contract**: current `main` → planning base `main` → merge target `main` (matches target ✓)

---

## Summary

Refactor the `felix-admin-habits` morning check-in workflow so that the four deterministic steps currently encoded in the agent's prompt (TZ-aware date resolution, Vikunja active-habit query + filter, due_date setting, completion exclusion) execute as standalone Python helper scripts in `scripts/habits/`. The agent's prompt retains only Step 5 (Format) and Step 6 (Output discipline), which are genuine LLM judgment work. Implementation follows the patterns established by `vikunja_writer.py` (canonical Vikunja-writing precedent) and the [helper-script-conventions.md](../../docs/design/helper-script-conventions.md) draft (Phase 3 of #281).

The mission is **behavior-preserving end-to-end** — Kent's daily 7:05 AM ET WhatsApp check-in must be observably identical pre- and post-refactor. Model migration (Sonnet → Haiku) is explicitly deferred to a follow-up after stable production runs.

---

## Technical Context

**Language/Version**: Python 3.11+ (matches existing helpers; office2 has Python 3 stdlib available)
**Primary Dependencies**: Python stdlib only (`urllib.request`, `json`, `os`, `sys`, `argparse`, `zoneinfo`, `datetime`). No third-party HTTP libraries; matches `scripts/security/credential_health_check/vikunja_writer.py` precedent (Phase 0 research R2).
**Storage**: Vikunja REST API (no new persistent storage in this mission). Credentials read from `/data/services/openclaw/secrets/vikunja-api` (mode 600 plaintext file) per `credentials-and-secrets.md` § Mechanism #3 (Phase 0 research R1).
**Testing**: pytest + `unittest.mock` (stdlib). Tests at `tests/habits/test_<helper>.py`, parallel to `scripts/habits/<helper>.py`. Mocking convention from `tests/security/test_vikunja_writer.py` precedent (Phase 0 research R3).
**Target Platform**: Linux (office2 Ubuntu 24.04 LTS). Mac (Kent's development) for local test execution.
**Project Type**: Single-project script + agent prompt refactor (no new applications, services, or compose stacks).
**Performance Goals**: Whole check-in flow (4 helper invocations + agent prompt) must complete within the cron's 240-second timeout (currently 240s on office2 per `service-inventory.json` `habit-checkin.timeout_seconds`). Each helper individually completes in < 10s under normal Vikunja API latency.
**Constraints**: NFR-002 (line-by-line WhatsApp output equivalence), NFR-003 (AGENTS.md ≤ 300L target), NFR-004 (TZ correctness — no UTC `Z` suffix; #112 regression-prevention), C-001 (no model migration in this mission), C-003 (no `scripts/lib/vikunja.py` extraction; second-helper-is-the-signal guardrail).
**Scale/Scope**: Refactor 1 agent's prompt (478L → ≤300L target) + create 4 new helper scripts + create 4 new test modules + update 1 architecture JSON entry. Single-mission scope; no cross-cutting reach beyond `felix-admin-habits` and its support files.

---

## Charter Check

**Mode**: compact (per `spec-kitty charter context --action plan --json`).

| Gate | Status | Note |
|---|---|---|
| Directive 6 alignment | ✅ PASS | This mission IS a Phase 4 application of Directive 6. Validated by [`felix-d6-survey.md`](../../docs/design/architecture/felix-d6-survey.md) as priority #1. |
| Directive 5 (Documentation Standards) | ✅ PASS | Architecture JSON updated (`service-inventory.json`); narrative views remain consistent (no per-helper narrative artifacts beyond AGENTS.md). |
| Change-Risk Taxonomy | ✅ PASS | Mission is Tier 3 (Logic/Workflow: Python scripts, agent prompts). Standard guardrail protocol applies. No Tier 0/1/2 surfaces touched (no UFW, no system services, no production DB schemas). |
| Helper-script conventions | ✅ PASS (with one acknowledged deviation) | All implementation follows the draft [conventions doc](../../docs/design/helper-script-conventions.md). The deviation: § 9 three-tier model "library extraction" is **explicitly deferred** per C-003 — first Phase 4 mission has no second-helper to justify library; deferral is documented. |
| Privacy boundaries | ✅ PASS | No access to `~/second-brain/notes/04-Growth/_private/`. Helpers only touch Vikunja Habits project. |
| Tool availability | ⚠️ NOTE | Charter context output flagged `pytest`/`python` as unavailable in the `DEFAULT_TOOL_REGISTRY` (governance resolution warning). This is a known charter-config gap, not a mission blocker — pytest is in fact available; the charter just doesn't enumerate it correctly. Not in scope to fix here. |

No charter violations. No `[NEEDS CLARIFICATION]` markers remain after Phase 0 research. Gates pass; proceed to Phase 1.

**Re-check after Phase 1**: see "Post-design Charter re-check" section below.

---

## Project Structure

### Documentation (this feature)

```
kitty-specs/habits-checkin-d6-extract-01KRNV46/
├── meta.json                            # Mission identity (from `mission create`)
├── spec.md                              # Feature specification (FR/NFR/Constraints)
├── plan.md                              # This file (implementation plan)
├── research.md                          # Phase 0 research findings (R1–R4)
├── data-model.md                        # Phase 1: entities, validation rules, output envelopes
├── contracts/                           # Phase 1: per-helper CLI + I/O contracts
│   ├── compute_today.md
│   ├── query_active_habits.md
│   ├── set_due_dates.md
│   └── exclude_completed.md
├── quickstart.md                        # Phase 1: local run + deploy + verify
├── checklists/
│   └── requirements.md                  # Spec-quality checklist (passing)
├── artifacts/                           # Created in WP01: holds pre-refactor reference message
│   └── reference-checkin-output.txt     # Captured before implementation starts (per Plan Q2)
└── status.events.jsonl                  # Spec-kitty workflow events (managed by spec-kitty)
```

### Source code (repository root)

```
scripts/habits/                          # NEW directory; 4 helpers
├── compute_today.py                     # FR-001: TZ-aware day + date + ET offset + EOD ISO
├── query_active_habits.py               # FR-002: Vikunja query + frequency filter + exclude PAUSED/done
├── set_due_dates.py                     # FR-003: PUT due_date end-of-day-ET per habit ID; partial-failure-tolerant
└── exclude_completed.py                 # FR-004: filter by today's completion-state comment

tests/habits/                            # NEW directory; 4 test modules
├── __init__.py
├── test_compute_today.py
├── test_query_active_habits.py
├── test_set_due_dates.py
└── test_exclude_completed.py

scripts/openclaw/agents/felix-admin-habits/
└── AGENTS.md                            # MODIFIED: Steps 1-4 → helper invocations; Step 5/6 unchanged

docs/design/architecture/data/
└── service-inventory.json               # MODIFIED: habit-checkin entry adds config_files refs + updated_by
```

**Structure Decision**: domain-co-located helpers under `scripts/habits/` per [conventions § 1](../../docs/design/helper-script-conventions.md). Tests parallel structure at `tests/habits/` per `tests/security/` precedent. Single-project layout — no apps/, packages/, or service splits required.

---

## Phase 0: Outline & Research

**Status**: COMPLETE. See [`research.md`](./research.md).

Resolved four research items: Vikunja auth source (R1), HTTP library (R2), test mocking convention (R3), test directory layout (R4). All decisions grounded in existing code + authoritative architecture docs (`credentials-and-secrets.md`, `credential-manifest.json`). No `[NEEDS CLARIFICATION]` markers remain.

Key cross-cutting finding: `scripts/security/credential_health_check/vikunja_writer.py` is the canonical Vikunja-writing precedent and already implements the #112 ET-end-of-day pattern. Per C-003 (no library extraction this mission), helpers duplicate the pattern rather than import it — extraction is justified only when a second mission needs the same primitives.

---

## Phase 1: Design & Contracts

**Status**: COMPLETE.

Artifacts:
- [`data-model.md`](./data-model.md) — entities (Habit, Completion comment, Today context, Helper output envelopes), validation rules, frequency descriptor lexicon, state-transition note (no new transitions; existing Vikunja state preserved)
- [`contracts/`](./contracts/) — four per-helper contract files specifying CLI args, JSON I/O schemas, exit codes, side effects, idempotency posture
- [`quickstart.md`](./quickstart.md) — local development quickstart (running helpers individually with example inputs, running tests, smoke-test on office2)

**No contracts/ schema validation framework introduced** — contracts are agent/human-readable markdown specifications, not enforced via runtime validation. This matches the existing convention in the repo (`vikunja_writer.py`'s contract lives in a sibling markdown file, not in jsonschema/openapi).

---

## Post-design Charter re-check

Re-running gate evaluation after Phase 1 design:

| Gate | Status | Notes after design |
|---|---|---|
| Directive 6 alignment | ✅ PASS | Design follows D6 directly: deterministic work in 4 helpers, AI-judgment-only blocks (Steps 5-6) stay in AGENTS.md |
| Helper-script conventions | ✅ PASS | All 12 conventions sections respected. Library deferral (§ 9) documented in C-003. SUMMARY: line, atomic writes (where applicable), idempotency, failure-mode handling — all designed in. |
| Behavior-preservation contract | ✅ PASS | NFR-002 acceptance via pre-refactor reference capture (Plan Q2 = A); smoke-test diff is the verification path. |
| TZ correctness (#112 regression-prevention) | ✅ PASS | `set_due_dates.py` contract explicitly forbids `Z` suffix; tests cover DST/EST transition dates. |
| Partial-failure resilience | ✅ PASS | NFR-007 expressed concretely in `set_due_dates.py` contract (continue on per-habit failure; exit 1 to signal partial state). |

No new gate violations. Design is consistent with charter + conventions. Ready for `/spec-kitty.tasks` (next step, NOT generated by this command).

---

## Complexity Tracking

*Fill ONLY if Charter Check has violations that must be justified.*

| Violation | Why Needed | Simpler Alternative Rejected Because |
|---|---|---|
| — | No charter violations | — |

No charter violations to track. Mission is canonical D6 application; design follows draft conventions; deviations (library deferral) are explicitly governed by C-003 and traceable to the conventions doc's "don't pre-extract" guardrail.

---

## Branch contract (restating per mandatory)

Current branch at plan start: **main**
Planning/base branch for this mission: **main**
Final merge target for completed changes: **main**
Branch matches target: **✓**

Completed changes from this mission merge into `main` as per the standard spec-kitty merge flow. No worktrees are created during specify/plan; worktrees will be created later during `/spec-kitty.implement` (one per execution lane).

---

## Next step

`/spec-kitty.tasks` — to be invoked by the user when ready to generate work packages. This plan does not generate `tasks.md` or `tasks/` content per the mandatory STOP point in the `/spec-kitty.plan` command file.

Recommended task structure for the user to consider during `/spec-kitty.tasks`:
- 1 WP per helper + its tests (4 WPs in the 200-500-line spec-kitty sweet spot each)
- 1 WP for AGENTS.md refactor + service-inventory update + deploy + smoke test
- Total: ~5 WPs, executable in dependency order (4 helpers can be parallel after the reference-capture preamble; AGENTS.md WP depends on all four helpers being approved)

But this is a recommendation only — `/spec-kitty.tasks` runs its own structuring logic and may decompose differently. Stopping here per the command file's MANDATORY STOP.
