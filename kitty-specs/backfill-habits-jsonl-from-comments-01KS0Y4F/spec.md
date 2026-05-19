# Backfill habits JSONL from Felix comments — Specification

**Mission**: `backfill-habits-jsonl-from-comments-01KS0Y4F`
**Mission ID**: `01KS0Y4F60A30H8CT28Z3VMVT6`
**Mission type**: software-dev
**Source**: GitHub issue [#307](https://github.com/kentonium3/kg-automation/issues/307) (Phase 4 of ADR-0002)
**Risk tier**: 3 (Logic / Workflow — standard)
**Created**: 2026-05-19

---

## Overview

Phase 4 of ADR-0002 is a one-shot operator-driven helper that reads existing `[Felix]` completion comments from production Vikunja habit tasks and replays them as JSONL entries in `/data/services/openclaw/state/habits-history.jsonl` (the Phase 2 substrate). The goal: preserve historical completion data before Phase 5 cutover (#308) switches the cron to consume the JSONL log as its canonical history source.

This is a Tier-3 mission: no production Vikunja state is mutated. Reads Vikunja comments (GET only), writes to a local JSONL log on office2. The log is append-only; the Phase 2 `state_log.append` library enforces dedup on the `(task_id, date, state)` tuple, making re-runs of the backfill safe and idempotent.

Production data probe on 2026-05-19 found a small dataset: **26 total `[Felix]` comments** across the 8 originally-touched habit tasks, with only **two distinct state values** (`complete` × 24, `will-not-do` × 2). The state-mapping table is therefore tiny and well-bounded — no need for ambiguous fallback logic.

---

## User Scenarios & Testing

### Primary actor

**Kent (operator)** — runs the backfill helper post-Phase-3, post-Tier-2-migration. May invoke `--dry-run` first to review the planned writes + the unmapped-state-values report, then live-runs to persist.

### Scenario 1 — Operator dry-runs the backfill

Kent invokes the helper with `--dry-run`. The helper enumerates the habit tasks (project-scoped to "Habits" per the Phase 3 lesson), fetches each task's comments via `GET /api/v1/tasks/<id>/comments`, parses each comment with the existing `FELIX_COMMENT_PATTERN` regex from `scripts/habits/exclude_completed.py`, maps the state through `HISTORICAL_STATE_MAP`, and PRINTS the planned writes to stdout. No JSONL is written. A summary report at the end shows: records-by-task, records-by-state, comments-skipped-as-malformed, unmapped-state-values (with the original state + the source comment for each), anomalies.

### Scenario 2 — Operator live-runs the backfill

Kent invokes the helper without `--dry-run`. The helper:
1. Creates a pre-backfill snapshot: `cp habits-history.jsonl habits-history.jsonl.pre-phase4-backfill.bak` (skipped if the JSONL log file doesn't yet exist, in which case the snapshot is unnecessary).
2. Enumerates + fetches + parses as in Scenario 1.
3. For each parsed + mapped record, calls `state_log.append("habits", record)` with `source="historical-backfill"` and `timestamp=comment.created`.
4. Prints the summary report.

Re-running the live command is a no-op: the Phase 2 dedup tuple `(task_id, date, state)` means every record already in the log gets skipped on the second pass. The summary report shows zero new writes.

### Scenario 3 — Some comment has an unmapped state

A `[Felix]` comment has `state="partial"` (not in `HISTORICAL_STATE_MAP`). The helper:
- Does NOT call `state_log.append` (so no malformed enum value reaches Phase 2's strict validator).
- Adds the entry to the summary's `unmapped-state-values` section, including the task_id, date, original state, and a snippet of the source comment.
- Continues processing other comments.

The operator decides what to do with the unmapped values: either update `HISTORICAL_STATE_MAP` and re-run (the new mappings will land), or leave them unmapped (they remain lost from JSONL but preserved in the original Vikunja comment).

### Scenario 4 — A comment fails to parse

A comment doesn't match `FELIX_COMMENT_PATTERN` (e.g., it's a freeform note, not a Felix-format record). The helper:
- Does NOT count it as a record (no JSONL write, no mapping attempt).
- Adds it to the summary's `comments-skipped-as-malformed` section with the task_id + a snippet.
- Continues.

This is expected behavior — not every Vikunja comment is a Felix-format completion record.

### Scenario 5 — Operator rolls back

If the operator wants to undo the backfill (e.g., to re-do with a corrected mapping table), they:
- Restore from the `.bak` file: `cp habits-history.jsonl.pre-phase4-backfill.bak habits-history.jsonl`.
- OR run a small filter command to remove `source="historical-backfill"` lines from the JSONL (documented in the helper's `--help` or runbook).

The Vikunja-side comments are untouched and remain the source of truth — rollback doesn't lose data; it just clears the JSONL replay.

---

## Functional Requirements

| ID | Requirement | Status |
|---|---|---|
| FR-001 | A backfill helper at `scripts/habits/backfill_jsonl_from_comments.py` exposes a `backfill()` Python API + a `__main__` CLI per the C-006 dual-surface pattern. | Active |
| FR-002 | The helper enumerates habit tasks via the same project-scoped pattern used by `scripts/habits/reconcile_completions.py` (resolve "Habits" project via `GET /projects`, then `GET /projects/<id>/tasks`). It does NOT use the broad `/tasks/all` endpoint. | Active |
| FR-003 | For each habit task, the helper fetches comments via `GET /api/v1/tasks/<id>/comments` and parses each comment using `FELIX_COMMENT_PATTERN` imported from `scripts/habits/exclude_completed.py`. | Active |
| FR-004 | The helper exports a module-level `HISTORICAL_STATE_MAP` constant mapping historical Felix state strings to the Phase 2 strict enum: `{"complete": "complete", "will-not-do": "skipped"}`. New mappings require editing this constant + re-running the helper. | Active |
| FR-005 | Records whose mapped state lands in `DOMAIN_STATES["habits"] = {complete, incomplete, skipped}` are appended via `state_log.append("habits", record)` with `source="historical-backfill"` and `timestamp` equal to the Vikunja comment's `created` ISO-8601 string. The `date` field is the date parsed from the `[Felix]` comment body (YYYY-MM-DD), and `title` is the Vikunja task's current title. | Active |
| FR-006 | The helper supports `--dry-run`: prints planned writes and the summary report to stdout but issues zero `state_log.append` calls. | Active |
| FR-007 | The live run (without `--dry-run`) is idempotent: re-invocation produces zero new JSONL writes because Phase 2's `(task_id, date, state)` dedup tuple short-circuits the append. | Active |
| FR-008 | Before the first JSONL write in a live run, the helper creates a snapshot copy of the existing `habits-history.jsonl` to a sibling file `habits-history.jsonl.pre-phase4-backfill.bak`. Skipped if the JSONL log file does not yet exist. | Active |
| FR-009 | The helper prints a structured summary report at the end of every run (dry or live), including: total comments fetched, total records appended (or "planned" in dry-run), records-by-task, records-by-state, comments-skipped-as-malformed (count + snippets), unmapped-state-values (count + original state + snippets per occurrence), and any anomalies (e.g., comments with missing `created` field). | Active |
| FR-010 | Comments with a state outside `HISTORICAL_STATE_MAP` are NOT appended to the JSONL; they appear in the `unmapped-state-values` section of the summary report. This prevents corruption of Phase 2's strict-enum dedup key. | Active |
| FR-011 | The helper does NOT modify Vikunja state: no PATCH, no POST, no PUT, no DELETE calls. Only GETs. | Active |
| FR-012 | After successful backfill, `docs/design/architecture/data/data-flows.json` reflects the one-shot backfill flow: `scripts/habits/backfill_jsonl_from_comments.py → state_log.append → habits-history.jsonl` with `kind="write"` and `purpose="One-time backfill of historical Felix comments as JSONL records (source=historical-backfill)"`. `docs/design/architecture/data/service-inventory.json` registers the new script. | Active |

## Non-Functional Requirements

| ID | Requirement | Threshold | Status |
|---|---|---|---|
| NFR-001 | Backfill helper completes a full live run (across all habit tasks) within 60 seconds on a healthy office2 / Vikunja pairing (current production volume is ~26 comments across 8 tasks; well under the threshold). | < 60s wall-clock | Active |
| NFR-002 | `--dry-run` runs in under 30 seconds (no I/O contention from JSONL writes; only HTTP fetches + summary build). | < 30s wall-clock | Active |
| NFR-003 | Net zero new third-party Python dependencies (stdlib + reuses `scripts.common.state_log` from Phase 2 + the regex from `scripts/habits/exclude_completed.py`). | 0 new deps | Active |
| NFR-004 | Test coverage on the new module is ≥85% line + branch (matches the Phase 3 NFR-005 standard for habits-domain code). | ≥ 85% | Active |
| NFR-005 | The helper logs no token contents, no full comment bodies (only first ~80 chars as snippets), and no PII beyond what already appears in the [Felix] comment shape. | No new sensitive-data leakage | Active |

## Constraints

| ID | Constraint | Status |
|---|---|---|
| C-001 | The helper MUST authenticate as `felix-bot` via the token at `/data/services/openclaw/secrets/vikunja-api` (the Phase 1 rotation outcome). | Active |
| C-002 | The helper MUST NOT extend the Phase 2 `DOMAIN_STATES["habits"]` enum. Historical state values that don't map to the enum stay unmapped (per Option B in #307's design discussion, with the mapping table locked to the data observed in the 2026-05-19 probe). | Active |
| C-003 | The helper MUST be callable from both Python (in-process import) and CLI (per the C-006 pattern established in earlier phases — for cron compatibility AND for LLM-agent invocation via Bash exec). | Active |
| C-004 | Reuse `FELIX_COMMENT_PATTERN` from `scripts/habits/exclude_completed.py` — do not duplicate the regex. Single source of truth for the parser. | Active |
| C-005 | The retired workout task (id 17) is in scope: the helper backfills its `[Felix]` comments along with the other habits. The retire-via-`done=true` outcome from Phase 3 does NOT exclude the task from comment-based history backfill. | Active |
| C-006 | The 3 new MWF strength-training tasks (ids 75, 76, 77) created by Phase 3 have zero existing comments — the helper processes them but appends nothing. No-op is the expected outcome for these. | Active |
| C-007 | No production agent or cron is modified by this phase. The backfill is invoked manually by Kent once; subsequent invocations (re-runs) are safe but produce no new writes. | Active |

---

## Key Entities

### `HISTORICAL_STATE_MAP` (canonical for this mission)

```python
HISTORICAL_STATE_MAP: dict[str, str] = {
    "complete": "complete",       # identity (already in Phase 2 enum)
    "will-not-do": "skipped",     # semantic: intentional skip, not failure
}
```

Production probe found exactly these two state values across 26 comments. If the operator later finds an unmapped state value in the summary report and decides to add it, the change is a 1-line edit to this constant.

### JSONL record shape (inherited from Phase 2 #305)

Every record this helper writes:

```json
{
  "domain": "habits",
  "task_id": <int>,
  "title": "<Vikunja task title at backfill time>",
  "date": "<YYYY-MM-DD from the [Felix] comment body>",
  "state": "<mapped state from HISTORICAL_STATE_MAP>",
  "source": "historical-backfill",
  "note": "<optional from the [Felix] comment's note segment, or null>",
  "timestamp": "<ISO-8601 datetime from the Vikunja comment's created field>"
}
```

The `date` and `timestamp` fields differ semantically: `date` is the day the completion was FOR (parsed from the Felix comment), `timestamp` is when the comment was written in Vikunja (could be later if Kent backdated the completion in a comment).

### Pre-backfill snapshot (`.bak`)

`/data/services/openclaw/state/habits-history.jsonl.pre-phase4-backfill.bak` — a byte-for-byte copy of the JSONL log immediately before the first backfill write. Mode 0644 claude:secondbrain. Operator-restorable via `cp <bak> <original>`.

### Summary report (stdout at end of run)

Plain-text block with these sections:

```
=== Backfill summary ===
Run mode: live | dry-run
Comments fetched: 26
Records appended: 24       (planned: 24 if dry-run)
Records skipped (dedup): 0
Records skipped (unmapped): 2

Records by task:
  task_id=14 (Wake at 5:00 AM): 8
  task_id=15 (Meditate): 5
  ...

Records by state (post-mapping):
  complete: 24

Unmapped state values:
  task_id=17 date=2026-05-12 state="will-not-do" — "[Felix] 2026-05-12 | will-not-do | sick"
  task_id=18 date=2026-05-15 state="will-not-do" — "[Felix] 2026-05-15 | will-not-do | travel"
  (NOTE: if HISTORICAL_STATE_MAP is updated to map "will-not-do" → "skipped", these will be backfilled on re-run.)

Comments skipped as malformed: 0

Anomalies: 0
```

---

## Success Criteria

| ID | Criterion |
|---|---|
| SC-001 | A live run on the production dataset (~26 comments) completes in under 60 seconds and produces the expected number of JSONL records (24 in the current dataset, assuming `will-not-do` maps to `skipped` per the locked HISTORICAL_STATE_MAP). |
| SC-002 | `state_log.read("habits", source="historical-backfill")` returns the full set of backfilled records after the live run, with `timestamp` values pulled from Vikunja's `created` field (not the backfill run time). |
| SC-003 | Re-running the live backfill is a no-op: zero new records appended, summary report shows `Records appended: 0` and `Records skipped (dedup): 26`. |
| SC-004 | The `--dry-run` mode produces the same summary report content as a live run would, with `Records appended: 0` and the planned counts in a separate "planned" field. No JSONL writes occur. |
| SC-005 | The summary report's `unmapped-state-values` section names every comment whose state didn't resolve via `HISTORICAL_STATE_MAP` (so the operator can audit + decide whether to extend the map). |
| SC-006 | The pre-backfill `.bak` file exists after a live run and contains the byte-for-byte content of the JSONL log immediately before the first backfill write (verifiable by hashing both pre-run-saved-copy and the `.bak`). |
| SC-007 | No Vikunja PATCH/POST/PUT/DELETE calls are issued by the helper (verifiable by mocking the Vikunja API at the test layer and asserting only GETs). |

---

## Assumptions

1. The Vikunja API token at `/data/services/openclaw/secrets/vikunja-api` is felix-bot's (Phase 1 outcome). Confirmed.
2. The Phase 2 `state_log` library + `DOMAIN_STATES["habits"] = {complete, incomplete, skipped}` are stable. Confirmed (commit `231e880` on main).
3. The Phase 3 Tier-2 migration has been applied (mission #40, commit `188268d`). The 11 habit tasks (14, 15, 16, 17, 18, 19, 20, 65, 75, 76, 77) are the universe for comment enumeration. Confirmed today.
4. The `Habits` project ID is resolvable via `GET /projects` by exact title match (same mechanism Phase 3's `reconcile_completions.py::_resolve_habits_project_id` uses).
5. The production state-value distribution does not shift dramatically between the 2026-05-19 probe and the backfill run. New unmapped values, if any, surface cleanly in the summary report.
6. Operator (Kent) is available to review the dry-run output before live-running.

---

## Out of scope

- Cron integration — Phase 5 (#308) wires the agent's standing orders to consume the JSONL log
- Escalation backfill — Phase 6 (#309) handles escalation history separately
- Tasker/enrichment backfill — Phase 7 (#310) handles enrichment history separately
- Webhook receiver — ADR-0002 Phase 8 deferred
- Any modification of Vikunja state — strictly out of scope (the comments stay in Vikunja as the redundant historical record)
- Adding `partial`, `done`, `not-done`, or any other unobserved historical state to `HISTORICAL_STATE_MAP` — the map ships locked to what the 2026-05-19 probe found; updates happen reactively when an operator-run surfaces an unmapped value
