# Contract — JSONL on-disk format

**Mission**: `shared-jsonl-state-log-library-01KS0E9A`
**Files**: `/data/services/openclaw/state/{habits,escalation,enrichment}-history.jsonl`

This is the on-disk format consumers can rely on — including emergency tooling that needs to read or repair the files without going through the Python library.

---

## File-level invariants

- **One JSON object per line.** Lines are terminated by `\n` (LF, not CRLF).
- **UTF-8 encoded.** No BOM. No leading whitespace.
- **Append-only in normal operation.** The library never rewrites or truncates. Operators may rotate manually if needed (out of scope for v0).
- **Lines are independently parseable.** Concatenating two lines does NOT produce valid JSON — this means line boundaries are byte-aligned and any line-based tool (`grep`, `head`, `tail`, `wc -l`, `jq -c`) works correctly.
- **No trailing newline guarantee.** The last line may or may not end with `\n` depending on whether the file was last touched mid-append. Tools MUST handle both cases.

---

## Line schema

Each line is a JSON object with these fields:

| Field | Type | Required | Description |
|---|---|---|---|
| `domain` | string | yes | One of `habits`, `escalation`, `enrichment`. Always matches the file name. |
| `task_id` | integer | yes | Vikunja task ID. Positive integer. |
| `title` | string | yes | Non-empty. Denormalized for human readability. |
| `date` | string | yes | ISO-8601 date `YYYY-MM-DD`. The day this record is FOR. |
| `state` | string | yes | Member of the per-domain enum (see [data-model.md](../data-model.md)). |
| `source` | string | yes | Non-empty. Writer identity, e.g., `whatsapp`, `vikunja-ui`, `cron`. |
| `timestamp` | string | yes | ISO-8601 datetime WITH timezone offset (e.g., `2026-05-19T11:05:11+00:00`). When the record was written. |
| `note` | string or null | no | Optional freeform annotation. Default `null`. |

### Field order

The Python library writes fields in a stable order (see below), but consumers reading via `jq` or similar MUST NOT depend on field order — JSON objects are unordered by spec. The library's stable order is for human readability only:

```
domain, task_id, title, date, state, source, note, timestamp
```

---

## Idempotency key

The dedup unique key for a domain file is the tuple `(task_id, date, state)`. The library guarantees no two lines in the same file have the same tuple.

Operators repairing files manually MUST preserve this invariant — running `sort -u` is NOT safe because it doesn't understand the JSON structure. Use the library or a JSON-aware deduper.

---

## Example file — habits-history.jsonl

```
{"domain":"habits","task_id":14,"title":"Wake at 5:00 AM","date":"2026-05-17","state":"complete","source":"whatsapp","note":null,"timestamp":"2026-05-17T11:05:11+00:00"}
{"domain":"habits","task_id":17,"title":"Strength training","date":"2026-05-17","state":"skipped","source":"whatsapp","note":"travel — no gym access","timestamp":"2026-05-17T11:05:22+00:00"}
{"domain":"habits","task_id":14,"title":"Wake at 5:00 AM","date":"2026-05-18","state":"complete","source":"vikunja-ui","note":null,"timestamp":"2026-05-19T11:00:03+00:00"}
{"domain":"habits","task_id":14,"title":"Wake at 5:00 AM","date":"2026-05-19","state":"incomplete","source":"whatsapp","note":null,"timestamp":"2026-05-19T11:05:01+00:00"}
```

(Line breaks shown here for readability; on disk these are 4 newline-separated lines.)

---

## Reading with stdlib tools

```bash
# All records as parsed objects (one per line)
jq -c . < habits-history.jsonl

# All records for task 14
jq -c 'select(.task_id == 14)' < habits-history.jsonl

# Just the dates
jq -r '.date' < habits-history.jsonl | sort -u

# Records where state is "skipped"
jq -c 'select(.state == "skipped")' < habits-history.jsonl

# Count records per state
jq -r '.state' < habits-history.jsonl | sort | uniq -c
```

These are stable across the v0 contract — the library guarantees the JSON shape.

---

## Compatibility surface

- **Adding a new optional field**: non-breaking. The library writes the field; consumers ignore unknown fields.
- **Adding a new state value to a domain enum**: non-breaking IF consumers handle the unknown state gracefully (e.g., display as-is, don't crash). Library-side validation will accept the new value once added to `DOMAIN_STATES`.
- **Renaming a required field**: BREAKING. Requires coordinated migration of all consumers + a one-off file rewrite utility.
- **Removing a required field**: BREAKING. Same as rename.
- **Changing the idempotency tuple**: BREAKING. Same as rename.
- **Adding a new domain**: non-breaking for existing consumers. A new file appears under `/data/services/openclaw/state/`; existing domain files are untouched.
