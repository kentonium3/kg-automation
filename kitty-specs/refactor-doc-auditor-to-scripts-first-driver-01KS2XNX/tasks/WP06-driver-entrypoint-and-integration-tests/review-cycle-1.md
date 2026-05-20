# Review Feedback: WP06 — Driver entrypoint and integration tests

The implementation of the driver entry point and orchestration loop is incomplete and diverges from the WP06 prompt in several critical areas.

**Issue 1: Missing Audit Workflow Implementation**
The WP06 prompt (**T027 step 4**) explicitly requires the driver to perform the audit workflow for `doc_audit` and `weekly_doc_audit` signals:
- Read in-scope docs (domain-map intersection).
- For each candidate edit: call `tier_classification` LLM → dispatch by tier.
- Run missing-artifact detection (deterministic per SKILL.md §6).
- Call `cross_file_implication` LLM for non-touched docs.
- Compose debt-issue bodies via `debt_body_generation` LLM.
- Invoke routing layer with the resulting edits and debt.

The current implementation in `scripts/doc_audit/run.py` skips all these steps, passing empty lists to `apply_routing`. The code comment claiming this lives in "downstream WPs (07-10)" is incorrect as per the `tasks.md` subtask list. WP06 is the synthesis WP where these components must be wired together.

**Issue 2: Missing Lock Acquisition**
The WP06 prompt (**T027 step 4**) requires the driver to "Acquire lock (add `status:in-progress` label)" before processing a doc audit. The current implementation fails to perform this operation, which is critical for preventing concurrent processing by multiple driver instances.

**Issue 3: Stuck-Lock Recovery Divergence**
The WP06 prompt (**T028 step 1**) requires modifying `GHIssueSignalSource._fetch_doc_audits()` to include stuck locks in the signal queue with a `payload.stale_lock = True` flag so they can be "processed normally" in the current tick. The current implementation instead clears the label in `_recover_stuck_locks`, delaying processing until the *next* tick. Additionally, the requested modification to `gh_issue.py` was not made.

**Issue 4: Inadequate Integration Tests**
The integration tests in `tests/doc_audit/test_integration_tick_outcomes.py` use monkeypatching to mock `run.apply_routing`, returning canned results that bypass the missing audit logic. To be a valid integration test, they should verify that the driver correctly orchestrates the judgment moments (using `mock_anthropic` for LLM responses) and passes the correctly populated lists to the routing layer.

**Issue 5: Missing activity_log.append_entry call**
The WP06 prompt (**T026 step 3**) pseudocode shows a call to `append_entry(config, result)` in the `finally` block of `main`. The current implementation calls `print_summary_line(result)` but does not appear to call `append_entry` (only per-audit entries via `_log_audit_outcome` which calls `append_audit_entry`). While `append_audit_entry` is called per signal, a per-tick summary entry in the activity log was requested. (Note: verify if `append_audit_entry` covers all logging needs or if a per-tick summary was intended as per T026).
