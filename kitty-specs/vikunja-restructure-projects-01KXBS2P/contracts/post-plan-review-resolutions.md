# Post-plan Codex review — resolutions

Reviewer: Codex (`spec-kitty-review` profile), 2026-07-12, on spec.md + plan.md +
research.md + data-model.md + contracts/vikunja-api.md. 10 findings (4 HIGH, 5
MED, 1 LOW). Codex confirmed **no project-delete / task-mutation path exists**
(highest-severity class clean). All findings folded before `/spec-kitty.tasks`.

| # | Sev | Finding | Resolution |
|---|-----|---------|-----------|
| 1 | HIGH | Title-only project matching can bind to archived/duplicate/wrong-parent/wrong-owner projects. | FR-014 + data-model match key: match only active, correctly-parented, **kent-owned** projects; abort fail-loud on ambiguity. |
| 2 | HIGH | Reusing existing `Clients` by title without proving it is active/top-level/unique. | research R-04 + data-model: `Clients` must resolve to exactly one active top-level kent-owned project before creating children, else abort. |
| 3 | HIGH | Filter delete relies only on `filter_id = -pseudo_id - 1`. | FR-007 + research R-06 + contract: `GET /filters/{id}` title readback before each DELETE; never delete `-1`. |
| 4 | HIGH | kent-token ownership asserted but not enforced; `VikunjaClient` defaults to felix-bot token. | FR-009 + research R-07: explicit kent `--token-file` (no fallback) + owner-scoped matching + create-response `owner==kent` assertion. **Live finding: `GET /user` is 401 for API tokens** (no whoami) and **felix-bot sees Kent's shared projects + its own Inbox id 14** — owner field is the enforceable signal. |
| 5 | MED | Pagination omitted despite the 50-item cap. | research R-05a + data-model + contract: paginate `GET /projects` `per_page=50&page=N` until empty; `null→[]`; tests place targets/filters on page 2. |
| 6 | MED | Spec said filter delete may be skipped/manual vs SC requires filters gone. | C-005 rewritten: delete path **confirmed** (`DELETE /filters/{id}`); manual fallback only with verified evidence, never a silent skip. |
| 7 | MED | "Habits prompts must keep working" not measurable; contract excludes cron checks. | FR-010 + SC-005: measurable **zero write ops** against project id 13 / any project outside the create set, asserted in summary + tests (in-scope, no cron probing). |
| 8 | MED | CLI modes/exit semantics underspecified. | FR-013 + contract CLI table: create-only (default), `--delete-legacy`+`--backup-confirmed <ref>`, `--dry-run`, `--json`; exit 2 (missing backup), 1 (API error), 0 (success/dry-run). |
| 9 | MED | Partial-failure reporting undefined. | NFR-005 + FR-012 + data-model: summary shows completed vs skipped after a mid-run failure; test injects failure after one mutation. |
| 10 | LOW | Filter ids shown as fixed `1..5` conflict with env-specific note. | data-model: labelled live-examples-only; tests use non-`1..5` derived ids. |
