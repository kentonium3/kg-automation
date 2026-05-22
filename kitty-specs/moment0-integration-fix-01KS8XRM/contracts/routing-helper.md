# Contract: route_drift_event() — shared Moment 0 helper

**Mission**: `moment0-integration-fix-01KS8XRM`
**Module**: `scripts/doc_audit/routing/drift_moment0.py`

The public API surface for the shared Moment 0 routing helper. Called from `signals/drift_event.py::commit()` (cron path) and `helpers/handle_drift_events.py::process_events()` (library/CLI path).

---

## Signature

```python
def route_drift_event(
    *,
    event: dict[str, Any],
    mapping: Mapping,
    config: Config,
    client: JudgmentClient,
    ledger_path: Path,
    repo: str,
    event_id: str,
    timestamp_utc: str,
    cursor_line: int,
    repo_root: Path,
) -> RoutingOutcome:
    """Moment 0 LLM judgment + verdict routing + ledger append.

    Args (all keyword-only):
        event: parsed dict from drift-events.jsonl
        mapping: matching Mapping from signal-to-doc-map.json (must NOT be None)
        config: full Config (for drift_interpretation block + repo settings)
        client: JudgmentClient (caller manages lifecycle; one per tick)
        ledger_path: path to drift-events-ledger.jsonl
        repo: GitHub repo slug for any issue/PR filings ("kentonium3/kg-automation")
        event_id: composite "cursor_line:timestamp_utc"
        timestamp_utc: ISO 8601 Z-suffixed string from the drift event
        cursor_line: line number in drift-events.jsonl (for event_id construction)
        repo_root: local repo checkout path (for loading doc_targets)

    Returns:
        RoutingOutcome with populated fields per data-model.md

    Raises:
        DriftInterpretationError: after retry exhaustion (caller writes
            RETRY_EXHAUSTED ledger row + falls back to file_doc_audit_issue)
        OSError: if ledger append fails after side effects landed (caller logs;
            does NOT fail the tick — the GitHub side effect already happened)
    """
```

## Pre-conditions

- `mapping is not None` — caller checks for the no-mapping case BEFORE calling
- `config.drift_interpretation.enabled is True` — caller checks the flag BEFORE calling (otherwise the caller uses the pre-#362 path directly, skipping this helper entirely)
- `client` is a fully-constructed `JudgmentClient` instance with API key loaded
- `event` has `timestamp_utc` and a decodable diff payload

## Post-conditions

- A ledger row has been appended (regardless of verdict)
- For PROPOSED_EDIT @ conf ≥0.80: side effect completed (commit / PR / debt-issue) per tier_classification verdict
- For JUDGMENT_REQUIRED: a `[doc-audit]` issue has been filed with the LLM's question in the body
- For NO_CHANGE_NEEDED: no GitHub side effect; ledger row only
- For confidence-demoted PROPOSED_EDIT (<0.80) or NO_CHANGE_NEEDED (<0.80): treated as JUDGMENT_REQUIRED (issue filed with original verdict folded into rationale)

## Side-effect ordering (critical for crash recovery)

1. LLM call (retries internally per #362's D6)
2. Tier routing side effects (commit / PR / issue) — these are visible to GitHub
3. Ledger append (last)

This ordering means: if the tick crashes after step 2, the ledger row is missing but the GitHub side effect is present. The cursor advance happens AFTER `route_drift_event` returns, so re-running the tick re-emits the same event_id but the side effect (idempotent GitHub close, e.g.) is safe.

## RoutingOutcome shape

Per [data-model.md](../data-model.md) — promoted from WP04-local.

## Failure modes

| Error class | When raised | Caller handling |
|---|---|---|
| `DriftInterpretationError("retry exhausted", ...)` | After 3 retries failed | Write `RETRY_EXHAUSTED` ledger row; file pre-#362 fallback issue |
| `DriftInterpretationError("out-of-set proposed doc_path")` | Semantic violation (no retry) | Same fallback path as retry exhausted |
| `OSError` from ledger append | Filesystem error after side effects | Log error; DO NOT fail tick |
| Re-raises from `file_doc_audit_issue` / tier_classification | Side-effect failed | Propagates; caller decides cursor advance behavior |

## Test fixtures

Inherits #362's fixtures (`drift_event_openclaw_cron.json`, `drift_event_openclaw_json_hash.json`, `drift_event_systemd_dropins.json`). Tests at `tests/doc_audit/routing/test_drift_moment0.py`.
