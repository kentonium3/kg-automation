# Contract: note-level `route_and_finalize` CLI + result shapes

The single deterministic command the `felix-admin-capture` agent runs **per note**
(not per route). The agent classifies the note's blocks and assembles a routing plan;
the helper executes it atomically. Invocation form (mandatory `-m`, C-001):

```
cd /home/claude/kg-automation && python3 -m scripts.inbox.route_and_finalize \
    --source-path <abs-path-of-source-note> \
    --plan-file <abs-path-of-routing-plan.json> \
    [--dry-run]
```

`--plan-file` is the agent-assembled `RoutingPlan` (see data-model.md): a per-block list
of `{block_index, kind, payload | task_id}`. An empty block list (or all-empty note body)
selects the `empty` disposition, which first validates the body is genuinely empty.

## Behavior (note-level, atomic, fail-loud, retry-safe)

The command performs, **as one indivisible note-level transaction**:

1. **Per block, in order**: route the block for its kind (create task / append journal /
   file issue / create event; or, for a tasker-delegated `vikunja_task`, take the supplied
   `task_id`; `empty` routes nothing) → **verify** the artifact (and, for delegated
   kinds, its provenance) → **write the block's routing-log entry** (keyed on
   filename+block_index+block_hash). A block whose key is already logged is **skipped**
   (idempotent; no side effect repeated).
2. **After all blocks are logged**: invoke `mark_processed` as a **subprocess** (preserves
   `_private`/inbox-root/symlink guards + stdout isolation) — marking the note ONCE.
3. **Any block failure** (route / verify / log) aborts before the mark: the note is left
   **unprocessed**, the failing block is named, exit is non-zero. Already-logged blocks are
   not rolled back (their artifacts exist and are logged); the next tick reconciles and
   completes the remaining blocks, then marks.

Exit code derives from the **note-level outcome**, never from an individual route step.

## Result JSON (stdout, single object)

```json
{"status": "finalized", "note_filename": "...", "marked_processed": true,
 "blocks": [{"block_index":0,"kind":"calendar","artifact":"<event_id>","logged":true},
            {"block_index":1,"kind":"someday","artifact":"512","logged":true,"skipped":false}]}
```

```json
{"status": "needs_clarification", "note_filename": "...",
 "blocks": [{"block_index":0,"kind":"calendar","missing":["start"]}]}
```
Note left unprocessed; capture enters the kind's clarification flow (calendar only, today).

```json
{"status": "error", "note_filename": "...",
 "blocks": [{"block_index":1,"kind":"vikunja_task","stage":"verify","error":"<verbatim>"}]}
```
A block failed → whole note NOT marked → retried next tick. Exit non-zero.

```json
{"status": "dry_run", "note_filename": "...", "would_finalize": true}
```

## Exit codes

| code | meaning |
|---|---|
| 0 | `finalized`, `needs_clarification`, or `dry_run` |
| non-zero | `error` (any block, any stage) — note NOT marked processed |

## Invariants

- INV-1: a note is marked `processed` **only** after every block is verified AND logged.
- INV-2: `processed ⇒ a routing-log entry per routed block` (total; `empty` writes kind=`empty`).
- INV-3: per-block idempotency — a re-run never double-creates (block-key skip + per-kind
  pre-side-effect guard: calendar source-path key; someday/vikunja block-key; journal
  per-block sentinel; github block-key + issue verify).
- INV-4: calendar create / `needs_clarification` / `error` behavior identical to #737
  (NFR-003); the old `finalized`+`routing_logged:false` leniency is **removed** (a log
  failure leaves the note unprocessed).
- INV-5: delegated `vikunja_task` id must belong to this note (provenance), not merely exist.
- INV-6: `empty` refuses a non-empty body.

## Removed from the agent toolkit (FR-005/FR-016)

- Standalone `mark_processed` and `append_routing_entry` invocations — gone from the
  standing orders. The agent classifies → builds the plan → calls one note-level finalize.
- The only sanctioned non-finalize frontmatter write remains the `needs-review` direct
  edit for unclassifiable notes (no `processed_at`; prescan-terminal).

## Health-rail surfacing (FR-014)

`prescan` reports a `processed-without-routing-log` anomaly for any `processed` note whose
blocks are not represented in the routing log; the Step 1 IDLE gate **blocks the `IDLE`
reply** and reports `archive_anomalies` so the alarm reaches Kent.
