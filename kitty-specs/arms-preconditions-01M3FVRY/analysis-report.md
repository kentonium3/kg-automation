---
schema_version: 1
artifact_type: spec-kitty.analysis-report
command: /spec-kitty.analyze
mission_slug: arms-preconditions-01M3FVRY
mission_id: 01M3FVRYMHCDM4BKRZ689V5P7J
generated_at: '2026-09-27T01:42:45.023059+00:00'
analyzer_agent: unknown
input_artifacts:
  spec.md:
    path: kitty-specs/arms-preconditions-01M3FVRY/spec.md
    sha256: c5df8a81ce6d1260c1c87adf07c9c63e0324a64804cf70758d03d9cda5f7cae5
  plan.md:
    path: kitty-specs/arms-preconditions-01M3FVRY/plan.md
    sha256: c66a23c475e254552857b11650ed92686715aabcc875598465f7bf292ee4853c
  tasks.md:
    path: kitty-specs/arms-preconditions-01M3FVRY/tasks.md
    sha256: 33fcb271972f790d2f79ed0565da94cb26ad63e976167f87fe04d6c43208e94b
  charter:
    path: .kittify/charter/charter.md
    sha256: 4891223a0c3fc0dc96917475523586e8f3147a3ccaa113ecb7ff19da646e82e2
verdict: ready
issue_counts:
  high: 0
  critical: 0
  medium: 0
  low: 2
  info: 0
findings:
- id: P1
  severity: low
  category: process
  summary: WP owned_files overlap deliberately (true coupled write scopes), departing from the tasks runbook's no-overlap rule; the tool collapses them into the one lane C-005 requires.
- id: S1
  severity: low
  category: style
  summary: spec.md FR table lists FR-016 before FR-015.
---

## Specification Analysis Report

| ID | Category | Severity | Location(s) | Summary | Recommendation |
|----|----------|----------|-------------|---------|----------------|
| P1 | Process | LOW | tasks.md header; tasks runbook L244 | Overlapping `owned_files` are deliberate (coupled edits). spec-kitty `lanes/compute.py` rule 1 unions overlapping WPs, which yields `lane_ids: ["lane-a"]` as C-005 requires. The runbook's no-overlap rule guards parallel lanes. | Keep; report the runbook/tool discrepancy to Kent. |
| S1 | Style | LOW | spec.md:139–140 | The FR-016 row precedes FR-015. | Cosmetic; no action. |

**Coverage Summary Table:**

| Requirement Key | Has Task? | Task IDs | Notes |
|-----------------|-----------|----------|-------|
| FR-001 arms-registered | Yes | T017 | red-first live-registration test |
| FR-002 g-refusals-and-halt | Yes | T008, T019 | |
| FR-003 one-refusal-class | Yes | T007 | |
| FR-004 no-arms-never-primary | Yes | T017 | regression guard (NFR-002 exemption) |
| FR-005 memory-series-end-to-end | Yes | T013, T014, T020 | |
| FR-006 run-level-report | Yes | T004, T015 | |
| FR-007 could-not-check | Yes | T004, T015 | |
| FR-008 ceiling-guard-at-send | Yes | T001, T011, T021 | |
| FR-009 live-style-resume | Yes | T026 | |
| FR-010 isolation-inventory | Yes | T006 | |
| FR-011 attempts-name-session | Yes | T003 | |
| FR-012 canonical-utc | Yes | T016 | |
| FR-013 token-table-at-freeze | Yes | T023 | the run is a freeze step |
| FR-014 env-gating | Yes | T025 | |
| FR-015 premerge-record | Yes | T027, T028 | |
| FR-016 g-db-routing | Yes | T009, T012 | |
| NFR-001 suite-green-both-envs | Yes | all DoDs, T027 | |
| NFR-002 can-fail-evidence | Yes | every WP's red-first section | |
| NFR-003 no-orphaned-attempts | Yes | T010, T024 | |
| NFR-004 freshness | Yes | T016 | |
| NFR-005 fail-closed | Yes | T001, T002, T021 | |

**Charter Alignment Issues:** none. Re-analysis after remediation @88a47c8: C1 is resolved (every WP DoD carries the live-caller check; `require_breached` is wired at the GTT bind in WP04 T021). T1 is resolved (dated D-7a pointers on plan.md:13 and research D-5).

**Unmapped Tasks:** none.

**Metrics:**
- Total requirements: 21 (16 FR + 5 NFR)
- Total tasks: 28
- Coverage: 100% (requirements with ≥ 1 task)
- Ambiguity count: 0
- Duplication count: 0
- Critical issues: 0 (high: 0)

**Next Actions:** proceed to `/spec-kitty.implement` WP01. P1 is reported to Kent.
