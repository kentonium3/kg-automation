# Phase 0 Research: Documentation Developer Portal

**Mission**: documentation-developer-portal-01KSJ75K
**Date**: 2026-05-26
**Purpose**: Resolve every open question from the spec before Phase 1 design.

---

## R-1: Allowed `doc_type` values for the portal

- **Decision**: Use `doc_type: index` for `docs/DEVELOPER_PORTAL.md`.
- **Rationale**: Inspection of `tooling/scripts/validate_docs.py` shows the allowed enum is `{'strategy','charter','decision','explanation','policy','handbook','postmortem','runbook','guide','reference','readme','index','project','note','func-spec','standard'}`. `index` is the most accurate semantic label — the portal is a sitemap/onboarding index. (Note: `docs/INDEX.md` itself uses `doc_type: reference`, which is older repo convention. We deliberately use `index` here because it is more accurate; this does not require changing `INDEX.md`.)
- **Alternatives considered**:
  - `guide`: valid, but suggests a tutorial/walkthrough rather than a navigation portal
  - `reference`: matches `INDEX.md` precedent, but the portal is more guided than a flat reference
- **Validation**: `python tooling/scripts/validate_docs.py` after creation must exit 0.

## R-2: Runbook `audience:` frontmatter coverage

- **Decision**: Treat the existing `audience:` enum (`agents`, `humans`, `agents_and_humans`) as authoritative input. Surface any runbook missing the field in an explicit "Unclassified" bucket of the generated filter, do not silently drop or default it.
- **Rationale**: Sample of `docs/runbooks/*.md` (10 files, sampled during plan) shows the `audience:` field is present and uses the three documented values. No silent miscategorization risk for current state. Future drift (a new runbook lands without `audience:`) is caught by surfacing the bucket — and the bucket appearing in the filter signals exactly where the fix is needed.
- **Alternatives considered**:
  - Default missing values to `humans` — silently hides the issue.
  - Fail the generator if any runbook lacks `audience:` — too aggressive; would block portal regeneration on legitimate drafts.

## R-3: Generated vs hand-maintained Virtual Runbook Filter

- **Decision**: Generate from frontmatter via a new helper script (`tooling/scripts/build_runbook_filter.py`).
- **Rationale**: Aligns with Felix Constitution Directive 6 (deterministic work belongs in scripts the agent invokes, not in LLM prompts). Categorizing files by a known enum is purely deterministic. Hand-maintenance creates invisible drift; generation prevents it.
- **Confirmed with operator**: 2026-05-26.
- **Alternatives considered**:
  - Hand-maintain (Phase 1 only, auto-generate later): rejected by operator; leaves drift risk indefinitely.
  - Read-time generation (point to a CLI command, no persistent table): rejected — portal becomes interactive rather than self-contained; agents reading the file get nothing.

## R-4: Where the generation script lives and how it integrates with validation

- **Decision**: Script lives at `tooling/scripts/build_runbook_filter.py`. Default mode is a drift-check (exit non-zero with diff if portal block is stale). `--write` mode rewrites the block in place between `<!-- begin:runbook-filter (generated; do not edit) -->` / `<!-- end:runbook-filter -->` markers. `tooling/scripts/validate_docs.py` is extended to call the script's check function so CI / local validation catches drift.
- **Rationale**: Single source of truth for the categorization logic. Markers keep the rest of the portal hand-editable. Wiring through `validate_docs.py` reuses the existing local validation entry point — contributors don't need to learn a new command.
- **Alternatives considered**:
  - Standalone CI workflow: more moving parts; `validate_docs.py` is already the umbrella check.
  - Pre-commit hook: heavier installation burden; the `validate_docs.py` route runs in CI anyway.
  - Embed the generation as a `validate_docs.py` subroutine directly (no separate file): mixes deterministic generation with validation; the separation is cleaner and makes the script independently runnable for manual refresh.

## R-5: Anchor location for the new pointer in `CLAUDE.md`

- **Decision**: Add the pointer line under the existing "Architecture Documentation" H2 section in the project-root `CLAUDE.md`, immediately after the existing list of architecture pointers.
- **Rationale**: That section is the established index for "where to find authoritative docs." Adding to it preserves CLAUDE.md's locality of reference: AI sessions already read that section for sitemap pointers. Placement does not require any existing line to move.
- **Alternatives considered**:
  - Top of `CLAUDE.md` (before "What This System Is"): higher visibility but disrupts the existing narrative flow; risk that an additive change starts looking like a structural one.
  - New top-level section: more visible but adds a section header, which is not strictly additive (it nudges the table of contents). Reject.
  - Append to bottom: too easy to miss; defeats the purpose.

## R-6: Should `docs/INDEX.md` link to the portal? Should the portal link back to `docs/INDEX.md`?

- **Decision**: Both directions. `docs/INDEX.md` gains one new entry under an "Onboarding & Navigation" subsection (or the most appropriate existing section if one fits — implementation chooses based on current layout). The portal opens with a one-line note pointing back at `docs/INDEX.md` as the full catalog.
- **Rationale**: Bidirectional linking prevents either file from becoming a dead end for readers who landed in the wrong place first.

## R-7: Quickstart artifact scope

- **Decision**: Produce a minimal `quickstart.md` showing the two contributor commands needed to operate the portal: `python tooling/scripts/build_runbook_filter.py --write` (refresh) and `python tooling/scripts/validate_docs.py` (verify). No more — the portal itself is the user-facing onboarding artifact for the broader system.
- **Rationale**: Quickstart is about *operating this mission's output*, not about onboarding to the repo. The latter is the portal's job.

---

## Open clarifications resolved

All `[NEEDS CLARIFICATION]` markers were resolved during specify and during R-1 through R-7. No outstanding ambiguities block Phase 1 design.

## Charter re-check (post-research)

- Directive 5: ✅
- Directive 6: ✅ (R-3 + R-4 confirm helper-script split)
- CLAUDE.md preservation: ✅ (R-5 placement does not displace existing content)
- Tier 4 classification: ✅ (docs + non-runtime helper script)

Proceed to Phase 1.
