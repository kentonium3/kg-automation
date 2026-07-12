# Post-plan Codex review — findings & resolutions

Reviewer: Codex (`spec-kitty-review` profile), 2026-07-12. 9 findings
(0 CRITICAL, 3 HIGH, 4 MEDIUM, 2 LOW). All folded before `/spec-kitty.tasks`.

| # | Sev | Finding | Resolution |
|---|-----|---------|------------|
| 1 | HIGH | Colors claimed "locked to the design doc", but the design doc specifies no colors (operator chose them 2026-07-12). | **Mission now adds the color column to `docs/design/vikunja-configuration-design.md`** so it remains the single taxonomy authority. Artifacts reworded: titles+dimensions locked to the design doc; colors are this mission's decision, written into the design doc + the helper constants + data-model, and asserted equal by the fidelity test. Design-doc update added to IC-01 scope + a tasks concern. |
| 2 | HIGH | An already-present taxonomy label with a wrong color could be reported `already-present` while SC-001 demands exact colors — silent false success. Open note left color-fix to discretion + guessed `POST /labels/{id}`. | Contract now **fails loud**: an already-present taxonomy label whose normalized color ≠ the declared color is reported `color-mismatch` and the run exits non-zero (never a silent SC-001 pass). Speculative `--fix-colors`/`POST /labels/{id}` note removed (all 12 are created fresh this run, so drift cannot occur on the first live run; the check is the safety net). |
| 3 | HIGH | Tier-2 Restic backup gate existed only as operator prose; `--delete-legacy` could delete with no machine-checkable confirmation. | Contract now **requires `--backup-confirmed <snapshot-id-or-timestamp>` as a mandatory companion to `--delete-legacy`**; the helper refuses to delete without it and echoes the value in JSON output/run notes. spec FR-006/C-002 + quickstart updated. (Helper does not query Restic itself — the operator asserts the ref; proportionate to a 3-label delete.) |
| 4 | MEDIUM | Plan's mock-fidelity risk listed `get/post/delete`, but create is `PUT /labels` and the client has `.put`. | plan IC-02 risk + research R-07 corrected to **`get`/`put`/`delete`**, asserting leading-slash paths and the `PUT /labels` body shape. |
| 5 | MEDIUM | Duplicate live labels with the same title unspecified; a `{title: label}` map silently overwrites, making the id-map ambiguous. | Contract + data-model now require **duplicate-title detection**: a taxonomy title matching >1 live label → fail non-zero, report all ids; a legacy title matching >1 under `--delete-legacy` → delete **all** exact-title matches (reported individually). |
| 6 | MEDIUM | Delete-404 behavior was "already-absent OR surface" (loose). | Single behavior defined: on `VikunjaNotFoundError` during delete, **re-list**; if the title is now absent → `already-absent` (idempotent), else **fail** (inconsistent id/title view). |
| 7 | MEDIUM | Claim that #716 consumes the label *ids* for the `vikunja_scope.py` habit-selector move — but the seam uses `{"kind":"label","value":"t:habit"}`, i.e. the title. | Reworded across spec/plan/quickstart: **#716 consumes the stable title `t:habit`**; the title→id map is for #717 migration / API mutation that needs numeric ids. |
| 8 | LOW | FR-003 "single ... helper invocation" conflicts with the quickstart's multiple invocations. | FR-003 reworded to "a single deterministic, tested helper (one implementation/CLI)"; the operational sequence may invoke it multiple times. |
| 9 | LOW | Quickstart dry-run "12 would-create, 3 would-delete" is only true for the audited initial state. | Quickstart reworded to "on the audited current live state, expect…" and to verify the specific target titles/actions rather than treat the counts as an invariant. |

No title/casing drift found (12 labels match the design doc). API-contract
assumptions confirmed by Codex against the real client + `setup_vikunja.py`
(create = `PUT /labels`, leading-slash paths, empty-body delete → `{}`).
