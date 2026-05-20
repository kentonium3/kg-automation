# Data Model

**Mission**: `habits-cutover-to-jsonl-v2-flow-01KS1FKE`
**Phase**: 1 (design)

Phase 5 has no programmatic data model — it's a Markdown content change. This document maps the AGENTS.md sections that change (BEFORE/AFTER) and the new operational shape of the morning check-in workflow.

---

## Entity 1 — AGENTS.md section map

The file at `scripts/openclaw/agents/felix-admin-habits/AGENTS.md` has the following top-level structure (line numbers reference the pre-mission file at 16,367 bytes):

| Section | Current line | Change in Phase 5 |
|---|---|---|
| `## Governance` | 1 | No change |
| `## Authority` | 13 | No change |
| `## Message identity` | 19 | No change |
| `## Output discipline` | 28 | No change |
| `## Scope` | 54 | No change |
| `## Morning check-in` | 68 | **Restructured** — add Step 0; rename helper invocations; drop Step 3 |
| `## Completion marking` | 187 | **Restructured** — replace inline POST/PUT instructions with `record_completion.py` invocation |
| `## Comment format specification` | 256 | **Keep + annotate** — add a short note clarifying JSONL is canonical; comment is UI mirror written by record_completion.py |
| `## Weekly pattern report` | 285 | **Restructured** — switch data source from comments to JSONL state_log |
| `## Track record query` | 336 | **Updated** — point to JSONL state_log as the data source |
| `## Habit management` | 364 | No change (this section is about adding/pausing/removing habits, not completion semantics) |
| `## Action Logging` | 411 | **Lightly annotated** — update language to reference JSONL entries as canonical action records |
| `## Error handling` | 459 | **May need light updates** — error patterns from helpers now bubble up via exit codes; the section's existing language about "API error returned from Vikunja" still applies |
| `## Privacy — absolute rule` | 470 | No change |

---

## Entity 2 — New morning check-in workflow (the v2 shape)

The "Morning check-in" section gets restructured. Before (v1) vs after (v2):

### Before (v1, current state)

```
Step 1: Compute today's context (helper)        → scripts/habits/compute_today.py
Step 2: Query habits scheduled for today        → scripts/habits/query_active_habits.py
Step 3: Set due_date end-of-day-ET              → scripts/habits/set_due_dates.py
Step 4: Exclude habits already addressed today  → scripts/habits/exclude_completed.py
Step 4.5: Helper failure handling
Step 5: Format the check-in message
Step 6: Output — check-in text only
```

### After (v2, post-cutover)

```
Step 0: Reconcile any Vikunja UI completions   → scripts/habits/reconcile_completions.py  (NEW)
Step 1: Compute today's context (helper)        → scripts/habits/compute_today.py        (unchanged)
Step 2: Query habits scheduled for today        → scripts/habits/query_active_habits_v2.py  (CHANGED)
Step 3: (REMOVED — Vikunja native repeat handles due_date)
Step 4: Exclude habits already addressed today  → scripts/habits/exclude_completed_v2.py    (CHANGED)
Step 4.5: Helper failure handling                                                         (unchanged)
Step 5: Format the check-in message                                                       (unchanged)
Step 6: Output — check-in text only                                                       (unchanged)
```

**Step number renumbering**: keep the existing numbering (0, 1, 2, 4, 4.5, 5, 6) with a gap at 3 — preserves the implementer's mental model and avoids breaking any external doc references. Alternative: renumber to 0/1/2/3/3.5/4/5; either is acceptable but the gap-preserving option is slightly safer.

---

## Entity 3 — New "Completion marking" workflow

### Before (v1)

The section instructs the agent to:
1. Recognize natural language completion signals from Kent's WhatsApp reply
2. Handle ambiguity (ask Kent to clarify if needed)
3. For each confirmed completion: agent makes inline POST `/tasks/<id>` with done=true AND PUT `/tasks/<id>/comments` with the `[Felix]` comment
4. Confirm to Kent

### After (v2)

Same Steps 1, 2, and 4. **Step 3 changes** to a single helper invocation:

```
For each confirmed completion:
  python3 -m scripts.habits.record_completion \
      --task-id <id> \
      --title "<task title>" \
      --date <YYYY-MM-DD today's UTC date> \
      --state complete \
      --source whatsapp
```

The helper handles the three-write atomic operation (Vikunja done=true + comment + JSONL append) per Phase 3 contract. The agent no longer makes any inline HTTP calls for completion.

For `incomplete` or `skipped` states (when Kent declines or marks something as intentional-skip), the agent invokes the same helper with the appropriate `--state` value. The Phase 2 enum (`complete`, `incomplete`, `skipped`) is locked.

---

## Entity 4 — New "Weekly pattern report" data source

### Before (v1)

Step 2 of the weekly report queries `/api/v1/tasks/<id>/comments` for each habit and parses `[Felix]` comments to extract completion dates.

### After (v2)

Step 2 queries the JSONL state log directly. Two implementation paths (implementer picks):

**Path A — Python module import**:
```python
from scripts.common import state_log
records = state_log.read("habits", date_from=date_from, date_to=date_to, state="complete")
```

**Path B — CLI invocation**:
```bash
python3 -m scripts.common.state_log read --domain habits --date-from <from> --date-to <to> --state complete
```

The implementer picks whichever fits the existing weekly-report code style better. The JSONL query is significantly faster than the per-task comment fetch (single file read vs N HTTP calls).

---

## Entity 5 — Deploy + sha256 verification

Operator runs (per `docs/runbooks/habits-ops.md`):

```bash
for f in SOUL.md USER.md IDENTITY.md TOOLS.md AGENTS.md; do
  ssh office2-claude "cat > /data/services/openclaw/habits-agent/$f" \
    < scripts/openclaw/agents/felix-admin-habits/$f
done
```

Post-deploy verification:

```bash
LOCAL_HASH=$(shasum -a 256 scripts/openclaw/agents/felix-admin-habits/AGENTS.md | awk '{print $1}')
REMOTE_HASH=$(ssh office2-claude 'sha256sum /data/services/openclaw/habits-agent/AGENTS.md' | awk '{print $1}')
[ "$LOCAL_HASH" = "$REMOTE_HASH" ] && echo "Deploy verified" || echo "MISMATCH — deploy failed"
```

This is the SC-001 verification.

---

## Entity 6 — Action log schema (unchanged)

The agent's action log writes (the JSONL files under `~/second-brain/agents/logs/` per `agent-activity` dir) keep their existing schema. Phase 5 only changes the *content* of completion-action log entries:

**Before**: action log entry references the inline POST/PUT calls.
**After**: action log entry references the `record_completion.py` invocation as the atomic unit; mentions the JSONL state_log entry by `(task_id, date, state)` tuple.

No schema fields added or removed.
