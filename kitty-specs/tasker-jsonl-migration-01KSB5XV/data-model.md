# Data Model: Tasker enrichment JSONL state migration

**Mission**: `tasker-jsonl-migration-01KSB5XV`

## E1 — EnrichmentCompletion (JSONL row)

```python
@dataclass(frozen=True)
class EnrichmentCompletion:
    """One enrichment state event for a Vikunja task. JSONL row."""

    task_id: int                 # Vikunja task ID
    state: str                   # "proposed" | "confirmed" | "skipped" | "declined"
    timestamp_utc: str           # ISO 8601 Z-suffixed
    source: str                  # "agent" | "reconcile" | "backfill" | "operator_repair"
    schema_version: int = 1
    note: Optional[str] = None
```

**Field order is canonical** (matches mirrored escalation schema). Used for deterministic JSONL serialization via `json.dumps(d, sort_keys=False)`.

## Constants

```python
VALID_STATES = frozenset({"proposed", "confirmed", "skipped", "declined"})
VALID_SOURCES = frozenset({"agent", "reconcile", "backfill", "operator_repair"})
SCHEMA_VERSION = 1
DEFAULT_LEDGER_PATH = Path("/data/services/openclaw/state/enrichment/enrichment-history.jsonl")
```

## State transitions

```
(empty) → proposed → confirmed | skipped | declined   [terminal states]
```

Single-offer policy: once a task reaches `skipped` or `declined`, it is never re-proposed automatically. `confirmed` means the task got structured + the enrichment cycle completed.

## Disambiguation rule (reconcile)

Vikunja comments parsed in reconcile match:
- `[Felix] enrichment | <state> | <ISO timestamp> | <optional notes>` ← parsed
- `[Felix] YYYY-MM-DD | <state>` ← NOT parsed (habit comment shape, owned by #371)

Second-field shape distinguishes: literal string `enrichment` vs date pattern `^\d{4}-\d{2}-\d{2}$`.
