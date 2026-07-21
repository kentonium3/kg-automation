# TOOLS.md

## calendar request orchestrator (your single calendar tool)

`scripts.calendar_routing.handle_calendar_request` is the ONE deterministic command you run for EVERY calendar request — a conversational request or a clarification reply. You have **no `gog`**, and you do **not** call the calendar helper, the validator, the clarification-state helper, or `log_action` directly — the orchestrator invokes all of them for you. This is what makes scheduling reliable: all date/time math and state changes are deterministic, never hand-built by you.

- Invocation (pipe the ExtractedCalendarBlock JSON on stdin). The orchestrator is stdlib-only and resolves the deploy venv internally for the helper subprocess, so run it under system `python3` anchored to the checkout:

  ```bash
  cd /home/claude/kg-automation && echo '<ExtractedCalendarBlock JSON>' | python3 -m scripts.calendar_routing.handle_calendar_request --account <account>
  ```

- Default `--account` is `personal`. The block fields you assemble are listed in **AGENTS.md → Calendar request handling, Step 1**.
- It returns ONE JSON object on stdout with a `status`; branch on it (AGENTS.md → Step 3):
  - `{"status":"created","mode":"conversational"|"clarification","event_id":…,"html_link":…,"summary":…,"start":…}` — created at the correct ET date/time. A clarification result also carries `"cleanup_ok": <bool>` (and a `cleanup` block): the orchestrator best-effort removes the pending record, flips the source note, and logs — so `cleanup_ok: false` means the event exists but the reminder wasn't cleared (surface that to Kent).
  - `{"status":"needs_clarification","mode":…,"missing":[…]}` — a required field is missing; ask Kent for exactly those.
  - `{"status":"ambiguous","candidates":[{"title","note_filename","created_at"},…]}` — the reply could resolve more than one open clarification; ask Kent which.
  - `{"status":"error","exit_code":<n>,"error":"<verbatim>"}` — the calendar helper failed and the calendar was NOT mutated; surface `error` VERBATIM (never fake a create, #683; no `gog` fallback).

- What it owns internally (so you never do): matching a reply to a live pending clarification (`/data/services/openclaw/state/pending-calendar-clarifications.json`), merging the reply onto the record, deterministic date/time parsing + timezone (America/New_York) → RFC3339, all-day handling, the `calendar_helper create` call with an idempotency key, removing the resolved record, flipping the source note (`mark_processed`), and `log_action` (`calendar_event_created` / `calendar_event_failed` / `calendar_event_clarification_resolved`).
