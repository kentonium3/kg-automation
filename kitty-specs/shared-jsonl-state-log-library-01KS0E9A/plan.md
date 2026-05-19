# Implementation Plan: Shared JSONL state-log library

**Mission**: `shared-jsonl-state-log-library-01KS0E9A`
**Mission ID**: `01KS0E9A6TZBA9AWT97DR1XMQB`
**Branch**: `main` (planning + merge target; matches current)
**Date**: 2026-05-19
**Spec**: [spec.md](spec.md) · **Source issue**: [#305](https://github.com/kentonium3/kg-automation/issues/305) · **ADR**: [0002 Q5-C](../../docs/design/architecture/adr/0002-felix-vikunja-task-model.md)

## Summary

Foundation Python library exposing `append(domain, record)` and `read(domain, **filters)` over per-domain JSONL state logs at `/data/services/openclaw/state/{habits,escalation,enrichment}-history.jsonl`. Strict per-domain state-enum validation. fcntl-based file locking for concurrent-write safety. Idempotent on `(task_id, date, state)`. Pure stdlib (no third-party deps). Foundation only — no consumer agents are touched in this mission; phases 3-7 are the downstream adopters.

## Technical Context

**Language/Version**: Python 3.10+ (matches existing `scripts/` baseline on office2)
**Primary Dependencies**: stdlib only — `json`, `fcntl`, `pathlib`, `datetime`, `typing`, `os`, `dataclasses` (NFR-004)
**Storage**: Local filesystem JSONL files under `/data/services/openclaw/state/` (on the Restic-backed `/data` mount, per C-001)
**Testing**: pytest with coverage measurement (existing pattern in `tests/`); multiprocessing for concurrent-write tests
**Target Platform**: Linux (office2, Ubuntu 24.04 LTS); MacOS dev works too — fcntl is POSIX
**Project Type**: Single project — library lives inside the existing `scripts/` tree alongside `scripts/inbox/`, `scripts/vikunja/`, etc.
**Performance Goals**: append < 50 ms p99 @ 10k-line file (NFR-001); read < 200 ms p99 @ 10k-line file (NFR-002)
**Constraints**: No third-party deps (NFR-004); no network I/O (C-004); no production agent adoption in this phase (C-002); ≥ 90% line + branch coverage (NFR-005)
**Scale/Scope**: ~1-5 records/day/domain expected; horizon is ~10k lines per domain over multiple years; single host

## Charter Check

*GATE: Must pass before Phase 0 research. Re-check after Phase 1 design.*

Charter context (compact mode): no enforced directives or tactics surfaced for this action. The Felix Constitution's Directive 6 (deterministic vs stochastic work split) is the implicit governance — this mission is the realization of that directive for the per-domain state history. **No gate violations.**

## Project Structure

### Documentation (this feature)

```
kitty-specs/shared-jsonl-state-log-library-01KS0E9A/
├── plan.md              # This file
├── spec.md              # Mission specification
├── research.md          # Phase 0 — engineering decisions
├── data-model.md        # Phase 1 — JSONL record + per-domain enums
├── quickstart.md        # Phase 1 — consumer-facing usage snippet
├── contracts/           # Phase 1 — Python API + CLI + JSONL line contracts
│   ├── api.md           # Python function signatures
│   ├── cli.md           # __main__ CLI surface
│   └── jsonl.md         # On-disk record format
└── tasks/               # Phase 2 — work packages (NOT created here)
```

### Source Code (repository root)

```
scripts/
└── common/                          # NEW — created by this mission
    ├── __init__.py                  # empty marker
    ├── state_log.py                 # public API + __main__ CLI wrapper
    └── state_log_schema.py          # DOMAIN_STATES enums + REQUIRED_FIELDS + validators

tests/
└── common/                          # NEW — created by this mission
    ├── __init__.py
    ├── test_state_log_append.py     # append happy path + idempotency + validation rejections
    ├── test_state_log_read.py       # read with each filter combination
    └── test_state_log_concurrent.py # multiprocessing concurrent-append safety

docs/design/architecture/data/
└── agent-state-log-schema.md        # NEW — schema doc (FR-012)

/data/services/openclaw/state/       # NEW directory on office2 — created at first append
├── habits-history.jsonl             # created on first habits append
├── escalation-history.jsonl         # created on first escalation append
└── enrichment-history.jsonl         # created on first enrichment append
```

**Structure Decision**: Single project. Library lives in `scripts/common/` (new module group, anticipating future shared helpers). Module is split into two files for clean separation:
- `state_log.py` — public API (`append`, `read`) + thin `__main__` CLI wrapper
- `state_log_schema.py` — pure data: domain enums, required-field list, type-validator functions. Importable independently so consumer phases can reference the enums without pulling the file-I/O machinery if they don't need it.

## Complexity Tracking

No charter check violations. No complexity to justify.

---

## Plan

Both phases (research + design) execute in this single planning pass. No external research needed (Python stdlib + fcntl + JSONL is well-understood territory).

### Phase 0 — Research artifacts

See [research.md](research.md). Engineering decisions captured:

1. **Locking strategy** — fcntl.LOCK_EX on the data file itself (not a sibling lockfile). Held across the read-check-write sequence.
2. **Idempotency mechanism** — linear scan of existing file for the `(task_id, date, state)` tuple before each write. O(N) per append; acceptable given the small N expected.
3. **Validation implementation** — hand-written validators in `state_log_schema.py`, no jsonschema dependency (NFR-004).
4. **CLI surface** — `__main__` wrapper takes mode (`append` | `read`), reads JSON record on stdin for append, returns matching records on stdout for read.
5. **Concurrent-write test** — multiprocessing-based test spawning N=10 workers, each calling append 10 times against the same domain; assert all 100 records present and well-formed.
6. **Atomic-append technique** — `os.O_APPEND` on file descriptor + `fcntl.LOCK_EX` guarantees the append is atomic at the kernel level once the lock is held.

### Phase 1 — Design artifacts

- [data-model.md](data-model.md) — JSONL record schema, per-domain enums, file layout
- [contracts/api.md](contracts/api.md) — Python function signatures + exceptions raised
- [contracts/cli.md](contracts/cli.md) — `python3 -m scripts.common.state_log ...` surface
- [contracts/jsonl.md](contracts/jsonl.md) — on-disk line format + example records
- [quickstart.md](quickstart.md) — how a Phase 3 consumer (habits agent) will import and call

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
