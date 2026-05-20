**Issue 1**: Stale-lock recovery misclassifies audits that are waiting on an open pending-approval with no decision label.

`scripts/doc_audit/run.py` builds the audit -> pending-approval index from `gh_source.pending()` only. But `scripts/doc_audit/signals/gh_issue.py` intentionally filters out `audit-pending-approval` issues unless they already have `audit-approve`, `audit-reject`, or `audit-skip`. The WP requires the stale-lock check to treat any open matching pending-approval, "with OR without a decision label", as an expected wait state. Today, an audit with `status:in-progress` plus an awaiting-review pending approval is not present in `pa_index`, so `_recover_stuck_locks()` clears the lock and reprocesses the audit incorrectly.

Fix: build the stale-lock cross-reference index from a dedicated query of all open `audit-pending-approval` issues, not just actionable pending-approval signals. Include title `Audit #N` and body `Refs #N` matching as specified, and add an integration/unit test for `status:in-progress` + pending approval with no decision label being skipped, not recovered.

**Issue 2**: The missing-file edge case does not satisfy the required recovery behavior.

The WP requires "Audit references missing file" to log the error, file a debt issue noting the discrepancy, close the audit with a summary, and continue. The current `FileNotFoundError` handler in `scripts/doc_audit/run.py` only appends the error and `result.debt_filed.append(0)`. It does not call the routing layer or GH to file a real debt issue, and it does not close/comment on the originating audit. The current edge-case test only asserts the placeholder, so it would pass while the operator-visible GH state remains unresolved.

Fix: when a missing referenced artifact is detected, create a real `DebtIssue` (or route through the existing helper that files debt), close/comment the audit with a missing-file summary, and record the real issue number in `debt_filed`. Update the integration test to assert the `gh issue create`/routing call and audit close/comment path.

**Issue 3**: LLM API failures inside judgment helpers can leave the tick marked `success`.

`_classify_proposed_edits()`, `_run_cross_file_implication()`, and `_generate_debt_bodies()` catch broad exceptions and append `result.errors`, but they do not set `result.status` to `partial`. If routing later returns `exit_code=0`, the tick exits 0 with `status="success"` despite a judgment-call failure. T029 requires Anthropic API/APIConnection errors to be logged and the tick to become partial, or failure when no signals made progress.

Fix: translate judgment boundary failures into partial/failure status consistently. Prefer catching the Anthropic API exception classes where available, but at minimum any caught judgment-call exception that appends to `result.errors` must prevent a success status. Add a test where `tier_classification` or `debt_body_generation` raises and routing succeeds; expected exit is 2 or 1, not 0.

**Issue 4**: The top-level finally block no longer appends the required activity-log tick entry.

T026 and the Definition of Done require `write_tick_signal()` and the activity log entry to be written in the top-level `finally`, even on crash. The implementation writes only the tick signal and summary line in `main()` and explicitly omits a per-tick activity log append. Per-audit entries do not cover empty-queue ticks or crashes before an audit is processed, so the "activity log entry ALWAYS appended" requirement is not met.

Fix: restore a best-effort activity-log append in `main()`'s `finally` using the WP05 activity-log API, while keeping per-audit entries if desired. Add/adjust integration coverage for empty queue and top-level failure so both tick signal and activity log are written.

**Validation note**: I could not run the integration tests in this shell because neither `pytest` nor `uv` is on PATH. `python3 scripts/doc_audit/run.py --version` and `--help` both work, and `scripts/doc_audit/run.py` is executable.

Downstream impact: WP07, WP08, and WP09 depend on WP06. If they have already started from this lane, they should rebase after the fixes land.
