---
name: task_intelligence
description: Transform raw task descriptions into fully structured Vikunja tasks. Use when an agent needs to infer attributes, place tasks in projects, link goals, set repeat intervals, or handle enrichment errors.
version: 1.0.0
---

# Task Intelligence Skill

This skill encodes the rules for transforming raw task descriptions into fully
structured Vikunja tasks. It is the knowledge base that felix-admin-tasker reads
to structure any task without additional guidance.

**Scope — what this skill covers**:
- Attribute inference from natural language
- Confidence thresholds for when to infer vs. ask
- Project placement mapping from content signals
- Identity label inference
- Goal relationship detection and linking
- Repeat interval conversion and detection
- Error handling and Vikunja unavailability procedures

**Scope — what this skill does NOT cover**:
- Vikunja CRUD operations (see `vikunja-api` skill)
- Authentication and token management (see `vikunja-api` skill)
- Inbox capture and note parsing (felix-admin-capture responsibility)
- WhatsApp or channel interaction mechanics (handled by the agent runtime)

All Vikunja API calls referenced below follow the patterns in the `vikunja-api`
skill. This skill adds the intelligence layer on top.

---

## Required Attributes

Every structured task must have all of these before creation. If any cannot be
determined with sufficient confidence, ask Kent.

| Attribute | Question | Can Infer? | Fallback |
|---|---|---|---|
| Title | What is the task? | Yes — from raw description | Clarify if ambiguous |
| Identity label | Which identity? (personal/intentional/metalcasework) | Usually yes | Ask if ambiguous |
| Project | Where does this belong? | Often yes | Ask |
| Due date | When must this be done? | Sometimes (explicit dates) | Ask |
| Priority | How important/urgent? | Sometimes (signal words) | Default to medium (2) |

## Optional Attributes

Include these only when the raw input provides clear signals. Do not ask about
them unless the signals are contradictory.

| Attribute | Question | When to Include |
|---|---|---|
| Start date | When should work begin? | Only if lead time or dependencies |
| Repeating interval | Does this recur? | Only if task sounds recurring |
| Goal relationship | Does this serve a declared goal? | Check against active goals |
| Subtask/parent | Is this part of a larger task? | If task sounds like a component |
| Blocking/blocked | Does anything depend on this? | If clear dependencies exist |

---

## Confidence Threshold Model

### Threshold

**Default confidence threshold: 90%**

- Confidence >= 90% — infer the attribute and include it in the proposal.
- Confidence < 90% — add to clarification questions and ask Kent.

**This threshold is configurable.** Changing the value here changes agent
behavior without code changes. Lower values make the agent more autonomous
(fewer questions, more inference). Higher values make it more conservative
(more questions, fewer mistakes). Start at 90% and tune after operational
feedback.

### Inference Rules by Attribute

**Title**:
- Always infer from raw text.
- Clean up voice-to-text artifacts (filler words, incomplete sentences).
- Clarify only if the raw text is genuinely ambiguous — multiple possible tasks
  in one description, or text so garbled the intent is unclear.
- Confidence is almost always high unless the input is truly unintelligible.

**Due date**:
- High confidence if explicit date/time in text: "next Friday", "April 15th",
  "by end of month", "tomorrow", "this weekend".
- Resolve relative dates against the current date at processing time.
- Low confidence if no date reference at all — must ask Kent.
- If the date reference is vague ("soon", "sometime"), confidence is low — ask.

**Priority**:
- High confidence if signal words are present:
  - Urgent/high: "urgent", "ASAP", "important", "critical", "emergency",
    "time-sensitive", "high priority"
  - Low: "low priority", "whenever", "no rush", "when you get a chance",
    "back burner"
- Default to medium (priority 2) if no signal words are present.
  This default does NOT require asking — medium is the safe default.
- Only ask if conflicting signals ("urgent but no rush").

**Identity label**:
- Follow the Identity Label Inference Rules section below.
- High confidence for clear business/consulting/metalcasework context.
- Default to personal when the context is ambiguous but clearly non-business.
- Ask only when multiple identities could plausibly apply.

### Decision Tree

For each incoming task, apply this procedure:

```
For each required attribute:
  1. Extract signals from raw text and context
  2. Apply the inference rules above
  3. If confidence >= threshold → include in proposal
  4. If confidence < threshold → add to clarification questions

After evaluating all attributes:
  If all required attributes are above threshold:
    → Send single confirmation message with full proposal
  If any required attribute is below threshold:
    → Ask clarification questions first
    → After receiving answers, send full proposal for confirmation
```

---

## Project Placement Mapping

Map task content and identity to the correct Vikunja project. **Always resolve
project by name at runtime via `GET /projects`. Never hardcode project IDs.**

| Content Signal | Identity | Target Project |
|---|---|---|
| Consulting, client work, marketing, thought leadership, revenue, sales, invoice | intentional | Intentional LLC |
| Business acquisition, CT course | personal | Business Acquisition |
| Health, fitness, PT, medical, physical therapy, doctor, dentist, exercise, diet | personal | Health & Conditioning |
| Personal growth, habits, mindset, learning, reading, journaling, meditation | personal | Personal Growth & Transformation |
| Metal casework, fabrication, ecommerce research, metalbox | metalcasework | Metal Casework |
| Day-to-day errands, household, shopping, appointments, car maintenance | personal | Everyday |
| Ambiguous / no clear signal | — | Ask Kent; default to Inbox |

### Ambiguity Handling

- If content maps to multiple projects: ask Kent which project.
- If identity label is ambiguous: ask Kent.
- If task spans multiple projects: place in primary project, add a `[Felix]`
  comment referencing the secondary project.

### Maintenance Note

New Vikunja projects added later will need mapping entries added to this table.
If a task's content clearly references a project not listed here, ask Kent for
placement and note that this table needs updating.

---

## Identity Label Inference Rules

**Always resolve label by name at runtime via `GET /labels`. Never hardcode
label IDs.** Identity labels: personal, intentional, metalcasework.

| Signal Words | Label |
|---|---|
| business, consulting, client, Intentional LLC, marketing, thought leadership, revenue, sales, invoice, SaaS, consulting engagement | intentional |
| metal casework, fabrication, ecommerce research, metalbox, casework design | metalcasework |
| Everything else (default when context is non-business or ambiguous) | personal |

### Rules

- If clear business/consulting context → intentional.
- If clear metal casework/fabrication context → metalcasework.
- If personal life, health, errands, growth, or ambiguous → personal.
- If genuinely ambiguous between two identities → ask Kent.
- The `personal` default is acceptable when the content is clearly non-business.
  Only ask when the content could plausibly be business-related.

---

## Goal Relationship Check

Before structuring any task, check whether it relates to an active goal.

### Procedure

1. Resolve the Goals project by name via `GET /projects` (never hardcode the ID).
2. Fetch all active goals:
   ```
   GET /tasks/all?filter=done%20%3D%20false%20%26%26%20project_id%20%3D%20{GOALS_PROJECT_ID}&sort_by=due_date&order_by=asc
   ```
3. For each goal, compare the task content (title, description, context signals)
   against the goal's title and description.
4. If a plausible relationship exists, include it in the proposal.

### Relation Kind Selection

- Task clearly contributes to a goal → `related` (default, low-commitment link).
- Task is an explicit, specific step toward a goal → `subtask` of the goal.
- Only propose `subtask` when the relationship is strong and specific.
- **Never** propose `blocking` or `precedes` for goal relationships.

### Goal Relationship Proposal Format

When proposing a goal link, present it as:

```
Related goal: "Goal title here"
Proposed link: related (this task supports the goal)
```

Or for subtask relationships:

```
Related goal: "Goal title here"
Proposed link: subtask (this task is a specific step toward the goal)
```

### When NOT to Propose

- If no goal has clear relevance — omit silently. Do not ask.
- If the relationship is tenuous or speculative — omit. Avoid false positives.
- Never propose more than one goal relationship per task.

### API Pattern for Creating Goal Relations

After Kent confirms the proposal (including the goal link):

```
PUT /tasks/{NEW_TASK_ID}/relations
```

```json
{
  "other_task_id": <GOAL_TASK_ID>,
  "relation_kind": "related"
}
```

Relations are directional. For `subtask`, the new task is a subtask of the goal:

```json
{
  "other_task_id": <GOAL_TASK_ID>,
  "relation_kind": "subtask"
}
```

This means the goal task is the parent. The new task (base) is the subtask of
the other task (the goal).

---

## Repeat Intervals

### Conversion Table

Translate natural language repeat requests into Vikunja's seconds-based
`repeat_after` field.

| Human Expression | repeat_after (seconds) | repeat_mode |
|---|---|---|
| "daily", "every day" | 86400 | 0 |
| "every other day", "every 2 days" | 172800 | 0 |
| "weekly", "every week" | 604800 | 0 |
| "bi-weekly", "every 2 weeks", "fortnightly" | 1209600 | 0 |
| "monthly", "every month" | 0 | 1 |
| "quarterly", "every 3 months" | 7776000 | 0 |
| "every 6 months", "twice a year" | 15552000 | 0 |
| "yearly", "annually", "every year" | 31536000 | 0 |
| "every N days" | N x 86400 | 0 |
| "N days after completion" | N x 86400 | 2 |

### repeat_mode Explanation

- **0 (Default)**: Adds `repeat_after` seconds to existing dates. If the task is
  overdue, skips forward past missed intervals to the next future occurrence.
- **1 (Month)**: Adds one calendar month. **Ignores the `repeat_after` value
  entirely.** Set `repeat_after` to 0 when using this mode.
- **2 (FromCurrentDate)**: Adds `repeat_after` seconds to the current time (not
  the old date). Use this for tasks like "N days after I finish this."

### CRITICAL API CAVEAT

> When marking a repeating task as done via the API, **always include
> `repeat_after` and `repeat_mode` in the payload**. Go's zero-value semantics
> can clear these fields to 0 if omitted, destroying the repeat configuration.

Example — marking a weekly repeating task done:

```json
POST /tasks/{TASK_ID}
{
  "done": true,
  "repeat_after": 604800,
  "repeat_mode": 0
}
```

### Repeat Detection Rules

- **High confidence** (include in proposal): explicit repeat language — "every",
  "recurring", "repeating", "weekly", "daily", "monthly", "each week".
- **Low confidence** (do not assume): implied repetition — "oil change" might be
  recurring but was not stated as such. Do not infer repeat intervals from task
  type alone.
- **When unsure**: ask Kent "Is this a repeating task?" Do not guess.

---

## Error Handling

### HTTP Error Response Actions

| Situation | Action |
|---|---|
| Vikunja 401 (auth failure) | Log error, alert Kent via channel, halt all operations. Do not retry — token may be expired or revoked. |
| Vikunja 403 (permission denied) | Log error, alert Kent, halt current task. |
| Vikunja 404 (not found) | Log warning, skip this task, continue batch. |
| Vikunja 500 (server error) | Log error, retry with backoff (30s, 60s, 120s), alert Kent after 3 failures. |
| Network error (unreachable) | Log error, alert Kent, halt batch, preserve task context for retry. |
| Ambiguous input | Ask clarification via channel — never guess. |

### Never Fail Silently (Felix Constitution Directive 4)

Every error must produce an observable output — both a log entry and a channel
notification to Kent. There are no silent failures.

If logging itself fails, the action did not happen (Felix Constitution
Directive 3 — if it is not logged, it did not happen).

**Alert message format**:

```
Alert: Task enrichment error: {error_description}. Task: "{task_title}". Action needed: {what_kent_should_do}
```

Examples:

```
Alert: Task enrichment error: 401 Unauthorized. Task: "Schedule oil change". Action needed: Check Vikunja API token — may be expired. See vikunja-ops.md for rotation procedure.
```

```
Alert: Task enrichment error: Network unreachable. Task: "Review Q2 goals". Action needed: Check office2 connectivity and Vikunja service status.
```

### Task Context Preservation

- If enrichment fails mid-flow, preserve the raw task input and any partial
  proposal. Do not discard work in progress.
- On retry, resume from the last known state rather than starting over.
- If Vikunja is down during a batch, pause the batch. When the service returns,
  resume from where the batch left off.
- Preserved context includes: raw text, inferred attributes, any clarification
  answers already received, and the enrichment state at the point of failure.
