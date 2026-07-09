# Issue matrix — prompt-sync-ff-race-01KX3SZC

Per FR-037 of the spec-kitty-mission-review skill Gate-4. One row per issue referenced in spec.md.

| Issue | Title | Verdict | Evidence ref |
|-------|-------|---------|--------------|
| #662 | harden inbox capture (incidental historical reference — the deploy during which the "28 commits behind" symptom was observed) | verified-already-fixed | Closed 2026-07-06; not a target of this mission — spec.md cites it only as the temporal marker for the symptom. |
| #636 | reconcile the two office2 deploy paths (separate checkouts) | deferred-with-followup | spec.md C-004 + research.md D6 — separate checkouts explicitly out of scope here; #636 tracks the deeper architectural fix this mission only partially de-risks. |

Valid `Verdict` values: `fixed`, `verified-already-fixed`, `deferred-with-followup`, `in-mission` (being fixed by a later WP in this mission; must reach a terminal verdict before mission `done`).
