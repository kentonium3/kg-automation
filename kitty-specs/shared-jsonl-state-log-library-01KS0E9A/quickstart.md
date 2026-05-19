# Quickstart — using the state log library

**Mission**: `shared-jsonl-state-log-library-01KS0E9A`
**Audience**: implementers of ADR-0002 Phases 3-7 (habits, escalation, tasker migrations)

Once Phase 2 lands, this is how a downstream consumer phase uses the library.

---

## From Python (preferred for in-process callers)

### Append a habit completion

```python
from scripts.common import state_log
from datetime import datetime, timezone

state_log.append("habits", {
    "domain": "habits",
    "task_id": 14,
    "title": "Wake at 5:00 AM",
    "date": "2026-05-19",
    "state": "complete",
    "source": "whatsapp",
    "note": None,
    "timestamp": datetime.now(timezone.utc).isoformat(),
})
```

### Backfill from Vikunja UI completion

```python
from scripts.common import state_log

state_log.append("habits", {
    "domain": "habits",
    "task_id": 14,
    "title": "Wake at 5:00 AM",
    "date": "2026-05-18",                  # the day the UI tick was FOR
    "state": "complete",
    "source": "vikunja-ui",
    "note": None,
    "timestamp": "2026-05-19T11:00:03+00:00",  # when reconciler caught it
})
```

### Read all habits records for a task

```python
from scripts.common import state_log

records = state_log.read("habits", task_id=14)
for r in records:
    print(r["date"], r["state"], r["source"])
```

### Read with a date range

```python
records = state_log.read("habits",
    task_id=14,
    date_from="2026-05-01",
    date_to="2026-05-31",
)
```

### Validate before appending

```python
from scripts.common import state_log

record = {...}  # build it
state_log.validate_record(record, domain="habits")  # raises ValueError on issue
state_log.append("habits", record)
```

### Discover valid states for a domain

```python
from scripts.common.state_log import DOMAIN_STATES

print(sorted(DOMAIN_STATES["habits"]))
# ['complete', 'incomplete', 'skipped']
```

---

## From shell / LLM agent via Bash exec

### Append

```bash
RECORD='{"domain":"habits","task_id":14,"title":"Wake at 5:00 AM","date":"2026-05-19","state":"complete","source":"whatsapp","note":null,"timestamp":"2026-05-19T11:05:11+00:00"}'

echo "$RECORD" | python3 -m scripts.common.state_log append --domain habits
```

Exit code 0 = appended or idempotent no-op. Non-zero = inspect stderr.

### Read

```bash
python3 -m scripts.common.state_log read --domain habits --task-id 14
# one JSON object per matching line on stdout
```

### Filtered read

```bash
python3 -m scripts.common.state_log read --domain escalation \
  --date-from 2026-05-01 \
  --date-to 2026-05-31 \
  --state level-2
```

---

## Typical consumer integration shape (Phase 3 habits example)

A Phase 3 cron tick will look something like:

```python
# scripts/habits/record_completion.py (built in Phase 3, NOT this phase)

from scripts.common import state_log
from datetime import datetime, timezone

def record_completion(task_id: int, title: str, completion_date: str, state: str, source: str):
    """Three-write completion helper per ADR-0002 Q3.

    1. POST /tasks/{id} with done=true (Vikunja auto-advance)
    2. PUT /tasks/{id}/comments with [Felix] mirror
    3. Append to /data/services/openclaw/state/habits-history.jsonl

    Idempotent on (task_id, completion_date, state); safe to retry.
    """
    # ... (writes 1 + 2 elided — Phase 3 work) ...

    state_log.append("habits", {
        "domain": "habits",
        "task_id": task_id,
        "title": title,
        "date": completion_date,
        "state": state,
        "source": source,
        "note": None,
        "timestamp": datetime.now(timezone.utc).isoformat(),
    })
```

Phase 3 will own the cron + WhatsApp integration; this library only provides the third write.

---

## What goes wrong and how to detect it

| Symptom | Probable cause | Fix |
|---|---|---|
| `ValueError: state 'Complet' not in habits enum {complete, incomplete, skipped}` at `append` | Typo at the call site | Fix the caller; library is doing its job |
| `ValueError: missing required field 'timestamp'` | Caller forgot to populate a field | Add the field |
| `OSError: [Errno 13] Permission denied` opening `habits-history.jsonl` | File owner / mode drift (similar to the inbox 0644 bug — #323) | Check perms; should be claude:secondbrain 0664 |
| Append succeeds but no new line in file (file size unchanged) | Idempotent no-op — record already exists. Verify by reading; this is expected behavior. | Not a bug |
| Two processes appending interleave (impossible if library is used correctly) | Bug in lock acquisition | File an issue; this is the failure NFR-003 is designed to prevent |

---

## What this library DOES NOT do

- Network I/O (no Vikunja calls — that's the consumer's job)
- Cross-host coordination (single host only)
- Rotation / archival (deferred)
- Async I/O (synchronous only)
- State transitions (each record is a discrete event; consumers compute current state by reading history)

---

## Where to find more

- [spec.md](spec.md) — the formal contract
- [data-model.md](data-model.md) — record schema + per-domain enums
- [contracts/api.md](contracts/api.md) — Python function signatures + exceptions
- [contracts/cli.md](contracts/cli.md) — CLI surface
- [contracts/jsonl.md](contracts/jsonl.md) — on-disk format
- ADR-0002 Q5-C — the design decision this library implements
