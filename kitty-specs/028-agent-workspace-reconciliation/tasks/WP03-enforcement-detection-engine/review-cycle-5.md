---
affected_files: []
cycle_number: 5
mission_slug: 028-agent-workspace-reconciliation
reproduction_command:
reviewed_at: '2026-04-13T18:30:44Z'
reviewer_agent: unknown
verdict: rejected
wp_id: WP03
---

**Issue 1**: `drift_check.py` cannot be run via the documented entrypoint, so the CLI acceptance criteria are not met. The script advertises `python3 scripts/openclaw/enforcement/drift_check.py ...`, but that invocation crashes immediately with `ModuleNotFoundError: No module named 'scripts'` because [scripts/openclaw/enforcement/drift_check.py](/Users/kentgale/repos/kg-automation/.worktrees/028-agent-workspace-reconciliation-lane-a/scripts/openclaw/enforcement/drift_check.py:22) imports `scripts.openclaw...` as if the repo root were on `sys.path`. Repro from the workspace root: `python3 scripts/openclaw/enforcement/drift_check.py report --json --config <temp-config>`. Fix by making the file executable as a direct script from the repo root (for example, bootstrap `sys.path`, use a package-safe invocation pattern, or restructure imports), then add an end-to-end CLI test that executes the documented command rather than only importing helper functions.

**Issue 2**: The current tests do not cover the documented CLI contract, which allowed the broken entrypoint above to ship. [tests/openclaw/enforcement/test_drift_check.py](/Users/kentgale/repos/kg-automation/.worktrees/028-agent-workspace-reconciliation-lane-a/tests/openclaw/enforcement/test_drift_check.py:1) only tests helper functions after importing the module; it never executes `python3 scripts/openclaw/enforcement/drift_check.py check --dry-run --json` or `report`. Add subprocess-level coverage for the direct script invocation and assert the JSON/text behavior through the actual CLI surface.

WP04 depends on WP03. If you update this WP, notify the WP04 agent to rebase afterward.
