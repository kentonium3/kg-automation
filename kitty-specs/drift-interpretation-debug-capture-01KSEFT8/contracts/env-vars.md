# Environment Variable Contracts — Drift Interpretation Debug Capture

**Mission**: drift-interpretation-debug-capture-01KSEFT8
**Status**: NEW (this mission introduces the variable)

---

## `DOC_AUDIT_DEBUG_DRIFT_PAYLOADS`

**Purpose**: Enable one-shot debug capture of raw 200-OK LLM response bodies when `_parse_verdict` in `scripts/doc_audit/judgment/drift_interpretation.py` raises `_RetrySchemaError`. Used to diagnose root cause of repeated schema-validation failures without persisting raw model output to disk or repo.

**Accepted values**:

| Value | Effect |
|-------|--------|
| `"1"` | Capture enabled. Each `_RetrySchemaError` raise site emits a `WARNING`-level log line containing the raw response body (truncated to 4096 bytes) before re-raising. |
| Any other value (including `"0"`, `"true"`, `"yes"`, `"on"`, empty string, unset) | Capture disabled. No log emission. `_RetrySchemaError` raises with no extra side effects. |

The exact-match semantics are deliberate. See [research.md R2](../research.md) for rationale.

**Default**: unset (capture disabled).

**Scope**: process-local. Read at each call to `_parse_verdict` (not cached at import time, so toggling the env var between calls within a single process is honored — useful for tests, irrelevant in production where the var is set once at service start).

**Reversibility**: fully reversible. Unsetting the variable (or setting it to anything other than `"1"`) immediately disables capture on subsequent calls. No state persists after the var is unset.

**Setting on office2** (operational use):

```bash
# Enable for one tick
ssh office2-claude 'systemctl --user edit felix-doc-auditor.service'
# In the editor, add:
#   [Service]
#   Environment="DOC_AUDIT_DEBUG_DRIFT_PAYLOADS=1"
# Save, exit.
ssh office2-claude 'systemctl --user daemon-reload'
ssh office2-claude 'systemctl --user start felix-doc-auditor.service'

# Watch capture in journal
ssh office2-claude 'journalctl --user -u felix-doc-auditor.service -f --no-pager | grep drift_interpretation.schema_fail'

# Disable after capture
ssh office2-claude 'systemctl --user edit felix-doc-auditor.service'
# Remove the Environment line, save, exit.
ssh office2-claude 'systemctl --user daemon-reload'
```

See [quickstart.md](../quickstart.md) for the full operator runbook.

**Security/privacy considerations**:
- Captured payloads MAY contain confidential repo content (commit messages, code excerpts, doc text). Treat the journal output as sensitive while the env var is enabled.
- DO NOT enable in long-running production. C-002 enforces off-by-default.
- DO NOT commit raw captured payloads to the repo. The diagnostic document author sanitizes before recording per C-001.

**Log line format**:

```
WARNING drift_interpretation.schema_fail | <error_message> | <raw_response_text_truncated_to_4096_bytes>[truncated]
```

The `[truncated]` suffix appears only when the original response exceeded 4096 bytes.

**Test contract** (enforced by the unit test suite):
- AS1 — env var set + invalid response → log line present
- AS2 — env var unset + invalid response → log line absent
- AS3 — env var set + valid response → log line absent
- AS4 — each `_RetrySchemaError` raise site produces a capture when the env var is set
