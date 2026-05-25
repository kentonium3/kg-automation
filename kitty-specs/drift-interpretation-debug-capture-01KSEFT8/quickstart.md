# Quickstart — Drift Interpretation Debug Capture

**Mission**: drift-interpretation-debug-capture-01KSEFT8

This is the operator runbook for using the debug capture once the code change merges to `main` and deploys to office2.

---

## Prerequisites

- `main` includes the merged mission (verify by `grep -n "DOC_AUDIT_DEBUG_DRIFT_PAYLOADS" scripts/doc_audit/judgment/drift_interpretation.py` — should return at least one hit).
- office2 has pulled `main` into `/home/claude/kg-automation`.
- `felix-doc-auditor.timer` is currently disabled (the steady state since #403 triage).

---

## Steps

### 1. Pull `main` to office2

```bash
ssh office2-claude 'cd /home/claude/kg-automation && git pull origin main'
```

### 2. Add the env var via systemd drop-in

```bash
ssh office2-claude 'systemctl --user edit felix-doc-auditor.service'
```

In the editor, add:

```ini
[Service]
Environment="DOC_AUDIT_DEBUG_DRIFT_PAYLOADS=1"
```

Save and exit. Reload the systemd user manager:

```bash
ssh office2-claude 'systemctl --user daemon-reload'
```

### 3. Trigger one tick

```bash
ssh office2-claude 'systemctl --user start felix-doc-auditor.service'
```

The service runs once and exits (it's a one-shot under the timer normally).

### 4. Watch for capture in the journal

```bash
ssh office2-claude 'journalctl --user -u felix-doc-auditor.service --since "5 minutes ago" --no-pager | grep drift_interpretation.schema_fail'
```

Expect at least one line of the form:

```
... drift_interpretation.schema_fail | <error_message> | <raw_response_text>...
```

If no line appears, troubleshoot:
- Did the tick encounter a drift event? `journalctl ... | grep "drift_event"`
- Did `_parse_verdict` succeed unexpectedly? Compare retry_count in the drift ledger.
- Is the env var set inside the service? `journalctl ... | grep "DOC_AUDIT"` (the service should print env at start under verbose logging, or we can read the unit's `Environment=` line back via `systemctl --user show felix-doc-auditor.service | grep Environment`).

### 5. Extract the captured payload

```bash
ssh office2-claude 'journalctl --user -u felix-doc-auditor.service --since "5 minutes ago" --no-pager | grep -A 2 drift_interpretation.schema_fail' > /tmp/drift_capture.txt
```

Inspect the file locally:

```bash
scp office2-claude:/tmp/drift_capture.txt /tmp/drift_capture.txt
less /tmp/drift_capture.txt
```

### 6. Disable the env var

```bash
ssh office2-claude 'systemctl --user edit felix-doc-auditor.service'
```

Remove the `Environment=` line. Save and exit. Reload:

```bash
ssh office2-claude 'systemctl --user daemon-reload'
```

Verify the drop-in is gone:

```bash
ssh office2-claude 'systemctl --user show felix-doc-auditor.service | grep DOC_AUDIT'
```

Should return no matching lines.

### 7. Confirm timer is still disabled

```bash
ssh office2-claude 'systemctl --user is-enabled felix-doc-auditor.timer'
```

Expected: `disabled`. (The timer was disabled before mission #404 and stays disabled until both #402 and the follow-up fix mission land per the continuity doc.)

### 8. Write the diagnostic doc

Create `docs/diagnostics/drift-interpretation-payload-shape.md` with:
- The (sanitized) captured payload
- Which `_RetrySchemaError` message appeared in the log line
- Root cause hypothesis: prompt regression / schema regression / model behavior change (pick one based on payload analysis)
- Recommendation for the follow-up fix issue

### 9. Close issue #404

```bash
gh issue close 404 --repo kentonium3/kg-automation --comment "Diagnostic captured 2026-MM-DD on office2 under mission drift-interpretation-debug-capture-01KSEFT8. Findings in docs/diagnostics/drift-interpretation-payload-shape.md. Follow-up fix tracked in #<new-issue-number>."
```

### 10. File the follow-up fix issue (if needed)

If the diagnostic reveals a fix is needed (almost certainly yes), file a new issue under the appropriate label:

- `P1-bug`, `area/felix-core`, `spec: brief` (then later `spec: ready` after formalization)
- Cross-reference #404 and the diagnostic doc in the issue body

---

## Reversibility

Every step in this quickstart is reversible. If something goes wrong mid-flow:

- The env var is process-local; removing the drop-in and reloading systemd makes the next service run identical to today's behavior.
- No state is written to disk by the capture path beyond the journal entries journald already manages.
- No changes to ledger files, status files, or repo content occur via the capture path.

---

## Time budget

- Code change + tests + review: ≤ 1 day (mission #404)
- Operational capture + diagnostic doc + #404 closure: ≤ 30 minutes once code is merged

Total mission wall-clock: 1 day + 30 min.
