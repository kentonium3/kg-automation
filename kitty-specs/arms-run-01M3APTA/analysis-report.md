---
schema_version: 1
artifact_type: spec-kitty.analysis-report
command: /spec-kitty.analyze
mission_slug: arms-run-01M3APTA
mission_id: 01M3APTADS39MF0NDWG9HDSW50
generated_at: '2026-09-25T00:31:03.840569+00:00'
analyzer_agent: unknown
input_artifacts:
  spec.md:
    path: kitty-specs/arms-run-01M3APTA/spec.md
    sha256: 4191761519444857d95a1c938285aef61e6c8fa79d3dd779c359f3be2fd57193
  plan.md:
    path: kitty-specs/arms-run-01M3APTA/plan.md
    sha256: ecfae0d3d44e43777344e4e9f306910b09afffac16837553d84ace6c0086d760
  tasks.md:
    path: kitty-specs/arms-run-01M3APTA/tasks.md
    sha256: 9f85bb725e6270590511b9d6d85092fbf96cb99d9b15bb0156269adec203c73a
  charter:
    path: .kittify/charter/charter.md
    sha256: 4891223a0c3fc0dc96917475523586e8f3147a3ccaa113ecb7ff19da646e82e2
verdict: blocked
issue_counts:
  critical: 0
  high: 1
  medium: 4
  low: 1
  info: 0
findings:
- id: I1
  severity: high
  category: inconsistency
  summary: "Task ordering contradiction: WP07 imports arms849.embed (owned by WP05) and WP04 calls WP02's substrate self-test, but neither lists that WP as a dependency, so parallel lanes would fail on import."
- id: I2
  severity: medium
  category: inconsistency
  summary: "spec.md predates the Codex-folded plan on two points: FR-009/Story 2 say D's dump is events then entities (plan D-7 adds edges); FR-014/Story 3 say three answers per question under X/Y/Z (plan/contracts export every scored cell under per-cell blinded ids)."
- id: I3
  severity: medium
  category: inconsistency
  summary: FR-017 requires bus posts at run start/resume/completion/halt; WP08 T032 narrows this to event rows plus an operator-relayed status line because the bus is MCP-only. Spec and tasks disagree on who posts.
- id: U1
  severity: medium
  category: underspecification
  summary: The question-manifest digest constant WP01 T003 embeds (4864c31c…) does not reproduce from rubric section 3's stated rule (recompute gives fe17beef…); the source of truth for the gate is unresolved (design-lead request 00:23Z open).
- id: C1
  severity: medium
  category: coverage
  summary: NFR-002 (resume to next cell < 30 s) and NFR-003 (gates < 5 min) have no task or test that measures them; NFR-004's 5 GiB headroom is sampled but not asserted as a threshold anywhere in tasks.
- id: S1
  severity: low
  category: inconsistency
  summary: WP09 bundles documentation (T036-T037) with execution (T038-T043) in one planning_artifact package for ownership reasons, so the README run section lands only after the run; sequencing is stated but the docs could serve implementers earlier.
---

## Specification Analysis Report

Mission `arms-run-01M3APTA` — spec @a34f12cc, plan @aa30c122 (+@51707915), tasks @a9d98fc4, charter `.kittify/charter/charter.md`.

| ID | Category | Severity | Location(s) | Summary | Recommendation |
|----|----------|----------|-------------|---------|----------------|
| I1 | Inconsistency | HIGH | tasks/WP07-arm-r.md (dependencies), tasks/WP04-gates-preflight-calibration.md (dependencies); tasks.md §WP04/§WP07 | WP07 T028 imports `arms849.embed` (WP05 T021); WP04 T017 `boundary` gate calls WP02's `run --self-test`; neither dependency is declared, so `lanes.json` may schedule them in parallel with their providers | Add `WP05` to WP07's dependencies and `WP02` to WP04's; re-run `finalize-tasks` to recompute lanes |
| I2 | Inconsistency | MEDIUM | spec.md FR-009, Story 2 AC; FR-014, Story 3 AC; plan.md IC-04/IC-08; research.md D-7; contracts/grading-view.md | Spec still says "events then entities" and "three answers per question under X/Y/Z"; the Codex-folded plan says events, entities, edges and per-cell blinded ids (nine entries) | Amend spec FR-009/FR-014 and the two acceptance scenarios to the folded wording via `spec-commit` (the plan is the stricter, ruled version) |
| I3 | Inconsistency | MEDIUM | spec.md FR-017; tasks/WP08 T032 | FR-017 assigns bus posts to the harness; T032 correctly notes the bus is MCP-only and makes the operator relay `--status` output | Reword FR-017: the harness records `event` rows and emits a status line; the operator posts it (matches WP09's instructions) |
| U1 | Underspecification | MEDIUM | tasks/WP01 T003; rubric §3 A4; contracts/gates.md | The gate compares to a constant that the rule text does not reproduce | Do not close WP01 T003 until the design lead publishes the eight hashed lines or re-registers the constant; the gate then compares to the confirmed value |
| C1 | Coverage | MEDIUM | spec.md NFR-002, NFR-003, NFR-004; tasks.md | No task measures resume latency or gate duration; headroom is recorded (WP04 T018) but no task asserts the ≤ 57.5 GiB ceiling | Add timing assertions to WP08 T035 (resume < 30 s on the fake run) and WP04 T020 (gate wall-clock recorded); assert the ceiling in WP08's execute loop (refuse a cell whose sampler already exceeds it) |
| S1 | Inconsistency | LOW | tasks.md §WP09, §MVP | Docs land with the run rather than before implementation | Acceptable as sequenced; optionally split docs into an earlier planning_artifact WP if implementers need the README Run section first |

**Coverage Summary Table:**

| Requirement Key | Has Task? | Task IDs | Notes |
|-----------------|-----------|----------|-------|
| FR-001 four-gate + prompt-hash precondition | yes | T016, T017, T032 | |
| FR-002 resumable 72-cell run | yes | T011–T013, T031, T040 | |
| FR-003 header binds corpus/prompt/serving | yes | T004, T011 | |
| FR-004 per-cell cost and plan columns | yes | T004, T024, T031 | |
| FR-005 outcomes distinct, never averaged | yes | T012, T014, T031 | |
| FR-006 D context classification | yes | T026, T027, T031 | |
| FR-007 bounded retry | yes | T012, T031 | |
| FR-008 arm G typed retrieval | yes | T022–T024 | |
| FR-009 arm D full dump | yes | T026 | spec wording stale (I2) |
| FR-010 arm R derived k | yes | T019, T028, T029 | |
| FR-011 registered prompt verbatim | yes | T002 | |
| FR-012 links G-only | yes | T022, T026, T028 (arm_view existing) | |
| FR-013 oracle isolation twice | yes | T008, T009, T017 | |
| FR-014 blinded grading view | yes | T034 | spec wording stale (I2) |
| FR-015 D-YaRN secondary | yes | T033, T042 | |
| FR-016 substrate lifecycle | yes | T006, T007 | |
| FR-017 status + bus | partial | T032, T038–T043 | narrowed (I3) |
| FR-018 sandbox note first | yes | research.md D-9 (written), T036, T038 | |
| NFR-001 ledger durability | yes | T013, T015 | |
| NFR-002 resume < 30 s | no | — | C1 |
| NFR-003 gates < 5 min | no | — | C1 |
| NFR-004 memory ceiling | partial | T018 | sampled, not asserted (C1) |
| NFR-005 determinism | yes | T005, T024, T025, T030 | |
| NFR-006 blinding integrity | yes | T034, T035 | |
| NFR-007 single writer | yes | T013, T015 | |
| NFR-008 per-attempt bound | yes | T031 | |

**Charter Alignment Issues:** none. Self-documenting (WP09), idempotent/replay-safe (WP03/WP05), loud failure (WP04), testing standards (every code WP carries tests on the real corpus), live verification defined and recorded (WP09), branch strategy (feature branch), deployment constraints (127.0.0.1 only; nothing on office2), Tier 3, rebaseline not required, supply chain recorded.

**Unmapped Tasks:** none (43 subtasks, each under a WP with requirement_refs).

**Metrics:**

- Total Requirements: 18 FR + 8 NFR + 9 C
- Total Tasks: 43 subtasks in 9 work packages
- Coverage %: FR 100 % (18/18); NFR 75 % (6/8 with a measuring task)
- Ambiguity Count: 0 (no vague adjectives without thresholds; no placeholders)
- Duplication Count: 0
- Critical Issues Count: 0 (1 high)

### Next Actions

- Resolve I1 before `/spec-kitty.implement`: add the two dependencies and re-run `spec-kitty agent mission finalize-tasks --mission arms-run-01M3APTA --json`, then re-run `/spec-kitty.analyze`.
- I2, I3: amend spec.md via `spec-kitty spec-commit` (wording only; the plan is the ruled version).
- U1: hold WP01 T003 on the design lead's answer; the constant is written but must not be trusted until reproduced.
- C1: add the timing/ceiling assertions to WP04 T020 and WP08 T035 prompts.
