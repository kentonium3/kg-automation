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

**State transitions** (the atomicity boundary this mission enforces):

```
unprocessed --finalize(success)--> processed        (route verified + logged + marked, as one unit)
unprocessed --finalize(failure)--> unprocessed       (fail-loud; retried next tick — NEVER processed)
unprocessed --unclassifiable-----> needs-review       (direct edit; no processed_at; out of health-rail scope)
```

Invariant **INV-1 (NFR-001)**: `status == processed` ⇒ a routing-log entry exists
for the note's filename. Made total by the `empty` no-route disposition (D4).

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
| `kind` | str | **enum grows**: was `issue_task`\|`calendar`; add `someday`, `journal`, `vikunja_task`, `github_issue`, `empty`. Old on-disk `issue_task` rows remain valid (reader keys on filename only). |
| `destination` | str | kind-specific identifier (task id / issue number / file path / event id / "") |

**Backward compatibility**: `RoutingLogReader` reads only `filename`; adding
`kind` values and older rows lacking new fields is harmless.

### FinalizeResult (stdout contract)

A single JSON object emitted by `route_and_finalize` (mirrors #737's finalize
result). Callers branch on `status`; exit code reflects the outcome.

| status | meaning | exit |
|---|---|---|
| `finalized` | route verified + marked processed + routing-logged | 0 |
| `needs_clarification` | payload incomplete (kind-specific `missing`); note left unprocessed | 0 |
| `error` | route/verify/mark failed (`stage`, `error` verbatim); note left unprocessed | non-zero |
| `dry_run` | credential-free wiring check (`would_finalize: true`) | 0 |

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

## Validation rules

- A finalize marks `processed` **only after** artifact verification succeeds (FR-003).
- routing-log append is idempotent (`has()` guard) and occurs **after** the mark (D1 ordering).
- `empty` disposition still writes a routing-log entry (INV-1 totality).
- `needs-review` never writes `processed`/`processed_at` and is excluded from the rail.
- Privacy: any `--source-path` under `04-Growth/_private/` is refused by `mark_processed` (exit 3), surfaced as a finalize error.
