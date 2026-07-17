# Data Model: Atomic Capture Finalize Across Route Kinds

## Entities

### Note (inbox capture)

A markdown file with YAML-ish frontmatter under the Obsidian vault
`01-Inbox/` (and later `02-Inbox-Processed/`).

| Field | Values | Notes |
|---|---|---|
| `status` | `unprocessed` → `processed` \| `needs-review` | `processed` is written **only** by `mark_processed` (invoked by finalize). |
| `processed_at` | ISO-8601 UTC (Z) | Present iff `status: processed`. Absent for `needs-review`. |
| body | verbatim | Never mutated; the original note is never moved/deleted (inbox invariant, C-003). |

**State transitions** (the atomicity boundary this mission enforces — note-level):

```
unprocessed --finalize(all blocks routed+verified+logged)--> processed   (marked ONCE, after all blocks)
unprocessed --finalize(any block fails)-------------------> unprocessed   (fail-loud; whole note retried; succeeded blocks skipped via block key)
unprocessed --unclassifiable------------------------------> needs-review  (direct edit; no processed_at; prescan-terminal; out of health-rail scope)
```

**Finalize state machine (D9)** — per block: `route → verify → write block
routing-log entry`; after **all** blocks logged → `mark note processed` (once). A
re-run reconciles from the routing log: blocks whose block key is already present are
skipped (no double-create). prescan's note dedup is by `status` (processed/needs-review
terminal), not by routing-log presence.

Invariant **INV-1 (NFR-001)**: `status == processed` ⇒ a routing-log entry exists
for **every routed block** of the note. Made total by the `empty` no-route disposition
(kind=empty entry) and by log-before-mark ordering (D9).

### Route kind

The classification that selects a route + verify adapter.

| kind | route action | verified artifact | routing-log `destination` |
|---|---|---|---|
| `someday` | create Vikunja task (Inbox / topic project, q:schedule, no due date) | task id resolves | task id |
| `vikunja_task` | in-process create **or** accept tasker-delegated id | task id resolves | task id |
| `journal` | append/create dated journal file | file exists at target path | file path |
| `github_issue` | file issue via `felix-file-issue.py` | issue number returned | issue number |
| `calendar` | create event (folded #737 path) | `status==created` + non-empty `event_id` | event id |
| `empty` | none (no-route disposition) | n/a | "" |

### RoutingEntry (routing log)

Append-only JSONL at `/data/services/openclaw/state/inbox-routing.jsonl`
(`scripts/inbox/routing_log.py`). **Extended** by this mission.

| Field | Type | Change |
|---|---|---|
| `filename` | str | unchanged (the only key the reader uses) |
| `issue_number` | int \| None | unchanged (populated for `github_issue`) |
| `vikunja_task_id` | int \| None | unchanged (populated for `someday`/`vikunja_task`) |
| `routed_at` | str (ISO-8601 UTC Z) | unchanged |
| `note_excerpt` | str | unchanged |
| `kind` | str | **enum grows**: was `issue_task`\|`calendar`; add `someday`, `journal`, `vikunja_task`, `github_issue`, `empty`. Old on-disk `issue_task` rows remain valid. |
| `destination` | str | kind-specific identifier (task id / issue number / file path / event id / "") |
| `block_index` | int \| None | **NEW** — index of the routed block within the note (D10). None on legacy rows. |
| `block_hash` | str \| None | **NEW** — content hash of the block; together with `filename`+`block_index` forms the block idempotency key. None on legacy rows. |

**Block key** = (`filename`, `block_index`, `block_hash`). The per-block dedup/idempotency
substrate: finalize skips a block whose key is already logged. **Backward compatibility**:
legacy rows lack `block_index`/`block_hash`; for them dedup falls back to `filename` (the
old #737 behavior), and the health rail treats any routing-log entry for the filename as
satisfying the invariant.

### RoutingPlan (agent → finalize input)

The agent-assembled per-note plan the note-level finalize executes. Keeps
classification (LLM) separate from execution (deterministic helper), C-005.

```json
{"note_filename": "Inbox 2026-07-17 0930.md",
 "blocks": [
   {"block_index": 0, "kind": "calendar", "payload": {...}},
   {"block_index": 1, "kind": "vikunja_task", "task_id": 512},   // tasker-delegated
   {"block_index": 2, "kind": "someday", "payload": {...}}
 ]}
```

An empty `blocks` list (or all-empty content) selects the `empty` disposition.

### FinalizeResult (stdout contract — note-level)

A single JSON object emitted by the note-level `route_and_finalize`. Carries
per-block sub-results; the note-level `status` is the aggregate. Callers branch on
`status`; exit code reflects the outcome.

| status | meaning | exit |
|---|---|---|
| `finalized` | ALL blocks routed+verified+logged; note marked once | 0 |
| `needs_clarification` | one or more blocks incomplete (per-block `missing`); note left unprocessed | 0 |
| `error` | any block route/verify/log failed (per-block `stage`,`error` verbatim); note left unprocessed | non-zero |
| `dry_run` | credential-free wiring check (`would_finalize: true`) | 0 |

```json
{"status": "finalized", "note_filename": "...", "marked_processed": true,
 "blocks": [{"block_index":0,"kind":"calendar","artifact":"<event_id>","logged":true},
            {"block_index":1,"kind":"someday","artifact":"512","logged":true}]}
```

A block already reconciled from the routing log on a re-run is reported
`skipped: true` (idempotent, no side effect repeated).

### ArchiveAnomaly (health rail — extended)

`scripts/inbox/prescan.py`. New `classification` value
`processed-without-routing-log` for a note with `status: processed` whose
filename is absent from the routing log.

| Field | Notes |
|---|---|
| `path` | absolute note path |
| `status_raw` | `processed` |
| `classification` | `processed-without-routing-log` (new) |
| `warning` | "status:processed but no routing-log entry (silent-loss signature #746)" |

The `processed-without-routing-log` anomaly must be **surfaced to the agent** (FR-014):
`prescan`'s Step 1 IDLE gate blocks the `IDLE` reply and reports `archive_anomalies`
when any exist (otherwise the rail writes to a field the agent never reads).

## Validation rules

- The note is marked `processed` **only after** every block is verified AND its
  routing-log entry is written (FR-001/FR-011 — log-before-mark, note-level).
- Each block's routing-log write is idempotent on its **block key** (filename+index+hash);
  a re-run skips already-logged blocks without repeating the side effect (FR-010).
- `empty` disposition validates the body is genuinely empty, then writes a kind=`empty`
  entry (INV-1 totality; FR-007).
- `needs-review` never writes `processed`/`processed_at`, is prescan-terminal (excluded
  from `unprocessed_paths`, FR-008), and is excluded from the rail.
- Delegated `vikunja_task` id is verified to **belong to this note** (source provenance),
  not merely to exist (FR-006).
- `github_issue` with a null/missing issue number is a finalize failure (FR-012).
- Privacy: any note path under `04-Growth/_private/` is refused by `mark_processed`
  (exit 3), surfaced as a finalize error.
