# Contract: `create_taxonomy_labels` helper CLI

Deterministic reconcile helper. Module: `scripts/vikunja/create_taxonomy_labels.py`.
Invoked as `python3 -m scripts.vikunja.create_taxonomy_labels [options]`.

## Purpose

Reconcile the live Vikunja label set toward the canonical taxonomy: create any
missing taxonomy label (with color), optionally delete the legacy labels, and
report outcomes + the title→id map. Deterministic, idempotent, no LLM.

## CLI

| Flag | Default | Effect |
|------|---------|--------|
| (none) | — | Create-only reconcile: create missing taxonomy labels, skip present ones, report outcomes + emit title→id map. No deletions. |
| `--delete-legacy` | off | Additionally delete the legacy labels (`personal`, `intentional`, `Duplicate`) by resolved id. Destructive (Tier-2). **Requires `--backup-confirmed`** — refuses to run the delete pass without it. |
| `--backup-confirmed <ref>` | — | Mandatory companion to `--delete-legacy`. A Restic snapshot id or ISO timestamp asserting a recent backup exists. The helper does not query Restic; it records the ref and echoes it in output (machine-checkable gate for C-002/SC-005). Absent + `--delete-legacy` → refuse, exit non-zero. |
| `--dry-run` | off | Compute and print the planned actions (would-create / would-delete) against the current live state without mutating; exits 0. Enables safe pre-check. |
| `--json` | off | Emit the outcome list + title→id map as JSON on stdout (for capture/automation). Human-readable summary otherwise. |
| `--base-url <url>` | from `vikunja_config` | Override base URL (else canonical config). |
| `--token <str>` / `--token-file <path>` | from `VikunjaClient` default | Override token (else canonical secret path). |

Wiring: constructs `VikunjaClient(base_url=..., token=...)` (both optional —
falls back to canonical defaults on office2).

## Behavior contract

1. **List** existing labels via paginated `GET /labels` (`per_page=50`), building `{normalized_title: [labels...]}` — a **list** per title so duplicates are detectable, not silently overwritten.
2. **Duplicate guard**: if any *taxonomy* title maps to >1 live label → record `duplicate-title` with all ids, do not mutate that title, and mark the run for a non-zero exit (FR-010).
3. **Create pass**: for each taxonomy entry whose title is absent, `PUT /labels` with `{"title", "hex_color"}`; record `created` + new id. If present with a matching normalized color → `already-present` + existing id. If present with a **different** normalized color → `color-mismatch` + existing id, mark non-zero exit (FR-011). (Cannot occur on the first live run — all created fresh.)
4. **Delete pass** (only if `--delete-legacy` AND `--backup-confirmed` given; else refuse with a clear error, exit non-zero): for each legacy title present, `DELETE /labels/{id}` for **every** exact-title match; record `deleted` per id. If absent, `already-absent`. On `VikunjaNotFoundError` mid-delete, re-list: title absent → `already-absent`; still present → fail (inconsistent view). Without `--delete-legacy`, each present legacy label is `skipped-no-flag`.
5. **Emit** the per-label outcome table, the title→id map for the 12 taxonomy labels, and (when deleting) the echoed `backup_confirmed` ref.
6. **Exit code**: `0` only when all taxonomy labels are present with correct colors and all requested deletions are done; **non-zero** on any `duplicate-title`, `color-mismatch`, refused delete, or surfaced API error.

## Idempotency

- Second run with no flag: every taxonomy label `already-present`, 0 creates → exit 0, 0 changes (NFR-002).
- Second run with `--delete-legacy` after legacy already gone: every legacy `already-absent`, 0 deletes → exit 0.

## Failure modes (must be surfaced, not swallowed)

| Condition | Behavior |
|-----------|----------|
| Vikunja unreachable / timeout | Propagate `VikunjaTimeoutError`/`VikunjaServerError`; non-zero exit; no partial claim of success. |
| Auth failure (401) | Propagate `VikunjaAuthError`; non-zero exit. |
| Delete of an id that 404s mid-run | Re-list; if the title is now absent → `already-absent` (idempotent); if still present → fail (inconsistent id/title view). Never crash the run. |
| Create returns unexpected shape | Surface `VikunjaServerError`; non-zero exit. |
| `--delete-legacy` without `--backup-confirmed` | Refuse before any mutation; clear error; non-zero exit. |
| Duplicate live labels sharing a taxonomy title | `duplicate-title`, report all ids, no mutation of that title; non-zero exit. |
| Already-present taxonomy label with wrong color | `color-mismatch`, non-zero exit — never a silent SC-001 pass. |

## Color correction (out of scope)

This mission creates all 12 labels fresh, so color drift cannot occur on the
first live run. The helper therefore **detects** a color mismatch and fails
loud (above) rather than correcting it — no color-update endpoint is used and
no `--fix-colors` flag is introduced. Correcting a drifted color is a future
concern only if a taxonomy label is later hand-edited.
