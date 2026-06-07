# Quickstart: Operator smoke test for inbox calendar and aspiration routing

**Mission**: `inbox-calendar-and-aspiration-routing-01KTHHXS`
**Spec**: [spec.md](./spec.md) | **Plan**: [plan.md](./plan.md)

This document is the post-deploy smoke test. Run it after the mission merges to main AND is deployed to office2 (existing post-merge sync). It exercises the calendar-create end-to-end, the aspiration→journal path, the Someday-task path, and the clarification reply loop.

Estimated runtime: ~10 minutes including waiting on cron ticks.

## Preconditions

- Mission merged to main on the kg-automation repo.
- Office2 has pulled the latest main (post-merge sync ran successfully).
- Capture cron is scheduled (7am/noon/5pm/10pm tick).
- Vikunja and Google Calendar are healthy (no current outage).

## Test 1 — Complete calendar event, one-off

**Setup**: drop a typed note in Kent's local Obsidian vault:

`~/second-brain/notes/01-Inbox/Inbox 2026-MM-DD HHmm.md` with frontmatter and a single calendar block:

```markdown
---
domain: capture
type: capture
updated: 2026-MM-DD
status: unprocessed
tags: []
source: "smoke test"
---

Coffee with David tomorrow at 2pm for 1 hour at Bourbon Coffee Lounge in Acton MA.
```

**Trigger**: wait for the next capture cron tick (or manually run from office2: `ssh office2-claude 'systemctl --user start felix-admin-capture-tick.service'`).

**Verify**:
- Google Calendar shows a new event tomorrow 2-3pm, summary "Coffee with David", location "Bourbon Coffee Lounge".
- Capture's WhatsApp turn-summary confirms the created event with the gcal link.
- `log_action` stream contains a `calendar_event_created` event with the gcal_event_id.
- `~/second-brain/agents/state/inbox-routing.jsonl` has a new line for this note with `task_id=-` (no Vikunja todo).
- Vikunja has NO new task for "Coffee with David".

**Tear down**: delete the test event from Google Calendar; archive or delete the test inbox note.

## Test 2 — Complete calendar event with weekly recurrence

**Setup**: drop a note with a recurring event (the trivia-night case from #324):

```markdown
---
... frontmatter as above ...
---

Trivia night Tuesdays 6pm at Tru West Brewery, 525 Massachusetts Ave, Acton, MA 01720. Every week.
```

**Trigger**: wait for cron tick.

**Verify**:
- Google Calendar shows a recurring event series: Tuesdays 6pm, location Tru West Brewery.
- The event series has the correct RRULE (FREQ=WEEKLY;BYDAY=TU).
- No Vikunja todo created.

## Test 3 — Aspiration → journal

**Setup**: drop a note with an aspirational block:

```markdown
---
... frontmatter ...
---

I should really get to bed earlier. Also, I wonder if I qualify for a small business loan up to $200K.
```

**Trigger**: cron tick.

**Verify**:
- `~/second-brain/notes/08-Journal/Journal YYYY-MM-DD HHmm.md` has a new dated file (or appended block) containing the cleaned content. Both aspirations land there.
- Vikunja has NO new tasks from either aspiration.
- `log_action` stream shows two `journal_entry_appended` actions (one per aspiration if the LLM split them into two blocks; or one if treated as one block — either is acceptable per the spec's classifier-fidelity-good-enough rule).

## Test 4 — Someday-shaped concrete item → Vikunja Someday

**Setup**:

```markdown
---
... frontmatter ...
---

Get rid of the old lawn tractor when I get around to it.
```

**Trigger**: cron tick.

**Verify**:
- Vikunja project `Someday` (id 4) has a new task titled approximately "Get rid of old lawn tractor".
- The new task has `due_date: null`.
- The identity label is `personal` (inferred per existing capture rules).
- `log_action` stream shows `someday_task_created` with the vikunja_task_id.
- No journal entry created from this block.

## Test 5 — Incomplete calendar event + WhatsApp reply

**Setup**:

```markdown
---
... frontmatter ...
---

Lunch with John next Tuesday.
```

(Deliberately missing start time and end/duration.)

**Trigger**: cron tick.

**Verify** (first phase):
- Capture's WhatsApp turn-summary includes a clarification prompt: `"Lunch with John next Tuesday" — need start time and end time or duration`.
- The source inbox note frontmatter is set to `status: needs-review` with no `processed_at`.
- `~/second-brain/agents/state/pending-calendar-clarifications.jsonl` has a new line with `clarification_id`, `missing_fields: ["start_datetime", "end_or_duration"]`.
- `log_action` shows `calendar_event_clarification_sent`.
- NO Vikunja todo created.
- NO journal entry created.

**Reply**: Kent sends a WhatsApp message: `"Tuesday at 1pm for an hour"`.

**Verify** (second phase):
- Felix main resolves the open clarification, creates the Google Calendar event for next Tuesday 1-2pm.
- `pending-calendar-clarifications.jsonl` no longer contains the entry (line removed).
- Source inbox note flips to `status: processed` with `processed_at: <timestamp>`.
- `log_action` shows `calendar_event_clarification_resolved` followed by `calendar_event_created`.
- WhatsApp turn-summary confirms the created event.

## Test 6 — 24h timeout (deliberate)

**Setup**: same as Test 5, but Kent does NOT reply.

**Verify** (after 24h):
- Next capture tick after 24h elapsed runs the timeout sweep.
- The pending clarification record gains `timed_out_at`.
- Source inbox note status remains `needs-review` (it was already).
- `log_action` shows `calendar_event_clarification_timeout`.
- Capture's WhatsApp turn-summary on the timeout tick mentions: `"Lunch with John" — clarification timed out, note left at status: needs-review`.

## Test 7 — Tightened task rule (regression)

**Setup**:

```markdown
---
... frontmatter ...
---

Call dentist to reschedule cleaning.
```

**Trigger**: cron tick.

**Verify**:
- Vikunja Inbox project gets a new task titled "Call dentist to reschedule cleaning".
- Task is classified as an active task (not Someday, not calendar, not aspiration).
- Identity label: personal.
- No calendar event, no journal entry.

## Test 8 — Negative case for tightened rule

**Setup**: a block that would previously have become a useless Vikunja todo:

```markdown
---
... frontmatter ...
---

Attend the marketing call Tuesday 2pm.
```

**Verify**:
- This block is classified as a calendar event (NOT a task).
- Vikunja has NO new task for "attend marketing call".
- Either: Google Calendar gets the event (Test 1 path) or, if some field is missing, a clarification prompt is sent (Test 5 path).

## Failure modes to watch

- gog auth expired (gog-credentials-keyring corrupted) → calendar create fails; needs-review surfaces this in the WhatsApp turn-summary
- Vikunja API unreachable → Someday task creation fails; needs-review status; logged in `log_action`
- Capture cron paused → no smoke test will fire; check `systemctl --user status felix-admin-capture-tick.timer` on office2
- WhatsApp inbound not routing to main → clarification replies won't resolve; check `openclaw doctor` for the channel routing warning

## Rollback

If the smoke test reveals a regression that needs immediate rollback:

```bash
git revert <merge-commit-hash>
git push origin main
# Wait for next office2 sync tick OR manually pull on office2
ssh office2-claude "cd /home/claude/kg-automation && git pull origin main"
```

No data destruction concerns: calendar events created during smoke testing can be deleted from Google Calendar UI; Vikunja test tasks can be deleted via UI; journal entries can be removed manually. The state file `pending-calendar-clarifications.jsonl` will be empty post-rollback if no real clarifications were in flight.
