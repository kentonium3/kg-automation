# Inbox calendar and aspiration routing

**Mission ID**: 01KTHHXSAP609CQYPJ490JV1NJ
**Mission slug**: inbox-calendar-and-aspiration-routing-01KTHHXS
**Mission type**: software-dev
**Target branch**: main
**Created**: 2026-06-07
**Source issue**: kentonium3/kg-automation#558 (supersedes #324; scoped slice of #271)

## Purpose

**TL;DR**: Stop the capture agent from creating useless Vikunja todos for calendar events and aspirations; route them to Google Calendar or the journal instead.

**Context**: When Kent submits items via WhatsApp or Obsidian inbox, the capture agent currently flattens everything into Vikunja todos — including calendar events that should be on Google Calendar, and aspirations/musings that should be journal entries. This mission adds explicit routing for calendar events (auto-scheduled via gog when complete; WhatsApp clarification loop when incomplete), routes aspirations to dated journal entries, and adds a Vikunja "Someday" destination for concrete-but-parked items. It also tightens the task rule so events and aspirations stop falling through it. This is a scoped slice of the #271 Felix-as-mirror epic and supersedes #324.

## Domain Language

Terminology discipline (used consistently throughout this spec and downstream artifacts):

- **Block**: a distinct topic or content unit extracted from a single inbox file. One inbox file can yield multiple blocks.
- **Calendar event**: a block that describes a scheduled time-bounded happening with a date/time (and optionally recurrence, location, attendees). Belongs on Google Calendar, never as a Vikunja task.
- **Aspiration / musing**: a block framed as a wish, wondering, or self-observation rather than a commitment. Belongs in the dated journal entry, not Vikunja.
- **Someday item**: a block describing a concrete actionable item that Kent explicitly frames as not-now ("eventually", "someday", "when I get around to it"). Belongs in the Vikunja "Someday" project, not the active Inbox.
- **Active task**: a block with a concrete verb AND a clear completability test ("call dentist to reschedule cleaning"). Belongs in the Vikunja Inbox project.
- **Complete calendar event**: a calendar-classified block with at least: title, start datetime, and end datetime or duration.
- **Incomplete calendar event**: a calendar-classified block missing one or more required fields.
- **Clarification prompt**: the portion of the capture agent's WhatsApp turn-summary that enumerates missing fields for an incomplete calendar event.
- **Clarification reply**: Kent's WhatsApp response that provides missing fields for one or more open clarifications.

## User Scenarios & Testing

### Primary scenario — calendar event, complete

- **Actor**: Kent.
- **Trigger**: capture agent's cron tick (7am/noon/5pm/10pm) picks up an unprocessed inbox file containing a complete calendar event.
- **Happy path**:
  1. Capture classifies the block as a calendar event.
  2. Capture extracts: title, start datetime, end datetime or duration, optional location, optional recurrence, optional attendees.
  3. Completeness check passes.
  4. Capture delegates to Felix main via the openclaw agent channel with a structured payload.
  5. Felix main creates the event in Google Calendar (one-off or recurring per the parsed RRULE).
  6. Capture's WhatsApp turn-summary confirms the created event with its title, time, and recurrence pattern.
- **Always-true rule**: no Vikunja task is created for this block.

### Primary scenario variant — calendar event, incomplete

- **Actor**: Kent.
- **Trigger**: same as above, but the block is missing a required field (e.g., "lunch with John next Tuesday" — no start time).
- **Happy path**:
  1. Capture classifies the block as a calendar event.
  2. Completeness check returns missing fields.
  3. The source inbox note is left in `01-Inbox/` with `status: needs-review` until clarification resolves.
  4. Capture's WhatsApp turn-summary enumerates the missing fields ("'lunch with John next Tuesday' — need start time and end time or duration").
  5. Kent replies via WhatsApp with the missing details.
  6. The receiving agent (capture or Felix main, determined by openclaw whatsapp inbound routing — confirmed in plan phase) reads the pending-calendar-clarifications state file, matches Kent's reply to the corresponding entry, and creates the event.
- **Exception (no reply within window)**: 24 hours after the clarification prompt, the source note remains at `status: needs-review` and the pending clarification is logged as timed out.

### Primary scenario — aspiration / musing → journal

- **Actor**: Kent.
- **Trigger**: capture cron tick picks up an inbox file containing an aspirational block ("I should get to bed earlier", "I wonder if I qualify for a small business loan").
- **Happy path**:
  1. Capture classifies the block as aspiration / musing.
  2. Capture writes or appends to `08-Journal/Journal YYYY-MM-DD HHmm.md` using the existing voice-dump cleanup conventions.
- **Always-true rule**: no Vikunja task is created for this block.

### Primary scenario — Someday-framed item → Vikunja Someday

- **Actor**: Kent.
- **Trigger**: capture cron tick picks up an inbox file with a concrete actionable block framed as parked ("get rid of the old lawn tractor when I get around to it").
- **Happy path**:
  1. Capture classifies the block as Someday item.
  2. Capture resolves the Vikunja "Someday" project and creates a task there with the inferred identity label and source reference.
- **Always-true rule**: no `due_date` is set; the task does not surface in the daily habit/morning check-in.

### Edge cases

- **Recurrence with ambiguous phrasing** ("trivia nights" without explicit weekday): completeness check returns "missing recurrence pattern"; clarification loop applies.
- **Calendar event mixed with task in the same block** ("attend marketing meeting Tuesday 2pm — also need to prep the deck"): split into two blocks per existing Step 2 conventions; calendar block routes to GCal, task block routes to Vikunja Inbox.
- **Goal declaration vs aspiration ambiguity**: existing Felix-declaration validation (specific date + present-tense + observable evidence) takes precedence. Valid declarations route to `03-Constitution/Goals-MOC.md`; aspirational shapes route to journal.
- **Someday vs aspiration ambiguity**: classification fidelity is intentionally good-enough; misroutes are recoverable via routing log + `log_action` audit trail.
- **Clarification reply provides partial fields**: the receiving agent re-prompts via WhatsApp turn-summary for remaining gaps until complete or 24h timeout.
- **Calendar write failure (`gog` error)**: source note remains at `status: needs-review`; failure logged and surfaced in WhatsApp turn-summary verbatim; no retry within the cron tick. Next cron tick does not re-attempt automatically — Kent decides whether to resubmit.

## Functional Requirements

| ID | Description | Status |
|---|---|---|
| FR-001 | Capture identifies calendar events as a distinct classification from tasks, aspirations, and Someday items. The classification prompt explicitly rejects "attend X meeting" shapes from the task category. | Pending |
| FR-002 | Capture extracts structured calendar event fields from a calendar-classified block: title, start datetime, end datetime or duration, optional location, optional recurrence phrase, optional attendees. | Pending |
| FR-003 | A calendar-completeness validator (deterministic helper, not an LLM call) accepts the extracted fields and returns either (a) a complete payload with a parsed RRULE and a ready-to-invoke calendar-write argument list, or (b) a structured `missing` list naming each absent required field. The validator never invokes Google Calendar directly. | Pending |
| FR-004 | The calendar-completeness validator parses natural-language recurrence into RFC 5545 RRULE strings for these patterns: weekly on a named weekday ("every Tuesday", "weekly on Tuesday"), biweekly ("every other week"), monthly on a numeric day ("monthly on the 15th"), and by-weekday-of-month ("first Monday of the month", "last Friday"). Patterns outside this set return "missing recurrence". | Pending |
| FR-005 | When the calendar event is complete, capture delegates to Felix main via the openclaw agent channel with a structured calendar-creation payload. Felix main creates the event in Google Calendar via the existing `gog` skill. Capture does not invoke `gog` directly. | Pending |
| FR-006 | When the calendar event is incomplete, capture's WhatsApp turn-summary enumerates the missing fields for each incomplete event. The source inbox note is left in `01-Inbox/` with `status: needs-review` until the clarification resolves or times out. | Pending |
| FR-007 | A pending-calendar-clarifications state file (JSONL, append-and-rewrite, located alongside the existing inbox routing log) records each open incomplete calendar event with: a clarification ID, source inbox path, source block index, fields-so-far, missing fields, sent_at timestamp. The receiving agent (capture or Felix main, depending on which one processes Kent's WhatsApp reply) reads this file to match the reply to an open clarification and complete the event creation. The receiving agent is responsible for removing the resolved entry. 24 hours after the prompt, an unresolved entry triggers `status: needs-review` on the source note and emits a `calendar_event_clarification_timeout` action; the entry remains in the state file until manually purged so the audit trail is preserved. | Pending |
| FR-008 | Capture identifies aspirations / musings as a distinct classification and routes them to `08-Journal/Journal YYYY-MM-DD HHmm.md` (creating or appending). Aspiration-classified blocks NEVER produce a Vikunja task. | Pending |
| FR-009 | Capture identifies Someday-framed items as a distinct classification and routes them to the Vikunja "Someday" project with the inferred identity label and source reference. Someday tasks have no `due_date` and do not appear in the active Vikunja Inbox project. | Pending |
| FR-010 | The "Task or action item" classifier qualifies a block as a task only when it has a concrete verb AND a clear completability test. Calendar event shapes ("attend X") and aspirational shapes ("be/become/get [adj]er") are explicitly rejected from this category. | Pending |
| FR-011 | Every classification decision and every downstream action (calendar create, journal append, Someday task create, clarification send, clarification resolve, clarification timeout) emits a structured `log_action` event using the existing observability convention. New action types are added to the capture agent's allowlist. | Pending |
| FR-012 | Re-processing the same inbox file (e.g., across cron retries) does not produce duplicate calendar events, journal entries, or Someday tasks. Dedup rides on the existing routing log substrate. | Pending |

**Design note on FR-007 (resolved at spec time):** the clarification originally proposed as `[NEEDS CLARIFICATION: ...]` here — whether the openclaw whatsapp channel preserves quoted context on inbound replies, and whether that obviates a state file — was resolved by always writing the state file. The state file is small, append-only, and matches existing inbox helper conventions, so there is no downside to writing it regardless of WhatsApp inbound behavior. Plan phase still verifies the inbound-routing behavior, but only to decide *which* agent reads the state file (capture vs Felix main); the FR-007 contract is invariant to that decision.

This resolution was made because spec-kitty 3.2.0rc37 has a bug (kg-automation#559) that prevents the Decision Moment Protocol from running during specify on this version. The clarification could not be cleanly deferred. Resolving it upfront is workaround A from kg-automation#559.

## Non-Functional Requirements

| ID | Description | Measurable threshold | Status |
|---|---|---|---|
| NFR-001 | Per-inbox-file classification and routing completes within an acceptable budget so cron ticks finish before the next scheduled tick. | ≤30 seconds per inbox file at the 95th percentile under normal load. | Pending |
| NFR-002 | No silent drops on the calendar write path. | 100% of calendar-classified complete events either appear on Google Calendar OR have a `calendar_event_failed` action logged AND a failure line in the WhatsApp turn-summary. | Pending |
| NFR-003 | Audit trail completeness. | 100% of classification decisions produce a `log_action` entry with category and outcome populated. | Pending |
| NFR-004 | Idempotency. | Re-processing the same inbox file 10 consecutive times produces exactly one calendar event / journal append / Someday task per original block. | Pending |
| NFR-005 | Calendar-completeness validator test coverage. | ≥90% line coverage and ≥85% branch coverage on the validator's unit tests. | Pending |

## Constraints

| ID | Description | Status |
|---|---|---|
| C-001 | Reuse the existing openclaw agent delegation pattern. No new agents are introduced. | Pending |
| C-002 | Calendar writes go through Felix main's existing `gog` skill. Capture does not invoke `gog` directly. | Pending |
| C-003 | Reuse the existing `log_action.py` observability stream. New action types extend the existing allowlist. | Pending |
| C-004 | Reuse the existing `~/second-brain/agents/state/inbox-routing.jsonl` dedup substrate. No parallel dedup mechanism is introduced. | Pending |
| C-005 | The absolute privacy rule applies: no read, write, reference, or log of `~/second-brain/notes/04-Growth/_private/` content. Aspirations that reference private growth work route only to public `04-Growth/` files or to `_bridge.md`, never to `_private/`. | Pending |
| C-006 | Change scope is Tier 3 (Logic / Workflow): agent standing orders, helper script, tests, and architecture JSON updates. No host configuration, network, credential, port, or sudo-protected resource is modified. | Pending |
| C-007 | This mission introduces no new external services and no new credentials. Existing Google Calendar credential reuse via Felix main is the only external write boundary. | Pending |

## Success Criteria

- **SC-001 — Routing accuracy**: across a curated classifier regression set (size determined in plan phase), the classifier routes each item to its expected destination at ≥90% accuracy on first review.
- **SC-002 — Zero false-Vikunja-todos for calendar events**: in the 14 days following deployment, zero calendar-classified blocks produce a Vikunja task (active or Someday), verified against the `log_action` stream.
- **SC-003 — Zero false-Vikunja-todos for aspirations**: in the 14 days following deployment, zero aspiration-classified blocks produce a Vikunja task, verified against the `log_action` stream.
- **SC-004 — End-to-end calendar create succeeds**: at least one real Kent-submitted complete calendar event (one-off OR recurring) is created on Google Calendar via the new path within the first 14 days, with Kent's WhatsApp turn-summary confirming the event.
- **SC-005 — Clarification loop closes**: at least one real incomplete calendar event surfaces in a WhatsApp clarification prompt and is resolved by Kent's reply (or times out cleanly to `needs-review`) within the first 14 days.
- **SC-006 — No regressions on existing routes**: all existing non-calendar, non-aspiration routing destinations (Constitution, Health, Business, Goals, GitHub issues, active tasks) continue to receive their correct blocks at the same rate as the pre-deployment baseline.

## Key Entities

- **Inbox note**: existing entity (Obsidian markdown file in `01-Inbox/` with YAML frontmatter).
- **Routing log entry**: existing entity (line in `inbox-routing.jsonl`). Extended only by widening the destination type vocabulary.
- **`log_action` event**: existing entity. Extended by new action types: `calendar_event_created`, `calendar_event_failed`, `calendar_event_clarification_sent`, `calendar_event_clarification_resolved`, `calendar_event_clarification_timeout`, `journal_entry_appended`, `someday_task_created`.
- **Calendar event payload**: new entity. Structured data passed from capture to Felix main: `{title, start_datetime, end_datetime_or_duration, location?, rrule?, attendees?, source_inbox_path}`. Lives transiently between classification and the delegation call.
- **Pending clarification record**: new entity. Shape: `{clarification_id, source_inbox_path, source_block_index, fields_so_far, missing_fields, sent_at}`. Stored as one JSONL line in the pending-calendar-clarifications state file.
- **Journal entry block**: existing entity (markdown content appended to a dated journal file in `08-Journal/`).
- **Someday task**: instance of the existing Vikunja task entity, routed to a specific project ("Someday") with no `due_date`.

## Assumptions

- Felix main currently has working `gog calendar create` invocation including `--rrule` for recurrence. Plan phase confirms via live probe on office2 per DIR-006.
- The Vikunja "Someday" project exists by name. Plan phase confirms via Vikunja API probe; if the project does not exist, plan phase decides whether to create it as part of this mission or treat its absence as a precondition.
- The openclaw agent delegation channel from capture → Felix main can carry a synchronous-style structured payload exchange within the cron tick window. Plan phase confirms by reusing or extending the existing `enrich_task` delegation pattern documented in capture's AGENTS.md.
- The openclaw whatsapp channel (v2026.5.28 plugin) routes Kent's inbound replies in a way that one of the existing agents (capture or Felix main) can read the message body and reconcile it against the pending-calendar-clarifications state file. Plan phase verifies which agent receives the inbound (capture vs main), but FR-007's contract is invariant to that choice — only the agent's standing orders change.
- The existing classifier LLM (Claude haiku per capture's identity label) can reliably distinguish the new categories with prompt-only guidance. Plan phase validates this assumption by running the regression set against the proposed prompt before committing to implementation.
- `08-Journal/Journal YYYY-MM-DD HHmm.md` files follow a consistent format the routing logic can append to. Plan phase confirms by reading existing journal files.

## Documentation Synchronization Requirement

Per DIR-005 and the kg-automation change-control protocol, this mission's merge MUST include synchronized updates to the following docs in the same PR (deferring to follow-on issues is an anti-pattern per the migration-no-vestiges convention):

- `docs/design/architecture/data/agent-inventory.json` — felix-admin-capture capability summary (revised routing surface) and Felix main capability summary (if a calendar-reply handler is added).
- `docs/design/architecture/data/data-flows.json` — three new flows: (1) inbox → capture → Felix main → gog → Google Calendar; (2) inbox → capture → WhatsApp clarification → Kent reply → calendar create; (3) inbox → capture → 08-Journal/.
- `scripts/openclaw/agents/felix-admin-capture/AGENTS.md` — Step 3 routing table, new completeness logic, WhatsApp clarification turn-summary shape, new action-type allowlist entries.
- Felix main standing-orders document (exact path confirmed during plan phase) — calendar-reply handler if FR-007's clarification resolves it to require one.
- `docs/INDEX.md` and `docs/DEVELOPER_PORTAL.md` — only if a new doc surface is added (e.g., a runbook for the clarification loop). Consult `docs/design/architecture/data/signal-to-doc-map.json` with `change_class: service-modified` and `change_class: data-flow-added-or-modified` for the canonical doc-target list.
- `tests/inbox/` — new unit tests for the calendar-completeness validator and the classifier regression set.

## Out of Scope

- The broader #271 Felix-as-mirror / back-chaining / tangent-detection framework.
- The hierarchical goal/priority/task tracking substrate.
- Email-derived calendar events. This mission covers WhatsApp + Obsidian inbox sources only.
- Calendar event updates and cancellations. This mission covers creation only.
- The rest of #556 (broader capture-side classification beyond calendar / aspiration / Someday / task tightening; habits side already resolved in 363685ea).
- Calendar conflict detection. Felix main creates the event as requested; conflict-checking is future work.
- Multi-day or all-day event nuance (timezone DST edge cases, all-day vs midnight-to-midnight). Plan phase verifies whether `gog` handles these implicitly; if not, they fall back to clarification.
- Attendee invitations. Attendee field is extracted but invitation-sending is a Google Calendar default behavior; this mission does not add custom invitation handling.

## Cross-references

- **kentonium3/kg-automation#558** — source feature issue (spec-ready). This mission addresses #558 in full.
- **kentonium3/kg-automation#324** — original calendar-routing issue. Closed by this mission's merge.
- **kentonium3/kg-automation#556** — broader inbox classification rework (parent). This mission carves out the capture-side calendar + aspiration slice; remainder of #556 remains open for follow-on work.
- **kentonium3/kg-automation#271** — Felix-as-mirror epic. Explicitly NOT addressed in this mission's scope.
- **Felix Constitution** — `docs/constitution/FELIX-CONSTITUTION.md` (Directive 6: scripts-vs-LLM split; Directive 5: documentation standards; Directive 8: operational symptom required for issues).
- **Capture agent standing orders** — `scripts/openclaw/agents/felix-admin-capture/AGENTS.md` (Step 3 routing table at lines ~199–222; goal-handling pattern at lines ~376–438).
- **Inbox helper conventions** — `scripts/inbox/` (`prescan.py`, `append_routing_entry.py`, `handle_parse_failures.py`).
- **Architecture signal-to-doc map** — `docs/design/architecture/data/signal-to-doc-map.json`.
