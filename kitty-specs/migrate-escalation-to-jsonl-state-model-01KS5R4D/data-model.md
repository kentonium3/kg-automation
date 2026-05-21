# Data Model: Migrate escalation to JSONL state model

**Mission**: `migrate-escalation-to-jsonl-state-model-01KS5R4D`
**Date**: 2026-05-21

Authoritative reference for on-disk shapes, schema enums, and the comment-vocabulary mapping used by the backfill helper.

---

## Entity 1 — Escalation JSONL record

A single line in `<project-slug>-escalation-history.jsonl`. JSON-encoded; one record per line.

### Required fields (shared with all `state_log` domains per Phase 2)

| Field | Type | Notes |
|---|---|---|
| `domain` | `str` | Always `"escalation"`. |
| `task_id` | `int` (positive) | Vikunja `id` (immutable per `reference_vikunja_id_vs_identifier.md`). |
| `title` | `str` (non-empty) | Vikunja task title snapshot at write-time. For human grep — NOT authoritative. |
| `date` | `str` (`YYYY-MM-DD`) | The local-TZ date on which the event was recorded. |
| `state` | `str` (enum) | Per the new DOMAIN_STATES enum (Entity 2). The Q1=A "event_type" in spec FR-003 IS this field. |
| `source` | `str` (non-empty) | One of `"agent"` (live escalation tick), `"reconcile"` (synthetic from reconcile sweep), `"backfill"` (one-time Phase 6 backfill), `"kent_reply"` (recorded after Kent's WhatsApp response). |
| `timestamp` | `str` (ISO-8601 datetime with tz) | UTC instant of the record write. |
| `note` | `str` or `None` (optional) | Free-text. Currently used only for backfill-time malformed-comment snippets. |

### Optional structured parameter fields (Phase 6 extension)

Per spec FR-003, the schema uses a flat-enum `state` field combined with structured parameter fields. Each event_type defines its own required parameters. Extra fields pass through the Phase 2 validator (which only enforces the 7 required fields + optional `note`).

| Field | Type | Required for `state` ∈ | Notes |
|---|---|---|---|
| `project_id` | `int` (positive) | ALL records | Vikunja project containing the task. Pairs with `task_id` for routing. |
| `level` | `int` (1 or 2) | `level_sent` | The escalation level just sent. |
| `snooze_days` | `int` (positive) | `snoozed` | Kent's stated snooze duration. |
| `snooze_until` | `str` (`YYYY-MM-DD`) | `snoozed` | Persisted at write-time per FR-004; `today + snooze_days` in America/New_York TZ. |
| `reschedule_to` | `str` (`YYYY-MM-DD`) | `rescheduled` | The new due_date Kent requested (or that the UI now shows, for reconcile-synthesized records). |
| `reason` | `str` | optional on `dismissed`, `done` | Free-text reason if Kent provided one. |

### Example records

```jsonl
{"domain":"escalation","task_id":1234,"title":"Email Q3 board summary","date":"2026-05-21","state":"level_sent","source":"agent","timestamp":"2026-05-21T12:00:01.234567+00:00","note":null,"project_id":4,"level":1}
{"domain":"escalation","task_id":1234,"title":"Email Q3 board summary","date":"2026-05-21","state":"snoozed","source":"kent_reply","timestamp":"2026-05-21T14:32:11.876543+00:00","note":null,"project_id":4,"snooze_days":3,"snooze_until":"2026-05-24"}
{"domain":"escalation","task_id":5678,"title":"Renew domain","date":"2026-05-21","state":"done","source":"reconcile","timestamp":"2026-05-21T12:00:05.111222+00:00","note":null,"project_id":2}
{"domain":"escalation","task_id":9012,"title":"File taxes","date":"2026-05-19","state":"rescheduled","source":"kent_reply","timestamp":"2026-05-19T16:45:00.000000+00:00","note":null,"project_id":7,"reschedule_to":"2026-06-15"}
```

### Schema validator (review surface per NFR-005)

A reviewer reading `scripts/escalation/schema.py` MUST be able to enumerate every event_type and its required parameter fields without running tests. The shape:

```python
# scripts/escalation/schema.py (NEW — see contracts/api.md)

EVENT_TYPE_PARAMETERS: dict[str, frozenset[str]] = {
    "level_sent":   frozenset({"level"}),
    "snoozed":      frozenset({"snooze_days", "snooze_until"}),
    "dismissed":    frozenset(),  # no required params; optional `reason`
    "done":         frozenset(),  # no required params; optional `reason`
    "rescheduled":  frozenset({"reschedule_to"}),
}
```

`validate_event_params(record)` checks that every field in `EVENT_TYPE_PARAMETERS[record["state"]]` is present in `record` and has the right type. Raises `EscalationSchemaError` on violation. The Phase 2 `state_log.validate_record` continues to handle the 7 shared required fields.

---

## Entity 2 — DOMAIN_STATES["escalation"] enum (after Phase 6)

Update applied in `scripts/common/state_log_schema.py` per amended C-003 and research D1:

```python
DOMAIN_STATES: dict[str, frozenset[str]] = {
    "habits": frozenset({"complete", "incomplete", "skipped"}),
    "escalation": frozenset({
        "level_sent",
        "snoozed",
        "dismissed",
        "done",
        "rescheduled",
    }),
    "enrichment": frozenset({"pending", "enriched", "deferred", "failed"}),
}
```

Diff scope: 5 lines changed in one file. No other library code touched.

---

## Entity 3 — `[Felix-Escalation]` comment → JSONL record mapping (backfill)

The backfill helper (`backfill_jsonl_from_comments.py`) walks every Vikunja task that has at least one `[Felix-Escalation]` comment and emits one JSONL record per parseable comment. Locked mapping per research D5:

| Comment shape (`date \| state \| disposition`) | Emitted JSONL `state` | Required parameters |
|---|---|---|
| `YYYY-MM-DD \| level-1 \| sent` | `level_sent` | `level: 1` |
| `YYYY-MM-DD \| level-2 \| sent` | `level_sent` | `level: 2` |
| `YYYY-MM-DD \| snoozed:Nd \| acknowledged` | `snoozed` | `snooze_days: N`, `snooze_until: (comment-date + N days)` |
| `YYYY-MM-DD \| dismissed \| acknowledged` | `dismissed` | — |
| `YYYY-MM-DD \| done \| acknowledged` | `done` | — |
| `YYYY-MM-DD \| rescheduled:YYYY-MM-DD \| acknowledged` | `rescheduled` | `reschedule_to: <date>` |

For every replayed comment, the JSONL record carries:
- `source: "backfill"`
- `date`: the date from the comment (YYYY-MM-DD)
- `timestamp`: a synthesized UTC timestamp using the comment's `created` field if available, else `comment_date + 12:00:00+00:00` (noon UTC) as a best-effort placeholder
- `project_id`: from Vikunja API lookup
- All other parameter fields per the mapping above

### Malformed comment handling

A comment is "malformed" if:
- The `[Felix-Escalation]` prefix is present but the split-on-`|` doesn't yield 3 fields
- The state field doesn't match any of the 6 patterns above
- The date field doesn't parse as ISO-8601
- A parameter field is required but cannot be parsed (e.g., `snoozed:abc` instead of `snoozed:3d`)

Malformed comments are NOT replayed. They are collected into a backfill summary report (stdout) with the task ID, comment snippet (first 80 chars), and parse error.

### Idempotency

Backfill is idempotent. The state_log library's append path includes content-based dedup; replayed records that already exist are no-ops.

---

## Entity 4 — Pre-backfill snapshot (rollback substrate)

Created by backfill before any JSONL writes. Path: `/data/services/openclaw/state/escalation/pre-phase6-snapshot.json`.

```json
{
  "snapshot_version": 1,
  "created_at": "2026-05-21T17:30:00+00:00",
  "tool_version": "scripts/escalation/backfill_jsonl_from_comments.py@<commit-sha>",
  "tasks": [
    {
      "task_id": 1234,
      "project_id": 4,
      "title": "Email Q3 board summary",
      "vikunja_url": "https://office2.tail0f5f56.ts.net/tasks/1234",
      "felix_comments": [
        {"comment_id": 5678, "created": "2026-05-15T08:00:00Z", "comment": "[Felix-Escalation] 2026-05-15 | level-1 | sent"},
        {"comment_id": 5901, "created": "2026-05-17T08:00:00Z", "comment": "[Felix-Escalation] 2026-05-17 | level-2 | sent"}
      ]
    }
  ]
}
```

Rollback procedure: see quickstart.md § Rollback. The snapshot allows the operator to verify that no Felix-driven Vikunja comments were lost during backfill.

---

## Entity 5 — Q10 hard-fail bug body template

Format used by the helpers when filing a hard-fail P2-bug via `felix-file-issue.py`:

**Title**: `Escalation hard-fail: <task title> (task #<vikunja_id>) — <short reason>`

**Body**:

```markdown
## Hard-fail context

Escalation tick skipped a task due to inconsistent state.

- **Task**: [<task title>](<vikunja URL>) (Vikunja `id` <id>, project `id` <project_id>)
- **Reason**: <one of: malformed_jsonl_record | phantom_subscription | derive_state_inconsistency>
- **Detected at**: <UTC timestamp>
- **JSONL file**: `<full path to project-slug-escalation-history.jsonl>`

## Detection snippet

```
<raw record(s) that triggered the hard-fail, or "no records found" for phantom_subscription>
```

## Vikunja state

- `done`: <true|false>
- `due_date`: <ISO-8601 or null>
- `[Felix-Escalation]` comment count: <N>
- Most recent comment: `<text or "none">`

## derive_state output (if applicable)

```
<EscalationStateError message>
```

## Recommended triage

1. Inspect the JSONL file at the path above. Identify the malformed line.
2. Cross-check against Vikunja state (link above).
3. Either repair the JSONL by hand (if recoverable) OR add a synthetic `{state: "<best-fit>", source: "operator_repair", note: "manual triage <date>"}` record.
4. Close this issue. The next escalation tick will reprocess.

## Labels

P2-bug, area/escalation
```

This template is rendered by the helper before calling `felix-file-issue.py`.

---

## Cross-references

- Spec FR-003 (flat-enum schema), FR-004 (snooze_until write-time), FR-008 (Q10 hard-fail), FR-009 (dedup keyed on Vikunja id)
- Research D1 (DOMAIN_STATES update), D5 (backfill mapping), D8 (hard-fail triggers), D9 (dedup query)
- Phase 2 contracts: `kitty-specs/shared-jsonl-state-log-library-01KS0E9A/contracts/`
- Phase 3 data-model: `kitty-specs/habits-native-repeat-jsonl-state-01KS0M59/data-model.md`
- `reference_vikunja_id_vs_identifier.md` (memory)
