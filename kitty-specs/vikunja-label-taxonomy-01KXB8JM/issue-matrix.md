# Issue matrix — vikunja-label-taxonomy-01KXB8JM

One row per GitHub issue referenced in the mission artifacts. Per the spec-kitty mission-review gate.

| Issue | Title | Verdict | Evidence ref |
|-------|-------|---------|--------------|
| #715 | Vikunja reset: create label taxonomy (f:, q:, t:, loe:) | fixed | This mission is #715. WP01 ships `scripts/vikunja/create_taxonomy_labels.py` — the idempotent reconcile helper that creates the 12 taxonomy labels (exact titles + colors) and, behind `--delete-legacy --backup-confirmed`, removes the 3 legacy labels — plus a 37-test offline suite and the design-doc color column. reviewer-renata APPROVE. The GitHub issue stays open until the post-merge office2 live run creates the labels and SC-001..005 are verified, then closed. |
| #723 | Deterministic escalation + weekly-report crons (vikunja_scope seam) | verified-already-fixed | Already shipped/merged/closed (merge 509a4b88). It added `scripts/common/vikunja_scope.py`, shaped so habit identity can move from project-id 13 to the `t:habit` label this mission creates. No work on #723 here; this mission produces the label its seam anticipates. |
| #716 | Vikunja reset: restructure projects (create topic projects, delete pseudo-view) | deferred-with-followup | Downstream child of #714. #716's habit-selector move consumes the **title** `t:habit` (`{"kind":"label","value":"t:habit"}` in `vikunja_scope.py`) that this mission creates — it needs the label to exist, not its id. Follow-up: #716. |
| #717 | Vikunja reset: migrate tasks (human-judgment relabel + move) | deferred-with-followup | Downstream child of #714. #717 applies these labels to tasks and consumes the title→id map this mission's run records on #715 (mutation is by numeric label id). Follow-up: #717. |
| #718 | Vikunja reset: saved filters + dashboard default | deferred-with-followup | Downstream child of #714. #718's saved-filter queries reference these exact label names (`t:habit`, `q:schedule`, `f:3-edge`). Depends on the labels existing. Follow-up: #718. |

Valid `Verdict` values: `fixed`, `verified-already-fixed`, `deferred-with-followup`, `in-mission` (being fixed by this mission; must reach a terminal verdict before mission `done`).
