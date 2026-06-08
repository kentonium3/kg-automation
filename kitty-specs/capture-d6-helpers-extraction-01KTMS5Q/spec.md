# Specification: Capture Directive-6 Helpers Extraction

**Mission**: `capture-d6-helpers-extraction-01KTMS5Q`
**Mission ID**: `01KTMS5QGXFJWQYVXB03SPYB48`
**Target branch**: `main`
**Mission type**: `software-dev`
**Issue**: kentonium3/kg-automation#566 (helpers half; AGENTS.md rewrite split to follow-on mission); parent epic #563
**Created**: 2026-06-08

## Purpose (Stakeholder Summary)

felix-admin-capture's `AGENTS.md` is currently 52,942 chars in repo (39,843 chars in the deployed copy as of `#567`'s first sync) — well over openclaw's 12,000-char workspace-bootstrap budget. Every cron tick silently truncates load-bearing Step 5 routing/preserve instructions, which is the root cause of the silent inbox content loss observed in epic #563. The structural fix (Felix Constitution Directive 6) is to extract the prompt's deterministic step-by-step recipes into helper scripts the agent invokes, and reserve the prompt for judgment, classification, and voice.

This mission ships **half 1**: six new stdlib Python helpers under `scripts/inbox/`, each with full test coverage, each invokable via `python3 -m scripts.inbox.<module>` (mandatory per `[[feedback_helper_m_invocation_form]]`). The AGENTS.md rewrite that invokes them is deliberately split into a **follow-on mission** so #567's 5-minute deploy pipeline can land the helpers on `/home/claude/kg-automation` before the prompt depends on them — avoiding the `ModuleNotFoundError` class that bit us in #558 + #562. Existing helpers in `scripts/inbox/` (`append_routing_entry`, `file_inbox_quality_issue`, `handle_marker_cleanup`, `handle_parse_failures`, `inject_parse_error_marker`, `prescan`, `routing_log`, `strip_parse_error_marker`) stay untouched.

## User Scenarios & Testing

### Primary scenario: future capture cron tick invokes the new classify + route chain

1. felix-admin-capture cron fires at 7am ET. AGENTS.md (rewritten in the follow-on mission) instructs the agent: "invoke `python3 -m scripts.inbox.classify_content --content-file <note>`".
2. The classifier returns structured JSON: `{blocks: [{kind: "journal", content: "...", confidence: "high"}, {kind: "ambiguous", content: "...", flag: "needs-llm-disambiguation"}]}`
3. The agent disambiguates ambiguous blocks via prompt judgment, then invokes one of: `route_journal_entry`, `route_someday`, `route_calendar_event` per classification.
4. For successfully routed notes, the agent invokes `python3 -m scripts.inbox.mark_processed --path <note>` which atomically writes `status: processed` + `processed_at: <ISO 8601>` to the note's frontmatter — and LEAVES the file in `01-Inbox/` (per Step 5c of the current prompt; the "do NOT delete" invariant that's been silently truncated).
5. The agent invokes `append_routing_entry` (existing helper) to record the route in the dedup substrate.

### Scenario: calendar event with all required fields

1. The agent classifies a block as `kind: calendar`.
2. The agent assembles the payload (date, time, title, etc.) and invokes `python3 -m scripts.inbox.route_calendar_event --payload-file <tmp>` which validates the payload via the existing `scripts/calendar_routing/validate_calendar_event.py` and emits a normalized delegation payload on stdout.
3. The agent delegates to Felix main for `gog calendar create` (delegation surface stays in the prompt; the helper just validates + emits).

### Scenario: calendar event with missing fields → clarification

1. Validation fails; `route_calendar_event` exits non-zero with structured stderr describing missing fields.
2. The agent invokes `python3 -m scripts.inbox.handle_clarification_state add --note-filename <name> --partial-payload <json>` which appends to `~/second-brain/agents/state/pending-calendar-clarifications.json`.
3. The agent sends a single WhatsApp clarification prompt.
4. Daily at 02:00 UTC, a sweep tick invokes `python3 -m scripts.inbox.handle_clarification_state sweep` which deletes entries older than 24h.

### Scenario: Someday item

1. The agent classifies a block as `kind: someday`.
2. The agent invokes `python3 -m scripts.inbox.route_someday --title "<title>" --body "<body>" --note-filename <name>` which creates a Vikunja task in the Someday project (resolved by name via `scripts/common/vikunja_client.py` from #542).
3. Helper exits 0 on success, non-zero on Vikunja errors (with structured stderr).

### Operator scenario: dry-run testing

1. From repo root (or office2's `/home/claude/kg-automation`): `python3 -m scripts.inbox.classify_content --content-file <test-note>` → prints classifier output to stdout for inspection.
2. No state mutation. Useful for prompt tuning and regression debug.

## Domain Language

| Term | Definition |
|---|---|
| **Note** | A markdown file in `01-Inbox/` with YAML frontmatter including a `status` field. |
| **Block** | A semantic unit within a note's body (separated by a heading, blank lines, or topic shift). One note can contain multiple blocks of different kinds. |
| **Block kind** | One of: `journal`, `calendar`, `someday`, `github_issue`, `vikunja_task`, `parse_failure`, `ambiguous`. The classifier emits these. |
| **Routing destination** | The Felix-canonical target for a block kind: journal → `08-Journal/Journal YYYY-MM-DD HHmm.md`; calendar → Felix main + gog; someday → Vikunja Someday project; github_issue → `kg-felix-bot` issue writer; vikunja_task → vikunja_client; parse_failure → quality issue + marker. |
| **Mark processed** | Atomic frontmatter update to `status: processed` + `processed_at: <ISO 8601>`. File STAYS at original path; not moved. |
| **Clarification state** | `~/second-brain/agents/state/pending-calendar-clarifications.json` — list of pending calendar events awaiting Kent's WhatsApp reply. Sweep ages out entries >24h. |
| **In-scope helper** | One of the 6 NEW helpers shipped in this mission. Excludes the existing 8 helpers in `scripts/inbox/`. |
| **`-m` invocation form** | `python3 -m scripts.inbox.<module>` — mandatory per NFR-004 and `[[feedback_helper_m_invocation_form]]`. Script-path form (`python3 scripts/inbox/x.py`) fails `ModuleNotFoundError` and has caused TWO production incidents. |

## Functional Requirements

| ID | Description | Status |
|---|---|---|
| FR-001 | `scripts/inbox/mark_processed.py` exists with CLI: `python3 -m scripts.inbox.mark_processed --path <abs-path>`. Atomically writes `status: processed` + `processed_at: <ISO 8601 UTC>` to the note's YAML frontmatter; preserves all other frontmatter fields; preserves the file location (does NOT move the file). | Specified |
| FR-002 | `mark_processed` is idempotent: invoking on a note already at `status: processed` is a no-op (exit 0, no mutation). | Specified |
| FR-003 | `scripts/inbox/route_journal_entry.py` exists with CLI: `python3 -m scripts.inbox.route_journal_entry --content-file <abs-path> --datetime <ISO 8601 local>`. Appends content as a new section under a level-2 heading (timestamp) to `08-Journal/Journal YYYY-MM-DD HHmm.md` (path derived from `--datetime`). Creates the journal file if absent with correct frontmatter (id, doc_type=journal, created date). | Specified |
| FR-004 | `scripts/inbox/route_someday.py` exists with CLI: `python3 -m scripts.inbox.route_someday --title "<title>" --body "<body>" --note-filename <name>`. Creates a Vikunja task in the project resolved by name to `Someday` via `scripts.common.vikunja_client.VikunjaClient`. Body includes the body text + a footer line `Source: <note-filename>`. | Specified |
| FR-005 | `scripts/inbox/route_calendar_event.py` exists with CLI: `python3 -m scripts.inbox.route_calendar_event --payload-file <abs-path>`. Validates the payload via `scripts.calendar_routing.validate_calendar_event` (existing helper). On valid: emits the normalized payload on stdout as JSON for the agent to delegate to Felix main. On invalid: exits non-zero with structured stderr listing missing fields. | Specified |
| FR-006 | `scripts/inbox/handle_clarification_state.py` exists with three subcommands: `add` (append pending clarification to state file), `sweep` (delete entries with `created_at` > 24h old), `match` (find the pending clarification for an incoming reply; output the clarification or empty). State file: `~/second-brain/agents/state/pending-calendar-clarifications.json` (array of objects: `{note_filename, partial_payload, created_at}`). | Specified |
| FR-007 | `scripts/inbox/classify_content.py` exists with CLI: `python3 -m scripts.inbox.classify_content --content-file <abs-path>`. Reads the note (frontmatter + body), splits body into blocks (heuristic: paragraph breaks + heading boundaries), applies deterministic per-block classification (regex/keyword/heading-based), and emits structured JSON: `{note_filename, blocks: [{index, kind, content, confidence}]}`. Blocks the helper cannot classify confidently are emitted with `kind: "ambiguous"` and a `flag: "needs-llm-disambiguation"` field — the agent prompt disambiguates. | Specified |
| FR-008 | Every helper accepts `--help` and prints CLI usage. | Specified |
| FR-009 | Every helper exits 0 on success and non-zero on failure with a structured error message on stderr (filename, error kind, error detail). | Specified |
| FR-010 | Every helper that mutates a file uses the atomic write pattern (write-temp + fsync + `os.replace`) per `tests/inbox/test_atomic_write_perms.py` precedent. | Specified |
| FR-011 | Helpers are runnable from BOTH the Mac repo root (`/Users/kentgale/repos/kg-automation`) AND office2 (`/home/claude/kg-automation`) without modification. Path lookups go through `scripts.vault.paths` (existing helper) where applicable. | Specified |
| FR-012 | No existing helper in `scripts/inbox/` is modified by this mission. New helpers may IMPORT from existing modules (e.g., `routing_log.py`) but MUST NOT alter their interfaces. | Specified |
| FR-013 | No file under `scripts/openclaw/agents/felix-admin-capture/` (i.e., AGENTS.md, IDENTITY.md, etc.) is modified by this mission. The AGENTS.md rewrite is the follow-on mission. | Specified |
| FR-014 | `classify_content.py` documents its classification heuristics (regex patterns, keyword lists, heading conventions) inline so the follow-on AGENTS.md rewrite has a stable reference. | Specified |
| FR-015 | The `handle_clarification_state.py sweep` subcommand is safe to run when the state file is absent or empty (no error, exit 0). | Specified |

## Non-Functional Requirements

| ID | Description | Status |
|---|---|---|
| NFR-001 | Each helper completes a single invocation in under 500 ms on office2 hardware for typical inputs (one note, <50KB). Measured: `time python3 -m scripts.inbox.<helper> <typical-args>`. | Specified |
| NFR-002 | Each helper imports only Python 3.10+ standard library OR existing modules under `scripts/` and `scripts/common/`. No new third-party dependencies (no `requests`, `httpx`, `pydantic`, `python-frontmatter`, etc.). | Specified |
| NFR-003 | Test coverage per helper: ≥90% line, ≥85% branch via `pytest --cov`. Enforced per-helper via the existing `tests/inbox/` conventions. | Specified |
| NFR-004 | Invocation form is `python3 -m scripts.inbox.<module>` in all documentation, runbooks, tests, and integration smoke. Script-path form is forbidden per `[[feedback_helper_m_invocation_form]]`. | Specified |
| NFR-005 | Helpers print machine-readable output (JSON for classify_content, structured key=value for others) on stdout; logs and errors go to stderr. | Specified |
| NFR-006 | Helpers are stateless except for their explicit state files. No in-process caches, no module-level globals beyond constants. | Specified |

## Constraints

| ID | Description | Status |
|---|---|---|
| C-001 | Per CLAUDE.md, `~/second-brain/notes/04-Growth/_private/` is NEVER read, written, referenced, or logged by any helper. Verified by a dedicated test that synthesizes a private-path input and asserts the helper refuses or never reaches it. | Specified |
| C-002 | Per CLAUDE.md and `[[reference_office2_agent_deploy_paths]]`, the second brain lives at `~/second-brain/` (kgale-owned). Helpers running as `claude` user on office2 read + write via the path-resolution helper (no hard-coded /home/kgale/ paths). | Specified |
| C-003 | Helpers MUST NOT call any external network endpoint EXCEPT Vikunja via the existing `scripts.common.vikunja_client.VikunjaClient` (which is already stdlib-only and rate-limited). No direct gog / GitHub / WhatsApp calls. | Specified |
| C-004 | Per `[[feedback_speckitty_split_code_and_deploy_missions]]`, the AGENTS.md rewrite is split into a follow-on mission. The helpers must reach office2 (via #567's deploy pipeline, 5 min lag) BEFORE the rewritten AGENTS.md invokes them. This is a sequencing constraint enforced by mission boundary, not by code. | Specified |
| C-005 | Risk tier 3 (Standard). No state-changing system config beyond writing files in user-owned paths. No service-inventory.json change beyond adding the new helper components. No new credential surface. | Specified |
| C-006 | `[[feedback_vikunja_post_partial_replace]]` — Vikunja POST partial-replace zeros unstated fields. `route_someday.py` MUST use the create endpoint (`POST /projects/<id>/tasks`), NOT a partial-update on an existing task. | Specified |

## Success Criteria

1. All 6 helpers exist under `scripts/inbox/` and are importable via `python3 -c "import scripts.inbox.<module>"` from repo root.
2. Each helper passes `pytest tests/inbox/test_<helper>.py --cov=scripts.inbox.<helper> --cov-branch --cov-fail-under=90` with branch coverage ≥85%.
3. End-to-end smoke: a synthetic inbox note with mixed-block content (journal + calendar + someday + parse_failure) classifies into the expected blocks via `classify_content`, and the per-block route helpers each succeed on their respective synthetic payloads.
4. From a clean office2 checkout post-merge (via #567's 5-min deploy tick): `python3 -m scripts.inbox.mark_processed --help` exits 0 with usage text. (Smoke check that `-m` invocation actually works in production env.)
5. No regression in existing inbox helpers: `pytest tests/inbox/` continues to pass at its current rate.
6. No file under `scripts/openclaw/agents/felix-admin-capture/` is modified in this mission's diff.

## Key Entities

| Entity | Fields | Notes |
|---|---|---|
| **ClassificationOutput** (JSON, classify_content stdout) | `note_filename` (str), `blocks` (array of Block) | The structured output that the follow-on AGENTS.md rewrite consumes. |
| **Block** (inside ClassificationOutput) | `index` (int, 0-based), `kind` (enum: journal/calendar/someday/github_issue/vikunja_task/parse_failure/ambiguous), `content` (str), `confidence` (enum: high/medium/low), `flag` (str, optional — e.g., `needs-llm-disambiguation` for `ambiguous` kind) | One Block per semantic unit within a note's body. |
| **CalendarPayload** (JSON, route_calendar_event input) | `title` (str), `start` (ISO 8601), `end` (ISO 8601, optional), `location` (str, optional), `description` (str, optional) | Validated via existing `scripts.calendar_routing.validate_calendar_event`. |
| **PendingClarification** (JSON, in state file) | `note_filename` (str), `partial_payload` (CalendarPayload-shaped, possibly missing fields), `created_at` (ISO 8601 UTC) | One entry per outstanding clarification. Aged out at 24h. |

## Assumptions

- The existing `scripts.common.vikunja_client.VikunjaClient` from #542 is stable; this mission consumes it without modification.
- The existing `scripts.calendar_routing.validate_calendar_event` is stable; this mission consumes it as the validation gate for `route_calendar_event`.
- Test fixtures use the same `tmp_path` + `conftest.py` pattern as existing `tests/inbox/` files. No new test infrastructure required.
- The `08-Journal/` path resolution goes through `scripts/vault/paths.json` → `paths.journal`. Helpers do NOT hard-code `~/second-brain/notes/08-Journal/`.
- Clarification state file lives at `~/second-brain/agents/state/pending-calendar-clarifications.json` per the #558 prior design; the helper creates the directory if absent.
- "Ambiguous" block kind from `classify_content` is for the LLM to disambiguate; no Anthropic SDK call from the helper itself (LLM call stays in the prompt where credentials live).
- Helpers run with claude user permissions on office2; `~/second-brain/` is readable + writable by claude (verified by existing helpers).

## Out of Scope

- AGENTS.md rewrite (follow-on mission, also closes #566).
- Modifications to existing helpers under `scripts/inbox/`.
- New top-level service in `service-inventory.json`. The deploy of the new helpers happens via #567's existing pipeline; no new systemd unit, no new credential.
- LLM disambiguation logic (stays in the prompt, where credentials and judgment live).
- The defensive prescan inverse check (#568, separate mission).
- WhatsApp send-side surface for clarification prompts (stays in the prompt; helpers only manage the state file).
- gog calendar create execution (stays in Felix main per #558).

## Architecture Documentation Updates (DIR-005)

This mission is intentionally narrow — new helper files in `scripts/inbox/` and matching tests in `tests/inbox/`. Architecture-doc impact is minimal:

| File | Update |
|---|---|
| `docs/design/architecture/data/service-inventory.json` | Extend `services[openclaw-gateway].agents.felix-admin-capture.components` array with 6 new component entries (mark-processed, route-journal-entry, route-someday, route-calendar-event, handle-clarification-state, classify-content). Set `updated_by` to include this mission. |
| `docs/design/architecture/data/signal-to-doc-map.json` | No change. The `agent-prompt-changed` change_class (added by #567) covers this mission's class. |
| `docs/runbooks/inbox-ops.md` (if present) | Brief mention of the new helper invocation patterns; defer full operator-runbook section to the follow-on mission where AGENTS.md changes are user-visible. |

## Reference Index

- Issue: kentonium3/kg-automation#566 (helpers half; AGENTS.md rewrite split to follow-on mission)
- Parent epic: kentonium3/kg-automation#563
- Sibling sub-issues (separate missions): #567 (deploy pipeline, MERGED 2026-06-08), #568 (prescan inverse check)
- Memory references:
  - `[[feedback_helper_m_invocation_form]]` — `-m` invocation form mandatory; production failures TWICE
  - `[[feedback_scripts_vs_llm]]` — Directive 6 split rationale (this mission IS the canonical example)
  - `[[feedback_speckitty_split_code_and_deploy_missions]]` — mission boundary rationale
  - `[[reference_office2_agent_deploy_paths]]` — kgale vs claude paths
  - `[[feedback_vikunja_post_partial_replace]]` — Vikunja gotcha for `route_someday`
- Architecture: `docs/design/architecture/data/service-inventory.json` § `services[openclaw-gateway].agents.felix-admin-capture` (verified production name per the 2026-06-08 lesson in #567's post-merge fix)
- Existing helper precedents: `scripts/inbox/append_routing_entry.py` (interface shape), `scripts/inbox/inject_parse_error_marker.py` (atomic write pattern), `tests/inbox/test_atomic_write_perms.py` (test pattern), `tests/inbox/test_classifier_regression.py` (classification testing pattern)
