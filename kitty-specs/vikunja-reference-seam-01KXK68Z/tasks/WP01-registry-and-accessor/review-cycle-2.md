---
affected_files: []
cycle_number: 2
mission_slug: vikunja-reference-seam-01KXK68Z
reproduction_command:
reviewed_at: '2026-07-15T17:55:57Z'
reviewer_agent: unknown
verdict: rejected
wp_id: WP01
---

# WP01 Review — Cycle 1 — REQUEST_CHANGES (reviewer: codex, gpt-5-codex)

Implementation is close (31 tests green, live-probed registry correct), but three
fail-loud/proof gaps must be fixed before approval. All three are on-contract
(the mission's whole point is fail-loud correctness + NFR-001 no-network).

1. **`scripts/common/vikunja_refs.py` `project_id()` — blind `int(value)` coercion.**
   A malformed provisioned entry with `"value": 0` returns the forbidden sentinel
   `0`, and a non-numeric string raises raw `ValueError` instead of `VikunjaRefError`.
   Proven live: `project_id("zero") -> 0`; a string value raised `ValueError`.
   **Required:** validate the `project_id` selector value is a positive integer id
   (`int`, `> 0`) before returning; raise `VikunjaRefError` (with a descriptive
   message naming the logical name) for a missing/zero/non-int/negative value.

2. **`scripts/common/vikunja_refs.py` `label_id()` — same blind `int(value)` coercion.**
   Label ids can return `0` or leak a raw `ValueError` for malformed registry values.
   **Required:** same positive-integer validation, failing loud with `VikunjaRefError`.

3. **`tests/common/test_vikunja_refs.py` no-network test is insufficient for NFR-001.**
   It only proves injected accessors avoid `_load_registry_file`; it does not prove
   the accessor module's import graph excludes network modules.
   **Required:** add a contract test that inspects `scripts.common.vikunja_refs`'s
   imports (e.g. parse the module source / `sys.modules` after fresh import, or walk
   the AST) and FAILS if `vikunja_client`, `requests`, or `urllib` are imported.

Also add/extend unit tests covering the new fail-loud paths in (1) and (2)
(value 0, negative, non-int string → `VikunjaRefError`).
