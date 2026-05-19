# Shared JSONL state-log library — Specification

**Mission**: `shared-jsonl-state-log-library-01KS0E9A`
**Mission ID**: `01KS0E9A6TZBA9AWT97DR1XMQB`
**Mission type**: software-dev
**Source**: GitHub issue [#305](https://github.com/kentonium3/issues/305) (Phase 2 of ADR-0002)
**Risk tier**: 3 (Logic / Workflow — standard)
**Created**: 2026-05-19

---

## Overview

Build the shared JSONL state-log foundation library that all Vikunja-touching Felix agents will use as canonical history per [ADR-0002 Q5-C](../../docs/design/architecture/adr/0002-felix-vikunja-task-model.md). This phase is a pure foundation — no agent consumes it yet. Phases 3 through 7 of ADR-0002 are the downstream consumers (habits, escalation, tasker/enrichment migrations).

The library replaces three separate in-prompt LLM parsers (one per domain) with a single deterministic helper. State values per domain are constrained by enums enforced at append time, eliminating typo-induced silent corruption of the idempotency dedup mechanism.

---

## User Scenarios & Testing

### Primary actor

The `claude` user on office2, operating either via the `felix-admin-capture`, `felix-admin-habits`, or `felix-admin-escalation` agents (future phases) or via direct CLI invocation by the operator.

### Scenario 1 — Agent appends a habit completion

A morning-cron agent confirms via WhatsApp that Kent completed a wake-time habit. The agent calls `append("habits", record)` with `task_id=14, date="2026-05-19", state="complete", source="whatsapp"`. The library validates the record, acquires an exclusive file lock on `/data/services/openclaw/state/habits-history.jsonl`, appends one line, releases the lock, and returns success. A subsequent retry of the same record (same `task_id + date + state`) is a no-op.

### Scenario 2 — Backfill from Vikunja UI completion

The `reconcile_completions.py` helper (built in a later phase) detects that Kent marked a habit done in the Vikunja UI. It calls `append("habits", {..., source: "vikunja-ui", timestamp: <vikunja_done_at>})`. Append succeeds. If reconcile runs twice for the same backfill, the second call is a no-op.

### Scenario 3 — Agent queries history for context

The escalation agent needs to know whether a task was escalated yesterday. It calls `read("escalation", task_id=42, date_from="2026-05-18", date_to="2026-05-19")` and gets back a list of zero or more matching records.

### Scenario 4 — Typo'd state rejected at append time

A future consumer agent emits `state="Complet"` (typo). `append()` raises `ValueError` before any I/O occurs. The dedup key never gets corrupted. The consumer learns of the bug immediately.

### Scenario 5 — Concurrent writes (defensive)

Two processes attempt to `append` to the same domain log simultaneously. fcntl-style exclusive locking serializes the writes — both records land cleanly on adjacent lines with no interleaving and no data loss.

---

## Functional Requirements

| ID | Requirement | Status |
|---|---|---|
| FR-001 | Library `scripts/common/state_log.py` exports two public functions: `append(domain: str, record: dict) -> None` and `read(domain: str, **filters) -> list[dict]`. | Active |
| FR-002 | `append` writes a single JSON line to `/data/services/openclaw/state/<domain>-history.jsonl` (one file per known domain). | Active |
| FR-003 | `append` validates that `record` has all required fields (`domain`, `task_id`, `title`, `date`, `state`, `source`, `timestamp`) and rejects records missing any field with a `ValueError`. | Active |
| FR-004 | `append` validates that `record["state"]` is a member of the per-domain enum (see Key Entities → State enums). Records with invalid state values are rejected with `ValueError` before any I/O. | Active |
| FR-005 | `append` validates field types: `task_id` is int, `title` is non-empty str, `date` is an ISO-8601 date string (YYYY-MM-DD), `state` and `source` are strings, `timestamp` is an ISO-8601 datetime string with UTC offset, `note` (if present) is str-or-null. | Active |
| FR-006 | `append` is idempotent on the `(task_id, date, state)` tuple within a domain — re-appending a record whose tuple matches an existing line is a no-op (no write performed, no error raised). | Active |
| FR-007 | `append` acquires an exclusive fcntl/flock lock on the target file for the duration of the read-existing + check-idempotency + write sequence. | Active |
| FR-008 | `append` ensures the parent directory exists (`/data/services/openclaw/state/`); creates it with mode `0775` claude:secondbrain if absent. | Active |
| FR-009 | `append` ensures target file permissions are mode `0664`, owner claude:secondbrain on creation. | Active |
| FR-010 | `read` accepts these optional filter kwargs: `task_id` (int), `date` (str — exact match), `date_from` / `date_to` (str — inclusive range), `state` (str), `source` (str). Returns a list of matching record dicts in append order. | Active |
| FR-011 | `read` returns an empty list (not an error) if the domain log file does not exist yet. | Active |
| FR-012 | The schema documentation lives at `docs/design/architecture/data/agent-state-log-schema.md` and authoritatively describes the JSONL shape, the per-domain state enums, and the idempotency contract. | Active |
| FR-013 | The three known domain enums (habits, escalation, enrichment) are defined in code (importable constants) and reproduced in the schema doc. | Active |

## Non-Functional Requirements

| ID | Requirement | Threshold | Status |
|---|---|---|---|
| NFR-001 | `append` of a single record (including idempotency check) completes within 50 ms p99 on office2 when the target file has up to 10,000 existing lines. | < 50 ms p99 | Active |
| NFR-002 | `read` with a single filter completes within 200 ms p99 on a 10,000-line file. | < 200 ms p99 | Active |
| NFR-003 | Concurrent `append` calls from two processes to the same domain produce two distinct, well-formed JSON lines with no interleaving, no truncation, no data loss. Verified by a multi-process test in CI. | 100% pass rate over 100 concurrent-write trials | Active |
| NFR-004 | Library depends only on Python stdlib (no `pip install` requirement). Specifically: `json`, `fcntl`, `pathlib`, `datetime`, `typing`, and `os`. | 0 third-party dependencies | Active |
| NFR-005 | Test coverage for `state_log.py` is ≥ 90% line + branch (measured by `coverage.py`). | ≥ 90% | Active |

## Constraints

| ID | Constraint | Status |
|---|---|---|
| C-001 | State files MUST live under `/data/services/openclaw/state/` (not `~/second-brain/agents/state/`). Rationale: `/data` is on the durable drive backed up by Restic; state logs are operational records that survive vault re-syncs. | Active |
| C-002 | The library does NOT yet consume from Phases 3-7 — no production agent code is modified in this phase. Phase 2 ships the library + tests + schema doc only. | Active |
| C-003 | Schema enforcement is strict on required fields AND on the per-domain `state` enum. Unknown fields are silently ignored (forward-compatible) but never required. | Active |
| C-004 | The library MUST not perform any network I/O (no Vikunja calls, no OpenClaw gateway calls). It is purely a local-disk JSONL helper. | Active |
| C-005 | The library MUST be safely callable from both Python scripts and from LLM agent contexts via `Bash` exec (i.e., usable as both a module and a CLI). A thin `__main__` wrapper exposing `append` via JSON-on-stdin and `read` via flag args is sufficient. | Active |
| C-006 | No production state is mutated during this phase. Rollback is `rm -rf` of the new files (library + tests + schema doc + `/data/services/openclaw/state/`). | Active |

---

## Key Entities

### State enums per domain

State value vocabularies enforced by `append`. New states require a PR to the library + schema doc + tests.

| Domain | Allowed `state` values |
|---|---|
| `habits` | `complete`, `incomplete`, `skipped` |
| `escalation` | `triggered`, `level-1`, `level-2`, `resolved`, `dismissed` |
| `enrichment` | `pending`, `enriched`, `deferred`, `failed` |

These are the initial sets. Each consumer phase (3, 6, 7) MAY propose additions during its own discovery — additions land as PRs to this library before the consumer phase merges.

### JSONL record schema

```json
{
  "domain": "<one of: habits, escalation, enrichment>",
  "task_id": <integer — Vikunja task ID>,
  "title": "<non-empty string — denormalized for human-readable history>",
  "date": "<YYYY-MM-DD — the day this record is FOR>",
  "state": "<one of the per-domain enum values above>",
  "source": "<short string identifying the writer: whatsapp, vikunja-ui, cron, manual, ...>",
  "note": "<optional string or null — freeform per-record annotation>",
  "timestamp": "<ISO-8601 datetime with UTC offset — when this record was WRITTEN>"
}
```

Note: `date` ≠ `timestamp`. `date` is the day-of-record (the habit "for"); `timestamp` is the wall-clock time the record was written. This distinction lets backfills work correctly.

### File layout

```
/data/services/openclaw/state/        # 0775 claude:secondbrain
├── habits-history.jsonl              # 0664 claude:secondbrain
├── escalation-history.jsonl          # 0664 claude:secondbrain
└── enrichment-history.jsonl          # 0664 claude:secondbrain
```

---

## Success Criteria

| ID | Criterion |
|---|---|
| SC-001 | A consumer can call `append("habits", record)` and observe the record persisted as a single line in `habits-history.jsonl` within 50 ms. |
| SC-002 | A consumer can call `read("habits", task_id=14)` and recover all records for that task across the file's history, in append order, within 200 ms p99 for files up to 10,000 lines. |
| SC-003 | A consumer that emits a typo'd state value (e.g., `"complet"`) sees a `ValueError` from `append` before any I/O; the file on disk is unchanged. |
| SC-004 | Two concurrent processes appending to the same domain produce two well-formed lines with no interleaving, verified by an automated test running 100 concurrent-write trials with zero corruption. |
| SC-005 | A retry of an `append` whose `(task_id, date, state)` tuple matches an existing line is a no-op — no write, no error, same file size. Verified by test. |
| SC-006 | New developer (or LLM agent) can answer "what states does the escalation domain allow?" by reading exactly one file (`scripts/common/state_log.py` or the schema doc) — no grep across the codebase. |
| SC-007 | All `state_log.py` source lines are exercised by the test suite at ≥ 90% line + branch coverage. |

---

## Assumptions

1. The three target domain enums above are correct for Phase 2's scope. Consumer phases (3, 6, 7) MAY add states via PRs to the library before they merge.
2. fcntl-style file locking is sufficient for the concurrency model on office2 (Linux, single host). Cross-host locking is out of scope — there is only one host.
3. The `/data` mount on office2 has free space and is included in the existing Restic backup. No new backup configuration is required for this phase.
4. Python ≥ 3.10 is available on office2 (already true per the existing `scripts/` pattern). No additional runtime requirements.
5. The library is invoked synchronously by callers; there is no need for async I/O or queueing in Phase 2.

---

## Out of scope

The following are NOT delivered by Phase 2 and are explicitly deferred:

- Any agent's adoption of the library (Phases 3 / 6 / 7)
- Migration of any existing in-prompt parsers (Phases 3, 6, 7)
- Rollover / rotation of log files by size or date (deferred — append-forever is acceptable given expected growth rate of ~1-5 records/day per domain)
- A query language richer than simple field filters (deferred until a consumer needs it)
- Cross-domain joins (each domain log is independent)
- The webhook receiver from ADR-0002 Q4 (deferred to ADR-0002 Phase 8)
- Migrating `~/second-brain/agents/state/inbox-routing.jsonl` to the new pattern (the inbox-routing log has different semantics and stays where it is)
