# Data Model — Drift Interpretation Debug Capture

**Mission**: drift-interpretation-debug-capture-01KSEFT8

This mission introduces **no new persistent entities, schemas, or stored data**. It adds a runtime-only logging path inside an existing script. The only "data" involved is:

1. The raw 200-OK LLM response body (a Python `str`), which already exists in memory inside `_parse_verdict` at the moment of failure — the mission's contribution is *making it visible* via a log emission rather than persisting it anywhere new.
2. An OS environment variable (`DOC_AUDIT_DEBUG_DRIFT_PAYLOADS`) that gates the visibility decision at the call site.

No SQLAlchemy models, no JSON ledger schemas, no API payloads, no on-disk artifacts beyond a stderr log line that journald captures by virtue of the service running under systemd.

For completeness, the runtime decision flow is:

```
_parse_verdict(response_text)
  ↓
schema validation fails
  ↓
_log_raw_response_if_debug(response_text, error_message)
  ├─ os.environ.get("DOC_AUDIT_DEBUG_DRIFT_PAYLOADS") == "1"?
  │    no → return (no-op)
  │    yes → truncate response_text to ≤4096 bytes
  │          emit logger.warning("drift_interpretation.schema_fail | <error_message> | <truncated text>")
  ↓
raise _RetrySchemaError(error_message)   # unchanged behavior
```

See [contracts/env-vars.md](contracts/env-vars.md) for the env var contract.
