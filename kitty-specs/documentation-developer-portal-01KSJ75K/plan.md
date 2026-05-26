# Implementation Plan: Documentation Developer Portal

**Mission**: documentation-developer-portal-01KSJ75K
**Date**: 2026-05-26
**Spec**: [spec.md](spec.md)
**Source issue**: [#417](https://github.com/kentonium3/kg-automation/issues/417)
**Blueprint**: `docs/temp/documentation_blueprint.md` v1.2 (authoritative scope)

**Branch contract** (from `setup-plan --json`):
- Current branch at plan start: `main`
- Planning/base branch: `main`
- Merge target: `main`
- `branch_matches_target`: true

## Summary

Add a single guided sitemap (`docs/DEVELOPER_PORTAL.md`) that complements the
existing flat catalog (`docs/INDEX.md`). The portal contains four sections
(Quick-Start Onboarding, ≤3-paragraph Execution Loop TL;DR, Verification
Command Quick-Reference, Virtual Runbook Filter). The runbook filter is
**generated** from each runbook's `audience:` frontmatter by a new helper
script (`tooling/scripts/build_runbook_filter.py`), regenerated between
explicit markers in the portal markdown, and a drift check is wired so CI
fails when the portal block is out of date.

A single additive pointer line is added to `CLAUDE.md` under the existing
"Architecture Documentation" section. No other `CLAUDE.md` content is
touched. `docs/INDEX.md` gains one entry pointing back at the portal.

## Technical Context

**Language/Version**: Python 3.11+ (matches existing `tooling/scripts/` codebase)
**Primary Dependencies**: PyYAML (already required by `validate_docs.py`); no new third-party deps expected
**Storage**: Markdown files on disk; no DB or persistent state
**Testing**: `pytest` for the new helper script; `validate_docs.py` for doc schema; manual diff review for the CLAUDE.md additive-only contract
**Target Platform**: Local dev machine (macOS) and CI (GitHub Actions Linux)
**Project Type**: Single project — tooling/docs only; no service deployment
**Performance Goals**: Helper script scans `docs/runbooks/**/*.md` (currently ~10 files) in well under 1 second; idempotent regeneration
**Constraints**:
  - Portal markdown file ≤ 25 KB (NFR-001)
  - `CLAUDE.md` diff is purely additive (C-001 / FR-007)
  - No new runbook frontmatter fields (C-003)
  - Execution Loop section is ≤3 paragraphs and links rather than duplicates (C-005, FR-003)
**Scale/Scope**: ~10 runbooks today; designed to remain correct as runbooks are added without portal hand-edits.

## Charter Check

*GATE: Must pass before Phase 0 research. Re-check after Phase 1 design.*

- **Directive 5 (Documentation Standards)**: Machine-readable + narrative split — N/A for the portal itself (it is narrative navigation, not authoritative state). The generated filter section's "machine-readable" counterpart is each runbook's frontmatter, which is already canonical. ✅ Pass.
- **Directive 6 (Design-time discipline — deterministic vs stochastic)**: The runbook-filter generation is purely deterministic — it reads frontmatter and emits a table. That work belongs in a script, not an LLM prompt. The plan correctly extracts it into `build_runbook_filter.py`. ✅ Pass.
- **Felix Constitution — CLAUDE.md preservation**: This is the load-bearing risk. C-001 + FR-007 mandate a purely additive `CLAUDE.md` diff; review must inspect `git diff CLAUDE.md` and reject any line that is not net-new. ✅ Pass (gated by review).
- **Tier 4 (Auto-commit) change-risk taxonomy**: New docs + non-runtime helper script are Tier 4 (Schema/Metadata). No pre-flight or post-change verification required beyond `validate_docs.py`. ✅ Pass.
- **Charter tool-registry mismatch** (known pre-existing): governance context reports pytest/python tagged unavailable. Per prior memory this is deferred until after mission #343 and does not block planning. ⚠️ Pre-existing — not introduced by this mission.

No new violations. Re-check after Phase 1 design.

## Project Structure

### Documentation (this feature)

```
kitty-specs/documentation-developer-portal-01KSJ75K/
├── plan.md              # This file
├── spec.md              # /spec-kitty.specify output
├── research.md          # Phase 0 output
├── data-model.md        # Phase 1 output
├── quickstart.md        # Phase 1 output
├── contracts/           # Phase 1 output (helper script contract)
│   └── build_runbook_filter.md
├── checklists/
│   └── requirements.md  # spec-quality checklist
└── tasks/               # Created by /spec-kitty.tasks (NOT by /spec-kitty.plan)
```

### Source Code (repository root)

```
docs/
├── DEVELOPER_PORTAL.md       # NEW — guided sitemap (FR-001 through FR-005, FR-009)
├── INDEX.md                  # MODIFIED — add one entry pointing to the portal (FR-008)
└── runbooks/                 # UNCHANGED on disk; read for `audience:` frontmatter

tooling/
└── scripts/
    ├── build_runbook_filter.py     # NEW — generates the runbook filter section
    └── validate_docs.py            # MODIFIED — adds drift check for the portal's generated block

CLAUDE.md                     # MODIFIED — one additive pointer line (FR-006, FR-007)
```

**Structure Decision**: Single project. All work lives under `docs/`, `tooling/scripts/`, and the top-level `CLAUDE.md`. No new service, no `office2` deployment, no architecture impact (no `docs/design/architecture/data/*.json` changes).

## Implementation Approach

### Portal layout (`docs/DEVELOPER_PORTAL.md`)

YAML frontmatter:
- `title: kg-automation Developer Portal`
- `doc_type: index` (semantically accurate — the portal is an onboarding index complementary to `docs/INDEX.md`, which is the flat catalog; both are valid `doc_type` enum values, but `index` better names what the portal does)
- `status: approved`
- `owners: [kgale]`
- `audience: agents_and_humans`
- `last_validated: 2026-05-26`
- `version: "1.0"`

Body sections, in order:
1. **One-paragraph orientation** — what this file is, who it's for, link back to `docs/INDEX.md`
2. **Quick-Start Onboarding Sequences** — three named paths (Feature Development / Runbook Execution / Bug Fix), each presented as an ordered checklist of "read these files in this order"
3. **The Execution Loop Explained** — ≤3 paragraphs covering Local → GitHub → office2 → OpenClaw, with explicit links to `docs/runbooks/agent-workspace-reconciliation.md` and `docs/runbooks/openclaw-agent-setup.md`. No duplication of those runbooks' content.
4. **Verification Command Quick-Reference** — table of local validation commands grouped by intent (doc validation, mermaid views, tests). Each row: command, what it checks, where to run it.
5. **Virtual Runbook Filter** — the auto-generated block. Three sub-headers: `Agent-executable`, `Dual-audience`, `Human-only`, with an `Unclassified` bucket appended if any runbook lacks the `audience:` field. The block is delimited by HTML comment markers:

   ```
   <!-- begin:runbook-filter (generated; do not edit) -->
   ...
   <!-- end:runbook-filter -->
   ```

### Helper script (`tooling/scripts/build_runbook_filter.py`)

Behavior contract is fully specified in `contracts/build_runbook_filter.md`. Summary:

- Input: walks `docs/runbooks/**/*.md`
- Reads YAML frontmatter via `python-frontmatter` or simple regex/PyYAML (match the existing `validate_docs.py` strategy)
- Emits the filter section content (Markdown), grouped by `audience` value
- Two modes:
  - **`--write`**: rewrites the block between the markers in `docs/DEVELOPER_PORTAL.md` in place
  - **default (check)**: prints what the block should be; exits 0 if the file's current block matches, exits non-zero with a diff if drift is detected

### Drift check integration

`validate_docs.py` is extended with a thin call into `build_runbook_filter.check_block()` (or equivalent). If the portal exists and the embedded block does not match what the script would produce, validation fails with a clear "run `python tooling/scripts/build_runbook_filter.py --write` to refresh" message.

### `CLAUDE.md` pointer

A single new line is added under the existing "Architecture Documentation" section. The line points to `docs/DEVELOPER_PORTAL.md` with one short descriptor. No other line in `CLAUDE.md` is rewritten, reordered, or removed. The reviewer will check the diff is purely additive.

### `docs/INDEX.md` entry

One bullet under the appropriate section (likely a new "Onboarding" subsection or as a top-line under "Constitution & Governance" or "System Architecture" — plan defers placement to implementation, which inspects the current INDEX layout before placing the entry).

## Complexity Tracking

No Charter Check violations. No complexity entries.

## Re-check Charter Check after Phase 1

After designing the data model, contracts, and quickstart:

- Directive 5: ✅ unchanged
- Directive 6: ✅ generation script extracted as planned; LLM is only asked to write the prose portal content, not to enumerate runbooks
- CLAUDE.md preservation: ✅ unchanged; gated by reviewer
- Tier 4 classification: ✅ unchanged

Plan is ready for `/spec-kitty.tasks`.
