# Contract: `route_and_finalize` CLI + result shapes

The single deterministic command the `felix-admin-capture` agent runs per route.
Invocation form (mandatory `-m`, C-001):

```
cd /home/claude/kg-automation && python3 -m scripts.inbox.route_and_finalize \
    --kind <someday|journal|vikunja_task|github_issue|calendar|empty> \
    --source-path <abs-path-of-source-note> \
    [--payload-file <abs-path>]        # kind-specific payload (someday/journal/github_issue/calendar)
    [--task-id <int>]                  # vikunja_task tasker-delegated provenance
    [--dry-run]                        # credential-free wiring check where supported
```

## Behavior (atomic, fail-loud)

For every kind, the command performs **as one indivisible unit**:

1. **Route** — perform the kind's route action (create task / append journal /
   file issue / create event), or, for a tasker-delegated `vikunja_task`, take the
   supplied `--task-id`; for `empty`, no route.
2. **Verify** — confirm the produced artifact exists (task id resolves, file
   exists, issue number returned, `event_id` non-empty). `empty` skips verify.
3. **Mark processed** — invoke `mark_processed` as a **subprocess** (preserves the
   `_private`/inbox-root/symlink guards + stdout isolation).
4. **Routing-log append** — write the routing-log entry **last**, idempotent via
   `RoutingLogReader.has()` (kind + destination + artifact id).

Exit code derives from the **outcome**, never from the always-0 route step.

## Result JSON (stdout, single object)

```json
{"status": "finalized", "kind": "someday", "artifact": "<task_id|path|issue|event_id>",
 "marked_processed": true, "routing_logged": true}
```

```json
{"status": "needs_clarification", "kind": "calendar", "missing": ["start"]}
```
Note left unprocessed; capture enters the kind's clarification flow (calendar only, today).

```json
{"status": "error", "kind": "vikunja_task", "stage": "verify", "error": "<verbatim>"}
```
Route/verify/mark failed. Note left unprocessed → retried next tick. Exit non-zero.

```json
{"status": "dry_run", "kind": "someday", "would_finalize": true}
```

## Exit codes

| code | meaning |
|---|---|
| 0 | `finalized`, `needs_clarification`, or `dry_run` |
| non-zero | `error` (any stage) — note NOT marked processed |

## Invariants

- INV-1: a note is marked `processed` **only** as step 3 of a successful finalize.
- INV-2: `processed ⇒ routing-log entry` (total; `empty` writes kind=`empty`).
- INV-3: idempotent re-run never double-creates an artifact (routing-log dedup +
  kind-specific idempotency keys, e.g. calendar's source-path key).
- INV-4: calendar behavior is byte-identical to #737 for create /
  `needs_clarification` / `error` (NFR-003).

## Removed from the agent toolkit (FR-005)

- Standalone `mark_processed` invocation — no longer in AGENTS.md standing orders.
- Standalone `append_routing_entry` invocation — folded into finalize.
- The only sanctioned non-finalize frontmatter write is the `needs-review`
  direct edit (unclassifiable notes; no `processed_at`).
