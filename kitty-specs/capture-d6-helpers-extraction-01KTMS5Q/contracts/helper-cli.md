# Contract: Helper CLI Surfaces (6 helpers)

**Modules**: `scripts/inbox/{mark_processed,route_journal_entry,route_someday,route_calendar_event,handle_clarification_state,classify_content}.py`
**Invocation form**: `python3 -m scripts.inbox.<module>` (MANDATORY per NFR-004 / `[[feedback_helper_m_invocation_form]]`)
**Working directory**: any (Mac repo root OR `/home/claude/kg-automation`); helpers resolve their own paths via `scripts.vault.paths`.

## Common conventions

- Exit codes: 0 = success, 1 = validation error, 2 = runtime error, 3 = refusal
- Stdout: machine-readable output (JSON or `key=value` lines)
- Stderr: errors (JSON `{"error": "<kind>", "detail": "..."}`) and operator-facing logs
- `--help` is supported on every helper; prints usage and exits 0

## `mark_processed`

```
python3 -m scripts.inbox.mark_processed --path <abs-path-to-note>
```

| Flag | Required | Notes |
|---|---|---|
| `--path` | yes | Absolute path to a note in `01-Inbox/` |

**Behavior**:
- Reads frontmatter from note at `--path`
- If `status: processed` already → exit 0 (idempotent no-op)
- Otherwise: set `status: processed`, set `processed_at: <ISO 8601 UTC>`, preserve all other frontmatter, preserve body verbatim, atomic-write
- Exit 0 on success
- Exit 1 if `--path` doesn't exist or isn't a markdown file with frontmatter
- Exit 3 if `--path` is under `~/second-brain/notes/04-Growth/_private/` (C-001 refusal)

## `route_journal_entry`

```
python3 -m scripts.inbox.route_journal_entry --content-file <abs-path> --datetime <ISO 8601>
```

| Flag | Required | Notes |
|---|---|---|
| `--content-file` | yes | Absolute path to a file containing the journal content (raw text, no frontmatter) |
| `--datetime` | yes | ISO 8601 datetime with timezone (e.g., `2026-06-08T07:32:00-04:00`); determines target file name |

**Behavior**:
- Target file: `<paths.journal>/Journal YYYY-MM-DD HHmm.md` (path from `scripts/vault/paths.json`; YYYY-MM-DD HHmm from `--datetime`)
- If target file absent: create with frontmatter `{id, doc_type: journal, created, last_validated}`
- Append the content under a level-2 heading: `## HH:mm — <first 60 chars of content trimmed>` (or `## HH:mm` if content is too short)
- Atomic write throughout
- Exit 0 on success
- Exit 1 if `--content-file` or `--datetime` invalid

## `route_someday`

```
python3 -m scripts.inbox.route_someday --title "<title>" --body "<body>" --note-filename <name>
```

| Flag | Required | Notes |
|---|---|---|
| `--title` | yes | Task title (becomes Vikunja task title) |
| `--body` | yes | Task body |
| `--note-filename` | yes | Source note filename (added to description as `\n\nSource: <name>`) |

**Behavior**:
- Instantiate `scripts.common.vikunja_client.VikunjaClient()`
- Resolve project by name `"Someday"` (`client.list_projects()` → filter by title)
- `client.create_task(project_id=<id>, title=<title>, description=<body>\n\nSource: <name>)` (per C-006, uses create endpoint NOT partial-update)
- Print created task id to stdout: `task_id=<int>`
- Exit 0 on success
- Exit 2 if Vikunja unreachable, project not found, or create fails (stderr has `{"error": "vikunja_error", "detail": "..."}`)

## `route_calendar_event`

```
python3 -m scripts.inbox.route_calendar_event --payload-file <abs-path>
```

| Flag | Required | Notes |
|---|---|---|
| `--payload-file` | yes | Absolute path to a JSON file containing a `CalendarPayload` |

**Behavior**:
- Load JSON from `--payload-file`
- Validate via `scripts.calendar_routing.validate_calendar_event.validate_payload`
- If valid: emit normalized payload as JSON on stdout (with `end` filled in if absent); exit 0
- If invalid: emit `{"error": "invalid_payload", "missing": [...]}` to stderr; exit 1

## `handle_clarification_state`

```
python3 -m scripts.inbox.handle_clarification_state add --note-filename <name> --partial-payload <json>
python3 -m scripts.inbox.handle_clarification_state sweep
python3 -m scripts.inbox.handle_clarification_state match --reply-content <text>
```

### subcommand: `add`

| Flag | Required | Notes |
|---|---|---|
| `--note-filename` | yes | Source note (uniqueness key for `match`) |
| `--partial-payload` | yes | JSON string of partial `CalendarPayload` |

Appends a `PendingClarification` to the state file (creates state file + parent dir if absent). Exit 0 on success.

### subcommand: `sweep`

No required flags. Removes entries with `created_at` > 24h old (relative to `now(timezone.utc)`). Safe on absent state file (exit 0, no error). Prints removed count to stdout: `removed=<int>`.

### subcommand: `match`

| Flag | Required | Notes |
|---|---|---|
| `--reply-content` | yes | The text of an incoming WhatsApp reply |

Heuristic match: returns the most-recent PendingClarification whose `partial_payload.title` substring appears in `--reply-content` (case-insensitive). If no match: print empty JSON `null` to stdout, exit 0. If match: print the matched entry as JSON, exit 0. (The `match` subcommand does NOT delete the entry; deletion is the caller's responsibility after the calendar event is successfully created.)

## `classify_content`

```
python3 -m scripts.inbox.classify_content --content-file <abs-path>
```

| Flag | Required | Notes |
|---|---|---|
| `--content-file` | yes | Absolute path to a note (frontmatter + body) |

**Behavior**:
- Read frontmatter + body
- Split body into blocks via the documented heuristic (R-003 in research.md)
- Per-block: apply regex/keyword/heading-based classification → `Block` entry
- Block kinds that can't be confidently classified → `kind: "ambiguous"`, `confidence: "low"`, `flag: "needs-llm-disambiguation"`
- Emit `ClassificationOutput` JSON to stdout
- Exit 0 on success
- Exit 1 if `--content-file` doesn't exist or can't be parsed
- Exit 3 if `--content-file` is under `04-Growth/_private/`

## Test contract (summary)

Each helper has a corresponding `tests/inbox/test_<helper>.py`. Per-helper expected test coverage:

- **`mark_processed`**: idempotency, frontmatter preservation, atomic write, private-path refusal, missing-file handling — ~12 cases
- **`route_journal_entry`**: file creation, file append, heading format, timezone math — ~10 cases
- **`route_someday`**: Vikunja client mocking, project-name resolution, create-not-update, error paths — ~10 cases
- **`route_calendar_event`**: valid payload → normalized output, invalid payload → structured error, end-time default fill — ~8 cases
- **`handle_clarification_state`**: each subcommand × (state-present / state-absent), 24h aging boundary, match heuristic — ~15 cases
- **`classify_content`**: each block kind × (high/medium/low confidence), boundary heuristics, ambiguous flagging — ~20 cases

Total: ~75 test functions across 6 test files. Coverage gate ≥90% line / ≥85% branch per helper.

## Backwards-compatibility commitment

These CLI surfaces are the externally observable contracts. Changes to flag names, exit codes, or output JSON shape are breaking changes and require a separate mission with migration notes.
