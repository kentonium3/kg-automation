---
schema_version: 1
artifact_type: spec-kitty.analysis-report
command: /spec-kitty.analyze
mission_slug: pointer-key-ledger-01M189P6
mission_id: 01M189P6KMJPHQ4ZPPNR25MGR8
generated_at: '2026-08-30T04:11:26.731745+00:00'
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
verdict: ready
issue_counts:
  critical: 0
  low: 1
  high: 0
  medium: 0
  info: 0
findings:
- id: T1
  severity: low
  category: terminology
  summary: The same artifact is called 'state pointer', 'state document' and 'health pointer' across spec, plan, contract and WP prompts; data-model names the entity StatePointer.
---

## Specification Analysis Report (re-run)

Mission `pointer-key-ledger-01M189P6`. Second pass, after remediating the first pass's blocking
findings in `af746125`.

### Disposition of the first pass

| ID | Severity | Status | How |
|---|---|---|---|
| I1 | CRITICAL | **Resolved** | The contract conflated two ideas: the *staleness anchor* (which must be unique) and *any key with a recency bound* (which need not be). Rule 7 now constrains only `freshness` + `anchor: true`; `snapshot_timestamp_utc` carries the anchor, `last_integrity_check_utc` carries its own 9-day bound without one. The ledger and its validator now agree. |
| C1 | HIGH | **Resolved** | FR-019's exemption is settled in the contract as `suppress_until_utc` and its validator acceptance moved into WP02, which runs first. WP03 now consumes a fixed vocabulary instead of inventing one it could not make legal. |
| U1 | HIGH | **Resolved** | Added an explicit per-predicate modifier allow-list. Rule 4 constrains *predicate* fields; modifiers are permitted only from that list, so the vocabulary cannot be extended by an implementer's guess. |
| I2 | MEDIUM | **Resolved** | WP04 T021 restated in terms of the anchor, with an added case for a non-anchor bounded key. |
| C2 | MEDIUM | **Resolved** | NFR-001/002/004/005 mapped across WP03–WP05 via `map-requirements`. |
| C3 | LOW | **Resolved** | C-002 mapped to WP06. |
| T1 | LOW | **Open — accepted** | See below. |

A fourth inconsistency surfaced while remediating and was fixed in the same commit: the contract's
Shape pointed `reconciliation_harness` at `test_pointer_emission.py` while WP02 and WP05 had agreed on
`test_ledger_reconciliation.py`. WP02 would have declared a harness path WP05 never creates, and the
validator's existence check would have failed at the end of the mission rather than the start.

### Remaining finding

| ID | Category | Severity | Location(s) | Summary | Recommendation |
|----|----------|----------|-------------|---------|----------------|
| T1 | Terminology | LOW | spec.md, plan.md, contracts, data-model.md, WP01, WP05 | "state pointer", "state document", "health pointer" and "the document" all name one artifact; `data-model.md` names the entity `StatePointer` while most prose says "state document". | Accepted rather than fixed. A mid-mission sweep across six artifacts to normalise a term carries more regression risk than the ambiguity does — every occurrence is locally unambiguous, and the entity name is stable in `data-model.md`. Worth normalising opportunistically during WP06's documentation pass, where the runbook is being rewritten anyway. |

### Coverage Summary

| Requirement class | Total | Mapped | Notes |
|---|---|---|---|
| Functional (FR) | 19 | **19 (100%)** | `unmapped_functional: []`, confirmed by `map-requirements` |
| Non-functional (NFR) | 6 | **6 (100%)** | NFR-001/002/004/005 added this pass |
| Constraints (C) | 8 | 8 (100%) | C-002 added this pass |

### Charter Alignment Issues

None. Test-first ordering is explicit in WP01/WP03/WP04 (and WP04 sequences its behaviour-preserving
refactor *before* the behavioural change, which is what makes its regression suite a trustworthy
oracle). The no-dead-code gate is an acceptance item. The live-verification gate is defined as the
post-merge operator canary and is falsifiable — it injects a synthetic failing verdict rather than
confirming a passing one, which the first draft got wrong.

### Unmapped Tasks

None. 33 subtasks, each in exactly one WP; 6 WPs, each mapping to at least one requirement; zero
ownership overlaps.

### Metrics

- Requirements: 33 total (19 FR, 6 NFR, 8 C) · **100% mapped**
- Work packages: 6 · Subtasks: 33 · Ownership overlaps: 0
- Critical: 0 · High: 0 · Medium: 0 · Low: 1
- Findings resolved since pass 1: 6 of 7, plus 1 found during remediation

### Next Actions

**Ready for `/spec-kitty.implement`.** No blocking findings.

The pattern worth carrying out of this analysis: all three blocking findings were introduced by the
*corrections* made after the post-plan review, not by the original draft. Fixing review findings is
itself a change that needs re-checking against the whole artifact — which is exactly what this gate
exists to do, and why running it as a formality would have been worthless here.
