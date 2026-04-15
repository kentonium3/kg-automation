---
affected_files: []
cycle_number: 3
mission_slug: 028-agent-workspace-reconciliation
reproduction_command:
reviewed_at: '2026-04-13T18:05:10Z'
reviewer_agent: unknown
verdict: rejected
wp_id: WP02
---

**Issue 1**: `scripts/openclaw/enforcement/generate_manifest.py` is missing, so T006 and the Definition of Done item "`generate_manifest.py` can be re-run to refresh the manifest" are not satisfied. The current change set adds `baseline-manifest.json`, `factory-baselines.json`, `drift-check-config.json`, and `__init__.py`, but there is no helper script under `scripts/openclaw/enforcement/` and no other manifest-generation entrypoint in the repo. Add the Python helper described in the WP: it must read the agent mapping from config (or a documented initial fallback), compute repo and office2 SHA256 values for all tracked files, and regenerate `scripts/openclaw/agents/baseline-manifest.json` in the documented schema.

**Downstream impact**: WP03 depends on WP02. After fixing this WP, notify the WP03 agent to rebase because the manifest-generation interface is part of the dependency surface.
