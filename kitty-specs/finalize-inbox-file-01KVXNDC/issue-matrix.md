# Issue matrix — finalize-inbox-file-01KVXNDC

Per FR-037 of the spec-kitty-mission-review skill Gate-4. One row per issue referenced in spec.md.

| Issue | Title | Verdict | Evidence ref |
|-------|-------|---------|--------------|
| #323 | Bug: felix-admin-capture stalls on phone-captured inbox files (perm 0644 vs 0664) | deferred-with-followup | spec.md Out of Scope: permission symptom is explicitly out of scope; #323 remains OPEN as the follow-up. This mission closes the non-atomic/unrecoverable finalize gap instead; the new helper's reuse of mark_processed._atomic_write preserves file mode (0o664) on the status write, which mitigates but does not close #323. |

Valid `Verdict` values: `fixed`, `verified-already-fixed`, `deferred-with-followup`, `in-mission` (being fixed by a later WP in this mission; must reach a terminal verdict before mission `done`).
