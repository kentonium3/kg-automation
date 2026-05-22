# Data Model: Fix Moment 0 wiring

**Mission**: `moment0-integration-fix-01KS8XRM`

This mission inherits all entities from #362 (DriftVerdict, DriftInterpretationContext, AuditLedgerEntry, DriftInterpretationError, DocTarget). No new entities, no shape changes.

One entity is **promoted** from WP04-local to public:

## RoutingOutcome (promoted to shared module)

Previously a private dataclass inside `handle_drift_events.py` (WP04). Promoted to `scripts/doc_audit/routing/drift_moment0.py` as the shared helper's return type.

```python
@dataclass(frozen=True)
class RoutingOutcome:
    """Metadata returned by route_drift_event() for caller diagnostics.

    All fields are populated; None where not applicable.
    """
    outcome: str                  # "auto_committed" | "pr_filed" | "issue_filed" | "auto_closed" | "retry_exhausted"
    tier_classification_outcome: Optional[str]  # "tier_a" | "tier_b" | "judgment" | None
    github_issue_number: Optional[int]
    retry_count: int                            # 0..3
    latency_ms: int                             # end-to-end including retries
```

The same enum values from #362's E3 (AuditLedgerEntry.outcome / tier_classification_outcome) apply.

## State transitions

Unchanged from #362's flow diagram. The only change is the ENTRY POINT into Moment 0 — now reached via `signals/drift_event.py::commit()` for cron, OR via `handle_drift_events.py::process_events()` for CLI replay. Both routes converge on `route_drift_event(...)`.

```
[CRON PATH]
felix-doc-auditor.service
  -> scripts/doc_audit/run.py
  -> DriftEventSignalSource.commit()
    -> route_drift_event(...)
      -> drift_interpretation.interpret()
        -> verdict routing (same as #362)
        -> drift_ledger.append(...)

[CLI / LIBRARY PATH]
python3 -m doc_audit.helpers.handle_drift_events
  -> process_events()
    -> route_drift_event(...)   [SAME helper]
      -> ... (same downstream as cron path)
```

Both paths invoke the same helper; the helper has identical side effects regardless of caller.
