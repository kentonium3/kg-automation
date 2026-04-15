---
affected_files: []
cycle_number: 2
mission_slug: 028-agent-workspace-reconciliation
reproduction_command:
reviewed_at: '2026-04-13T18:25:35Z'
reviewer_agent: unknown
verdict: rejected
wp_id: WP03
---

**Issue 1**: `scripts/openclaw/enforcement/drift_check.py` misclassifies SSH failures as file drift instead of skipping errored files. `compute_remote_hashes()` ignores non-zero `ssh` exit codes and returns an empty dict, and `compute_all_hashes()` then maps every missing remote entry to `None`, which `classify_drift()` reports as `FILE_MISSING_OFFICE2`. This violates the WP edge-case requirement to log SSH errors, skip affected files, and continue with the rest. Reproduce with `compute_remote_hashes('definitely-invalid-host-for-test', ['/tmp/a'])`, which currently returns `{}`. Fix by checking the SSH process return code, preserving per-file error state separately from real missing-file state, and excluding errored files from drift classification/output.

**Issue 2**: The tests only cover `detection.py`; there is no coverage for `drift_check.py` helper or CLI behavior. That leaves the required hash-computation edge cases untested, including SSH failure handling, missing manifest/config errors, and the `check --dry-run --json` reporting path. Add targeted tests for the CLI/hash layer with mocked `subprocess.run` so unit tests do not perform SSH, and verify that transport failures do not surface as `FILE_MISSING_*` drift results.

**Downstream impact**: WP04 depends on WP03. If you pick this back up, rebase WP04's lane work after the fix before continuing dependent work.
