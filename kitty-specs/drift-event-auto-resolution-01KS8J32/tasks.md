# Tasks: Drift event auto-resolution via LLM judgment

**Mission**: `drift-event-auto-resolution-01KS8J32`
**Mission ID**: `01KS8J321F8KE7369R3DA02329`
**Branch**: `main` (planning + merge target)
**Generated**: 2026-05-22

6 work packages, 32 subtasks. Mirrors mission #309 / #371 lane structure (parallel helper lanes feeding a single integration WP; docs in their own lane).

---

## Subtask Index

| ID | Description | WP | Parallel |
|---|---|---|---|
| T001 | drift_interpretation.py module skeleton + DriftVerdict/DriftInterpretationContext/DocTarget dataclasses + module constants | WP01 | [D] | [D] |
| T002 | drift_interpretation.prompt.md — cache-aware system prompt with rules, examples, output schema | WP01 | [D] |
| T003 | Doc-state truncation helper (D2 tiered strategy by file size) | WP01 | [D] |
| T004 | interpret() function — LLM call, response parsing, schema validation, confidence demotion | WP01 | [D] |
| T005 | Retry policy wrapper (30s/60s/120s backoff per D6) | WP01 | [D] |
| T006 | CLI surface for drift_interpretation (exit codes 0/1/3/5) | WP01 | [D] |
| T007 | Tests for drift_interpretation — mocked SDK, all verdict paths, edge cases, ≥85% coverage | WP01 | [D] |
| T008 | drift_ledger.py module skeleton + AuditLedgerEntry dataclass + module constants | WP02 | [D] |
| T009 | append() function — atomic write, JSONL serialization, field ordering | WP02 | [D] |
| T010 | read_window() — tail-from-end for large files; window filtering | WP02 | [D] |
| T011 | compute_triage_rate() + outcome breakdown helpers | WP02 | [D] |
| T012 | CLI surface for drift_ledger (summary / tail / triage-rate subcommands) | WP02 | [D] |
| T013 | Tests for drift_ledger — atomicity, JSONL parse round-trip, window correctness, ≥85% coverage | WP02 | [D] |
| T014 | data_model.py — add `drift_derived` to ProposedEdit change_type documentation | WP03 | [D] |
| T015 | drift_to_proposed_edit.py — build() function with pre-condition validation | WP03 | [D] |
| T016 | Routing package init (__init__.py with public surface) | WP03 | [D] |
| T017 | Tests for translator — pre-conditions, out-of-set rejection, ≥85% coverage | WP03 | [D] |
| T018 | handle_drift_events — load config.toml drift_interpretation block | WP04 | [D] |
| T019 | handle_drift_events — invoke Moment 0 behind config flag | WP04 | [D] |
| T020 | handle_drift_events — verdict routing (PROPOSED_EDIT → translator → tier_classification; JUDGMENT_REQUIRED → file issue; NO_CHANGE_NEEDED → ledger only) | WP04 | [D] |
| T021 | handle_drift_events — ledger entry append for every event (including RETRY_EXHAUSTED fallback) | WP04 | [D] |
| T022 | handle_drift_events — `--reset-cursor` flag | WP04 | [D] |
| T023 | Extended tests for handle_drift_events — config-disabled fallback, all verdict paths, retry exhausted | WP04 | [D] |
| T024 | cutover_362.py module skeleton + CutoverResult dataclass + marker path constants | WP05 | [D] |
| T025 | GitHub issue query + close-with-comment logic | WP05 | [D] |
| T026 | Cursor reset + marker write (idempotent; tempfile + rename) | WP05 | [D] |
| T027 | CLI flags (--dry-run, --force) + main() entry point | WP05 | [D] |
| T028 | Tests for cutover_362 — mocked gh, mocked filesystem, idempotency, dry-run, --force | WP05 | [D] |
| T029 | service-inventory.json update — register new modules + extend judgment_moments | WP06 | [D] |
| T030 | data-flows.json update — Moment 0 LLM call path; ledger write paths | WP06 | [D] |
| T031 | Markdown architecture views match JSON sources (service-inventory.md, data-flows.md, data-flows.view.md) | WP06 | [D] |
| T032 | doc-auditor-driver-ops.md — add Moment 0 to operations description; document config flag + ledger queries | WP06 | [D] |

---

## Dependency Graph

```
WP01 (drift_interpretation) ──┐
WP02 (drift_ledger) ──────────┼──> WP04 (handle_drift_events) ──> WP05 (cutover_362)
WP03 (translator) ────────────┘
                               
WP06 (docs)  [parallel — no code deps]
```

Lanes (post-finalize-tasks):
- **Lane A**: WP01 → WP04 → WP05
- **Lane B**: WP02 → (feeds WP04)
- **Lane C**: WP03 → (feeds WP04)
- **Lane D**: WP06 (fully parallel)

MVP scope: WP01 + WP02 + WP03 + WP04 delivers a working pipeline. WP05 (cutover) is one-shot operational support; without it the backlog stays manual. WP06 (docs) lags slightly without breaking the pipeline.

---

## Phase 1 — Helpers (parallel lanes)

### WP01 — drift_interpretation module + prompt

**Goal**: Implement the Moment 0 LLM judgment surface. This is the load-bearing module of the entire mission — it produces the verdict that determines downstream routing.

**Priority**: P0 (blocks WP04)
**Dependencies**: none
**Independent test**: `pytest tests/doc_audit/judgment/test_drift_interpretation.py -v` ≥85% coverage. `python3 -m scripts.doc_audit.judgment.drift_interpretation --input-file tests/doc_audit/fixtures/drift_event_openclaw_cron.json` returns a valid `DriftVerdict` JSON (with mocked SDK).

**Estimated prompt size**: ~480 lines (7 subtasks)
**Prompt**: [WP01-drift-interpretation.md](tasks/WP01-drift-interpretation.md)

Included subtasks:
- [x] T001 Module skeleton + dataclasses + module constants (WP01)
- [x] T002 Cache-aware prompt (WP01)
- [x] T003 Doc-state truncation helper (WP01)
- [x] T004 interpret() core function (WP01)
- [x] T005 Retry policy wrapper (WP01)
- [x] T006 CLI surface (WP01)
- [x] T007 Tests (WP01)

**Risks**:
- Prompt drift — system prompt must produce strict JSON; small changes can break parsing. Tests must cover all 3 verdict shapes + malformed responses.
- Truncation heuristic — D2 tiered strategy is deterministic but the LLM may reason worse with truncated context; reserve a fixture for a >32KB target doc.
- Retry policy interaction with NFR-002 — single-call P95 ≤15s, end-to-end ≤90s P95. Need to test that retries don't blow the latency budget.

---

### WP02 — drift_ledger module

**Goal**: Implement the append-only JSONL ledger that captures verdict + outcome per drift event. Powers NFR-001 triage rate metric and operator observability.

**Priority**: P0 (blocks WP04)
**Dependencies**: none
**Independent test**: `pytest tests/doc_audit/output/test_drift_ledger.py -v` ≥85% coverage. Atomic-write race test passes. CLI `summary` + `triage-rate` subcommands run cleanly against a fixture ledger.

**Estimated prompt size**: ~360 lines (6 subtasks)
**Prompt**: [WP02-drift-ledger.md](tasks/WP02-drift-ledger.md)

Included subtasks:
- [x] T008 Module skeleton + AuditLedgerEntry dataclass (WP02)
- [x] T009 append() — atomic write (WP02)
- [x] T010 read_window() — efficient tail (WP02)
- [x] T011 compute_triage_rate() + helpers (WP02)
- [x] T012 CLI surface (WP02)
- [x] T013 Tests (WP02)

**Risks**:
- Atomic write semantics — naive `open("a")` works under single-writer; ensure flush+fsync. Tests must cover partial-write scenarios (kill mid-write).
- Field ordering — deterministic diffing requires preserved field order. Use `json.dumps(..., sort_keys=False)` and pin dict insertion order.
- Large ledger reads — `read_window()` for a 10MB+ ledger must not load the whole file. Implement tail-scan.

---

### WP03 — Translator + ProposedEdit extension

**Goal**: Implement the thin translator that converts a `DriftVerdict (PROPOSED_EDIT)` into a `ProposedEdit` dataclass that the existing `tier_classification` consumes. Also documents the new `drift_derived` change_type value.

**Priority**: P0 (blocks WP04)
**Dependencies**: none (uses DriftVerdict TYPE from WP01 but doesn't require WP01 implementation; can stub the type)
**Independent test**: `pytest tests/doc_audit/routing/test_drift_to_proposed_edit.py -v` ≥85% coverage. Pre-condition violations raise `ValueError`. Out-of-set `doc_path` rejection tested.

**Estimated prompt size**: ~220 lines (4 subtasks — slightly under target range but cohesive)
**Prompt**: [WP03-translator.md](tasks/WP03-translator.md)

Included subtasks:
- [ ] T014 data_model.py docstring update (WP03)
- [ ] T015 drift_to_proposed_edit.py — build() (WP03)
- [ ] T016 Routing package init (WP03)
- [ ] T017 Tests (WP03)

**Risks**:
- Coupling to data_model.py — only docstring change, but the change_type set is documented in multiple places (SKILL.md §4.1). Don't update SKILL.md from this WP (out of scope; the change is additive and tier_classification handles unknown values via JUDGMENT fallback).
- Out-of-set rejection — must be testable without requiring a full DriftInterpretationContext; the translator should accept a minimal allowed-doc-paths list as input.

---

## Phase 2 — Integration

### WP04 — handle_drift_events integration

**Goal**: Wire Moment 0 into the existing drift-event processing pipeline. This is the integration point where all upstream pieces converge.

**Priority**: P0 (blocks WP05)
**Dependencies**: WP01, WP02, WP03
**Independent test**: `pytest tests/doc_audit/helpers/test_handle_drift_events.py -v` ≥85% coverage including new paths. Smoke run with `[drift_interpretation].enabled = false` produces pre-#362 behavior (existence test).

**Estimated prompt size**: ~400 lines (6 subtasks)
**Prompt**: [WP04-handle-drift-events.md](tasks/WP04-handle-drift-events.md)

Included subtasks:
- [ ] T018 Config.toml loading (WP04)
- [ ] T019 Moment 0 invocation behind flag (WP04)
- [ ] T020 Verdict routing (WP04)
- [ ] T021 Ledger entry append for every event (WP04)
- [ ] T022 `--reset-cursor` flag (WP04)
- [ ] T023 Extended tests (WP04)

**Risks**:
- Backward compatibility — the existing CLI surface (per C-002) must NOT change. New flags are additive; existing flags + JSON outputs unchanged.
- Failure-mode coverage — RETRY_EXHAUSTED path must fall through to pre-#362 issue filing. Test with mocked LLM that always errors.
- Cursor semantics — cursor advance must happen ONLY on successful event processing (including RETRY_EXHAUSTED, which is "processed but failed" — still cursor-advance to avoid loops).

---

### WP05 — Cutover script

**Goal**: One-shot operator script that closes the 13 known pre-#362 `[doc-audit]` P3 issues + resets cursor + writes marker.

**Priority**: P1 (not strictly required for the pipeline to work; required for clean cutover UX)
**Dependencies**: WP04 (for the `--reset-cursor` flag)
**Independent test**: `pytest tests/doc_audit/helpers/test_cutover_362.py -v` ≥85% coverage. Mocked gh + mocked filesystem. Idempotency verified.

**Estimated prompt size**: ~280 lines (5 subtasks)
**Prompt**: [WP05-cutover-script.md](tasks/WP05-cutover-script.md)

Included subtasks:
- [ ] T024 Module skeleton + CutoverResult (WP05)
- [ ] T025 GitHub close-with-comment (WP05)
- [ ] T026 Cursor reset + marker write (WP05)
- [ ] T027 CLI flags + main() (WP05)
- [ ] T028 Tests (WP05)

**Risks**:
- GitHub rate-limit — closing 13 issues with comments is ~26 API calls. Stay under the 5000/hr authenticated limit easily, but space calls slightly (~0.5s apart) to be polite.
- Marker file race — only one cutover process per host; no concurrency concern. But the tempfile+rename pattern still applies for resilience.

---

## Phase 3 — Documentation

### WP06 — Architecture docs + ops runbook

**Goal**: Update arch JSON + markdown views + ops runbook for the v2 pipeline. Implements C-007 (in-mission doc updates per Constitution Directive 5).

**Priority**: P1
**Dependencies**: none (fully parallel)
**Independent test**: `python3 -c "import json; json.load(open('docs/design/architecture/data/service-inventory.json'))"` succeeds. Runbook walks the cutover end-to-end without dangling references.

**Estimated prompt size**: ~240 lines (4 subtasks)
**Prompt**: [WP06-architecture-docs.md](tasks/WP06-architecture-docs.md)

Included subtasks:
- [x] T029 service-inventory.json update (WP06)
- [x] T030 data-flows.json update (WP06)
- [x] T031 Markdown views match JSON (WP06)
- [x] T032 doc-auditor-driver-ops.md update (WP06)

**Risks**:
- JSON ↔ markdown drift — every JSON entry needs a markdown counterpart.
- Existing `task-detection` cron drift on `felix-admin-tasker` entry (separate issue, but discovered during #310 spec-readiness probe) is out of scope here.

---

## Estimated size summary

| WP | Subtasks | Est. lines |
|---|---|---|
| WP01 | 7 | ~480 |
| WP02 | 6 | ~360 |
| WP03 | 4 | ~220 |
| WP04 | 6 | ~400 |
| WP05 | 5 | ~280 |
| WP06 | 4 | ~240 |
| **Total** | **32** | **~1980** |

All WPs within ideal range (3-7 subtasks, 200-500 lines).

---

## Next step

Run `spec-kitty agent mission finalize-tasks --mission drift-event-auto-resolution-01KS8J32 --json` to parse dependencies + commit. Then `/spec-kitty.implement` (or auto-drive via the spec-kitty-implement-review skill).
