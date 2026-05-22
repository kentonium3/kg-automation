# Implementation Plan: Habits check-in + reply scripts-first port

**Mission**: `habits-checkin-reply-scripts-first-01KS86ZQ`
**Mission ID**: `01KS86ZQE8GSZ77ZSGSSQMN08K`
**Branch**: `main` (planning + merge target; matches current)
**Date**: 2026-05-22
**Spec**: [spec.md](spec.md) · **Source issue**: [#371](https://github.com/kentonium3/kg-automation/issues/371) · **Pattern source**: mission #309 (escalation port)

## Summary

Port the `felix-admin-habits` morning check-in + reply parsing to a scripts-first pattern, mirroring mission #309. Adds three helper scripts under `scripts/habits/` (morning list emitter, reply parser, narrow-LLM disambiguator), persists a per-date canonical-list JSON artifact, cuts `AGENTS.md` to ≤14K source chars to stay within the openclaw effective budget, and re-enables the habits cron post-cutover. No changes to existing Phase 3/5 helpers (record_completion, reconcile, backfill) or to the Phase 2 state_log library. Tonight's target: production cutover before tomorrow morning's 7:05 AM ET cron.

## Technical Context

**Language/Version**: Python 3.10+ (matches existing `scripts/habits/` baseline).
**Primary Dependencies**: stdlib (`json`, `argparse`, `pathlib`, `datetime`, `re`, `sys`, `urllib`, `subprocess`) plus `scripts.common.state_log` (Phase 2) plus `scripts.habits.query_active_habits_v2` + `scripts.habits.exclude_completed_v2` for habit-set computation. For the narrow-LLM disambiguator: `anthropic` SDK (already a dependency from #343).
**Storage**:
- Vikunja v0.24.6 (production habit task state) — read-only for the morning-list helper; existing `record_completion.py` is the only writer.
- Per-date JSON artifact at `/data/services/openclaw/state/habits/morning-checkin-<YYYY-MM-DD>.json` — new file class per FR-001.
**Testing**: pytest with mocked `urllib` for the Vikunja API surface + mocked Anthropic SDK for the disambiguator. New tests live under `tests/habits/`. ≥85% line + branch per NFR-002.
**Target Platform**: Linux (office2, Ubuntu 24.04 LTS); macOS for unit-test dev.
**Project Type**: Single project. Helpers in `scripts/habits/` alongside existing Phase 3+5 helpers.
**Performance Goals**: morning-list emission ≤10s (NFR-003), reply parsing ≤5s per typical reply (NFR-003).
**Constraints**: No Phase 3/5 helper modifications (C-001); no escalation code touched (C-002); no Phase 2 library modifications (C-003); cron disabled until merge (C-004); agent stays thin (C-005); reply-grammar range syntax out of scope (C-006); arch docs in-mission (C-007); Observed L2 autonomy (C-008); second-brain privacy (C-009).
**Scale/Scope**: 8-12 active habits per day. State artifact ~1KB per date file (NFR-005). Reply parsing handles tokens ≤20 typical per reply.

## Charter Check

*GATE: Must pass before Phase 0 research. Re-check after Phase 1 design.*

Charter context (compact mode): no enforced directives or tactics surfaced for this action. Felix Constitution Directive 6 (deterministic vs stochastic split) actively supports the design: ordering + position-matching are deterministic and move to scripts; LLM judgment is reserved for the narrow ambiguity-resolution surface. Directive 5 (machine-readable JSON authoritative) supports the persisted morning-list artifact as the canonical ordering substrate. **No charter violations.**

## Project Structure

### Documentation (this feature)

```
kitty-specs/habits-checkin-reply-scripts-first-01KS86ZQ/
├── plan.md                  # This file
├── spec.md                  # Mission specification
├── research.md              # Phase 0 — engineering decisions (this pass)
├── data-model.md            # Phase 1 — JSON artifact schemas, parser output schema, AGENTS.md target structure
├── quickstart.md            # Phase 1 — cutover playbook (re-enable cron, manual verification, rollback)
├── contracts/               # Phase 1 — Python + CLI surfaces
│   ├── api.md               # Python function signatures
│   └── cli.md               # CLI flags + exit codes
├── checklists/
│   └── requirements.md      # Spec quality checklist (from specify phase)
└── tasks/                   # Phase 2 — work packages (NOT created here)
```

### Source Code (repository root)

```
scripts/habits/                                # EXTENDS existing directory
├── (existing Phase 3+5 files unchanged)
├── record_completion.py                       # UNCHANGED — Phase 3 helper, contract fixed (C-001)
├── reconcile_completions.py                   # UNCHANGED — Phase 3 helper
├── backfill_jsonl_from_comments.py            # UNCHANGED — Phase 4 helper
├── query_active_habits_v2.py                  # UNCHANGED — consumed by new morning_checkin_list
├── exclude_completed_v2.py                    # UNCHANGED — consumed by new morning_checkin_list
│
├── morning_checkin_list.py                    # NEW — FR-001, FR-002, FR-007
├── parse_morning_reply.py                     # NEW — FR-003, FR-004, FR-005, FR-008, FR-009
├── judgment/                                  # NEW subdir (mirrors scripts/doc_audit/judgment/)
│   ├── __init__.py
│   ├── disambiguate_reply.py                  # NEW — FR-006 narrow LLM judgment
│   └── prompts/
│       └── disambiguate_reply.prompt.md       # NEW — cache-aware prompt template
└── (other UNCHANGED files)

scripts/openclaw/agents/felix-admin-habits/
└── AGENTS.md                                  # MODIFIED — cut to ≤14K source chars (FR-011)

tests/habits/                                  # EXTENDS existing directory
├── (existing Phase 3+5 tests unchanged)
├── test_morning_checkin_list.py               # NEW
├── test_parse_morning_reply.py                # NEW
├── test_disambiguate_reply.py                 # NEW
└── fixtures/                                  # NEW (if needed for test inputs)

docs/design/architecture/data/
├── service-inventory.json                     # MODIFIED — register new helpers (C-007)
└── data-flows.json                            # MODIFIED — new write/read paths (C-007)

docs/runbooks/
└── habits-ops.md                              # MODIFIED — updated tick flow, cutover steps, rollback (C-007)

/data/services/openclaw/state/habits/           # NEW subdir on office2 (or under existing state dir)
└── morning-checkin-<YYYY-MM-DD>.json           # Per-date persisted artifact (FR-001)
```

**Structure Decision**: Single project. New helpers under `scripts/habits/`. The `scripts/habits/judgment/` subdir mirrors `scripts/doc_audit/judgment/` from #343 so the narrow-LLM pattern is consistent across the codebase. State files live under a new `habits/` subdir of the existing openclaw state dir (parallel to `escalation/`).

## Complexity Tracking

No charter violations. Three design tensions worth flagging:

1. **The disambiguator is a new LLM-judgment surface in habits.** Habits today has zero LLM calls (Phase 3-5 made everything deterministic). Introducing it for ambiguity-resolution carries a small token-cost ongoing. Mitigation: the disambiguator only fires when the deterministic parser emits `judgment_required` — most replies will produce zero LLM calls. Worst case: ~2-3 calls per day if Kent uses ambiguous shorthand.

2. **AGENTS.md cuts are subtractive, not additive.** Easy to over-cut. Mitigation: a dedicated audit task (mirror WP07 cycle 2/3 of mission #309) that verifies the cut version retains: identity, autonomy declaration, tick-workflow skeleton (invoke helpers + iterate + ask clarifying questions), Tailscale connectivity reminders, fallback behavior on tool failure.

3. **The morning-list artifact lifetime is implicit.** Files accumulate at ~1 per day = 365/year. Eventually needs a cleanup convention (e.g., archive files older than 30 days). Out of scope for this mission; will be documented in habits-ops.md as an open operational item.

---

## Plan

Both phases (research + design) execute in this single planning pass. The ADR-0002 and mission #309 patterns close most of the design space; remaining decisions are tactical.

### Phase 0 — Research artifacts

See [research.md](research.md). Engineering decisions captured:

1. **State artifact location + naming** — `/data/services/openclaw/state/habits/morning-checkin-<YYYY-MM-DD>.json`. Date is in `America/New_York` to match Kent's local calendar (the day "today" means Kent's day, not UTC).
2. **Atomic write of the artifact** — write to `<path>.tmp`, fsync, rename. No state_log library involved (the artifact is not a JSONL append-record; it's a per-date snapshot).
3. **Parser deterministic-match rules** — exact title match first; case-insensitive simple-substring match second; "all done" family third. Anything else routes to `judgment_required`.
4. **Disambiguator prompt structure** — system prompt explains the task, user prompt provides reply text + candidates. Single-turn. Returns chosen task_id OR `"clarify"`. Cache-aware (system prompt cached; user prompt varies).
5. **Disambiguator model** — Haiku 4.5 (matches #343's `claude-haiku-4-5` for the doc-auditor judgment surface). Fast + cheap; sufficient capability for this narrow choice.
6. **Disambiguator API key** — same path as doc-auditor: `/data/services/openclaw/secrets/anthropic`.
7. **Reply special-token taxonomy** — `"all done"`, `"done with everything"`, `"everything done"`, plus close paraphrases. Deterministic enumeration in the parser; no LLM needed for these.
8. **Number range syntax** — out of scope (C-006). Comma-separated single positions only.
9. **Idempotency** — the parser does NOT directly dedup; idempotency comes from `record_completion.py`'s existing `idempotent_record_event` contract. Multiple replies same day flow through the normal dedup.
10. **AGENTS.md cut targets** — remove §"Level determination algorithm" prose (no longer needed; helper computes), §"Completion marking → Recognize natural language" enumerated examples (helper enumerates them), §"Match against habit titles using fuzzy matching" prose (helper handles), and §"If Kent references numbers... match against the numbered list from the most recent check-in message in this session" (the bug-line; helper persists list). Keep: governance, identity, output discipline, scope, fallback-on-helper-failure, helper-invocation skeleton, ambiguity-clarification protocol.
11. **Cutover sequence** — manual: pull repo on office2 → smoke-test helpers via CLI → diff old vs new AGENTS.md → cp new AGENTS.md to deploy path → manual tick trigger → verify journalctl shows no truncation warning → verify persisted JSON appears → simulated reply → verify recorded JSONL → re-enable cron.

### Phase 1 — Design artifacts

- [data-model.md](data-model.md) — Morning-list JSON schema, parser-output JSON schema, disambiguator I/O contract, AGENTS.md target outline
- [contracts/api.md](contracts/api.md) — Python function signatures for `morning_checkin_list`, `parse_morning_reply`, `disambiguate_reply`
- [contracts/cli.md](contracts/cli.md) — CLI surface, flags, exit codes (mirror mission #309 contract style)
- [quickstart.md](quickstart.md) — cutover playbook (pre-flight, deploy, manual tick verification, re-enable cron, rollback)

### Charter re-check (post-design)

Same outcome as pre-design — no charter directives constrain this mission. Re-check pass.

---

## Branch contract (restated)

- **Current branch at plan start**: `main`
- **Planning/base branch**: `main`
- **Final merge target**: `main`
- **branch_matches_target**: `true`

Completed changes from this mission merge into `main`.

---

## Stop

Planning artifacts complete. Next: `/spec-kitty.tasks` to break the plan into work packages.
