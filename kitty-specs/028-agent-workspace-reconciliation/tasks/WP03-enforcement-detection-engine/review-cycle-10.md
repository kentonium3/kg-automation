---
affected_files: []
cycle_number: 10
mission_slug: 028-agent-workspace-reconciliation
reproduction_command:
reviewed_at: '2026-04-13T18:37:20Z'
reviewer_agent: unknown
verdict: rejected
wp_id: WP03
---

**Issue 1**: Factory-default detection is computed only from the repo hash, so new customizations made on `office2` are misreported as still factory-default. In [scripts/openclaw/enforcement/detection.py](/Users/kentgale/repos/kg-automation/.worktrees/028-agent-workspace-reconciliation-lane-a/scripts/openclaw/enforcement/detection.py:123), `detect_all_drift()` calls `is_factory_default(current_repo, ...)` and stores a single boolean on `DriftResult`. That loses the transition the WP explicitly calls out: `OFFICE2_CHANGED + was factory default -> this is a new customization event`. A concrete repro is `repo=factory`, `office2=custom`, baseline both `factory`: the current code returns `OFFICE2_CHANGED` with `is_factory_default=True`, which is the opposite of the `office2` side’s actual state. Fix this by tracking factory-default status for the side that changed, or by storing repo/office2 factory-default state separately, and add a test that covers an `office2` customization transition.

**Issue 2**: The required manifest/config loader and single-file remote hash functions from the WP prompt are missing from `drift_check.py`. The WP explicitly requires `load_manifest()`, `load_factory_baselines()`, `load_config()`, and `compute_remote_hash()` in [WP03-enforcement-detection-engine.md](</Users/kentgale/repos/kg-automation/kitty-specs/028-agent-workspace-reconciliation/tasks/WP03-enforcement-detection-engine.md:52>). The implementation provides only a generic `load_json()` plus `compute_remote_hashes()` in [scripts/openclaw/enforcement/drift_check.py](/Users/kentgale/repos/kg-automation/.worktrees/028-agent-workspace-reconciliation-lane-a/scripts/openclaw/enforcement/drift_check.py:36), and the test suite does not verify the required API surface. Add the specified functions, keep batching if you want for performance, and cover the named entry points in tests so downstream WP04 can rely on the agreed interface.

WP04 depends on WP03. If you update WP03, notify the WP04 agent to rebase after the fix lands.
