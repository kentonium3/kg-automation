---
work_package_id: WP05
title: Corpus migration
dependencies:
- WP01
- WP04
requirement_refs:
- FR-001
- FR-002
- FR-007
- FR-008
- FR-009
- FR-010
planning_base_branch: feat/adr-first-class-statuses
merge_target_branch: feat/adr-first-class-statuses
branch_strategy: Planning artifacts for this mission were generated on feat/adr-first-class-statuses. During /spec-kitty.implement this WP may branch from a dependency-specific base, but completed changes must merge back into feat/adr-first-class-statuses unless the human explicitly redirects the landing branch.
created_at: '2026-09-18T18:45:00Z'
subtasks:
- T020
- T021
- T022
- T023
- T024
- T025
phase: Phase 3 - Migration
history:
- timestamp: '2026-09-18T18:45:00Z'
  agent: system
  action: Prompt generated via /spec-kitty.tasks
agent_profile: curator-carla
authoritative_surface: docs/design/architecture/adr/
create_intent: []
execution_mode: planning_artifact
owned_files:
- docs/design/architecture/adr/**
- docs/INDEX.md
- docs/design/research/felix-workspace-api-vs-gog-681.md
- docs/design/architecture/security-posture.md
- docs/design/architecture/data/signal-to-doc-map.json
role: curator-carla
tags: []
tracker_refs: []
---

## ⚡ Do This First: Load Agent Profile

Before reading anything else in this file, load your assigned profile:

```
/ad-hoc-profile-load curator-carla
```

Do not begin implementation until the profile is loaded. It carries the identity, boundaries, and
governance scope you are working under.

## Objective

Make every decision document state its own standing and its own history. **This WP is SC-001** — the
reason the mission exists.

## Context you need

`contracts/migration-matrix.md` is the specification for this WP. **Every row is derived from cited
evidence; do not infer standing for any document.** If a row looks wrong, stop and report it rather
than guessing.

The defect being fixed, stated once: state *about* a document was recorded *somewhere else*. It has
happened three times — ADR-0002's dead Q6, ADR-0003's promotion, ADR-0008's erratum — and the third was
observed live on 2026-09-18, when an agent read ADR-0008, hit reasoning that had been erratum'd three
weeks earlier, and reported it as new.

## Subtasks

**T020 — Frontmatter, nine ADRs.** `doc_type: reference` → `decision`, and status per the matrix.
ADR-0003 becomes `approved` (affirmed by Kent 2026-09-18 — its body set the promotion condition, #508
met it on 2026-06-06, both indexes recorded it, only the ADR was never updated).

**T021 — Decision logs.** Append `## Decision log` to every ADR; empty is `*No entries.*`. Seed the
three rows the matrix specifies, with the exact `Type` values given: ADR-0002 `amendment` (**not**
`superseded-by` — it is not superseded as a whole), ADR-0003 `amendment`, ADR-0008 `erratum`.

**T022 — ADR-0004 special case.** ⚠ **Blocking finding #3 — read the matrix section in full.** Preserve
the existing `## ACL changes log` verbatim (frozen body). Append the canonical `## Decision log` after
it. Carry forward the entries that are about ADR-0004 itself, mapped to the vocabulary. **Relocate — do
not copy —** the entry that is about ADR-0008 into ADR-0008's own log. Close the legacy route with a
pointer, without rewriting the frozen section.

**T023 — The three external pointers.** `security-posture.md`, `signal-to-doc-map.json` and ADR-0009 all
currently direct authors to ADR-0004's legacy log. Update them to the canonical log. Missing this leaves
two competing logs with new writes flowing to the obsolete one — recreating the defect in the one place
it had already been solved.

**T024 — RFC #681.** `docs/design/research/felix-workspace-api-vs-gog-681.md` is the other
`doc_type: decision` document. It already has a valid status; it needs the log section.

**T025 — Reconcile the indexes.** ADR README doctrine (status set, the immutability refinement — the
decision is frozen, the log is append-only, the log has no authority) plus both index tables, so no
standing is discoverable only from prose in another file.

## Definition of Done

- All eleven rows migrated per the matrix; nothing inferred.
- **SC-001 asserted by test**: for each document, standing and complete amendment history derive from
  that document alone. Specifically — ADR-0002 surfaces its dead Q6, ADR-0003 its promotion, ADR-0008
  its own erratum.
- No ADR body prose edited. Frozen means frozen.
- Repo-wide `validate_docs.py` green under WP03's rules.

## Risks

- **Bodies are frozen.** You change frontmatter and append a section. Existing body `Status:` lines that
  disagree with frontmatter (ADR-0007 and ADR-0008 both say "Accepted") are left alone — frontmatter
  governs.

## Branch Strategy

Planning branch: `feat/adr-first-class-statuses`. Final merge target: `feat/adr-first-class-statuses`.
Execution worktrees are allocated per computed lane from `lanes.json` — do not create them by hand.

## Reviewer guidance

Read `kitty-specs/adr-first-class-statuses-01M2TVSP/contracts/` before reviewing. The decided model is
not open for relitigation: a new ADR is the only place decisions are made; `status` is the authoritative
standing; the decision log is history with **no authority**. `partially_superseded` must never exist.
`approved` is retained over `accepted`. Frontmatter beats body text.
