# Research Methodology: F017 Vikunja Habit Tracking Architecture

**Date**: 2026-04-06
**Spec**: [spec.md](spec.md)
**Plan**: [plan.md](plan.md)

---

## Pre-research findings (from diagnostic session)

Before this research mission was created, a diagnostic session was
conducted in the same conversation. These findings are confirmed and
should be incorporated into the WP rather than re-gathered:

### RQ-2 partial answers (verified 2026-04-06)

- **Cron jobs**: `habits-morning-checkin` (UUID: 3082343c-...) exists,
  enabled, status `ok`. Runs daily at 11:05 UTC (7:05 AM ET). Last 7
  runs all successful with WhatsApp delivery confirmed.
- **Task state**: Habit tasks 14, 17, 20 inspected via API. All show
  `due_date: "0001-01-01T00:00:00Z"` (null sentinel), `repeat_after: 0`,
  `repeat_mode: 0`. No due_date or recurrence configured on any habit.
- **Agent behavior**: AGENTS.md confirms query-only model — agent reads
  existing tasks, checks for completion comments, delivers WhatsApp
  check-in. Agent never sets due_date or creates new tasks.
- **Completion tracking**: Comment-based model operational. Format:
  `[Felix] YYYY-MM-DD | {complete|rescheduled|will-not-do} | note`

### What remains for RQ-2

- Confirm all 7 tasks (14-20) match the pattern (only 3 sampled so far)
- Check whether any completion comments actually exist (comment endpoint
  not yet queried)
- Cross-reference against the F009 spec to document gaps between intent
  and deployment

## Decisions from planning

| Decision | Rationale | Alternatives rejected |
|----------|-----------|----------------------|
| Single WP for all four RQs | Questions build naturally on each other; incremental review adds overhead without proportional value for a focused investigation | Separate WPs per RQ or per dependency tier |
| Open-ended evaluation of Option C's external log | No reason to constrain the hybrid approach before research reveals what's needed | Pre-selecting a specific log technology |
| Incorporate pre-research findings | Diagnostic data was gathered with the same API access and is recent (same day); re-gathering wastes time | Starting from scratch |

## Methodology per research question

### RQ-1: Vikunja recurring task behavior

1. Check Vikunja version on office2 from `service-inventory.json`
2. Read Vikunja API docs — task schema fields: `repeat_mode`,
   `repeat_after`, `repeat_from_current_date`
3. Read Vikunja help docs on dates and reminders
4. Search Vikunja community forum for recurring task completion behavior
5. Optionally: create a throwaway test task with recurrence on a
   non-production Vikunja instance to verify behavior firsthand
   (NOTE: C-001 prohibits this on the live instance — only if an
   external test instance is available, e.g., try.vikunja.io)
6. Document: what happens to due_date, done status, and comments when
   a recurring task is marked done

### RQ-2: Current F009 deployment state

1. Start from pre-research findings above
2. Query remaining tasks (15, 16, 18, 19) to confirm pattern
3. Query comment endpoints for a sample of tasks to verify completion
   records exist
4. Read F009 spec to identify intended vs. actual behavior gaps
5. Document factually: what was built, what works, what's missing

### RQ-3: Candidate approach comparison

1. Requires RQ-1 findings (to evaluate Option A accurately)
2. For each of the three options, assess against all five evaluation
   criteria using evidence from RQ-1, RQ-2, and external sources
3. For Option C, evaluate candidate external log technologies:
   - Existing comment model (already in use)
   - JSONL file on office2
   - Second Vikunja project as a log
   - SQLite database
   - Any other lightweight option that emerges from research
4. Produce comparison table with evidence citations
5. State recommendation with rationale

### RQ-4: API capability confirmation

1. Requires RQ-3 recommendation
2. For the recommended approach, confirm each required API call exists:
   - Task creation/update endpoints and fields
   - Filtering by due_date (for Today view confirmation)
   - Comment creation/query endpoints
   - Any other endpoints the approach requires
3. Document endpoint, method, key fields, and expected behavior
4. Flag any capabilities that cannot be confirmed as gaps

---

**END OF RESEARCH METHODOLOGY**
