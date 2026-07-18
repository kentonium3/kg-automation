# Quickstart: All-Day Fallback for Unanswered Clarifications

How to exercise items 2+3 end-to-end (deterministic path; no live WhatsApp needed).

## Preconditions

- Branch `feat/clarification-allday-fallback`, on `main` @ b84bc081 base.
- `make test` green before starting.

## Unit-level (deterministic, no calendar API)

1. **validate emits resolved date + missing_fields** — feed
   `validate_calendar_event.validate` a block for "Meet Rob Thursday" (resolved
   date, no time) at a fixed tick; assert the incomplete result carries
   `missing_fields` including the start-time signal **and** a resolved
   `start_date` (YYYY-MM-DD) matching the tick-anchored Thursday.

2. **record persists the signal** — `handle_clarification_state add` with a
   `--partial-payload` containing `missing_fields` + `start_date`; assert the
   stored record round-trips both.

3. **all-day seam** — feed `route_calendar_event` an all-day payload
   (`start_date`/`end_date`, no `start`); assert `validate_payload` accepts it and
   `build_delegation_payload` emits a `--payload-file` with `start_date`/`end_date`
   (not `start_rfc3339`), and that the **timed** path still works unchanged.

## Integration-level (transaction + fake calendar)

4. **eligible age-out → all-day create** — seed one aged-out eligible record
   (created_at 25h ago, `missing_fields=["start_time"]`, `start_date` set) + its
   inbox note; run the sweep-finalize path with a fake `calendar_helper`/service;
   assert: one all-day event created (`start_date`, `end_date = +1 day`), note
   marked processed, routing-log has the **distinct age-out-create** event, record
   removed.

5. **idempotency across retry** — same record, but the record-removal (or verify)
   fails on the first pass; run the sweep twice against a shared fake store; assert
   **exactly one** event (idempotency-key dedup), note processed once, no orphan.

6. **boundary — non-start-time NOT converted** — aged-out records with
   `missing_fields=["title"]`, with a compound `["start_time","end_or_duration"]`,
   and a legacy record with **no** `missing_fields`/`start_date`; assert **zero**
   all-day events and each follows delete-and-release.

7. **fail-closed** — eligible record but `calendar_helper create` errors; assert
   the record is **retained**, the note is **unprocessed**, no partial event.

8. **week-drift guard** — a record whose `start_natural` ("Thursday") would parse
   to a *different* week at sweep time than at capture; assert the created event's
   date equals the **persisted** `start_date`, not a re-parsed value.

## Gate

- `make test` green (full suite).
- Adversarial review (Codex primary; reviewer-renata fallback) on the diff.

## Live-verify (office2, post-merge)

- Deploy via `agent-prompt-sync` (AGENTS.md) + office2 self-pull (Python).
- Dry-run the finalize subcommand on office2 against a seeded aged-out eligible
  record with a `--dry-run`/fake account (no real event); confirm the deterministic
  path selects it and builds the correct all-day plan. Confirm `Rebaseline: not
  required` holds (no hashed audited surface changed).
