---
work_package_id: WP02
title: Lift drift-ledger contract to live arch docs
dependencies:
- WP01
requirement_refs:
- C-001
- C-002
- C-003
- NFR-004
planning_base_branch: main
merge_target_branch: main
branch_strategy: Planning artifacts for this feature were generated on main. During /spec-kitty.implement this WP may branch from a dependency-specific base, but completed changes must merge back into main unless the human explicitly redirects the landing branch.
created_at: '2026-05-24T05:36:17+00:00'
subtasks:
- T007
- T008
- T009
history: []
authoritative_surface: docs/design/architecture/contracts/
execution_mode: code_change
mission_id: 01KSC6AJ2JK8N2NJT4QB6AB36Z
mission_slug: drift-ledger-retry-count-hardening-01KSC6AJ
owned_files:
- docs/design/architecture/contracts/drift-ledger-schema.md
- docs/design/architecture/README.md
tags: []
---

# WP02 — Lift Drift Ledger Contract to Live Arch Docs

## Objective

The existing drift-ledger schema contract lives in `kitty-specs/drift-event-auto-resolution-01KS8J32/contracts/ledger-schema.md`, which is workflow-managed and read-only per global CLAUDE.md. Once a mission merges, its contract artifact is frozen — it can't be updated to reflect later schema changes.

This WP lifts the contract to a live docs location at `docs/design/architecture/contracts/drift-ledger-schema.md` (sibling to the existing `data/` directory). The content matches the kitty-specs version with two updates: (a) `retry_count` bound widened to `[0, retry_max]` per #403, (b) a "Source of truth for `retry_max`" subsection explaining the derivation. It also updates the architecture README index to mention the new `contracts/` subdirectory so future contract docs have a discoverable home.

This establishes the pattern: **`docs/design/architecture/contracts/` is where living contract docs go.** Future missions touching ledger schemas, event formats, or signal contracts can add files here without re-litigating where the canonical doc lives.

## Context (read first)

- **Spec**: [../spec.md](../spec.md) — NFR-004 specifies the schema reference doc must be updated
- **Research**: [../research.md](../research.md) — Decision 3 (why lift the contract, vs. updating in place or making docstring canonical)
- **Source content**: [`kitty-specs/drift-event-auto-resolution-01KS8J32/contracts/ledger-schema.md`](../../drift-event-auto-resolution-01KS8J32/contracts/ledger-schema.md) — the existing contract, read-only
- **Updated content (planning preview)**: [../contracts/drift-ledger-schema.md](../contracts/drift-ledger-schema.md) — this WP creates the live version at the docs/ location

## Branch Strategy

- Planning branch: `main`
- Final merge target: `main`
- Worktree allocated per `lanes.json` at implementation time
- **No code dependencies on WP01.** WP01 updates `drift_ledger.py`'s docstring to reference this WP's file path. The link is forward-referencing; both WPs can land in either order. The link is briefly stale if WP01 lands first; resolved when WP02 merges.

## Subtasks

### T007 — Create live contract doc

**Files**:
- `docs/design/architecture/contracts/drift-ledger-schema.md` (NEW; the directory itself is new — Git will create it from the file write)

**Source**: Copy content from [../contracts/drift-ledger-schema.md](../contracts/drift-ledger-schema.md) (the planning-time preview is the authoritative draft).

**Required content**:

1. Lead section: title, file-on-disk, writer module, dataclass, schema version
2. Row schema table — same fields as the kitty-specs archive, with `retry_count` row showing `[0, retry_max]` (currently `4`)
3. "Source of truth for `retry_max`" subsection explaining `1 + len(RETRY_DELAYS_SECONDS)`
4. Serialization rules — identical to archive
5. Atomicity — identical to archive
6. Example rows — include all four verdict cases. Update the RETRY_EXHAUSTED example to show `retry_count: 4` (the post-fix value)
7. Query examples — keep the existing triage-rate and reliability-rate examples. Add a new "retry-budget consumption" example showing how to compute the distribution of `retry_count` values
8. Rotation/archival — identical
9. Backwards compatibility — identical, plus an explicit paragraph explaining why widening a range is backward-compatible without a schema_version bump
10. Change history table — two rows:
    - 2026-05-22 / `drift-event-auto-resolution-01KS8J32` (#362) / Initial schema. `retry_count: [0, 3]`
    - 2026-05-24 / `drift-ledger-retry-count-hardening-01KSC6AJ` (#403) / Widened `retry_count` bound. Lifted from archive.

The full draft is in `../contracts/drift-ledger-schema.md` in this mission's planning artifacts. Copy verbatim; only the file location changes.

### T008 — Update architecture README

**File**: `docs/design/architecture/README.md`

Locate the "Documents" table (around line ~25 in the current file). Add a new section above or below it explaining `contracts/`:

```markdown
## Schema Contracts

`docs/design/architecture/contracts/` holds the canonical schemas for the system's
internal contracts — ledger row schemas, event formats, signal contracts, and
similar. Each file is the authoritative source for the contract it documents;
code modules that implement the contract reference these files from their
docstrings.

| Contract | Used by |
|----------|---------|
| [Drift Ledger Schema](<./contracts/drift-ledger-schema.md>) | `scripts/doc_audit/output/drift_ledger.py` |
```

Match the existing README's tone and style. If there's a better natural place to integrate the entry (e.g., extend the existing "Documents" table), use judgment.

### T009 — Verify cross-link

This is a verification subtask, not a code change.

After WP01 lands its docstring update and this WP's content is in place, confirm:

1. Open `scripts/doc_audit/output/drift_ledger.py` and locate the `AuditLedgerEntry` dataclass docstring
2. Confirm the "See ..." reference points to `docs/design/architecture/contracts/drift-ledger-schema.md`
3. Confirm that file exists on the filesystem
4. Confirm the path resolves from the repo root

If the link is broken or points elsewhere, this is a failure mode — flag it for the reviewer rather than silently rewriting. The link target was decided in this mission's planning ([research.md](../research.md), Decision 3).

## Definition of Done

- [ ] T007 complete — `docs/design/architecture/contracts/drift-ledger-schema.md` exists with all required content, including widened `retry_count` bound and change history
- [ ] T008 complete — `docs/design/architecture/README.md` has a discoverable entry for `contracts/`
- [ ] T009 complete — cross-link from `drift_ledger.py` docstring to the new contract doc verified

## Risks and Mitigations

- **R1: Documentation drift over time.** Future schema changes may land in code (`drift_ledger.py` validator) without updating this contract doc. **Mitigation**: the docstring in `drift_ledger.py` should be a terse pointer to this file, not a duplicate of the schema. Reviewers of future schema changes should always check that the contract doc was updated.

- **R2: Adding a `contracts/` subdirectory may collide with the F015 constraint** that exempts `data/` from moves. **Mitigation**: `contracts/` is a separate sibling, not a relocation of `data/`. F015 doesn't apply. Read `docs/design/architecture/README.md` lead paragraph about machine-readable-artifact-home to confirm interpretation.

## Reviewer Guidance

- Confirm the new contract doc's row schema matches the post-#403 reality (especially the `retry_count` bound)
- Confirm the change history table includes both rows (initial + this widening)
- Confirm the README update is discoverable (an operator browsing the architecture docs should land here naturally)
- Confirm the doc renders cleanly in a markdown preview (no broken table cells, no escape-issues with backticks/pipes)

## Implementation Command

```bash
spec-kitty agent action implement WP02 --mission drift-ledger-retry-count-hardening-01KSC6AJ --agent claude:opus:python-implementer:implementer
```
