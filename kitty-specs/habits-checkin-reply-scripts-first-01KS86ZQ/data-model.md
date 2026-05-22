# Data Model: Habits check-in + reply scripts-first port

**Mission**: `habits-checkin-reply-scripts-first-01KS86ZQ`
**Date**: 2026-05-22

Authoritative reference for on-disk shapes, parser I/O, disambiguator I/O, and the AGENTS.md target structure.

---

## Entity 1 — Morning-list artifact

A single JSON file per Kent-day. Path: `/data/services/openclaw/state/habits/morning-checkin-<YYYY-MM-DD>.json`.

### Schema

```json
{
  "schema_version": 1,
  "date": "2026-05-23",
  "generated_at": "2026-05-23T11:05:01Z",
  "habits": [
    {"position": 1, "vikunja_task_id": 14, "title": "Wake at 5:00 AM"},
    {"position": 2, "vikunja_task_id": 18, "title": "Meditate"},
    {"position": 3, "vikunja_task_id": 19, "title": "Morning shoulder PT"},
    {"position": 4, "vikunja_task_id": 20, "title": "Get steps in today"},
    {"position": 5, "vikunja_task_id": 65, "title": "Read 30 min minimum"},
    {"position": 6, "vikunja_task_id": 16, "title": "Evening shoulder PT"},
    {"position": 7, "vikunja_task_id": 17, "title": "Morning hip PT"},
    {"position": 8, "vikunja_task_id": 15, "title": "Strength training — Friday"}
  ]
}
```

### Field semantics

| Field | Type | Required | Notes |
|---|---|---|---|
| `schema_version` | int | yes | Starts at 1. Bumped if the schema changes in a breaking way. |
| `date` | str | yes | `YYYY-MM-DD` in America/New_York. The day the check-in is FOR. |
| `generated_at` | str | yes | ISO-8601 UTC timestamp of when the file was written. |
| `habits` | list | yes | Ordered list. `position` field is 1-indexed and matches list index + 1. |
| `habits[].position` | int | yes | 1-indexed. The number Kent sees in the WhatsApp message. |
| `habits[].vikunja_task_id` | int | yes | The Vikunja `id` (immutable per `reference_vikunja_id_vs_identifier.md`). |
| `habits[].title` | str | yes | Vikunja task title verbatim. Used for fuzzy matching in the reply parser. |

### Validation rules

- `position` values MUST be 1, 2, 3, ... N consecutively (no gaps; matches list-index + 1).
- `vikunja_task_id` MUST be a positive int.
- `title` MUST be a non-empty string after strip.
- `habits` array MAY be empty (no habits to surface today); in that case the morning message is "All habits complete for today." per existing SKILL.md rule.
- `date` MUST be a valid ISO date.
- `generated_at` MUST be a valid ISO-8601 datetime with `Z` or `+00:00` suffix.

---

## Entity 2 — Reply parser output

The output of `parse_morning_reply.py`. Emitted as JSON to stdout.

### Schema

```json
{
  "schema_version": 1,
  "reply_text": "Skipped 3,7,8 done",
  "morning_list_path": "/data/services/openclaw/state/habits/morning-checkin-2026-05-23.json",
  "tuples": [
    {"task_id": 14, "state": "complete", "matched_via": "position", "position": 1},
    {"task_id": 18, "state": "complete", "matched_via": "position", "position": 2},
    {"task_id": 19, "state": "skipped", "matched_via": "position", "position": 3}
  ],
  "judgment_required": [
    {
      "token": "PT",
      "candidate_task_ids": [19, 16, 17],
      "candidate_titles": ["Morning shoulder PT", "Evening shoulder PT", "Morning hip PT"],
      "inferred_state": "complete"
    }
  ],
  "errors": []
}
```

### Field semantics

| Field | Type | Required | Notes |
|---|---|---|---|
| `schema_version` | int | yes | Starts at 1. |
| `reply_text` | str | yes | Echo of the input reply text (for debugging). |
| `morning_list_path` | str | yes | Echo of the morning-list artifact path used. |
| `tuples` | list | yes | Deterministic (task_id, state) pairs. State is `complete \| incomplete \| skipped` (Phase 2 enum). |
| `tuples[].task_id` | int | yes | Vikunja task id from the morning list. |
| `tuples[].state` | str | yes | One of `complete`, `incomplete`, `skipped`. |
| `tuples[].matched_via` | str | yes | One of `position`, `exact_title`, `substring`, `special_token`. Useful for debugging + audit trail. |
| `tuples[].position` | int | optional | If matched via position, the 1-indexed position. |
| `judgment_required` | list | yes | Empty list if no ambiguity. |
| `judgment_required[].token` | str | yes | The ambiguous reply token. |
| `judgment_required[].candidate_task_ids` | list[int] | yes | The task_ids that matched the ambiguous token. |
| `judgment_required[].candidate_titles` | list[str] | yes | Parallel to candidate_task_ids. |
| `judgment_required[].inferred_state` | str | yes | The state Kent paired with the token (e.g., `complete`, `skipped`). |
| `errors` | list | yes | Empty if parse succeeded. Otherwise: structured error records. |
| `errors[].type` | str | yes | One of `no_morning_list`, `invalid_token`, `unparseable_reply`. |
| `errors[].detail` | str | yes | Free-text human-readable detail. |

### Mutual exclusivity

If `errors` is non-empty, the agent files a hard-fail bug and does NOT route any tuples or judgment_required items. Errors are terminal for the parse.

If `tuples` is non-empty AND `judgment_required` is non-empty: the agent (a) routes the deterministic tuples to `record_completion.py` AND (b) invokes the disambiguator for the judgment_required items, possibly asking Kent ONE clarifying question per cluster.

---

## Entity 3 — Disambiguator input

The input to `scripts/habits/judgment/disambiguate_reply.py`. Passed as JSON (stdin or `--input-file`).

### Schema

```json
{
  "schema_version": 1,
  "reply_text": "Skipped PT, meditation done",
  "ambiguity": {
    "token": "PT",
    "candidate_task_ids": [19, 16, 17],
    "candidate_titles": ["Morning shoulder PT", "Evening shoulder PT", "Morning hip PT"],
    "inferred_state": "skipped"
  }
}
```

---

## Entity 4 — Disambiguator output

JSON emitted by the disambiguator to stdout. EXACTLY one of two shapes:

### Shape A — confident choice

```json
{
  "schema_version": 1,
  "result": "chosen",
  "chosen_task_id": 19,
  "reason": "Kent's reply mentions only PT once with no qualifier; he typically refers to 'morning PT' when not specifying time of day, and position 3 is morning shoulder PT in the list."
}
```

### Shape B — needs clarification

```json
{
  "schema_version": 1,
  "result": "clarify",
  "reason": "The token 'PT' matches three habits with no contextual disambiguation in Kent's reply.",
  "suggested_question": "When you said 'PT', did you mean morning shoulder PT (#3), evening shoulder PT (#6), or morning hip PT (#7)?"
}
```

### Field semantics

| Field | Type | Required | Notes |
|---|---|---|---|
| `result` | str | yes | `chosen` or `clarify`. |
| `chosen_task_id` | int | required if `result=chosen` | A task_id from the input's candidate_task_ids. |
| `reason` | str | yes | Short justification (for audit trail / logging). |
| `suggested_question` | str | required if `result=clarify` | A copy-pastable question for the agent to send Kent. |

### Validation rules

- If `result=chosen`, `chosen_task_id` MUST be in the input's `candidate_task_ids` list. Disambiguator that returns an out-of-set ID is a hard-fail.
- If `result=clarify`, `suggested_question` MUST be a single sentence ≤200 chars (short enough for WhatsApp).

---

## Entity 5 — AGENTS.md target structure (post-cut)

The deployed `/data/services/openclaw/habits-agent/AGENTS.md` after this mission, target ≤14,000 source chars.

### Skeleton

```markdown
## Governance
<3-5 lines: constitution link, autonomy level, tiebreaker>

# AGENTS.md — Standing orders: habit check-in and accountability

## Authority
<2-3 lines: who you are, what you're authorized to do>

## Message identity
<3-5 lines: identity line convention, how Felix relays your reply>

## Output discipline
**Hard rule #1**: <one paragraph: identity line first>
**Hard rule #2**: <one paragraph: no preambles, no commentary between tool calls>
**Never include in your output**: <bulleted list, ~5 items>

## Scope
<3-5 lines: what habits accountability is and isn't>

## Morning check-in (tick workflow)

When this cron fires, follow these steps:

### Step 1: Invoke the morning-list helper
```
python3 -m scripts.habits.morning_checkin_list --date $(TZ=America/New_York date +%Y-%m-%d)
```

The helper:
- Reads today's active habits from Vikunja
- Excludes habits already addressed today
- Writes `/data/services/openclaw/state/habits/morning-checkin-<date>.json`
- Emits the formatted WhatsApp message to stdout

### Step 2: Relay the helper's stdout verbatim as your final reply

No commentary. No transformation. The helper's output IS the WhatsApp message Kent receives.

### Step 3: On helper failure (exit non-zero)

File a P2-bug via `felix-file-issue.py` describing the failure mode. Reply with `IDLE`.

## Completion marking (reply workflow)

When Kent sends a reply mentioning habit completion / skipping:

### Step 1: Invoke the parser
```
python3 -m scripts.habits.parse_morning_reply --reply "$KENT_REPLY_TEXT" --date <today-local>
```

### Step 2: Route the deterministic tuples

For each `(task_id, state)` in the parser's `tuples` array:
```
python3 -m scripts.habits.record_completion --task-id <id> --state <state> --date <date> --source kent_reply --idempotent
```

### Step 3: Handle judgment_required (if any)

For each ambiguity:
```
python3 -m scripts.habits.judgment.disambiguate_reply --input-file <ambiguity.json>
```

If disambiguator returns `chosen`: invoke `record_completion` with the chosen task_id.
If disambiguator returns `clarify`: include the `suggested_question` in your reply to Kent. Ask ONE clarifying question per ambiguity cluster — never silently guess.

### Step 4: On parser hard-fail (errors non-empty)

File a P2-bug via `felix-file-issue.py`. Reply asking Kent to re-state his habit progress in natural language.

## Tailscale connectivity

<3-5 lines: assumes office2 reachable; on disconnect, retry, then IDLE>

## Reference

Spec: `kitty-specs/habits-checkin-reply-scripts-first-01KS86ZQ/spec.md` (#371)
Migration: SKILL.md fuzzy-matching prose moved to helpers (2026-05-22 per #371 cycle 1)
```

### Target char-count

The skeleton above is ~3,500 chars. Allowing for prose expansion in each section, the final AGENTS.md should be ~10,000-12,000 chars source content. Effective budget after openclaw inflation: ~14,000 limit per memory. Headroom is intentional.

---

## Entity 6 — Test fixture: 2026-05-22 morning list (synthetic)

For SC-002 testing, the parser tests MUST include a fixture matching the 2026-05-22 morning list from #371:

```json
{
  "schema_version": 1,
  "date": "2026-05-22",
  "generated_at": "2026-05-22T11:05:00Z",
  "habits": [
    {"position": 1, "vikunja_task_id": 14, "title": "Wake at 5:00 AM"},
    {"position": 2, "vikunja_task_id": 18, "title": "Meditate"},
    {"position": 3, "vikunja_task_id": 19, "title": "Morning shoulder PT"},
    {"position": 4, "vikunja_task_id": 20, "title": "Get steps in today"},
    {"position": 5, "vikunja_task_id": 65, "title": "Read 30 min minimum"},
    {"position": 6, "vikunja_task_id": 16, "title": "Evening shoulder PT"},
    {"position": 7, "vikunja_task_id": 17, "title": "Morning hip PT"},
    {"position": 8, "vikunja_task_id": 15, "title": "Strength training — Friday"}
  ]
}
```

(Task IDs are placeholders unless verified against actual Vikunja state. Implementation phase confirms IDs by querying Vikunja and replacing them in the fixture.)

Reply test: `"Skipped 3,7,8 done"`

Expected parser output (Entity 2 shape):

```json
{
  "schema_version": 1,
  "reply_text": "Skipped 3,7,8 done",
  "morning_list_path": "<fixture path>",
  "tuples": [
    {"task_id": 14, "state": "complete", "matched_via": "position", "position": 1},
    {"task_id": 18, "state": "complete", "matched_via": "position", "position": 2},
    {"task_id": 19, "state": "skipped",  "matched_via": "position", "position": 3},
    {"task_id": 20, "state": "complete", "matched_via": "position", "position": 4},
    {"task_id": 65, "state": "complete", "matched_via": "position", "position": 5},
    {"task_id": 16, "state": "complete", "matched_via": "position", "position": 6},
    {"task_id": 17, "state": "skipped",  "matched_via": "position", "position": 7},
    {"task_id": 15, "state": "skipped",  "matched_via": "position", "position": 8}
  ],
  "judgment_required": [],
  "errors": []
}
```

The intent encoded here matches what Kent expressed on 2026-05-22 (per #371 evidence) — positions 3, 7, 8 skipped; rest done.

---

## Cross-references

- Spec FR-001 (artifact schema), FR-003 (parser output), FR-006 (disambiguator I/O), FR-011 (AGENTS.md target)
- Research D1 (artifact location), D2 (atomic write), D4 (disambiguator prompt), D10 (AGENTS.md cuts)
- Phase 2 contracts: `kitty-specs/shared-jsonl-state-log-library-01KS0E9A/contracts/`
- Phase 3 reference: `scripts/habits/record_completion.py` (existing helper this mission preserves)
- Mission #309 data-model: `kitty-specs/migrate-escalation-to-jsonl-state-model-01KS5R4D/data-model.md` (pattern source)
- Mission #343 judgment surface: `scripts/doc_audit/judgment/client.py` (pattern source for disambiguator)
- Memory: `reference_openclaw_gotchas.md` (AGENTS.md effective budget)
