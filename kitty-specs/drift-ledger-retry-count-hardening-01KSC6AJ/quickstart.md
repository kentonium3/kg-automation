# Quickstart: Verifying Drift Ledger Retry Count Hardening

**Mission**: `drift-ledger-retry-count-hardening-01KSC6AJ`
**Audience**: Operator (Kent) — post-implementation, before merge and after merge to office2.

---

## 1. Local verification (pre-merge, after implementation)

Run the full doc-audit pytest suite:

```bash
pytest tests/doc_audit/ -v
```

Expected: all tests pass, including the new regression test in `tests/doc_audit/signals/test_drift_event.py` (parametrized over `exc.attempts ∈ {0, 1, retry_max-1, retry_max}`).

Run the specific regression test in isolation to confirm the bug-fix path:

```bash
pytest tests/doc_audit/signals/test_drift_event.py -k retry_count -v
```

If you want to confirm the test would have caught the bug, temporarily revert the validator-bound widening in `scripts/doc_audit/output/drift_ledger.py` and re-run. The new test should fail with `ValueError: retry_count must be in [0, 3]; got 4`. Restore the fix before committing.

## 2. Office2 verification (post-merge)

The `felix-doc-auditor.timer` was disabled during the 2026-05-24 incident (per [#403](https://github.com/kentonium3/kg-automation/issues/403)). After merging this mission to `main`, deploy and re-enable:

### Pull the merged code on office2

```bash
ssh office2-claude 'cd /home/claude/kg-automation && git pull origin main'
```

Confirm `scripts/doc_audit/output/drift_ledger.py` and `scripts/doc_audit/signals/drift_event.py` reflect the new code.

### Re-enable the timer

```bash
ssh office2-claude 'systemctl --user enable --now felix-doc-auditor.timer'
```

### Trigger one tick and watch

```bash
ssh office2-claude 'systemctl --user start felix-doc-auditor.service'
ssh office2-claude 'journalctl --user -u felix-doc-auditor.service -f --no-pager'
```

Watch for at least one drift event to be processed. Look for:

- ✅ `drift_event.commit` completes without `ValueError`
- ✅ At least one `RETRY_EXHAUSTED` row appears in the ledger (because #404 is still open and `_RetrySchemaError` still fires; the difference is that the crash no longer follows)
- ✅ The tick proceeds to the doc-audit issue queue after drift events drain

### Confirm the ledger row

```bash
ssh office2-claude 'tail -5 /data/services/security-monitor/logs/drift-events-ledger.jsonl | jq -c "select(.verdict==\"RETRY_EXHAUSTED\") | {event_id, retry_count, outcome}"'
```

Expected: one or more rows with `retry_count: 4` (not `3` — that's the fidelity goal).

## 3. Acceptance check against spec success criteria

Map back to [spec.md](spec.md) Success Criteria:

| SC | Verification |
|---|---|
| SC-001 | Step 2: no `ValueError` in journalctl during a tick that exhausts retries |
| SC-002 | Step 2: ledger row with `retry_count = 4` (actual attempt count, not silent clamp) |
| SC-003 | Step 2: subsequent drift events / audit issues process after the RETRY_EXHAUSTED event |
| SC-004 | Step 1: new regression test exists and passes |
| SC-005 | Step 1: `pytest tests/doc_audit/` all green |
| SC-006 | Step 2: timer enabled, tick triggered, ledger row present, no crashes |

## 4. What this does NOT fix

- The underlying reason `_RetrySchemaError` fires on every call is still open as [#404](https://github.com/kentonium3/kg-automation/issues/404). After this mission, every drift event will still waste ~3.5 min on retries and end in `RETRY_EXHAUSTED`. That's the expected interim state until #404 lands.
- `audit_interpretation` oversized-diff handling is still open as [#402](https://github.com/kentonium3/kg-automation/issues/402). Don't unpark issue [#350](https://github.com/kentonium3/kg-automation/issues/350) until #402 lands.

## 5. Rollback (if needed)

Revert the merge commit:

```bash
git revert <merge-commit-sha>
git push origin main
ssh office2-claude 'cd /home/claude/kg-automation && git pull origin main'
```

The schema widening is additive, so reverting cannot corrupt existing ledger rows. The validator returns to the old `[0, 3]` bound; new rows written by the in-process service will revert to the old crash behavior, so disable the timer if rolling back without an immediate forward-fix.
