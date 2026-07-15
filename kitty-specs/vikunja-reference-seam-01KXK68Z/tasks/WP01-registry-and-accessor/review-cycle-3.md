---
affected_files: []
cycle_number: 3
mission_slug: vikunja-reference-seam-01KXK68Z
reproduction_command:
reviewed_at: '2026-07-15T18:03:25Z'
reviewer_agent: unknown
verdict: rejected
wp_id: WP01
review_artifact_override_at: "2026-07-15T18:14:07Z"
review_artifact_override_actor: "operator"
review_artifact_override_wp_id: "WP01"
review_artifact_override_reason: "codex cycle-3 approve"
---

# WP01 Review — Cycle 2 — REQUEST_CHANGES (reviewer: codex, gpt-5-codex)

Findings 1 & 2 (positive-int validation on project_id/label_id) are **confirmed
resolved**. 39 tests pass. One remaining gap in finding 3's fix:

1. **`tests/common/test_vikunja_refs.py` import-graph test only records top-level
   import roots.** So `from scripts.common.vikunja_client import VikunjaClient` and
   `import scripts.common.vikunja_client` both reduce to root `scripts` and do NOT
   trip the guard — but `scripts.common.vikunja_client` IS the network module this
   test must catch. Proven: `from scripts.common.vikunja_client import VikunjaClient
   => imported=['scripts'] leaked=[]`.
   **Required:** inspect the **full dotted module path** of every import in
   `scripts/common/vikunja_refs.py` (both `import a.b.c` and `from a.b import c`
   forms, including aliases) and fail if any path **component or suffix** matches a
   forbidden name — at minimum `vikunja_client`, `requests`, `urllib`. Match on the
   qualified path (e.g. `"scripts.common.vikunja_client".split(".")` contains
   `vikunja_client`), not just the first segment.
   **Also add a regression assertion / source fixture** proving a fully-qualified
   `scripts.common.vikunja_client` import WOULD be caught (e.g. run the same AST
   check against a small inline source snippet containing that import and assert it
   is flagged).

Nothing else outstanding — fix this and the WP is approvable.
