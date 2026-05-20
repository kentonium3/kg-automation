# Contract — AGENTS.md required content per section

**Mission**: `habits-cutover-to-jsonl-v2-flow-01KS1FKE`

This document specifies the required content for each modified section of `scripts/openclaw/agents/felix-admin-habits/AGENTS.md`. The implementer reads this to know exactly what the new AGENTS.md must contain.

Format: each subsection below names a current AGENTS.md section, summarizes the BEFORE state, and specifies the required AFTER content.

---

## Section: `## Morning check-in` (current line 68)

### BEFORE

Lines 68-186 contain the v1 workflow: Steps 1-6 (with Step 4.5 for helper failure handling). Helper invocations point to `query_active_habits.py`, `set_due_dates.py`, `exclude_completed.py`.

### AFTER — Required content

The opening paragraph (line ~70) remains. Replace the step-list block with the v2 shape:

```
Steps 0-4 are deterministic and delegated to helper scripts in
`/home/claude/kg-automation/scripts/habits/`. Steps 5-6 are
LLM-mediated message composition + output.

### Step 0: Reconcile any Vikunja UI completions (helper, NEW)

Before any habit enumeration, invoke:

    python3 -m scripts.habits.reconcile_completions

This helper:
  - Detects any habit tasks Kent ticked done in the Vikunja UI since the
    last check-in tick.
  - Appends backfill records to the JSONL state log with
    source="vikunja-ui" so subsequent steps see them as "already complete
    today".
  - Reports any drift (JSONL says complete but Vikunja shows done=false)
    via stdout warnings. The agent surfaces drift warnings in the action
    log but does NOT block check-in delivery on drift.

Exit code 0 = success (with or without drift); 1 = enumerate failure
(treat per Step 4.5 helper failure handling).

### Step 1: Compute today's context (helper)

[unchanged content — preserves the existing compute_today.py invocation
and date/timezone derivation]

### Step 2: Query habits scheduled for today (helper, CHANGED)

Invoke:

    python3 -m scripts.habits.query_active_habits_v2

The v2 helper uses Vikunja's native filter (`due_date <= now/d AND
done = false`) and is project-scoped to the Habits project. It returns
all habit tasks active for today (those with due_date <= today and
not yet marked done).

[Output format expectations remain the same — JSONL on stdout.]

### Step 4: Exclude habits already addressed today (helper, CHANGED)

Pipe the Step 2 output through:

    python3 -m scripts.habits.exclude_completed_v2

The v2 helper consults the JSONL state log directly (no LLM-mediated
parsing of Vikunja comments). It removes any habit task whose
(task_id, today's date, state="complete") triple already exists in
the log. This includes:
  - Completions Kent already confirmed via WhatsApp earlier today.
  - Backfills from Vikunja UI completions (added by Step 0's reconcile).
  - Manual operator-driven entries (source="manual").

[Output format expectations remain the same.]

### Step 4.5: Helper failure handling

[unchanged content]

### Step 5: Format the check-in message

[unchanged content]

### Step 6: Output — check-in text only

[unchanged content]
```

**NOTE about Step 3**: there is no Step 3 in the new flow. The previous Step 3 (set_due_dates.py) is removed because Vikunja's native `repeat_after` (set in Phase 3 mission #40) now handles due_date roll automatically when a task is marked done=true. Keep the gap-numbered (0, 1, 2, 4, 4.5, 5, 6) to preserve any external doc references.

---

## Section: `## Completion marking` (current line 187)

### BEFORE

The section instructs the agent to:
1. Recognize natural language completion signals
2. Handle ambiguity
3. **Make inline POST /tasks/<id> with done=true AND PUT /tasks/<id>/comments**
4. Confirm to Kent

### AFTER — Required content

Subsections 1, 2, and 4 (Recognize / Handle ambiguity / Confirm to Kent) remain unchanged. Subsection 3 ("Record completion in Vikunja") changes:

```
### Record completion in Vikunja (CHANGED)

For each habit Kent confirmed complete in his WhatsApp reply, invoke
the record_completion helper exactly once:

    python3 -m scripts.habits.record_completion \
        --task-id <vikunja-task-id> \
        --title "<task title>" \
        --date $(date -u +%Y-%m-%d) \
        --state complete \
        --source whatsapp

The helper performs the three-write atomic operation per ADR-0002 Q3-D:
  1. POST /api/v1/tasks/<id> with done=true (Vikunja auto-advance)
  2. PUT /api/v1/tasks/<id>/comments with body
     `[Felix] <date> | complete` (UI-visible mirror)
  3. Append to /data/services/openclaw/state/habits-history.jsonl
     (canonical history)

Exit codes:
  0 = success or idempotent no-op
  1 = Vikunja write failure (record exists in JSONL only if step 4
      partially succeeded — surface in action log)
  2 = state_log write failure (Vikunja already committed — record
      this anomaly in the action log; next morning's reconcile will
      backfill from done_at)
  3 = validation/usage error (bad state, missing args)

For habits Kent explicitly declined ("not today", "skipping", etc.),
use --state incomplete or --state skipped per the natural language
mapping table below. The Phase 2 strict enum allows only
{complete, incomplete, skipped} for the habits domain.

DO NOT make inline POST or PUT calls to Vikunja for habit completion.
The helper owns those writes.
```

Add a small "State mapping table" subsection if it would aid the LLM in distinguishing the three valid states:

```
### State mapping table (Kent's natural language → helper state)

| Kent says                  | --state argument |
|----------------------------|------------------|
| "done", "complete", "✓"    | complete         |
| "no", "didn't", "skip it"  | incomplete       |
| "skipping", "won't do",    | skipped          |
| "intentional skip" cues    |                  |

Ambiguous cases: ask Kent to clarify per Step 2 (Handle ambiguity).
```

---

## Section: `## Comment format specification` (current line 256)

### BEFORE

Documents the `[Felix] YYYY-MM-DD | state | note` shape and the parser regex used by the agent.

### AFTER — Required content

Keep the format documentation. Add a short pointer note at the top of the section:

```
> NOTE: As of Phase 5 cutover (#308), the JSONL state log
> (/data/services/openclaw/state/habits-history.jsonl) is the canonical
> history source. The [Felix] comments documented in this section are
> the Vikunja UI mirror, written automatically by record_completion.py
> (Phase 3). The agent no longer parses these comments for decision-making;
> they exist for human readability in the Vikunja UI.
```

The format spec itself (the regex, the date/state/note structure) remains accurate and useful — `record_completion.py` writes comments in this format, so the spec is still the contract for that comment shape.

---

## Section: `## Weekly pattern report` (current line 285)

### BEFORE

Step 2 of the weekly report queries `/api/v1/tasks/<id>/comments` per habit and parses `[Felix]` comments to extract dates/states for the report period (rolling 7 days).

### AFTER — Required content

Step 2 changes:

```
### Step 2: Query completion history (CHANGED)

Query the JSONL state log for the report period. Choose either path:

**Path A — Python module import (preferred if the weekly-report invocation
is Python-based)**:

    from scripts.common import state_log

    records = state_log.read(
        "habits",
        date_from=report_start_date,  # YYYY-MM-DD
        date_to=report_end_date,
        state="complete",
    )

**Path B — CLI (if the weekly-report invocation is shell-based)**:

    python3 -m scripts.common.state_log read \
        --domain habits \
        --date-from <YYYY-MM-DD> \
        --date-to <YYYY-MM-DD> \
        --state complete

Each returned record has fields: task_id, title, date, state, source,
note (optional), timestamp. The report groups by task_id + counts by date.

Performance: a single JSONL read replaces N per-task HTTP comment
fetches. Expected runtime < 200ms for a 7-day window even with the
full historical log present.
```

Subsections 1, 3, 4 (date range determination, rate calculation, formatting) remain unchanged in structure; the calculation logic only needs adjusting to reference the JSONL field names (`date`, `state`) instead of the comment-parser's parsed-output field names. The data shape is equivalent.

---

## Section: `## Track record query` (current line 336)

### BEFORE

Section documents how the agent answers ad-hoc questions about historical completion patterns (e.g., "did I do meditation last Wednesday?"). Uses comment-parsing.

### AFTER — Required content

Update the data-source instruction:

```
Use `state_log.read("habits", task_id=<id>, ...)` to retrieve the
historical completion record for a given task. The JSONL log is the
canonical history source. See `## Weekly pattern report` Step 2 for
the read API.
```

Replace any explicit comment-parsing instructions in this section with the state_log read pattern.

---

## Section: `## Action Logging` (current line 411)

### BEFORE

Documents that the agent writes action-log entries to `~/second-brain/agents/logs/agent-activity/<date>.jsonl` describing each action taken.

### AFTER — Required content

Lightly annotate to clarify that completion-action entries now reference the JSONL state_log entry as the canonical record:

```
For completion actions: the action-log entry MUST include the
(task_id, date, state) tuple that identifies the corresponding
record in /data/services/openclaw/state/habits-history.jsonl. This
makes the action log cross-referenceable with the state_log.

Example action-log entry (illustrative):
    {
        "timestamp": "2026-05-20T11:05:33+00:00",
        "agent": "felix-admin-habits",
        "action": "record_completion",
        "task_id": 14,
        "date": "2026-05-20",
        "state": "complete",
        "source": "whatsapp",
        "context": "Kent confirmed 'wake done' in 11:05 reply",
    }
```

The rest of the section (action types, context fields, "what changed" semantics from F014) remains unchanged.

---

## Sections NOT changed by this mission

The following sections remain byte-identical to the pre-mission file:

- `## Governance` (lines 1-12)
- `## Authority` (lines 13-18)
- `## Message identity` (lines 19-27)
- `## Output discipline` (lines 28-53)
- `## Scope` (lines 54-67)
- `## Habit management` (lines 364-410)
- `## Error handling` (lines 459-469) — verify no v1-specific language; light-touch if needed
- `## Privacy — absolute rule` (lines 470-end)

---

## Size budget

Pre-mission: 16,367 bytes.
Estimated post-mission size: 17,500-19,500 bytes (small expansion from adding Step 0 + state-mapping table + pointer notes; some shrinkage from removing inline POST/PUT instructions). Should fit within NFR-002's ~24,500-byte ceiling.

---

## Validation grep contract (used by the implementer's self-check)

After editing, the implementer MUST run these grep assertions and confirm each:

```bash
# Required present (each returns ≥1 line):
grep -F "reconcile_completions" scripts/openclaw/agents/felix-admin-habits/AGENTS.md
grep -F "query_active_habits_v2" scripts/openclaw/agents/felix-admin-habits/AGENTS.md
grep -F "exclude_completed_v2" scripts/openclaw/agents/felix-admin-habits/AGENTS.md
grep -F "record_completion" scripts/openclaw/agents/felix-admin-habits/AGENTS.md
grep -F "habits-history.jsonl" scripts/openclaw/agents/felix-admin-habits/AGENTS.md

# Required ABSENT from the active workflow sections (Morning check-in,
# Completion marking, Weekly pattern report, Track record query):
# The implementer manually inspects these sections to ensure no v1 helper
# names appear AS WORKFLOW INSTRUCTIONS. Historical-context references
# (e.g., "in the prior comment-parsing flow") with explicit framing are
# acceptable.

# Optional — informational checks:
grep -F "set_due_dates" scripts/openclaw/agents/felix-admin-habits/AGENTS.md  # should not appear in workflow (D1)
```
