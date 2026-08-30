---
schema_version: 1
artifact_type: spec-kitty.analysis-report
command: /spec-kitty.analyze
mission_slug: pointer-key-ledger-01M189P6
mission_id: 01M189P6KMJPHQ4ZPPNR25MGR8
generated_at: '2026-08-30T04:08:13.142864+00:00'
analyzer_agent: unknown
input_artifacts:
  spec.md:
    path: kitty-specs/pointer-key-ledger-01M189P6/spec.md
    sha256: d0d1a9fa913438df569421afda302afc31de9a77faf221741da4bdd7be6141b0
  plan.md:
    path: kitty-specs/pointer-key-ledger-01M189P6/plan.md
    sha256: c0ed8cd1d4bdddd8cafa3266cfe4155d5321f279b50bf5a36feaa94cf3a7a9c1
  tasks.md:
    path: kitty-specs/pointer-key-ledger-01M189P6/tasks.md
    sha256: 81e595cc29c0e6e8c82c6d5d87b2e43f230c51fb1901e6cbecb77b8f599cecfb
  charter:
    path: .kittify/charter/charter.md
    sha256: 4891223a0c3fc0dc96917475523586e8f3147a3ccaa113ecb7ff19da646e82e2
verdict: blocked
issue_counts:
  medium: 2
  critical: 1
  low: 2
  high: 2
  info: 0
findings:
- id: I1
  severity: critical
  category: inconsistency
  summary: Contract structural rule 7 forbids more than one freshness predicate, but the contract's own ledger Shape declares freshness on two keys — the declared ledger would fail its own validator.
- id: C1
  severity: high
  category: coverage
  summary: FR-019's suppression clause extends the predicate vocabulary in WP03, but the validator that must accept it is owned by WP02, which runs first and may not be edited by WP03.
- id: U1
  severity: high
  category: underspecification
  summary: Predicate modifier fields (max_age_seconds, unmeasured_is_unknown) are used in the contract Shape, but structural rule 4 says exactly one recognised predicate per key and never defines how modifiers are validated.
- id: C2
  severity: medium
  category: coverage
  summary: NFR-001, NFR-002, NFR-004 and NFR-005 appear in no work package's requirement_refs; they are covered only implicitly by per-WP test strategy prose.
- id: I2
  severity: medium
  category: inconsistency
  summary: WP04 T021 refers to 'the declared freshness key' in the singular, which is ambiguous once two keys legitimately carry a recency bound.
- id: T1
  severity: low
  category: terminology
  summary: The same artifact is called 'state pointer', 'state document' and 'health pointer' across spec, plan, contract and WP prompts.
- id: C3
  severity: low
  category: coverage
  summary: C-002 (manual operator install) is realised by WP06 T032 but appears in no requirement_refs, so it is invisible to coverage tooling.
---

## Specification Analysis Report

Mission `pointer-key-ledger-01M189P6`. Artifacts analysed: `spec.md` (v2), `plan.md` (v2),
`tasks.md`, `contracts/key-ledger.md` (v2), `data-model.md` (v2), `research.md` (v2), and the six WP
prompts.

Context: these artifacts already passed a three-lens post-plan review, and its ~39 findings are folded
in. The findings below are what survived *that* — three of them are defects introduced by the
corrections themselves, which is worth noting as a pattern: the fixes for the review's findings were
not themselves re-checked against the whole contract.

| ID | Category | Severity | Location(s) | Summary | Recommendation |
|----|----------|----------|-------------|---------|----------------|
| I1 | Inconsistency | CRITICAL | contracts/key-ledger.md:31-32 vs :138 | The Shape declares `freshness` on both `snapshot_timestamp_utc` and `last_integrity_check_utc`; structural rule 7 says "at most one key carries the `freshness` predicate". WP02 would author a validator that rejects the ledger WP02 also authors. | Rule 7's real intent is that the **staleness anchor** be unambiguous, not that only one key may carry a recency bound. Split the concepts: rename the anchor role (e.g. `freshness: {anchor: true}`) and permit any number of non-anchor recency-bounded keys, with the rule restated as "at most one key may be the anchor". Update rule 7, the Shape, WP02 T007/T009, WP03, and WP04 T021 together. |
| C1 | Coverage | HIGH | tasks/WP03:T016, tasks/WP02:T007-T008 | FR-019 requires a first-run suppression clause. WP03 invents it, but the validator that must accept it lives in WP02 — which is a *dependency* of WP03 and outside WP03's `owned_files`. WP03's own prompt tells the implementer to update the contract but not WP02's files, leaving no WP that makes the validator accept the clause. | Decide the suppression clause's shape **now**, in the contract, and move its validator acceptance into WP02 T007/T008. WP03 then only consumes a vocabulary that already exists. |
| U1 | Underspecification | HIGH | contracts/key-ledger.md:31-33, :92, :134 | The Shape uses `max_age_seconds` alongside `freshness` and `unmeasured_is_unknown` alongside `minimum`, but rule 4 says "exactly one recognised predicate per adjudicated key" and no rule defines the permitted modifier fields. A validator implementing rule 4 literally rejects both. | Add an explicit modifier allow-list per predicate to the contract's structural rules, and to WP02's test list. Without it, WP02's implementer must guess, and the guess determines whether WP03 and WP01's ledger entries are legal. |
| C2 | Coverage | MEDIUM | spec.md NFR table; all WP frontmatter | Only NFR-003 and NFR-006 are mapped (both to WP04). NFR-001 (decision correctness), NFR-002 (deterministic/offline), NFR-004 (evidence names the cause) and NFR-005 (no new false positives) are addressed in WP test-strategy prose but map to no WP. | Add them to the relevant WPs' `requirement_refs` — NFR-002 and NFR-004 span WP03/WP04/WP05; NFR-001 and NFR-005 belong with WP04/WP05. This is a traceability gap rather than a work gap. |
| I2 | Inconsistency | MEDIUM | tasks/WP04:T021 | "When the ledger declares a `freshness` predicate on key K, resolve K specifically" reads as though exactly one such key exists. Once I1 is resolved and two keys carry recency bounds, the anchor and the merely-bounded key need different handling. | Restate T021 in terms of the anchor role from I1's fix, and add a case for a non-anchor recency-bounded key. |
| T1 | Terminology | LOW | spec.md, plan.md, contracts, WP01, WP05 | "state pointer", "state document", "health pointer" and "the document" all name the same artifact. `data-model.md` calls the entity `StatePointer` while most prose says "state document". | Pick one — `state document` reads best and matches the entity's role — and note the alias once. Not worth a broad rewrite mid-mission; fix opportunistically. |
| C3 | Coverage | LOW | spec.md C-002; tasks/WP06:T032 | The manual operator install is the mission's completion gate, realised in WP06 T032, but C-002 is in no `requirement_refs`. | Add C-002 to WP06's refs so the completion gate is visible to coverage tooling. |

### Coverage Summary

| Requirement Key | Has Task? | Task IDs | Notes |
|---|---|---|---|
| FR-001 … FR-019 | Yes | across WP01–WP06 | 19/19 functional mapped; confirmed by `map-requirements` (`unmapped_functional: []`) |
| NFR-003, NFR-006 | Yes | WP04 | Mapped explicitly |
| NFR-001, 002, 004, 005 | Implicit only | WP03–WP05 test strategy | **C2** — addressed in prose, unmapped |
| C-001, C-003…C-008 | Yes | WP01, WP02, WP04 | Realised via FR work |
| C-002 | Yes | WP06 T032 | **C3** — unmapped |

### Charter Alignment Issues

None. Test-first ordering (DIRECTIVE_034) is explicit in WP01/WP03/WP04; the no-dead-code gate is an
acceptance item in WP03/WP05; the live-verification gate is defined as the plan's post-merge operator
canary; the Tier-2 classification matches the producer change; the rebaseline record is a WP06
acceptance item and was verified against the drift tool rather than asserted.

### Unmapped Tasks

None. All 33 subtasks belong to exactly one WP, and every WP maps to at least one requirement.

### Metrics

- Total functional requirements: **19** · mapped: **19** (100%)
- Total non-functional requirements: 6 · explicitly mapped: 2 (33%) — see C2
- Total constraints: 8 · explicitly mapped: 7 (88%) — see C3
- Total work packages: 6 · total subtasks: 33
- Ownership overlaps: **0** (confirmed by finalize-tasks)
- Ambiguity findings: 2 (U1, I2) · Duplication findings: 0 · Inconsistency findings: 2 (I1, I2)
- Critical issues: **1**

### Next Actions

**I1 must be resolved before implementation.** It is not a documentation nit: WP02's implementer would
author a validator whose rule 7 rejects the ledger authored in the same work package, and the WP would
be internally unimplementable. C1 and U1 are the same class — both are places where the contract's
vocabulary is under-defined and a downstream WP is expected to invent it without owning the file that
must accept it.

All three are cheap to fix because they are contract edits, not code: resolve the anchor-versus-bound
distinction, define the modifier allow-list, and settle the suppression clause's shape. Then WP02 has a
complete vocabulary to validate and WP03 consumes rather than invents.

C2 and C3 are traceability improvements and can be folded in with the same edit. T1 is cosmetic.

Suggested sequence: amend `contracts/key-ledger.md` (I1, U1, C1), amend WP02/WP03/WP04 prompts to
match, add the missing `requirement_refs` (C2, C3), then re-run `/spec-kitty.analyze` to confirm a
`ready` verdict before `/spec-kitty.implement`.
